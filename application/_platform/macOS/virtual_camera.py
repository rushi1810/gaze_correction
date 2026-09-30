import gc
import sys
import ctypes
from ctypes.util import find_library
import logging
import os
import numpy as np

from application._platform import base
from application.check_install_errors import CheckInstallErrors
from application.send_crash_report import CrashReportSender
from application.settings import Settings

logger = logging.getLogger(__name__)


class VirtualCamera(base.virtual_camera.VirtualCamera):
    """ Virtual camera. """
    ret_codes = {
        1: "Status Success",
        1001: "Invalid Frame Width",
        1002: "Invalid Frame Height",
        1003: "Invalid Frame Rate",
        1004: "Camera not found",
        1005: "Camera frame not available",
        1006: "Camera streaming error",
        1007: "Virtual camera cannot find device",
        1008: "Virtual camera cannot get CMIO device ID",
        1009: "Virtual camera cannot get CMIO stream IDs",
        1010: "Virtual camera cannot initialize sink stream"
    }
    user_id = Settings().user_id

    def __init__(self, dylib_dir: str = "/usr/local/lib"):
        self.dylib_file = os.path.join(dylib_dir, 'libCasablancaVirtualCamera.dylib')
        self.virtual_cam_dylib = None
        self.initialize()


    def initialize(self):
        """ Call this function first before you start working with Casablanca camera library. """
        if not os.path.exists(self.dylib_file):
            raise OSError("Virtual camera library not found. Make sure it was installed correctly.")
        try:
            self.virtual_cam_dylib = ctypes.cdll.LoadLibrary(self.dylib_file)
        except OSError:
            raise RuntimeError(
                'libCasablancaVirtualCamera.dylib file is not present in /usr/local/lib, please re-install the app or contact customer support')
        if self.virtual_cam_dylib:
            # Set function prototypes once
            self.virtual_cam_dylib.InitializeCamera.argtypes = []
            self.virtual_cam_dylib.InitializeCamera.restype = ctypes.c_int

            self.virtual_cam_dylib.DeInitializeCamera.argtypes = []
            self.virtual_cam_dylib.DeInitializeCamera.restype = ctypes.c_int

            self.virtual_cam_dylib.GetCameraStreamingStatus.argtypes = []
            self.virtual_cam_dylib.GetCameraStreamingStatus.restype = ctypes.c_int

            self.virtual_cam_dylib.RealCameraStartCapture.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_int, ctypes.c_int]
            self.virtual_cam_dylib.RealCameraStartCapture.restype = ctypes.c_int

            self.virtual_cam_dylib.RealCameraStopCapture.argtypes = []
            self.virtual_cam_dylib.RealCameraStopCapture.restype = ctypes.c_int

            self.virtual_cam_dylib.RealCameraRestartCapture.argtypes = []
            self.virtual_cam_dylib.RealCameraRestartCapture.restype = ctypes.c_int

            self.virtual_cam_dylib.RealCameraGetFrame.argtypes = [ctypes.POINTER(ctypes.c_ubyte)]
            self.virtual_cam_dylib.RealCameraGetFrame.restype = ctypes.c_int

            self.virtual_cam_dylib.RealCameraGetList.argtypes = [ctypes.POINTER(ctypes.c_ubyte), ctypes.POINTER(ctypes.c_ubyte), ctypes.c_int]
            self.virtual_cam_dylib.RealCameraGetList.restype = ctypes.c_int

            self.virtual_cam_dylib.WriteImageBufferToCamera.argtypes = [ctypes.c_void_p]
            self.virtual_cam_dylib.WriteImageBufferToCamera.restype = ctypes.c_int

            virtual_cam_init = self.virtual_cam_dylib.InitializeCamera()
            err_msg = self.ret_codes.get(virtual_cam_init, "unknown error")
            if virtual_cam_init != 1:
                error_report = f"Error occurred while initializing virtual camera: {err_msg} and error code is: {virtual_cam_init}"
                if virtual_cam_init == 1007:
                    logger.error(f"Error occurred: {err_msg} and error code is: {virtual_cam_init}")
                    button_selected_by_user = CheckInstallErrors.create_custom_display(
                        msg="The Casablanca App can't reach our virtual camera. Click on 'Continue to activate it'",
                        title="Need Permissions",
                        buttons='["Cancel", "Continue"]', num_buttons=2)
                    if b"cancel" in button_selected_by_user.lower():
                        msg = "User Cancelled"
                        CheckInstallErrors.execute_exit_code(msg=msg)
                        error_report_handler = CrashReportSender(
                            error_report + "\nUser cancelled the automation prompt",
                            self.user_id)
                        error_report_handler.send_crash_report()
                    elif b"continue" in button_selected_by_user.lower():
                        if b"copy" in button_selected_by_user.lower():
                            CheckInstallErrors.copy_logs(CheckInstallErrors.debug_log_file,
                                                         CheckInstallErrors.desktop_log_dir,
                                                         CheckInstallErrors.persistent_dir)
                        CheckInstallErrors.activate_extension()
                        is_success_line = \
                        CheckInstallErrors.read_last_lines(file_path=CheckInstallErrors.debug_log_file)[0]
                        CheckInstallErrors.resolve_installation_errors(line=is_success_line)
                else:
                    error_report_handler = CrashReportSender(error_report,
                                                             self.user_id)
                    error_report_handler.send_crash_report()
                    raise RuntimeError(f"Error occurred: {err_msg} and error code is: {virtual_cam_init}")
            if not virtual_cam_init:
                raise RuntimeError("Unable to initialize virtual camera, please contact customer support")

    @property
    def virtual_camera_handler(self):
        if not hasattr(self, 'virtual_cam_dylib') or self.virtual_cam_dylib is None:
            logger.error("This should not have happened, VirtualCameraLib should have been initialized before calling this property")
            self.initialize()
        return self.virtual_cam_dylib


    @property
    def resolution(cls):
        """ The resolution of the virtual camera. """
        # Currently the driver supports only one resolution
        return 720, 1280


    def close(self):
        self.virtual_cam_dylib.DeInitializeCamera()

    @property
    def is_used(self):
        """
        Status of the virtual camera.
        :return: True if the virtual camera is used by an application (e.g. Skype), otherwise False.
        """
        return self.virtual_cam_dylib.GetCameraStreamingStatus() == 1


    def write_frame(self, image):
        """
        Write a frame to the virtual camera.
        :param image: a HxWx3 numpy byte array, (H, W) must match cls.resolution.
        """
        if image.dtype != np.uint8:
            raise ValueError(f"Image dtype is '{image.dtype}' but should be 'np.uint8'")
        if image.shape[:2] != self.resolution:
            raise ValueError(f"Image resolution is {image.shape[:2]} but should be {self.resolution}")
        if image.shape[2] != 2:
            raise ValueError(f"Image has {image.shape[2]} channels but should have 2 channels")
        image = np.ascontiguousarray(image[..., ::-1])
        buffer, buffer_size = self._np_array_to_ctypes(image)

        result = self.virtual_cam_dylib.WriteImageBufferToCamera(buffer)
        if result == 0:
            raise RuntimeError('VirtualCameraWriteFrame() failed')

        # Prevent memory hogging leading to app crash
        del buffer
        del buffer_size
        del image

    @classmethod
    def _np_array_to_ctypes(cls, array):
        """
        Convert a numpy array to ctype data.
        :param array:
        :return: pointer to the buffer, buffer size
        """
        if not array.data.c_contiguous:
            raise ValueError('Array must be contiguous')
        cimage = array.ctypes
        buffer_size = ctypes.c_long(array.nbytes)
        buffer = ctypes.c_void_p(cimage.data)
        return buffer, buffer_size

    def __del__(self):
        del self.virtual_cam_dylib
        gc.collect()



class RealCameraInfo:
    """ Information about real camera. """

    def __init__(self, name, index):
        self.index = index
        self.name = name

    def __str__(self):
        return f'{self.index}: {self.name}'
