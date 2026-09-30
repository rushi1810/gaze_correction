import json
import os
import shutil
import subprocess
import sys
import time
import logging

from application.send_crash_report import CrashReportSender
from application.settings import Settings
import platform
from packaging import version

logger = logging.getLogger(__name__)


class CheckInstallErrors:

    debug_log_file = os.path.abspath(os.path.join(os.getcwd(), "../DebugLog.txt"))
    persistent_dir = os.path.abspath(os.path.join(os.getcwd(), "persistent/"))
    desktop_log_dir = os.path.join(os.path.expanduser("~/Desktop/"), "Casablanca_logs")
    default_logs = os.path.abspath(os.path.join(persistent_dir, "logs_with_stdout.log"))

    PRIMARY_MSG = f"""
    Our install logs reports that your Macbook is managed by MDM software \n\n
    Please contact your IT ADMIN to grant an exception to the Casablanca Application.app from MDM with the below details:\n\n
    \tApple Developer Team ID: 76U5G36RZ8 \n\tBundle Identifier: com.casablanca.ai.virtualcamera.extension \n\n
    Please re-start the app after acquiring permissions. \n\n
    If the issue persists, write to Casablanca Customer Support: support@casablanca.ai \n\n
    Note: We can help you best, if you send us the screenshots and logs, located at below path(s): \n
    -> {debug_log_file} \n
    -> /Library/Application Support/Casablanca/app-ort/persistent
    """

    SECONDARY_MSG = f"""
    We hope you received an exception from your IT ADMIN for the Casablanca Application.app, we will now try to activate the Casablanca System Extension \n \n
    If the issue persists, write to the Casablanca Customer Support: support@casablanca.ai \n \n
    Note: We can help you best, if you send us the screenshots and logs, located at below path(s): \n
    -> {debug_log_file} \n
    -> /Library/Application Support/Casablanca/app-ort/persistent
    """

    is_started_from_app = False
    is_first_run = False



    @classmethod
    def set_is_started_from_app(cls, new_value):
        cls.is_started_from_app = new_value

    @classmethod
    def get_is_started_from_app(cls):
        return cls.is_started_from_app

    @classmethod
    def get_crash_handler(cls, crash_report: str):
        crash_report_handle = CrashReportSender(crash_report, Settings().user_id)
        return crash_report_handle

    @classmethod
    # Whenever this exit code is executed, the logs are sent to the Casablanca server
    # Should be removed in future when the application is stable
    def execute_exit_code(cls, msg: str = "Cancelled by User!"):
        cancel_script = f'''
                            display dialog "Exiting the application." buttons {{"OK"}} default button "OK" with title "{msg}" with icon stop giving up after 3
                         '''
        if cls.is_started_from_app:
            cancel_script = f'''
                                tell application "Casablanca Application"
                                display dialog "Exiting the application." buttons {{"OK"}} default button "OK" with title "{msg}" with icon stop giving up after 3
                                end tell
                             '''
        try:
            crash_report = cls.read_last_lines(cls.default_logs, num_lines=100)
            crash_handler = cls.get_crash_handler(crash_report)
            logger.info(f"sending crash report: {crash_report}")
            crash_handler.send_crash_report(is_logs_checked=True, is_call_back_ok=False)
            output = subprocess.check_output(["osascript", "-e", cancel_script])
            logger.error(f"Exiting the application: {msg} \nExit script output: {output}")
            sys.exit(1)
        except subprocess.CalledProcessError as e:
            logger.error(f"Exiting the application: {msg} \nExit script output: {output}")
            sys.exit(1)

    @classmethod
    def share_logs(cls, file_path: str = None, static_logs: str = None):
        if file_path is not None:
            if not os.path.exists(file_path):
                with open(cls.default_logs, "w") as f:
                    # Sanity check, if the log file is not created, then write this message for debugging
                    f.write("This should not have happened, the log file should have been created at the start\n")
        logs = " ".join(cls.read_last_lines(cls.default_logs, num_lines=100)) if static_logs is None else static_logs
        crash_handler = cls.get_crash_handler(logs)
        crash_handler.send_crash_report(is_logs_checked=True, is_call_back_ok=False)

    @classmethod
    def check_extension_activation_status(cls, status_to_check: list = ["activated enabled"], timer_limit: int = 60,
                                          exit_app_after_timer: bool = True) -> list:
        timer = 0
        while timer < timer_limit:
            if timer % 15 == 0:
                logger.info(
                    f"Querying systemextensionsctl list to check if extension is activated: counter- {timer}")
            out_sys_ctl = cls.query_systemextensionsctl()
            if out_sys_ctl == b'':
                return []
            if out_sys_ctl:
                matched = [to_check for to_check in status_to_check if to_check in str(out_sys_ctl).lower()]
                if matched:
                    logger.info(f"Extension activated successfully after {timer} seconds")
                    with open(cls.debug_log_file, "a") as f:
                        f.write('\n' + "Extension activated successfully" + '\n')
                    time.sleep(3)  # Extension is not activated immediately, empirically added 3 seconds delay
                    return matched
            time.sleep(1)
            timer += 1
        logger.info(f"timer is over: {timer} seconds, status: {str(out_sys_ctl).lower()}")
        if timer == timer_limit:
            exit_app_after_timer = True
        if exit_app_after_timer:
            logger.error("Failed to activate extension, 60 seconds are over")
            cls.execute_exit_code(msg="Permission denied")
        if "activated waiting for user" in str(out_sys_ctl).lower():
            return ["activated waiting for user"]
        else:
            return []

    @classmethod
    def activate_extension(cls):
        try:
            if os.path.exists("application/activate_extension.scpt"):
                output = subprocess.check_output(["osascript", "application/activate_extension.scpt", str(cls.is_first_run)])
                return output
            else:
                crash_report = "No activate_extension.scpt, It's not possible setup.py should have packed it?"
                logger.error(crash_report)
                crash_handler = cls.get_crash_handler(crash_report)
                logger.info(f"sending crash report: {crash_report}")
                crash_handler.send_crash_report(is_logs_checked=True, is_call_back_ok=False)
        except subprocess.CalledProcessError as e:
            return e.output

    @classmethod
    def query_systemextensionsctl(cls):
        cmd_check_sys_extension = "systemextensionsctl list | grep 'com\\.casablanca'"
        try:
            cmd_check_sys_extension_out = subprocess.check_output(cmd_check_sys_extension, shell=True, stderr=subprocess.STDOUT)
            return cmd_check_sys_extension_out
        except subprocess.CalledProcessError as e:
            # In this case the command returns b'', i.e. it does not find any com.casablanca.*
            return e.output

    @classmethod
    def copy_logs(cls, debug_log_file, desktop_log_dir, persistent_dir):
        if os.path.exists(cls.desktop_log_dir):
            shutil.rmtree(cls.desktop_log_dir)
            os.mkdir(cls.desktop_log_dir)
        else:
            os.mkdir(cls.desktop_log_dir)
        shutil.copy(cls.debug_log_file, cls.desktop_log_dir)
        shutil.copytree(cls.persistent_dir, cls.desktop_log_dir, dirs_exist_ok=True)
        logger.info(f"Copied logs to Desktop: {cls.desktop_log_dir}")

    @classmethod
    def create_custom_display(cls, msg: str, title: str = "", buttons: str = '', num_buttons: int = 3, timeout: int = -1):
        if timeout == -1:
            apple_script = f'''
                    try 
                        set fileAlias to alias POSIX file "assets/Logo_Casablanca_icon_black_128.ico"
                        display dialog "{msg}" with title "{title}" buttons {buttons} default button {num_buttons} with icon fileAlias
                    on error number -128
                        return "cancelled"
                    end try
                            '''
        else:
            apple_script = f'''
                                try 
                                    set fileAlias to alias POSIX file "assets/Logo_Casablanca_icon_black_128.ico"
                                    display dialog "{msg}" with title "{title}" buttons {buttons} default button {num_buttons} with icon fileAlias giving up after {timeout}
                                on error number -128
                                    return "cancelled"
                                end try
                                        '''
        if CheckInstallErrors.get_is_started_from_app():
            if "exit" in buttons:
                icon = "stop"
            else:
                icon = "caution"
            apple_script = f'''
            tell application "Casablanca Application"
                display dialog "{msg}" with title "{title}" buttons {buttons} default button 1 with icon {icon}
            end tell
            '''

        try:
            output = subprocess.check_output(["osascript", "-e", apple_script])
            return output
        except subprocess.CalledProcessError as e:
            return e.output

    @classmethod
    def resolve_installation_errors(cls, line: str):
        if "ossystemextensionerrordomain error 10" in line.lower():
            cls.share_logs(file_path=cls.debug_log_file)
            activation_log = "persistent/activation.json"
            if os.path.exists(activation_log):
                with open(activation_log, "r+") as f:
                    number_of_failed_logins = json.load(f)
                    number_of_failed_logins["count"] += 1
                    f.seek(0)
                    json_ = json.dumps(number_of_failed_logins, indent=4, sort_keys=True)
                    f.write(json_)
            else:
                number_of_failed_logins = {"count": 0}
            logger.error(f"OSSystemExtensionErrorDomain error 10 found in DebugLog {line}, trying to resolve")

            if number_of_failed_logins['count'] == 0:
                display_cmd_out = cls.create_custom_display(msg=cls.PRIMARY_MSG,
                                                  title="Casablanca Application requires additional permissions",
                                                  buttons='["Cancel", "Exit"]', num_buttons=2)
                with open(activation_log, "w+") as f:
                    json_ = json.dumps(number_of_failed_logins, indent=4, sort_keys=True)
                    f.write(json_)
            else:
                display_cmd_out = cls.create_custom_display(msg=cls.SECONDARY_MSG,
                                                  title="Casablanca Application requires additional permissions",
                                                  buttons='["Cancel", "Continue"]', num_buttons=2)

            if display_cmd_out != b"" and b"cancelled" in display_cmd_out.lower():
                logger.error(f"Cancelled by user: {display_cmd_out}, Exiting the application")
                cls.execute_exit_code()

            if b"exit" in display_cmd_out.lower():
                cls.execute_exit_code()

            elif b"continue" in display_cmd_out.lower():
                cls.activate_extension()
                activation_status = cls.check_extension_activation_status(
                    ["activated enabled", "activated waiting for user"], timer_limit=60,
                    exit_app_after_timer=False)
                if "activated enabled" in activation_status:
                    logger.info("Extension activated successfully")
                    return
                elif "activated waiting for user" in activation_status:
                    # try once again to activate extension
                    cls.activate_extension()
                    activation_status = cls.check_extension_activation_status(["activated waiting for user"],
                                                                              timer_limit=60,
                                                                              exit_app_after_timer=False)
                    if "activated enabled" in activation_status:
                        logger.info("Extension activated successfully")
                        return
                else:
                    last_debug_log = cls.read_last_lines(cls.debug_log_file, num_lines=1)
                    if "ossystemextensionerrordomain error" in line.lower():
                        logger.error(f"Error in activating extension: {last_debug_log}")
                        cls.create_custom_display(msg=cls.PRIMARY_MSG,
                                                  title="Casablanca Application requires additional permissions",
                                                  buttons='["Cancel", "Exit"]', num_buttons=2)
                        cls.execute_exit_code(msg="Exiting please contact your IT ADMIN")
        elif "failed with error" in line.lower():
            cls.share_logs(file_path=cls.debug_log_file)
            out = cls.create_custom_display(
                msg="There is an error during installation, please send the logs to support@casablanca.ai",
                title="Unknown Error!",
                buttons='["OK", "Exit"]', num_buttons=2)
            sys.exit(1)

    @classmethod
    def check_casablanca_permission(cls):
        out_sys_ctl = cls.query_systemextensionsctl()
        if out_sys_ctl and b"activated enabled" not in out_sys_ctl.lower():
            logger.error(
                f"Camera extension blocked: {str(out_sys_ctl).lower()}")
            cls.share_logs(static_logs=f"Activating Extension | Camera extension blocked: {str(out_sys_ctl).lower()} ")
            logger.info("Activating Extension")
            cmd_sys_extension_out = cls.activate_extension()
            if b"error" in cmd_sys_extension_out.lower():
                logger.error(f"Error while activating extension: {cmd_sys_extension_out}")
                cls.create_custom_display(
                    msg="Error while activating extension, please contact Casablanca support: support@casablanca.ai",
                    title="Error!", buttons='["OK"]', num_buttons=1)

            else:
                '''
                Check every 1 second if the extension is activated. 
                After 60 seconds exit the app if user is unable to grant permission
                '''
                logger.info(f"log from applescript: {cmd_sys_extension_out}")  # The log lines from apple script is being returned in
                cls.check_extension_activation_status()

    @classmethod
    def read_last_lines(cls, file_path, num_lines=1):
        with open(file_path, "r") as file:
            lines = file.readlines()
            return lines[-num_lines:]

    @classmethod
    def pre_execution_error_checks(cls, num_lines: int = 1):
        if sys.platform != "darwin":
            return
        if os.path.exists(cls.debug_log_file):
            read_log_lines = cls.read_last_lines(cls.debug_log_file, num_lines)
            for line in read_log_lines:
                cls.resolve_installation_errors(line)
        cls.check_casablanca_permission()

    @classmethod
    def display_os_update_warning(cls):
        if sys.platform != "darwin":
            return
        display_min_version = version.parse("15.0")
        display_max_version = version.parse("15.4")
        current_mac_os_version = version.parse(platform.mac_ver()[0])

        msg = f"Our models run much faster on macOS {str(display_max_version)} and above.\n\nTo have a smooth experience with our app, please update your macOS to {str(display_max_version)}."
        title = f"Update your macOS!"
        buttons = '["OK"]'
        num_buttons = 1
        if display_min_version <= current_mac_os_version < display_max_version:
            cls.create_custom_display(msg,title=title,buttons=buttons,num_buttons=num_buttons, timeout=20)
        return


