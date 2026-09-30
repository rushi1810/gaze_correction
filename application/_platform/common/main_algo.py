import logging
from collections import deque
from enum import Enum
import numpy as np

from application._platform import base

logger = logging.getLogger(__name__)

class HeadCorrectionState(Enum):
    MANUAL = [1, 0, 0, 0]
    DYNAMIC = [0, 1, 0, 0]
    ONBUTTON = [0, 0, 1, 0]
    OCCLUDED = [0, 0, 0, 1]

class GazeCorrectionState(Enum):
    MANUAL = [1, 0, 0, 0, 0]
    DYNAMIC = [0, 1, 0, 0, 0]
    ONBUTTON = [0, 0, 1, 0, 0]
    OCCLUDED = [0, 0, 0, 1, 0]
    ALWAYS = [0, 0, 0, 0, 1]

class MainAlgo(base.main_algo.MainAlgo):

    def __init__(self, settings, config):
        self._settings = settings
        self._config = config
        self.last_frame_had_face = False
        self.times_face_was_lost_count = 0
        self.frame_count = 0
        self.gaze_angle_horizontal_counts = {}
        self.gaze_angle_vertical_counts = {}
        self.head_angle_horizontal_counts = {}
        self.head_angle_vertical_counts = {}
        self.manually_corrected_gaze_angle_horizontal_counts = {}
        self.manually_corrected_gaze_angle_vertical_counts = {}
        self.manually_corrected_head_angle_horizontal_counts = {}
        self.manually_corrected_head_angle_vertical_counts = {}
        self.difference_predicted_and_manually_corrected_gaze_angle_horizontal_counts = {}
        self.difference_predicted_and_manually_corrected_gaze_angle_vertical_counts = {}
        self.difference_predicted_and_manually_corrected_head_angle_horizontal_counts = {}
        self.difference_predicted_and_manually_corrected_head_angle_vertical_counts = {}
        self.frames_with_dynamic_correction_available_count = 0
        self.frames_with_corrected_gaze_count = 0
        self.frames_with_corrected_head_count = 0
        self.roi_size_counts = {}

        self.gaze_left_right_rescale = self._config["gaze_corrector"]["mac_left_right_rescale"]
        self.gaze_up_down_rescale = self._config["gaze_corrector"]["mac_up_down_rescale"]
        self.head_left_right_rescale = self._config["head_corrector"]["mac_left_right_rescale"]
        self.head_up_down_rescale = self._config["head_corrector"]["mac_up_down_rescale"]

        self.head_gaze_w_history = np.zeros((30, 4), dtype=np.float32)
        self.old_w_target = np.zeros((1, 4), dtype=np.float32)
        self.head_gaze_w_d_previous_corrections = np.zeros((1, 4), dtype=np.float32)
        self.dyn_enable_head = np.array(
            HeadCorrectionState.DYNAMIC.value if self._settings.dynamic_correct else HeadCorrectionState.MANUAL.value,
            dtype=np.float32)
        self.dyn_enable_gaze = np.array(
            GazeCorrectionState.DYNAMIC.value if self._settings.dynamic_correct else GazeCorrectionState.MANUAL.value,
            dtype=np.float32)
        self.hand_occlusion_mean_threshold = self._config["hand_occlusion"]["mean_threshold"]
        self.max_frame_to_track_mean = self._config["hand_occlusion"]["max_frame_to_track_mean"]
        self.last_n_occlusion_history = deque()
        self.switch_off_head_correction: bool = False
        self.sum_last_n_occlusion_scores = 0

    def is_occluded(self, occlusion_conf: float) -> bool:
        if len(self.last_n_occlusion_history) >= self.max_frame_to_track_mean:
            val = self.last_n_occlusion_history.popleft()
            self.sum_last_n_occlusion_scores -= val
        self.sum_last_n_occlusion_scores += occlusion_conf
        self.last_n_occlusion_history.append(occlusion_conf)
        mean_occlusion_score = self.sum_last_n_occlusion_scores / self.max_frame_to_track_mean
        if mean_occlusion_score > self.hand_occlusion_mean_threshold:
            return True
        return False

    def process_frame(self, cropped_roi, is_test_frame=False, dyn_gaze_offsets=None, base_angles=None):
        return self.process_frame_lsm(
            cropped_roi, is_test_frame=is_test_frame, dyn_gaze_offsets=dyn_gaze_offsets, base_angles=base_angles)

    def update_roi_bounding_box(
            self, head_movement_vector, *,
            translation_speed: float = 0.2, scaling_speed: float = 0.5, stickiness_threshold: float = 0.002) -> None:
        # Remap from -1 to 1 range to 0.5 to 1 range
        # to make smaller ROIs move slower in absolute numbers than bigger ROIs
        scaling_factor = (self._settings.roi_size + 3) / 4
        x_translation = head_movement_vector[1] * translation_speed
        if abs(x_translation) >= stickiness_threshold:
            self._settings.roi_center_x = max(0, min(1, self._settings.roi_center_x + x_translation * scaling_factor))
        y_translation = head_movement_vector[2] * translation_speed
        if abs(y_translation) >= stickiness_threshold:
            self._settings.roi_center_y = max(0, min(1, self._settings.roi_center_y + y_translation * scaling_factor))

        def additive_size_change():
            roi_blending_pixel_width = 32
            roi_total_pixel_width = 288
            roi_blending_size_adjustment = 1 - (roi_blending_pixel_width / roi_total_pixel_width)
            target_roi_size_divided_by_current_roi_size = head_movement_vector[0] / roi_blending_size_adjustment
            return target_roi_size_divided_by_current_roi_size - 1

        size_change = additive_size_change() * scaling_speed
        if abs(size_change) >= stickiness_threshold * 10:
            self._settings.roi_size = max(-1, min(1, self._settings.roi_size + size_change.item()))

    def get_model_inputs(self, cropped_roi, is_test_frame, dyn_gaze_offsets=None, base_angles=None):
        if not is_test_frame:
            self.frame_count += 1
        src = (cropped_roi.transpose(2, 0, 1)[None, ...] * (2 / 255) - 1).astype(np.float16)
        if dyn_gaze_offsets is not None:
            self.dyn_enable_head = np.array(HeadCorrectionState.MANUAL.value, dtype=np.float32)
        elif self.switch_off_head_correction:
            self.dyn_enable_head = np.array(HeadCorrectionState.OCCLUDED.value, dtype=np.float32)
        elif self._settings.dynamic_correct:
            self.dyn_enable_head = np.array(HeadCorrectionState.DYNAMIC.value, dtype=np.float32)
        else:
            self.dyn_enable_head = np.array(HeadCorrectionState.MANUAL.value, dtype=np.float32)

        if dyn_gaze_offsets is not None or not self._settings.dynamic_correct:
            self.dyn_enable_gaze = np.array(GazeCorrectionState.MANUAL.value, dtype=np.float32)
        elif self._settings.constant_eye_contact_available and self._settings.constant_eye_contact_wanted:
            self.dyn_enable_gaze = np.array(GazeCorrectionState.ALWAYS.value, dtype=np.float32)
        else:
            self.dyn_enable_gaze = np.array(GazeCorrectionState.DYNAMIC.value, dtype=np.float32)

        if is_test_frame:
            w_d_prev = np.zeros((1, 4), dtype=np.float32)
        else:
            w_d_prev = self.head_gaze_w_d_previous_corrections

        if base_angles is not None:
            if dyn_gaze_offsets is not None:
                base_angles += np.array(
                    [dyn_gaze_offsets[0] * self._config["gaze_corrector"]["win_left_right_rescale"],
                     dyn_gaze_offsets[1] * self._config["gaze_corrector"]["win_up_down_rescale"],
                     0,
                     0], np.float32)
            w_d_manual = base_angles
            w_d_prev = base_angles
        else:
            w_d_manual = np.array([[
                self._settings.gaze_left_right * self.gaze_left_right_rescale,
                -self._settings.gaze_up_down * self.gaze_up_down_rescale,
                self._settings.head_left_right * self.head_left_right_rescale,
                -self._settings.head_up_down * self.head_up_down_rescale
            ]]).astype(np.float32)
        gaze_thresholds = np.asarray([
            self._settings.gaze_x_correction_threshold,
            self._settings.gaze_y_correction_threshold,
            self._settings.gaze_x_static_threshold,
            self._settings.gaze_y_static_threshold]).astype(np.float32)
        head_thresholds = np.asarray([
            self._settings.head_x_correction_threshold,
            self._settings.head_y_correction_threshold,
            self._settings.head_x_static_threshold,
            self._settings.head_y_static_threshold]).astype(np.float32)
        if self._settings.setup_calibrations.get(self._settings.camera_name) is not None:
            dyn_gaze_offsets = np.array([self._settings.setup_calibrations[self._settings.camera_name]["x"]
                                         * self._config["gaze_corrector"]["win_left_right_rescale"],
                                         self._settings.setup_calibrations[self._settings.camera_name]["y"]
                                         * self._config["gaze_corrector"]["win_up_down_rescale"]], np.float32)
        else:
            dyn_gaze_offsets = np.array([0, 0], np.float32)
        model_input = dict(src=src, w_history=np.zeros((30, 4), dtype=np.float32) if is_test_frame else self.head_gaze_w_history,
                           old_w_target=np.zeros((1, 4), dtype=np.float32) if is_test_frame else self.old_w_target,
                           w_d_prev=w_d_prev,
                           w_d_manual=w_d_manual,
                           dyn_enable_head=self.dyn_enable_head,
                           dyn_enable_gaze=self.dyn_enable_gaze,
                           dyn_gaze_offsets=dyn_gaze_offsets,
                           gaze_thresholds=gaze_thresholds,
                           head_thresholds=head_thresholds)
        return model_input

    def post_process_model_output(self, result, is_test_frame):
        self.switch_off_head_correction = (self._settings.turn_off_correction_on_occlusion
                                           and self.is_occluded(result["hand_occlusion_confidence"].item()))
        head_gaze_w = result["w_in"]
        camera_score = np.linalg.norm(head_gaze_w[:, 2:])
        generated = ((np.moveaxis(result["generated"][0], 0, -1) + 1) * (255 / 2)).astype(np.uint8)
        if is_test_frame:
            return camera_score, generated
        self.head_gaze_w_history = np.concatenate([self.head_gaze_w_history[1:], result["w_in"]], axis=0)
        self.head_gaze_w_d_previous_corrections = result["w_d"]
        self.old_w_target = result["new_target"]
        self._settings.head_is_in_roi_confidence = float(result["conf"].squeeze())
        minimal_required_head_in_roi_confidence = 0.2
        if self._settings.head_is_in_roi_confidence > minimal_required_head_in_roi_confidence:
            head_movement_vector = result["s_tx_ty"].squeeze()
            self.update_roi_bounding_box(head_movement_vector)
            self.last_frame_had_face = True
            self.record_predicted_head_and_gaze_angles(head_gaze_w)
            if not self._settings.dynamic_correct and not self.switch_off_head_correction:
                self.record_manually_corrected_head_and_gaze_angles(result["w_d"])
                self.record_difference_predicted_and_manually_corrected_head_and_gaze_angles(head_gaze_w, result["w_d"])
            if self._settings.dynamic_correct:
                self.frames_with_dynamic_correction_available_count += 1
                if self.is_gaze_corrected(head_gaze_w):
                    self.frames_with_corrected_gaze_count += 1
                if self.is_head_corrected(head_gaze_w):
                    self.frames_with_corrected_head_count += 1
        else:
            if self.last_frame_had_face:
                self.times_face_was_lost_count += 1
            self.last_frame_had_face = False
        return (camera_score if self.last_frame_had_face else -1), generated

    def is_gaze_corrected(self, head_gaze_w):
        return (abs(head_gaze_w[0, 0]) < self._settings.gaze_x_correction_threshold
                and abs(head_gaze_w[0, 1]) < self._settings.gaze_y_correction_threshold)

    def is_head_corrected(self, head_gaze_w):
        return (abs(head_gaze_w[0, 2]) < self._settings.head_x_correction_threshold
                and abs(head_gaze_w[0, 3]) < self._settings.head_y_correction_threshold)

    def record_predicted_head_and_gaze_angles(self, head_gaze_w):
        gaze_x_angle, gaze_y_angle, head_x_angle, head_y_angle = head_gaze_w[0]
        self.gaze_angle_horizontal_counts[int(gaze_x_angle)] = \
            self.gaze_angle_horizontal_counts.get(int(gaze_x_angle), 0) + 1
        self.gaze_angle_vertical_counts[int(gaze_y_angle)] = \
            self.gaze_angle_vertical_counts.get(int(gaze_y_angle), 0) + 1
        self.head_angle_horizontal_counts[int(head_x_angle)] = \
            self.head_angle_horizontal_counts.get(int(head_x_angle), 0) + 1
        self.head_angle_vertical_counts[int(head_y_angle)] = \
            self.head_angle_vertical_counts.get(int(head_y_angle), 0) + 1
        self.roi_size_counts[int(self._settings.roi_size * 10) / 10] = \
            self.roi_size_counts.get(int(self._settings.roi_size * 10) / 10, 0) + 1

    def record_manually_corrected_head_and_gaze_angles(self, head_gaze_w_d):
        manual_gaze_x_angle, manual_gaze_y_angle, manual_head_x_angle, manual_head_y_angle = head_gaze_w_d[0]
        self.manually_corrected_gaze_angle_horizontal_counts[int(manual_gaze_x_angle)] = \
            self.manually_corrected_gaze_angle_horizontal_counts.get(int(manual_gaze_x_angle), 0) + 1
        self.manually_corrected_gaze_angle_vertical_counts[int(manual_gaze_y_angle)] = \
            self.manually_corrected_gaze_angle_vertical_counts.get(int(manual_gaze_y_angle), 0) + 1
        self.manually_corrected_head_angle_horizontal_counts[int(manual_head_x_angle)] = \
            self.manually_corrected_head_angle_horizontal_counts.get(int(manual_head_x_angle), 0) + 1
        self.manually_corrected_head_angle_vertical_counts[int(manual_head_y_angle)] = \
            self.manually_corrected_head_angle_vertical_counts.get(int(manual_head_y_angle), 0) + 1

    def record_difference_predicted_and_manually_corrected_head_and_gaze_angles(self, head_gaze_w, head_gaze_w_d):
        gaze_x_angle, gaze_y_angle, head_x_angle, head_y_angle = head_gaze_w[0]
        manual_gaze_x_angle, manual_gaze_y_angle, manual_head_x_angle, manual_head_y_angle = head_gaze_w_d[0]
        difference_predicted_and_manually_corrected_gaze_x_angle = gaze_x_angle - manual_gaze_x_angle
        difference_predicted_and_manually_corrected_gaze_y_angle = gaze_y_angle - manual_gaze_y_angle
        difference_predicted_and_manually_corrected_head_x_angle = head_x_angle - manual_head_x_angle
        difference_predicted_and_manually_corrected_head_y_angle = head_y_angle - manual_head_y_angle
        self.difference_predicted_and_manually_corrected_gaze_angle_horizontal_counts[
            int(difference_predicted_and_manually_corrected_gaze_x_angle)] = (
                self.difference_predicted_and_manually_corrected_gaze_angle_horizontal_counts.get(
                    int(difference_predicted_and_manually_corrected_gaze_x_angle), 0) + 1)
        self.difference_predicted_and_manually_corrected_gaze_angle_vertical_counts[
            int(difference_predicted_and_manually_corrected_gaze_y_angle)] = (
                self.difference_predicted_and_manually_corrected_gaze_angle_vertical_counts.get(
                    int(difference_predicted_and_manually_corrected_gaze_y_angle), 0) + 1)
        self.difference_predicted_and_manually_corrected_head_angle_horizontal_counts[
            int(difference_predicted_and_manually_corrected_head_x_angle)] = (
                self.difference_predicted_and_manually_corrected_head_angle_horizontal_counts.get(
                    int(difference_predicted_and_manually_corrected_head_x_angle), 0) + 1)
        self.difference_predicted_and_manually_corrected_head_angle_vertical_counts[
            int(difference_predicted_and_manually_corrected_head_y_angle)] = (
                self.difference_predicted_and_manually_corrected_head_angle_vertical_counts.get(
                    int(difference_predicted_and_manually_corrected_head_y_angle), 0) + 1)
