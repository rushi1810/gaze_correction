from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout

from PyQt5.QtCore import Qt

from application import utils
from application.api import API
from application.diagnostic import SessionDiagnostics
from application.settings import Settings
from application.windows.casablanca_window import CasablancaWindow

import webbrowser

class AccountExpiredWindow(CasablancaWindow):
    def __init__(
            self, app: QApplication, settings: Settings,
            session_diagnostic: SessionDiagnostics, developer_mode: bool = False):
        super().__init__(app=app, settings=settings, developer_mode=developer_mode)
        central_widget = QWidget()
        layout = QVBoxLayout(central_widget)
        self.session_diagnostic = session_diagnostic
        self.setWindowFlag(Qt.WindowMinimizeButtonHint)
        self.setWindowFlag(Qt.WindowMaximizeButtonHint, False)
        self.crashed_label = utils.RLabel("You have been using Casablanca for the last 3 months.\n"
                                          "If you managed to achieve successes we are looking forward to your feedback.\n"
                                          "In case you want to continue using Casablanca, you can buy your license here")
        self.crashed_label.setAlignment(Qt.AlignHCenter)
        layout.addWidget(self.crashed_label)
        self.button_row = QHBoxLayout()
        self.get_pro_license_button = utils.RButton("Get Casablanca Premium")
        self.get_pro_license_button.clicked.connect(
            lambda: webbrowser.open_new("https://www.casablanca.ai/pricing"))
        self.button_row.addWidget(self.get_pro_license_button)

        def log_out():
            self.hide()
            self.session_diagnostic.end_session()
            API.log_out()
            self.app.exit(106)

        self.logout_button = utils.RButton("Log out")
        self.logout_button.clicked.connect(log_out)
        self.button_row.addWidget(self.logout_button)
        layout.addLayout(self.button_row)

        self.setCentralWidget(central_widget)
        self.set_dark_light_mode_according_to_state()
        self.show()
