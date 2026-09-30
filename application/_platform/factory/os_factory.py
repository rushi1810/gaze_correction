import logging
import os
import sys

logger = logging.getLogger(__name__)


class Factory:
    is_mac = True if sys.platform == "darwin" else False

    @classmethod
    def create_main_algo_instance(cls, settings, config):
        if cls.is_mac:
            try:
                from application._platform.macOS.main_algo import MainAlgo
            except RuntimeError as e:
                logger.error(f"Encountered error: {e}")
                cls.open_privacy_and_security_menu()
                raise RuntimeError(f"Opened Privacy and Security menu due to 1007 error. Original error: {e}")
        else:
            from application._platform.windows.main_algo import MainAlgo
        return MainAlgo(settings, config)

    @staticmethod
    def init_windows():
        from casablanca_camera.python.casablanca_camera import cameras
        virtual_cam_dll = os.path.join(os.path.dirname(__file__), "..", "..", "..", "casablanca_camera", "bin")
        cameras.initialize(virtual_cam_dll)

    @classmethod
    def virtual_camera(cls):
        if cls.is_mac:
            try:
                from application._platform.macOS.virtual_camera import VirtualCamera
            except (RuntimeError, OSError) as e:
                logger.error(f"Encountered error: {e}")
                cls.open_privacy_and_security_menu(error=e)
                raise e
            return VirtualCamera()
        else:
            from casablanca_camera.python.casablanca_camera import cameras
            virtual_cam_dll = os.path.join(os.path.dirname(__file__), "..", "..", "..", "casablanca_camera", "bin")
            cameras.initialize(virtual_cam_dll)
            return cameras.VirtualCamera()

    @classmethod
    def available_processors(cls):
        if cls.is_mac:
            try:
                from application._platform.macOS.processor_info import get_processors
            except RuntimeError as e:
                logger.error(f"Encountered error: {e}")
                cls.open_privacy_and_security_menu()
                raise e
            return get_processors()
        else:
            from application._platform.windows.processor_info import get_processors
            return get_processors()

    @classmethod
    def open_privacy_and_security_menu(cls, error=None):
        error = str(error) if error is not None else " "
        logger.error(
            f"Assuming lacking permissions for Casablanca Application. Requesting access" if error == " " else error)
        os.system("open 'x-apple.systempreferences:com.apple.preference.security?Privacy'")
        os.system(
            "osascript -e 'tell application \"Casablanca Application\" "
            "to display dialog "
            f"\"Something is happening -> {error}\n \n"
            "This problem could be due to a lack of permissions\n"
            "Please follow below steps to give permission access to Casablanca\n\n"
            "Go to System Settings\n"
            "-> Privacy and Security\n"
            "-> Scroll down to the Security section\n"
            "-> Below the message\n"
            "\t´System software from application\n"
            "\tCasablanca Virtual Camera was \n"
            "\tblocked from loading´\n"
            "Click ´Allow´\n\n"
            "Then restart the app \n"
            "If the problem persists, please write to Casablanca customer support: support@casablanca.ai \n"
            "-> Also, share the screenshots and logs, located at: \n"
            "/Library/Application Support/Casablanca/app-ort/persistent\" "
            "buttons {\"OK\"} "
            "with title \"Casablanca Application requires additional permissions\" "
            "with icon note' ")
