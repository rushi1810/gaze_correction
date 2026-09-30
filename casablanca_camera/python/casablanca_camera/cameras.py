import glob
import ctypes
import enum
import logging
import os
import time

import numpy as np

from . import windows

logger = logging.getLogger(__name__)

_dll = None
""" The handle to the underlying DLL. """

_virtual_camera_instance = None
""" The single instance of the VirtualCamera class. """


class VirtualCameraStreamStatus(enum.IntEnum):
    """ Internal class, the camera stream status. """
    StreamStarted = 1
    StreamStopped = 2


class CameraDeviceInfo(ctypes.Structure):
    """ Internal class, camera device info. """
    _fields_ = [('camera_index', ctypes.c_int),
                ('camera_name', ctypes.c_wchar * windows.MAX_PATH)
                ]


def _np_array_to_ctypes(array):
    """
    Convert a numpy array to ctype data.
    :param array:
    :return: pointer to the buffer, buffer size
    """
    if not array.data.c_contiguous:
        raise ValueError('Array must be contiguous')

    cimage = array.ctypes
    buffer_size = ctypes.c_long(array.size)
    buffer = ctypes.c_void_p(cimage.data)

    return buffer, buffer_size


class RealCameraInfo:
    """ Information about real camera. """
    def __init__(self, camera_device_info):
        self.index = camera_device_info.camera_index
        self.name = camera_device_info.camera_name

    def __str__(self):
        return f'{self.index}: {self.name}'


def initialize(dll_dir):
    """ Call this function first before you start working with Casablanca camera library. """
    global _dll
    _dll = ctypes.WinDLL(os.path.join(dll_dir, 'CasablancaCameraAPI.dll'))


def get_real_cameras():
    """ Returns a list of RealCameraInfo objects with the information about real cameras. """
    max_num_cameras = 1000
    camera_device_info = (CameraDeviceInfo * max_num_cameras)()

    number_of_camera_devices = ctypes.c_int(max_num_cameras)

    result = _dll.RealCameraGetList(
        ctypes.byref(camera_device_info),
        ctypes.byref(number_of_camera_devices),
    )

    if result != windows.S_OK:
        raise RuntimeError(
            f'RealCameraGetList() failed, error {result}. Make sure the virtual camera driver is installed')

    logger.info(f'Detected {number_of_camera_devices.value} cameras')

    real_cameras = []
    for i in range(number_of_camera_devices.value):
        real_cameras.append(RealCameraInfo(camera_device_info[i]))

    return real_cameras


class RealCamera:
    """ Real camera interface, more reliable than the opencv one. """

    def __init__(self, new_camera_name, desired_resolution=(720, 1280), desired_frame_rate=60):
        """
        Open real camera. It will be opened in the format equal (if supported) or closest to the given
        desired parameters.
        :param index the index from RealCameraInfo returned by get_real_cameras().
        :param desired_resolution desired resolution of the real camera (H, W).
        :param desired_frame_rate desired resolution of the real camera (H, W).
        """
        camera_infos = {camera.name: camera.index for camera in get_real_cameras()}
        camera_found = False
        for camera_name, camera_index in camera_infos.items():
            if camera_name.startswith(new_camera_name):
                self.camera_name = camera_name
                self.camera_index = camera_index
                camera_found = True
                break
        if not camera_found:
            logger.error(f"Camera {new_camera_name} not available. Defaulting to other camera")
            camera_name, camera_index = list(camera_infos.items())[0]
            logger.info(f"Opening {camera_name}")
            self.camera_name = camera_name
            self.camera_index = camera_index

        self._image_buffer = None

        logging.info(f'Opening real camera {self.camera_name} using virtual camera driver')

        frame_width = ctypes.c_int(desired_resolution[1])
        frame_height = ctypes.c_int(desired_resolution[0])
        frame_rate = ctypes.c_float(desired_frame_rate)

        result = _dll.RealCameraOpen(
            ctypes.c_int(self.camera_index),
            ctypes.byref(frame_width),
            ctypes.byref(frame_height),
            ctypes.byref(frame_rate)
        )

        if result != windows.S_OK:
            raise RuntimeError(f'RealCameraOpen() failed, error {result}')

        logging.info(f'Opened real camera {self.camera_index}, frame rate {frame_rate.value}, '
                     f'width {frame_width.value}, height {frame_height.value}')

        self._resolution = (frame_height.value, frame_width.value)
        self._frame_rate = frame_rate.value

        # Allocate buffer
        # Buffer size for YUY2 frame = height * width * 2, since 2 bytes per pixel for YUY2
        self._image_buffer = np.zeros((frame_height.value, frame_width.value, 2), dtype=np.uint8)

    def __del__(self):
        self.close()

    @property
    def resolution(self):
        """ The resolution (H, W) of the camera. """
        return self._resolution

    @property
    def frame_rate(self):
        """ The frame rate. """
        return self._frame_rate

    @staticmethod
    def close():
        _dll.RealCameraClose()

    def read_frame(self):
        """
        Read a frame from the real camera.
        :return: a numpy array with the real camera image. The returned image is read-only
        and shall not be modified directly.
        """
        buffer, buffer_size = _np_array_to_ctypes(self._image_buffer)
        result = _dll.RealCameraGetFrame(buffer, ctypes.byref(buffer_size))
        if result != windows.S_OK:
            raise RuntimeError(f'RealCameraGetFrame() failed, error {result}')

        frame = self._image_buffer

        return frame

    def stop(self):
        _dll.RealCameraClose()

    def start(self):
        self.__init__(self.camera_name)


class VirtualCamera:
    """ Virtual camera. """

    def __init__(self):
        """
        Create a virtual camera.
        """
        global _virtual_camera_instance
        if _virtual_camera_instance is not None:
            raise RuntimeError('Only one virtual camera at a time can be created')

        virtual_camera_interface_found = ctypes.c_int()

        result = _dll.VirtualCameraOpen(ctypes.byref(virtual_camera_interface_found))

        if result != windows.S_OK or virtual_camera_interface_found.value == 0:
            raise RuntimeError(f'VirtualCameraOpen() failed, error {result}. '
                               f'Make sure the virtual camera driver is installed')
        self.frame_count = 0
        self.last_time_point = time.perf_counter()

    def __del__(self):
        self.close()
        global _virtual_camera_instance
        _virtual_camera_instance = None

    @property
    def resolution(self):
        """ The resolution of the virtual camera. """
        # Currently the driver supports only one resolution
        return 720, 1280

    def close(self):
        _dll.VirtualCameraClose()

    @property
    def is_used(self):
        """
        Status of the virtual camera.
        :return: True if the virtual camera is used by an application (e.g. Skype), otherwise False.
        """
        virtual_camera_status = ctypes.c_byte()
        _dll.VirtualCameraGetStreamStatus(ctypes.byref(virtual_camera_status))
        return virtual_camera_status.value == VirtualCameraStreamStatus.StreamStarted

    def write_frame(self, image):
        """
        Write a frame to the virtual camera.
        :param image: a HxWx3 numpy byte array, (H, W) must match self.resolution.
        """
        if image.dtype != np.uint8:
            raise ValueError(f"Image dtype is '{image.dtype}' but should be 'np.uint8'")
        if image.shape[:2] != self.resolution:
            raise ValueError(f"Image resolution is {image.shape[:2]} but should be {self.resolution}")
        if image.shape[2] != 2:
            raise ValueError(f"Image has {image.shape[2]} channels but should have 2 channels")

        buffer, buffer_size = _np_array_to_ctypes(image)

        result = _dll.VirtualCameraWriteFrame(buffer, buffer_size)
        if result != 0:
            logger.error(f"VirtualCameraWriteFrame() failed with results = '{result}'")
            if result == 6:
                logger.error(f"Re-initializing virtual camera")
                self.__init__()
            else:
                raise RuntimeError('VirtualCameraWriteFrame() failed')

        self.frame_count += 1
        current_time_point = time.perf_counter()
        if current_time_point - self.last_time_point > 60:
            fps = self.frame_count / (current_time_point - self.last_time_point)
            self.last_time_point = current_time_point
            self.frame_count = 0
            logger.info(f"Virtual camera performance: {fps:.1f} FPS")
