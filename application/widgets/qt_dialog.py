import logging

from PyQt5 import QtGui
from application.api import API
from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtWidgets import QFrame, QGroupBox, QVBoxLayout, QHBoxLayout, QSizePolicy

from application import utils
from application.feedback import Feedback
from application.mixpanel_integration import MixpanelTracker, MixpanelQDialog
from application.widgets.qt_widgets import StarRatingBar

logger = logging.getLogger(__name__)


class FeedbackDialog(MixpanelQDialog):
    toasted_message = pyqtSignal(str)

    def __init__(self, user_id: str, version: str, parent=None, mixpanel_tracker: MixpanelTracker = None,
                 mixpanel_close_event_name: str = "Closed feedback menu", mixpanel_close_event_data={}):
        super().__init__(parent=parent, mixpanel_tracker=mixpanel_tracker,
                         mixpanel_close_event_name=mixpanel_close_event_name,
                         mixpanel_close_event_data=mixpanel_close_event_data)
        self.user_id = user_id
        self.version = version
        self.main_layout = QVBoxLayout()
        self.main_layout.addStretch(1)
        self.setWindowFlag(Qt.WindowMinimizeButtonHint, True)
        self.setWindowTitle("Give Feedback")

        self.heading = utils.RLabel("Please Rate Your Experience: From 0 (poor) to 5 (excellent)")
        heading_font = QtGui.QFont()
        self.heading.setFont(heading_font)
        self.heading.setAlignment(Qt.AlignCenter)
        self.main_layout.addWidget(self.heading)

        self.rating_bar = StarRatingBar()
        rating_row = QHBoxLayout()
        rating_row.addStretch()
        rating_row.addWidget(self.rating_bar)
        rating_row.addStretch()
        self.main_layout.addLayout(rating_row)

        self.description = utils.RLabel("Got feedback? Your insights are crucial to us!")
        self.description.setAlignment(Qt.AlignCenter)
        self.main_layout.addWidget(self.description)

        textbox_layout = QHBoxLayout()
        textbox_layout.setContentsMargins(50, 20, 50, 0)
        self.textbox = utils.RTextEdit(self)
        self.textbox.setPlaceholderText("Write your comment")
        self.textbox.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.textbox.setGeometry(50, 50, 300, 200)
        self.textbox.setStyleSheet("border: 1px solid; border-radius:10px; ")
        textbox_layout.addWidget(self.textbox)
        self.main_layout.addLayout(textbox_layout)
        self.main_layout.addWidget(self.textbox)

        self.send_button = utils.RButton("Submit Feedback", self)
        self.send_button.clicked.connect(self.send_feedback)
        submit_button_layout = QHBoxLayout()
        submit_button_layout.addStretch()
        submit_button_layout.addWidget(self.send_button)
        submit_button_layout.addStretch()
        self.main_layout.addLayout(submit_button_layout)
        self.main_layout.addStretch(2)

        self.setLayout(self.main_layout)

    def send_feedback(self, ):
        feedback = self.textbox.toPlainText()
        if self.rating_bar.rating is None:
            self.toasted_message.emit("Please select a rating first")
        elif not feedback:
            self.toasted_message.emit("Can not send empty feedback")
        elif feedback and len(feedback) < 10:
            self.toasted_message.emit("Feedback should be more than 10 characters")
        else:
            bug_report_sent = Feedback.send_feedback(
                user_id=self.user_id, feedback_text=feedback, rating=self.rating_bar.rating, version=self.version)
            if bug_report_sent:
                self.toasted_message.emit("Thank you for submitting your feedback! It's on the way...")
            else:
                self.toasted_message.emit("Unable to submit the feedback. Please check your internet connection!")
            self.close()

class InsightsModal(MixpanelQDialog):
    def __init__(self, parent=None, mixpanel_tracker: MixpanelTracker = None,
                 mixpanel_close_event_name: str = "Closed insights menu", mixpanel_close_event_data={}):
        super().__init__(parent=parent, mixpanel_tracker=mixpanel_tracker,
                         mixpanel_close_event_name=mixpanel_close_event_name,
                         mixpanel_close_event_data=mixpanel_close_event_data)
        self.setup_ui()
        self.update_insights()
        self.adjust_size_to_screen()

    def setup_ui(self):
        self.setWindowTitle("Usage Insights")
        self.setWindowIcon(QtGui.QIcon('assets/Logo_Casablanca_icon_black_128.png'))
        self.setWindowFlag(Qt.WindowMinimizeButtonHint, True)
        self.layout = QVBoxLayout()
        self.setup_header()
        self.setup_separator()
        self.setup_insights()
        self.setLayout(self.layout)

    def setup_header(self):
        header_layout = QHBoxLayout()
        title = utils.RLabel(f"Your usage insights!", font_size=20)
        header_layout.addWidget(title)
        header_layout.addStretch()

        self.timeframe_dropdown = utils.RCombo(font_size = 20)
        self.timeframe_dropdown.addItems(["Last 7 Days", "Last 30 Days"])
        self.timeframe_dropdown.setCurrentIndex(0)
        self.timeframe_dropdown.setCursor(Qt.PointingHandCursor)
        self.timeframe_dropdown.view().setCursor(Qt.PointingHandCursor)
        self.timeframe_dropdown.currentIndexChanged.connect(self.update_insights)
        header_layout.addWidget(self.timeframe_dropdown)
        self.layout.addLayout(header_layout)

    def setup_separator(self):
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        line.setStyleSheet("background-color: #d3d3d3;")
        self.layout.addWidget(line)

    def setup_insights(self):
        self.insights_labels = {
            "video_call_count": {"value": utils.RLabel(font_size = 25), "trend": utils.RLabel()},
            "average_call_duration": {"value": utils.RLabel(font_size = 25), "trend": utils.RLabel()},
        }
        self.setup_insight_box(
            "Number of meetings with Casablanca",
            self.insights_labels["video_call_count"]["value"],
            self.insights_labels["video_call_count"]["trend"]
        )
        self.setup_insight_box(
            "Average Call Duration",
            self.insights_labels["average_call_duration"]["value"],
            self.insights_labels["average_call_duration"]["trend"]
        )

    def setup_insight_box(self, title, value_label, trend_label):
        insight_box = QGroupBox(title)
        insight_box.setStyleSheet("""
            QGroupBox {
                border: 1px solid #ccc;
                border-radius: 15px;
                margin: 5px;
                padding: 5px;
            }
        """)
        layout = QVBoxLayout()
        value_layout = QHBoxLayout()
        value_layout.addWidget(value_label)
        value_layout.addStretch()
        value_layout.addWidget(trend_label)
        layout.addLayout(value_layout)
        value_label.setStyleSheet("font-weight: bold; margin-top: 15px;")
        insight_box.setLayout(layout)
        self.layout.addWidget(insight_box)

    def update_insights(self):
        target_timeframe = self.timeframe_dropdown.currentText()
        n_last_days = ''.join(filter(str.isdigit, target_timeframe))
        if not n_last_days:
            self.set_no_data_state()
            return
        usage_data = API.fetch_report(n_last_days)
        if not usage_data:
            self.set_no_data_state()
            return
        self.update_insight_value(
            "video_call_count",
            usage_data.get("total_count_call", 0),
            usage_data.get("total_count_call_increase", 0))

        def formatted_duration(seconds):
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            return f"{hours}h {minutes}min"
        self.update_insight_value(
            "average_call_duration",
            formatted_duration(usage_data.get('average_call_duration', 0)),
            usage_data.get("average_call_duration_increase", 0))

    def set_no_data_state(self):
        self.update_insight_value("video_call_count", 0, 0)
        self.update_insight_value("average_call_duration", "0h 0min", 0)

    def update_insight_value(self, key, value, trend_value):
        self.insights_labels[key]["value"].setText(f"<b>{value}</b>")
        if trend_value is None:
            self.insights_labels[key]["trend"].setText("")
            self.insights_labels[key]["trend"].setStyleSheet("")
        else:
            self.insights_labels[key]["trend"].setText(f"{'+' if trend_value >= 0 else ''}{trend_value}%")
            self.insights_labels[key]["trend"].setStyleSheet(f"color: {'green' if trend_value >= 0 else 'red'}")

    def adjust_size_to_screen(self):
        screen = QtGui.QGuiApplication.primaryScreen().availableGeometry()
        self.resize(int(screen.width() * 0.25), int(screen.height() * 0.25))
        self.setMinimumSize(800, 400)
        self.setMaximumSize(int(screen.width() * 0.9), int(screen.height() * 0.9))
        self.move(int((screen.width() - self.width()) / 2), int((screen.height() - self.height()) / 2))
