import os
import sys
import requests
from requests.exceptions import ConnectionError

from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout
from PyQt5.QtGui import QIcon

from application.feedback import Feedback
from application import utils


import logging

logger = logging.getLogger(__name__)


class CrashReportSender:
    persistent_dir = "persistent"
    appended_logs = ""
    crash_report = None
    user_id = None

    def __init__(self, crash_report, user_id):
        CrashReportSender.crash_report = crash_report
        CrashReportSender.user_id = user_id
        CrashReportSender.appended_logs = ""

    @classmethod
    def read_logs(cls, log_file: str) -> str:
        try:
            num_last_lines = 50
            with open(log_file, "r") as file:
                read_lines = file.readlines()
                joined_log_lines = " ".join(read_lines[-num_last_lines:])
                return joined_log_lines
        except FileNotFoundError:
            logger.error(f"{log_file} not found")
            return ""

    @classmethod
    def get_all_logs(cls):
        logs = [os.path.abspath(os.path.join(cls.persistent_dir, file)) for file in os.listdir(cls.persistent_dir)
                if ".log" in file]
        if sys.platform == "darwin":
            logs.append(os.path.abspath(os.path.join(os.getcwd(), "../DebugLog.txt")))
        for log in logs:
            cls.appended_logs += f"\n{'-' * 25}{log}{'-' * 25}\n\n{cls.read_logs(log)}"
        return cls.appended_logs

    @classmethod
    def send_crash_report(cls, is_logs_checked: bool = False, is_call_back_ok: bool = False) -> bool:
        form_url = "https://docs.google.com/forms/d/e/1FAIpQLSemUH7ZkbWgSEjaBf_MQKOros830-qHLInMB6lymI569sAqHg/formResponse"
        cls.appended_logs = cls.get_all_logs() if is_logs_checked else cls.appended_logs
        form_data = {
            "entry.1198905657": cls.crash_report,
            "entry.72824854": Feedback.app_version,
            "entry.136663075": cls.user_id,
            "entry.815749515": cls.appended_logs,
            "entry.1010462108": is_call_back_ok}
        try:
            post_response_code = requests.post(form_url, data=form_data).status_code
            if post_response_code != 200:
                logger.error(f"Failed to send crash report due the status code {post_response_code}")
                return False
            cls.appended_logs = ""
            return True

        except ConnectionError:
            logger.error("Failed to send crash report")
            return False


class AppCrashDialog(utils.RDialog):

    def __init__(self, crash_report, user_id, restart_app: bool = False):
        super().__init__()
        self.crash_report_handle = CrashReportSender(crash_report, user_id)
        self.send_crash_report = self.crash_report_handle.send_crash_report
        self.restart_app = restart_app
        self.initUI()

    def initUI(self):
        self.setWindowIcon(QIcon('assets/Logo_Casablanca_icon_black_128.ico'))
        layout = QVBoxLayout()

        crash_message = utils.RLabel(
            'It looks like the Casablanca App encountered an issue. '
            'Would you like to help us fix it by sending a crash report?',
            self)
        layout.addWidget(crash_message)
        layout.addSpacing(20)

        if self.restart_app:
            restart_note = utils.RLabel('Casablanca will restart after you close this window.', self)
            layout.addWidget(restart_note)
            layout.addSpacing(20)

        self.check_send_logs = utils.RCheckButton('Send logs to improve Casablanca', self, font_size=18)
        self.check_send_logs.setChecked(True)
        self.check_send_logs.stateChanged.connect(self.check_state_changed)
        layout.addWidget(self.check_send_logs)
        layout.addSpacing(20)

        self.check_contact_me = utils.RCheckButton('Get contacted by Casablanca support, to help with this issue', self, font_size=18)
        self.check_contact_me.setChecked(True)
        self.check_contact_me.stateChanged.connect(self.check_state_changed)
        layout.addWidget(self.check_contact_me)
        layout.addSpacing(20)
        if self.crash_report_handle.user_id == "Unknown":
            self.check_contact_me.hide()

        submit_button_row = QHBoxLayout()
        submit_button_row.addSpacing(10)

        self.button_submit = utils.RButton('Submit', self)
        self.button_submit.setEnabled(True)
        self.button_submit.clicked.connect(self.submit)
        submit_button_row.addWidget(self.button_submit)
        submit_button_row.addSpacing(5)

        self.button_cancel = utils.RButton('Cancel', self)
        self.button_cancel.clicked.connect(self.cancel)
        submit_button_row.addWidget(self.button_cancel)
        submit_button_row.addSpacing(10)

        layout.addLayout(submit_button_row)

        self.setLayout(layout)
        self.setWindowTitle('Casablanca App Crashed!')

    def closeEvent(self, event):
        if event.spontaneous():
            self.send_crash_report()
        super().closeEvent(event)
        if self.restart_app:
            self.restart_casablanca()

    def check_state_changed(self):
        any_checked = self.check_send_logs.isChecked() or self.check_contact_me.isChecked()
        self.button_submit.setEnabled(any_checked)

    def submit(self):
        is_logs_checked = self.check_send_logs.isChecked()
        is_contact_me_checked = self.check_contact_me.isChecked()

        self.send_crash_report(is_logs_checked, is_contact_me_checked)
        self.close()

    def cancel(self):
        self.send_crash_report()
        self.close()

    @classmethod
    def read_logs(cls, log_file: str) -> str:
        try:
            num_last_lines = 100
            with open(log_file, "r") as file:
                read_lines = file.readlines()
                joined_log_lines = " ".join(read_lines[-num_last_lines:])
                return joined_log_lines
        except FileNotFoundError:
            logger.error(f"{log_file} not found")
            return ""

    def get_all_logs(self):
        logs = [os.path.abspath(os.path.join(self.persistent_dir, file)) for file in os.listdir(self.persistent_dir)
                if ".log" in file]
        if sys.platform == "darwin":
            logs.append(os.path.abspath(os.path.join(os.getcwd(), "../DebugLog.txt")))
        for log in logs:
            self.appended_logs += f"\n{'-'*25}{log}{'-'*25}\n\n{self.read_logs(log)}"
        return self.appended_logs

    def send_crash_report(self, is_logs_checked: bool = False, is_call_back_ok: bool = False) -> bool:
        form_url = "https://docs.google.com/forms/d/e/1FAIpQLSemUH7ZkbWgSEjaBf_MQKOros830-qHLInMB6lymI569sAqHg/formResponse"
        self.appended_logs = self.get_all_logs() if is_logs_checked else self.appended_logs
        form_data = {
            "entry.1198905657": self.crash_report,
            "entry.72824854": Feedback.app_version,
            "entry.136663075": self.user_id,
            "entry.815749515": self.appended_logs,
            "entry.1010462108": is_call_back_ok}
        try:
            if requests.post(form_url, data=form_data).status_code != 200:
                logger.error("Failed to send crash report")
                return False
            self.appended_logs = ""
            return True

        except ConnectionError:
            logger.error("Failed to send crash report")
            return False

    @classmethod
    def restart_casablanca(cls):
        is_mac = sys.platform == "darwin"
        if is_mac:
            try:
                with open("/Library/Application Support/Casablanca/isRestart.txt", "w") as file:
                    file.write("true")
            except (FileNotFoundError, PermissionError) as e:
                logger.error(f"Failed to access isRestart file: {e}")
        else:
            import subprocess
            process = subprocess.Popen([".\\Casablanca.lnk"], shell=True)
            process.wait()
