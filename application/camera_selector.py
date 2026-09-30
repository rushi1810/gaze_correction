import json
import logging
import multiprocessing
import os
import pickle
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from multiprocessing import Lock
from typing import List

import cv2
import numpy as np
from PyQt5.QtWidgets import QWidget

from application.face_detector import FaceDetector

is_mac = True if sys.platform == "darwin" else False

logger = logging.getLogger(__name__)

_file_lock = Lock()
_dict_subprocess_shared_data: dict | None = None
_Count_Frame4Scoring = 20
_Face_Not_Found_Termination = 10
_Frame_Collector_Interval = 1
_Test_Inference_Interval = 1

"""
Flags for communication among processes used to handle best frame collection, scoring, and newly attached camera detection.

• Prefix values:
0 → Camera just found, frame collection not started.
1 → Camera is in the process of collecting frames.
2 → Frame collection completed, ready for scoring.
9 → Unexpected issue with frame collection (e.g., camera disconnected or no face detected), camera can be excluded.

• Suffix values:
0 → Scoring not started.
1 → Scoring process started for the camera.
2 → Scoring completed for the camera, next camera scoring can begin.
9 → Unexpected issue during scoring, camera can be excluded.

When all cameras have received either 2 or 9 as both prefix and suffix, the final comparison is initiated, and the best camera is selected.
"""


def initiate_shared_dictionary():
    _dict_subprocess_shared_data['reload_camera_history'] = False
    _dict_subprocess_shared_data['scoring_requested'] = False
    _dict_subprocess_shared_data['switch_to_camera'] = ''
    _dict_subprocess_shared_data['read_new_camera_info'] = False
    _dict_subprocess_shared_data['can_use_auto_camera_selector'] = True
    _dict_subprocess_shared_data['manually_selected_stop_scoring'] = False
    _dict_subprocess_shared_data['auto_selector_service_stopped_flag'] = False
    _dict_subprocess_shared_data['frame_should_be_collected4windows'] = []
    _dict_subprocess_shared_data['camera_waiting_list'] = []
    _dict_subprocess_shared_data['camera_for_score'] = ''
    _dict_subprocess_shared_data['currently_selected_camera'] = ''
    _dict_subprocess_shared_data['is_app_in_suspension'] = False
    _dict_subprocess_shared_data['app_is_about2close'] = False
    _dict_subprocess_shared_data['process_pid'] = 0


def load_history_and_initiate_listener():
    if _Face_Not_Found_Termination > _Count_Frame4Scoring:
        raise TypeError
    list_devices = _read_list_camera()
    dict_history = _load_camera_history_from_disk()
    camera_name = _find_already_configured_camera(list_devices, dict_history)
    camera_name and set_selected_camera_name(camera_name)
    process = multiprocessing.Process(
        target=_listener,
        args=(_dict_subprocess_shared_data, not bool(camera_name),)
    )
    process.start()
    _dict_subprocess_shared_data['process_pid'] = process.pid
    return camera_name


def application_close_signal():
    if not _dict_subprocess_shared_data or not _dict_subprocess_shared_data['process_pid']:
        return
    if is_mac:
        os.kill(_dict_subprocess_shared_data['process_pid'], signal.SIGTERM)
    else:
        pid = _dict_subprocess_shared_data['process_pid']
        subprocess.run(f'taskkill /F /PID {pid}', shell=True)


def set_application_suspension(suspension_value):
    try:
        _dict_subprocess_shared_data['is_app_in_suspension'] = suspension_value
    except BrokenPipeError:
        logger.error("Encountered BrokenPipeError on setting is_app_in_suspension attribute")


def set_selected_camera_name(camera_name):
    try:
        _dict_subprocess_shared_data['currently_selected_camera'] = camera_name
    except BrokenPipeError:
        logger.error("Encountered BrokenPipeError on setting currently_selected_camera attribute")


def can_use_auto_camera_selector(can_use):
    if not _dict_subprocess_shared_data:
        return
    can_use = bool(can_use)
    try:
        target_state_already_reached = can_use is _dict_subprocess_shared_data['can_use_auto_camera_selector']
    except BrokenPipeError:
        logger.error("Encountered BrokenPipeError on accessing can_use_auto_camera_selector attribute")
        target_state_already_reached = False
    if target_state_already_reached:
        return
    try:
        _dict_subprocess_shared_data['can_use_auto_camera_selector'] = can_use
    except BrokenPipeError:
        logger.error("Encountered BrokenPipeError on setting can_use_auto_camera_selector attribute")
    if can_use:
        load_history_and_initiate_listener()


def _listener(dict_shared_info, is_initial_check_required):
    def _dict_preferred_camera_history():
        nonlocal preferred_camera_history
        try:
            if preferred_camera_history is None or dict_shared_info['reload_camera_history']:
                preferred_camera_history = _load_camera_history_from_disk()
            return preferred_camera_history
        except BrokenPipeError:
            logger.error("Encountered BrokenPipeError on accessing reload_camera_history attribute")
            return []

    preferred_camera_history = None
    last_check = time.time()
    camera_list = None if is_initial_check_required else _read_list_camera()
    while True:
        diff = time.time() - last_check
        if diff < 1:
            time.sleep(1 - diff)
        last_check = time.time()

        try:
            if dict_shared_info['is_app_in_suspension']:
                continue
        except BrokenPipeError:
            logger.error("Encountered BrokenPipeError on accessing is_app_in_suspension attribute")
            continue
        try:
            if not dict_shared_info['currently_selected_camera']:
                # Wait for the default camera to be selected
                continue
        except BrokenPipeError:
            logger.error("Encountered BrokenPipeError on accessing currently_selected_camera attribute")
            continue

        try:
            if not dict_shared_info['can_use_auto_camera_selector']:
                dict_shared_info['auto_selector_service_stopped_flag'] = True
                dict_shared_info['camera_waiting_list'] = []
                dict_shared_info['camera_for_score'] = ''
                return
        except BrokenPipeError:
            logger.error("Encountered BrokenPipeError on accessing can_use_auto_camera_selector attribute "
                         "or setting auto_selector_service_stopped_flag, camera_waiting_list or camera_for_score attribute")
            continue

        new_camera_list = _read_list_camera()
        next_camera4frame_collection = _next_camera4frame_collection(dict_shared_info)
        if next_camera4frame_collection:
            multiprocessing.Process(
                target=_activate_other_camera,
                args=(dict_shared_info, next_camera4frame_collection,),
            ).start()

        if _is_2_camera_list_equals(camera_list, new_camera_list):
            continue

        try:
            dict_shared_info['manually_selected_stop_scoring'] = False
        except BrokenPipeError:
            logger.error("Encountered BrokenPipeError on setting manually_selected_stop_scoring attribute")
        camera_list = new_camera_list
        _init_or_update_camera_waiting_list(dict_shared_info, camera_list)
        already_configured = _find_already_configured_camera(camera_list, _dict_preferred_camera_history())
        try:
            if already_configured:
                dict_shared_info['switch_to_camera'] = already_configured
                dict_shared_info['camera_waiting_list'] = []
                continue
        except BrokenPipeError:
            logger.error("Encountered BrokenPipeError on setting switch_to_camera or camera_waiting_list attribute")


def _read_list_camera():
    def exclude_casablanca_virtual_camera(list_camera):
        return [camera for camera in list_camera if 'casablanca' not in camera.lower()]

    if sys.platform == "darwin":
        try:
            result = subprocess.run(
                ["system_profiler", "SPCameraDataType"],
                capture_output=True, text=True
            )
            titles = []
            for line in result.stdout.splitlines():
                line = line.strip()
                if line.endswith(":") and 'casablanca' not in line.lower():
                    titles.append(line[:-1])
            titles.remove('Camera')
            return exclude_casablanca_virtual_camera(titles)
        except Exception as e:
            return f"Error: {str(e)}"
    else:
        from pygrabber.dshow_graph import FilterGraph
        camera_device_reader = FilterGraph()
        return exclude_casablanca_virtual_camera(camera_device_reader.get_input_devices())


def user_manually_selected(camera_name):
    def background():
        list_camera = _read_list_camera()
        if len(list_camera) <= 1:
            return
        _write_to_camera_history(camera_name, list_camera, is_manual=True)
        try:
            _dict_subprocess_shared_data['reload_camera_history'] = True
        except BrokenPipeError:
            logger.error("Encountered BrokenPipeError on setting reload_camera_history attribute")

    try:
        _dict_subprocess_shared_data['camera_waiting_list'] = []
        _dict_subprocess_shared_data['camera_for_score'] = ''
        _dict_subprocess_shared_data['manually_selected_stop_scoring'] = True
    except BrokenPipeError:
        logger.error(
            "Encountered BrokenPipeError on setting camera_waiting_list, camera_for_score, or manually_selected_stop_scoring attribute")
    threading.Thread(target=background).start()


def find_the_best_camera(list_frame_holders):
    def background():
        best_camera_name = sorted(list_frame_holders, key=lambda x: x.score, reverse=True)[0]
        _write_to_camera_history(
            best_camera_name,
            [cam.camera_name for cam in list_frame_holders],
            is_auto=True,
        )
        try:
            _dict_subprocess_shared_data['reload_camera_history'] = True
        except BrokenPipeError:
            logger.error("Encountered BrokenPipeError on setting reload_camera_history attribute")

    threading.Thread(target=background).start()


def _is_2_camera_list_equals(first_list, second_list):
    first_list = {item for item in (first_list or []) if "casablanca" not in item}
    second_list = {item for item in (second_list or []) if "casablanca" not in item}

    return set(first_list) == set(second_list)


def _load_camera_history_from_disk():
    _file_path = os.path.join((_persistence_folder := "./persistent"), "camera.json")
    os.makedirs(_persistence_folder, exist_ok=True)
    with _file_lock:
        if not os.path.exists(_file_path):
            with open(_file_path, "w") as f:
                json.dump({}, f)

        with open(_file_path, "r") as f:
            return json.load(f)


def _write_to_camera_history(camera_name, list_camera, is_auto=False, is_manual=False):
    if camera_name not in list_camera:
        logger.error(f'The selected camera is not in the list of available cameras. {camera_name} {list_camera}')
        return
    data = _load_camera_history_from_disk()
    with _file_lock:
        for name_in_history, list_camera_in_history in data.items():
            if _is_2_camera_list_equals(list_camera_in_history, list_camera):
                data.pop(name_in_history)
                break
        if is_auto:
            key = f'auto {camera_name}'
        elif is_manual:
            key = f'manual {camera_name}'
        else:
            raise ValueError
        data[key] = list_camera
        with open(os.path.join("./persistent", "camera.json"), "w") as f:
            json.dump(data, f, indent=4)


def _find_already_configured_camera(list_camera, dict_prefer):
    list_camera = list(filter(lambda _camera_name: "casablanca" not in _camera_name.lower(), list_camera))
    if len(list_camera) == 1:
        return list_camera[0]
    for camera_name, list_configured_camera in dict_prefer.items():
        if _is_2_camera_list_equals(list_camera, list_configured_camera):
            name = camera_name.replace('manual ', '')
            name = name.replace('auto ', '')
            return name


def _activate_other_camera(dict_shared, name, count_try=0):
    def load_cam4mac():
        from application._platform.macOS.camera import RealCamera
        mac_cam = RealCamera()
        mac_cam.initialize_camera(camera_name=name)
        return mac_cam

    def load_cam4windows():
        import casablanca_camera.python.casablanca_camera.cameras as virtual_camera
        from application._platform.factory.os_factory import Factory
        Factory.init_windows()
        win_cam = virtual_camera.RealCamera(name)
        win_cam.start()
        return win_cam

    holder = FrameHolder4Score(camera_name=name)
    is_mac = sys.platform == 'darwin'
    try:
        cam = load_cam4mac() if is_mac else load_cam4windows()
    except RuntimeError:
        if count_try >= 5:
            _defected_camera(dict_shared, name)
            try:
                cam.stop()
            except UnboundLocalError:
                pass
            return
        multiprocessing.Process(
            target=_activate_other_camera,
            args=(dict_shared,),
            kwargs={'count_try': count_try + 1, 'name': name}
        ).start()
        return
    except OSError:
        _defected_camera(dict_shared, name)
        return
    frame_pre = None
    last_time_frame_collected = None
    latest_camera_time = None
    while True:
        if not _is_camera_still_connected(dict_shared, name):
            cam.stop()
            return

        try:
            if dict_shared['manually_selected_stop_scoring']:
                FrameHolder4Score.delete_all_score_files()
                cam.stop()
                return
        except BrokenPipeError:
            logger.error("Encountered BrokenPipeError on accessing manually_selected_stop_scoring attribute")
            return
        if latest_camera_time and (time.time() - latest_camera_time) < (_Frame_Collector_Interval * 0.001):
            continue

        try:
            frame_new = cv2.cvtColor(cam.read_frame(), cv2.COLOR_YUV2RGB_YUY2)
        except RuntimeError:
            _defected_camera(dict_shared, name)
            return

        if frame_pre is not None and not np.all(frame_new == 0) and not np.array_equal(frame_new, frame_pre):
            last_time_frame_collected = time.time()
            try:
                latest_camera_time = time.time()
                holder.add_new_frame(frame_new)
            except TypeError:
                _defected_camera(dict_shared, name)
                return
            if holder.is_enough_frame_collected:
                hasattr(cam, 'unselect_camera') and cam.unselect_camera()
                cam.stop()
                holder.flush2disk()
                _frame_collection_done(dict_shared, name)
                break
        if last_time_frame_collected and (time.time() - last_time_frame_collected) > 2:
            _defected_camera(dict_shared, name)
            return

        frame_pre = frame_new


def _init_or_update_camera_waiting_list(dict_shared_data, list_camera):
    try:
        list_wait = dict_shared_data['camera_waiting_list']
    except BrokenPipeError:
        logger.error("Encountered BrokenPipeError on accessing camera_waiting_list attribute")
        list_wait = []
    if list_wait:
        list_new_wait = []
        for newly_detected_camera in list_camera:
            if already_existed := list(filter(lambda name: newly_detected_camera in name, list_wait)):
                list_new_wait.append(already_existed[0])
            else:
                list_new_wait.append(f'0__{newly_detected_camera}__0')
        list_wait = list_new_wait
    else:
        list_wait = []
        for camera_name in list_camera:
            try:
                if camera_name == dict_shared_data['currently_selected_camera']:
                    list_wait.append(f'2__{camera_name}__0')
                else:
                    list_wait.append(f'0__{camera_name}__0')
            except BrokenPipeError:
                logger.error("Encountered BrokenPipeError on accessing currently_selected_camera attribute")
                list_wait.append(f'9__{camera_name}__9')

    if len(list_wait) <= 1:
        dict_shared_data['camera_waiting_list'] = []
        dict_shared_data['camera_for_score'] = ''
        return

    dict_shared_data['camera_waiting_list'] = list_wait


def _next_camera4frame_collection(dict_shared_data):
    try:
        list_wait = dict_shared_data['camera_waiting_list']
    except BrokenPipeError:
        logger.error("Encountered BrokenPipeError on accessing camera_waiting_list attribute")
        list_wait = []
    if len(list_wait) <= 1:
        try:
            dict_shared_data['camera_waiting_list'] = []
        except BrokenPipeError:
            logger.error("Encountered BrokenPipeError on accessing camera_waiting_list attribute")
    if any(_camera_name.startswith('1') for _camera_name in list_wait):
        return
    for index, camera_name in enumerate(list_wait):
        if camera_name[0] == '0':
            list_wait[index] = f'1{camera_name[1:]}'
            try:
                dict_shared_data['camera_waiting_list'] = list_wait
            except BrokenPipeError:
                logger.error("Encountered BrokenPipeError on setting camera_waiting_list attribute")
            camera_name = camera_name.split('__')[1]
            return camera_name


def _defected_camera(dict_shared_data, defected_camera):
    logger.info(f'defected camera {defected_camera}')
    try:
        list_wait = dict_shared_data['camera_waiting_list']
    except BrokenPipeError:
        logger.error("Encountered BrokenPipeError on accessing camera_waiting_list attribute")
        list_wait = []
    for index, camera_name in enumerate(list_wait):
        if defected_camera in camera_name:
            camera = f'9{camera_name[1:-1]}9'
            list_wait[index] = camera
            dict_shared_data['camera_waiting_list'] = list_wait
            break
    if len(list(filter(lambda item: item.startswith('9'), list_wait))) + 1 == len(list_wait):
        logger.info(f'Not enough camera to score stopping the process {list_wait}')
        dict_shared_data['camera_waiting_list'] = []


def _set_next_camera4scoring(dict_shared_data):
    def can_be_selected(camera_name):
        try:
            return (
                    camera_name.startswith('2')
                    and
                    camera_name.endswith('0')
                    and
                    dict_shared_data['currently_selected_camera'] not in camera_name
            )
        except BrokenPipeError:
            logger.error("Encountered BrokenPipeError on accessing currently_selected_camera attribute")
            return False

    try:
        if dict_shared_data['camera_for_score']:
            return
    except BrokenPipeError:
        logger.error("Encountered BrokenPipeError on accessing camera_for_score attribute")
        return
    try:
        waiting_list = dict_shared_data['camera_waiting_list']
    except BrokenPipeError:
        logger.error("Encountered BrokenPipeError on accessing camera_waiting_list attribute")
        waiting_list = []
    if len(waiting_list) <= 1:
        try:
            _dict_subprocess_shared_data['camera_waiting_list'] = []
            _dict_subprocess_shared_data['camera_for_score'] = ''
        except BrokenPipeError:
            logger.error("Encountered BrokenPipeError on accessing camera_waiting_list or camera_for_score attribute")
        FrameHolder4Score.delete_all_score_files()
        return

    for index, camera in enumerate(waiting_list):
        if can_be_selected(camera):
            waiting_list[index] = f'{camera[:-1]}1'
            try:
                dict_shared_data['camera_waiting_list'] = waiting_list
            except BrokenPipeError:
                logger.error("Encountered BrokenPipeError on setting camera_waiting_list attribute")
            logger.info(f'Camera selected to be scored {waiting_list}')
            dict_shared_data['camera_for_score'] = camera.split('__')[1]


def _frame_collection_done(dict_shared_data, camera_name):
    try:
        list_wait = dict_shared_data['camera_waiting_list']
    except BrokenPipeError:
        logger.error("Encountered BrokenPipeError on accessing camera_waiting_list attribute")
        list_wait = []
    for index, camera_in_waiting_list in enumerate(list_wait):
        if camera_name in camera_in_waiting_list:
            list_wait[index] = f'2{camera_in_waiting_list[1:]}'
            try:
                dict_shared_data['camera_waiting_list'] = list_wait
            except BrokenPipeError:
                logger.error("Encountered BrokenPipeError on setting camera_waiting_list attribute")
            _set_next_camera4scoring(dict_shared_data)
            logger.info(f'Scoring can be initiated for {list_wait[index]}')


def _scoring_done(dict_shared_data, camera_name):
    try:
        list_wait = dict_shared_data['camera_waiting_list']
    except BrokenPipeError:
        logger.error("Encountered BrokenPipeError on accessing camera_waiting_list attribute")
        list_wait = []
    for index, camera_in_waiting_list in enumerate(list_wait):
        if camera_name in camera_in_waiting_list:
            list_wait[index] = f'{camera_in_waiting_list[:-1]}2'
            try:
                dict_shared_data['camera_waiting_list'] = list_wait
            except BrokenPipeError:
                logger.error("Encountered BrokenPipeError on setting camera_waiting_list attribute")
            _set_next_camera4scoring(dict_shared_data)
            logger.info(f'Scoring has been finished for camera {list_wait}')


def _is_camera_still_connected(dict_shared_data, camera_name):
    try:
        list_wait = dict_shared_data['camera_waiting_list']
    except BrokenPipeError:
        logger.error("Encountered BrokenPipeError on accessing camera_waiting_list attribute")
        list_wait = []
    return bool(list(filter(lambda camera: camera_name in camera, list_wait)))


@dataclass
class FrameHolder4Score:
    camera_name: str
    _list_frame: List = field(default_factory=list)
    list_score: List = field(default_factory=list)
    _list_face_detections: List = field(default_factory=list)
    _face_detector: FaceDetector = field(repr=False, default=None)
    _no_face_counter = 0
    _roi_size_model: object = field(repr=False, default=None)
    _zero_score_counter = 0
    _is_currently_selected: bool = field(repr=False, default=False)

    @classmethod
    def currently_selected_camera(cls):
        return cls(
            _is_currently_selected=True,
            camera_name='currently_selected_camera'
        )

    @classmethod
    def load(cls, camera_name):
        with open(os.path.join("./persistent", f"score_{camera_name}.pkl"), "rb") as file:
            return pickle.load(file)

    def __post_init__(self):
        from application.windows.app_window import RoiSize
        self._roi_size_model = RoiSize()

    @property
    def score(self):
        if (
                not self.list_score
                or
                self._is_no_face_threshold_reached
        ):
            return 100

        return sum(self.list_score) / len(self.list_score)

    def add_score(self, value):
        if not value:
            self._zero_score_counter += 1
            return
        if value == -1:
            self._no_face_counter += 1
            return

        self.list_score.append(value)

    @property
    def _is_no_face_threshold_reached(self):
        return self._no_face_counter >= _Face_Not_Found_Termination

    @property
    def is_all_scored(self):
        if self._is_no_face_threshold_reached:
            return True
        if self._is_currently_selected:
            return _Count_Frame4Scoring == len(self.list_score)
        return len(self.list_score) == len(self._list_frame)

    def flush2disk(self):
        self._face_detector = None
        self._roi_size_model = None
        with open(os.path.join("./persistent", f"score_{self.camera_name}.pkl"), "wb") as file:
            pickle.dump(self, file)
        logger.info(f'Flushing to disk {self.camera_name}')

    @property
    def is_enough_frame_collected(self):
        return len(self._list_frame) >= _Count_Frame4Scoring

    def add_new_frame(self, frame):
        from application.windows.app_window import AppWindow

        self._face_detector = self._face_detector or FaceDetector()
        try:
            calculated_roi_tuple = AppWindow.roi_coordinate_from_face_detector(
                face_detector=self._face_detector,
                frame=frame,
                model_roi_size=self._roi_size_model,
            )[0]
            self._list_face_detections.append(calculated_roi_tuple)
            self._list_frame.append(frame)
        except Exception:
            self._no_face_counter += 1
            if self._is_no_face_threshold_reached:
                logger.error(f'No face has been detected in frames of {self.camera_name}')
                raise TypeError

    def get_frame(self):
        for index, frame in enumerate(self._list_frame):
            yield frame, self._list_face_detections[index]

    def delete(self):
        os.remove(os.path.join("./persistent", f"score_{self.camera_name}.pkl"))

    @staticmethod
    def delete_all_score_files():
        import os
        directory = "./persistent"
        try:
            for filename in os.listdir(directory):
                if filename.startswith("score_"):
                    file_path = os.path.join(directory, filename)
                    if os.path.isfile(file_path):
                        os.remove(file_path)
        except Exception as e:
            logger.error(f"An error occurred while deleting all scores: {e}")


class CameraScoring(QWidget):

    def __init__(self, *args, **kwargs):
        self._currently_selected_camera_holder = None
        self._dict_score = {}
        super().__init__(*args, **kwargs)
        self._camera_frames_holder: None | FrameHolder4Score = None
        self.collect_score4currently_active_camera = False
        self._frame_generator = None
        self._last_test_frame_scored_time = None
        self._switch2came = None
        self.set_test_camera_score_counter = 0
        self._is_waiting_for_inference_results = False

        self.counter4test_frame_ingestion_turn = None

    def _load_camera_frame_for_test(self, camera_name):
        self.collect_score4currently_active_camera = not bool(self._currently_selected_camera_holder)
        self.counter4test_frame_ingestion_turn = _Test_Inference_Interval
        self._currently_selected_camera_holder = FrameHolder4Score.currently_selected_camera()
        self._camera_frames_holder = FrameHolder4Score.load(camera_name)
        self._frame_generator = self._camera_frames_holder.get_frame()

    def set_score4test_camera(self, value):
        if not self._currently_selected_camera_holder:
            return
        if not _is_camera_still_connected(_dict_subprocess_shared_data, self._camera_frames_holder.camera_name):
            self._currently_selected_camera_holder = None
            self._frame_generator = None
            _set_next_camera4scoring(_dict_subprocess_shared_data)
            return

        self.set_test_camera_score_counter += 1
        self._is_waiting_for_inference_results = False
        self._camera_frames_holder.add_score(value)
        if not self._camera_frames_holder.is_all_scored:
            return
        threading.Thread(
            target=self._scored_done,
            args=(self._camera_frames_holder.camera_name, self._camera_frames_holder.score),
        ).start()
        self._camera_frames_holder.delete()
        self._camera_frames_holder = None

    def set_score4currently_selected_camera(self, value):
        if not self._currently_selected_camera_holder:
            return
        self._currently_selected_camera_holder.add_score(value)

        if not self._currently_selected_camera_holder.is_all_scored:
            return
        self.collect_score4currently_active_camera = False
        threading.Thread(
            target=self._scored_done,
            args=(
                _dict_subprocess_shared_data['currently_selected_camera'],
                self._currently_selected_camera_holder.score,
            ),
        ).start()

    def capture_frame(self) -> None:
        try:
            if (
                    _dict_subprocess_shared_data['manually_selected_stop_scoring']
                    or
                    _dict_subprocess_shared_data['auto_selector_service_stopped_flag']

            ):
                FrameHolder4Score.delete_all_score_files()
                self._frame_generator = None
                self._dict_score.clear()
                self._currently_selected_camera_holder = None
                self.counter4test_frame_ingestion_turn = None
                _dict_subprocess_shared_data['camera_for_score'] = ''
                _dict_subprocess_shared_data['manually_selected_stop_scoring'] = False
                _dict_subprocess_shared_data['auto_selector_service_stopped_flag'] = False
            elif (
                    self._frame_generator
                    and
                    not self._is_waiting_for_inference_results
                    and
                    (
                            self.counter4test_frame_ingestion_turn and self.counter4test_frame_ingestion_turn >= _Test_Inference_Interval)
            ):
                try:
                    frame, (x, y, size) = next(self._frame_generator)
                    self.process_frame(frame, roi_size=size, roi_center_x=x, roi_center_y=y, is_test_frame=True, )
                    self._is_waiting_for_inference_results = True
                except StopIteration:
                    self._frame_generator = None
                    _dict_subprocess_shared_data['camera_for_score'] = ''

            elif name := _dict_subprocess_shared_data['camera_for_score']:
                _dict_subprocess_shared_data['camera_for_score'] = ''
                threading.Thread(target=self._load_camera_frame_for_test, args=(name,)).start()
            elif self._switch2came or _dict_subprocess_shared_data['switch_to_camera']:
                self._switch2came = self._switch2came or _dict_subprocess_shared_data['switch_to_camera']
                if self._switch2came != _dict_subprocess_shared_data['currently_selected_camera']:
                    logger.info(f'Switch to Camera {self._switch2came}')
                    self.select_camera(self._switch2came)
                self._switch2came = None
                _dict_subprocess_shared_data['switch_to_camera'] = ''
        except BrokenPipeError:
            logger.error("Encountered BrokenPipeError during capture frame")

    def _scored_done(self, camera_name, score):
        _scoring_done(_dict_subprocess_shared_data, camera_name)
        self._dict_score[camera_name] = score
        try:
            for camera in _dict_subprocess_shared_data['camera_waiting_list']:
                if camera[-1:] in ['1', '0']:
                    return
        except BrokenPipeError:
            logger.error("Encountered BrokenPipeError on accessing camera_waiting_list attribute")
            return
        # scoring done switch to the best camera scored
        logger.info(f'dict scoring after all cameras has been scored {self._dict_score}')
        best_camera = min(self._dict_score, key=self._dict_score.get)
        len(self._dict_score.keys()) > 1 and _write_to_camera_history(
            best_camera,
            list(self._dict_score.keys()),
            is_auto=True,
        )
        self._dict_score.clear()
        self._switch2came = best_camera
        self._currently_selected_camera_holder = None
        self.counter4test_frame_ingestion_turn = None
        try:
            _dict_subprocess_shared_data['camera_waiting_list'] = []
        except BrokenPipeError:
            logger.error("Encountered BrokenPipeError on setting camera_waiting_list attribute")
