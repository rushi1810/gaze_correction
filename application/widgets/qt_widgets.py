import os
import sys
import time
import webbrowser
from typing import Optional, List, Callable, Dict

import moviepy.editor as mp
from PyQt5.QtCore import Qt, pyqtSignal, QPropertyAnimation, QTimer, QEasingCurve, QPoint, \
    QSize, QPauseAnimation, QSequentialAnimationGroup, QParallelAnimationGroup, QUrl, \
    QEvent
from PyQt5.QtGui import QPainter, QColor, QBrush, QPen, QPixmap, QIcon, QCursor, QMouseEvent, QShowEvent, QPaintEvent, \
    QImage, QKeySequence
from PyQt5.QtMultimedia import QCameraInfo, QMediaPlayer, QMediaContent
from PyQt5.QtWidgets import QMessageBox, QWidget, QVBoxLayout, QApplication, QHBoxLayout, QSlider, QStyle, \
    QToolButton, QToolTip, QDialog, QScrollArea, QAction, QPushButton, QCheckBox, QRadioButton

from application import utils
from application.api import API
from application.feedback import Feedback
from application.mixpanel_integration import MixpanelTracker, MixpanelQToolButton, MixpanelQLabel, \
    MixpanelQDialog
from application.threads.calibration_thread import CalibrationThread


class MouseDraggingRecordingLabel(MixpanelQLabel):
    gaze_adjusted = pyqtSignal(float, float)
    head_adjusted = pyqtSignal(float, float)

    def __init__(
            self, parent=None, mixpanel_tracker: MixpanelTracker = None, *, is_accepting_input: bool = True):
        super(MouseDraggingRecordingLabel, self).__init__(parent=parent, mixpanel_tracker=mixpanel_tracker)
        self.left_mouse_position = None
        self.right_mouse_position = None
        self.left_mouse_pressed_start_time = None
        self.right_mouse_pressed_start_time = None
        self.move_gaze = QPixmap("assets/Icon_MoveGaze.png").scaled(40, 40)
        self.move_gaze_cursor = QCursor(self.move_gaze, hotX=-20, hotY=-20)
        self.move_head = QPixmap("assets/Icon_MoveHead.png").scaled(40, 40)
        self.move_head_cursor = QCursor(self.move_head, hotX=-20, hotY=-20)
        self.move_gaze_and_head = QPixmap("assets/Icon_MoveGazeAndHead.png").scaled(76, 40)
        self.move_gaze_and_head_cursor = QCursor(self.move_gaze_and_head, hotX=-38, hotY=-20)
        self.operation_mode_indicator = utils.RLabel(self)
        self.is_mac = True if sys.platform == "darwin" else False
        self.is_accepting_input = is_accepting_input

    def mousePressEvent(self, event: QMouseEvent) -> None:
        super().mousePressEvent(event)
        if not self.is_accepting_input:
            return
        if event.button() == Qt.LeftButton:
            self.left_mouse_position = event.pos()
            self.left_mouse_pressed_start_time = time.time()
        elif event.button() == Qt.RightButton:
            self.right_mouse_position = event.pos()
            self.right_mouse_pressed_start_time = time.time()
        if self.is_mac:
            self.set_appropriate_cursor_mac(event)
        else:
            self.set_appropriate_cursor_windows(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if not self.is_accepting_input:
            return
        if event.buttons() & Qt.LeftButton:
            try:
                delta_x = (event.pos() - self.left_mouse_position).x() * 0.01
                delta_y = -(event.pos() - self.left_mouse_position).y() * 0.01
                self.gaze_adjusted.emit(delta_x, delta_y)
            except TypeError:
                pass
            self.left_mouse_position = event.pos()
        if event.buttons() & Qt.RightButton:
            try:
                delta_x = (event.pos() - self.right_mouse_position).x() * 0.01
                delta_y = -(event.pos() - self.right_mouse_position).y() * 0.01
                self.head_adjusted.emit(delta_x, delta_y)
            except TypeError:
                pass
            self.right_mouse_position = event.pos()
        if self.is_mac:
            self.set_appropriate_cursor_mac(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if not self.is_accepting_input:
            return
        if event.button() == Qt.LeftButton:
            self.left_mouse_position = None
            if self.left_mouse_pressed_start_time is not None:
                adjustment_duration = time.time() - self.left_mouse_pressed_start_time
                self.left_mouse_pressed_start_time = None
            else:
                adjustment_duration = 0
            self.mixpanel_tracker.track(event_name="Adjusted gaze", properties={"duration": adjustment_duration})
        elif event.button() == Qt.RightButton:
            self.right_mouse_position = None
            if self.right_mouse_pressed_start_time is not None:
                adjustment_duration = time.time() - self.right_mouse_pressed_start_time
                self.right_mouse_pressed_start_time = None
            else:
                adjustment_duration = 0
            self.mixpanel_tracker.track(event_name="Adjusted head", properties={"duration": adjustment_duration})
        if self.is_mac:
            self.set_appropriate_cursor_mac(event)
        else:
            self.set_appropriate_cursor_windows(event)

    def set_appropriate_cursor_windows(self, event: QMouseEvent) -> None:
        if event.buttons() == Qt.LeftButton | Qt.RightButton:
            self.setCursor(self.move_gaze_and_head_cursor)
        elif event.buttons() == Qt.LeftButton:
            self.setCursor(self.move_gaze_cursor)
        elif event.buttons() == Qt.RightButton:
            self.setCursor(self.move_head_cursor)
        else:
            self.setCursor(Qt.ArrowCursor)

    def set_appropriate_cursor_mac(self, event: QMouseEvent) -> None:
        if event.buttons() == Qt.LeftButton | Qt.RightButton:
            self.operation_mode_indicator.setPixmap(self.move_gaze_and_head)
            self.operation_mode_indicator.move(event.pos().x() + 10, event.pos().y() + 10)
            self.operation_mode_indicator.show()
        elif event.buttons() == Qt.LeftButton:
            self.operation_mode_indicator.setPixmap(self.move_gaze)
            self.operation_mode_indicator.move(event.pos().x() + 10, event.pos().y() + 10)
            self.operation_mode_indicator.show()
        elif event.buttons() == Qt.RightButton:
            self.operation_mode_indicator.setPixmap(self.move_head)
            self.operation_mode_indicator.move(event.pos().x() + 10, event.pos().y() + 10)
            self.operation_mode_indicator.show()
        else:
            self.operation_mode_indicator.hide()

class CalibrationWindow(MixpanelQDialog):
    def __init__(
            self,
            parent,
            settings,
            main_algo_config,
            developer_mode,
            mixpanel_tracker,
            input_roi,
        ):
        super().__init__(parent=parent, mixpanel_tracker=mixpanel_tracker)
        self._settings = settings
        self.calibration = self._settings.setup_calibrations.get(
            self._settings.camera_name, {"x": 0.0, "y": 0.0}).copy()
        self.calibration_thread = CalibrationThread(
            settings=settings, main_algo_config=main_algo_config, developer_mode=developer_mode)
        self.calibration_thread.start()
        self.setWindowTitle("Calibrate Eye Contact")
        self.setWindowModality(Qt.ApplicationModal)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.layout = QVBoxLayout()
        self.setLayout(self.layout)

        self.instruction_label = utils.RLabel()
        self.instruction_label.setWordWrap(True)
        self.layout.addWidget(self.instruction_label)

        self.output_image = MouseDraggingRecordingLabel(mixpanel_tracker=mixpanel_tracker)
        self.output_image.gaze_adjusted.connect(self.adjust_gaze)
        self.output_image.setStyleSheet("background: transparent;")
        self.layout.addWidget(self.output_image, alignment=Qt.AlignCenter)

        self.button_layout = QHBoxLayout()
        self.layout.addLayout(self.button_layout)

        self.perfect_button = utils.RButton("Save calibration")
        def save_and_close():
            self.update_setup_calibration(self.calibration)
            self.close()
        self.perfect_button.clicked.connect(save_and_close)
        self.button_layout.addWidget(self.perfect_button)

        self.reset_button = utils.RButton("Reset calibration to default")
        def reset():
            self.calibration = {"x": 0.0, "y": 0.0}
            self.update_setup_calibration(self.calibration)
            self.set_images()
        self.reset_button.clicked.connect(reset)
        self.button_layout.addWidget(self.reset_button)

        self.reload_image_button = utils.RButton("Reload image")
        def reload_images():
            self.mixpanel_tracker.track(event_name="Calibration setup reloaded")
            self.input_roi = self.parent().latest_cropped_roi[...]
            self.start_setup()
        self.reload_image_button.clicked.connect(reload_images)
        self.button_layout.addWidget(self.reload_image_button)

        self.cancel_button = utils.RButton("Cancel")
        self.cancel_button.clicked.connect(self.close)
        self.button_layout.addWidget(self.cancel_button)

        self.input_roi = input_roi
        self.mixpanel_tracker.track(event_name="Calibration setup started")
        self.start_setup()


    def start_setup(self):
        self.perfect_button.show()
        self.reset_button.show()
        self.reload_image_button.hide()
        self.instruction_label.setText("Adjust your gaze by left-clicking and dragging on your picture "
                                       "until you feel there is eye contact.")
        if self.input_roi is None:
            self.instruction_label.setText("We couldn't load an image. Please ensure your camera is working.")
            self.perfect_button.hide()
            self.reset_button.hide()
            self.reload_image_button.show()
            self.mixpanel_tracker.track(event_name="Calibration setup failed",
                                        properties={"reason": "No frame available"})
            return
        self.calibration_thread.send_image_data(self.input_roi, [self.calibration["x"], self.calibration["y"]])
        while self.calibration_thread.result is None:
            time.sleep(0.1)
        _, _, head_in_roi_confidence, is_corrected, self.base_angles = self.calibration_thread.result
        self.calibration_thread.result = None
        if head_in_roi_confidence < 0.2:
            self.instruction_label.setText("We couldn't make out a face in your image. Please make sure "
                                           "to uncover your camera and position yourself in front of it.")
            self.perfect_button.hide()
            self.reset_button.hide()
            self.reload_image_button.show()
            self.mixpanel_tracker.track(event_name="Calibration setup failed",
                                        properties={"reason": "Face not found"})
            return
        if not is_corrected:
            self.instruction_label.setText("It seems like your gaze or head is diverted too far from the camera, for us to correct it."
                                           " If this is representative of your usual setup, "
                                           "consider activating the manual correction in the 'More Settings'-Menu")
            self.perfect_button.hide()
            self.reset_button.hide()
            self.reload_image_button.show()
            self.mixpanel_tracker.track(event_name="Calibration setup failed",
                                        properties={"reason": "Gaze angles too high"})
            return
        self.set_images()

    def set_images(self):
        self.calibration_thread.send_image_data(
            self.input_roi, [self.calibration["x"], self.calibration["y"]], base_angles=self.base_angles)
        while self.calibration_thread.result is None:
            time.sleep(0.1)
        input_roi, output_roi, _, _, _ = self.calibration_thread.result
        self.calibration_thread.result = None
        pixmap_height = int(self.parent().app.desktop().screenGeometry().height() * 0.5)
        output_pixmap = QPixmap(QImage(output_roi, 256, 256, QImage.Format_RGB888).mirrored(True, False)
                                ).scaled(pixmap_height, pixmap_height, Qt.KeepAspectRatio)
        self.output_image.setPixmap(output_pixmap)

    def adjust_gaze(self, delta_x: float, delta_y: float) -> None:
        self.calibration["y"] = min(1.0, max(-1.0, self.calibration["y"] - delta_y))
        self.calibration["x"] = min(1.0, max(-1.0, self.calibration["x"] - delta_x))
        self.set_images()

    def update_setup_calibration(self, calibration):
        self._settings.setup_calibrations[self._settings.camera_name] = calibration.copy()
        self.mixpanel_tracker.track(
            event_name="Completed manual after-calibration",
            properties={"calibration": calibration})
        self._settings.save()

    def closeEvent(self, event):
        super().closeEvent(event)
        self.calibration_thread.suspended = True

class ToastMessage(QWidget):
    def __init__(self, text: str, duration_ms: int = None, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.text = text
        self.message_label = utils.RLabel(self.text)
        self.message_label.setAlignment(Qt.AlignCenter)
        self.message_label.setStyleSheet("color: #000; font-size: 16px;")

        layout = QVBoxLayout()
        layout.addWidget(self.message_label)
        self.setLayout(layout)

        if duration_ms is not None:
            self.duration_ms = duration_ms
        else:
            min_duration = 3000
            max_duration = 14000
            ms_required_per_character = 100
            self.duration_ms = min(max(len(text) * ms_required_per_character, min_duration), max_duration)

        opacity_animation = QSequentialAnimationGroup(self)

        fade_in_animation = QPropertyAnimation(self, b"windowOpacity")
        fade_in_animation.setDuration(500)
        fade_in_animation.setStartValue(0.0)
        fade_in_animation.setEndValue(1.0)
        fade_in_animation.setEasingCurve(QEasingCurve.InQuad)
        opacity_animation.addAnimation(fade_in_animation)

        pause_animation = QPauseAnimation(self)
        pause_animation.setDuration(self.duration_ms)
        opacity_animation.addAnimation(pause_animation)

        fade_out_animation = QPropertyAnimation(self, b"windowOpacity")
        fade_out_animation.setDuration(1000)
        fade_out_animation.setStartValue(1.0)
        fade_out_animation.setEndValue(0.0)
        fade_out_animation.setEasingCurve(QEasingCurve.OutQuad)
        opacity_animation.addAnimation(fade_out_animation)

        position_animation = QPropertyAnimation(self, b"pos")
        position_animation.setDuration(500)
        screen_center_x = (QApplication.desktop().screenGeometry().width() - self.width()) // 2
        position_animation.setStartValue(QPoint(screen_center_x, 0))
        position_animation.setEndValue(QPoint(screen_center_x, 100))
        position_animation.setEasingCurve(QEasingCurve.OutQuad)
        self.setMaximumSize(0, 0)

        self.full_animation = QParallelAnimationGroup(self)
        self.full_animation.addAnimation(opacity_animation)
        self.full_animation.addAnimation(position_animation)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self.full_animation.start()
        self.full_animation.finished.connect(self.close)

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QBrush(QColor(69, 170, 242, 255)))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(self.rect(), 10, 10)


class ToggleSwitch(QWidget):
    toggled = pyqtSignal(bool)

    def __init__(self, parent=None):
        super(ToggleSwitch, self).__init__(parent)
        self.setFixedSize(60, 30)
        self.button_checked = True

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QBrush(QColor(206, 206, 206)))
        painter.setPen(QPen(QColor(206, 206, 206), 0.5))
        painter.drawRoundedRect(0, 0, 60, 30, 15, 15)

        painter.setBrush(QBrush(QColor(65, 65, 65)))
        painter.setPen(QPen(QColor(65, 65, 65), 1.5))
        if self.button_checked:
            painter.drawEllipse(35, 5, 20, 20)
        else:
            painter.drawEllipse(5, 5, 20, 20)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.button_checked = not self.button_checked
            self.toggled.emit(self.button_checked)
            self.update()

    def sizeHint(self):
        return self.minimumSizeHint()


class PngButton(QPushButton):

    def __init__(
            self,
            png_file: str,
            tooltip_message: str = "",
            mixpanel_event_name: Optional[str] = None,
            mixpanel_event_data: Optional[dict] = None,
            dark_mode: bool = False,
            mixpanel_tracker: MixpanelTracker = None,
            parent=None,
            shortcut_key=None,
    ):
        super().__init__(parent=parent)
        self.mixpanel_tracker = mixpanel_tracker
        self.dark_mode = dark_mode
        shortcut_description = ''
        if shortcut_key:
            if sys.platform == "darwin":
                sequence = QKeySequence(Qt.SHIFT + Qt.ALT + shortcut_key)
                shortcut_description = f' (⌥⇧{QKeySequence(shortcut_key).toString()})'
            else:
                sequence = QKeySequence(Qt.CTRL + Qt.ALT + shortcut_key)
                shortcut_description = f' ({QKeySequence(sequence).toString()})'
            self.setShortcut(sequence)
        self.base_png_file = png_file
        self.base_tooltip_message = tooltip_message + shortcut_description
        self.base_mixpanel_event_name = mixpanel_event_name
        self.base_mixpanel_event_data = mixpanel_event_data

        self.current_png_file = self.base_png_file
        self.current_tooltip_message = self.base_tooltip_message
        self.current_mixpanel_event_name = self.base_mixpanel_event_name
        self.current_mixpanel_event_data = self.base_mixpanel_event_data

        self.current_icon = QIcon(self.current_png_file)
        self.setStyleSheet(
            """
            PngButton {
                border: none; 
                border-radius: 16px; 
                width: 32px; 
                height: 32px;
            }
            """)
        self.setIcon(self.current_icon)
        self.setIconSize(QSize(20, 20))
        self.adjust_icon_to_mode()
        self.setCursor(Qt.PointingHandCursor)

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        self.mixpanel_tracker.track(
            event_name=self.current_mixpanel_event_name,
            properties=self.current_mixpanel_event_data)

    def enterEvent(self, event) -> None:
        QToolTip.showText(QCursor.pos(), self.current_tooltip_message)

    def adjust_icon_to_mode(self, is_darkmode: Optional[bool] = None):
        if is_darkmode is not None:
            self.dark_mode = is_darkmode
        image = QImage(self.current_png_file + ("_dark" if self.dark_mode else "_light") + ".png")
        icon = QIcon(QPixmap.fromImage(image))
        self.setIcon(icon)


class DoublePngButton(PngButton):
    click_activated = pyqtSignal(bool)

    def __init__(
            self,
            png_file: str,
            alternative_png_file: str,
            tooltip_message: str = "",
            alternative_tooltip_message: str = "",
            mixpanel_event_name: Optional[str] = None,
            alternative_mixpanel_event_name: Optional[str] = None,
            mixpanel_event_data: Optional[dict] = None,
            alternative_mixpanel_event_data: Optional[dict] = None,
            dark_mode: bool = False,
            mixpanel_tracker: MixpanelTracker = None,
            activated: bool = False,
            parent=None,
            shortcut_key=None,
    ):

        super().__init__(
            png_file,
            tooltip_message,
            mixpanel_event_name,
            mixpanel_event_data,
            dark_mode,
            mixpanel_tracker,
            parent,
            shortcut_key
        )
        self.activated = activated
        self.alternative_png_file = alternative_png_file
        self.alternative_tooltip_message = alternative_tooltip_message
        self.alternative_mixpanel_event_name = alternative_mixpanel_event_name
        self.alternative_mixpanel_event_data = alternative_mixpanel_event_data
        self.refresh_icon()

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        self.activated = not self.activated
        self.click_activated.emit(self.activated)
        self.refresh_icon()

    def refresh_icon(self):
        if self.activated:
            self.current_png_file = self.alternative_png_file
            self.current_tooltip_message = self.alternative_tooltip_message
            self.current_mixpanel_event_name = self.alternative_mixpanel_event_name
            self.current_mixpanel_event_data = self.alternative_mixpanel_event_data
        else:
            self.current_png_file = self.base_png_file
            self.current_tooltip_message = self.base_tooltip_message
            self.current_mixpanel_event_name = self.base_mixpanel_event_name
            self.current_mixpanel_event_data = self.base_mixpanel_event_data
        self.adjust_icon_to_mode()

    def event(self, a0):
        if 'QShortcutEvent' in str(a0):
            self.activated = not self.activated
            self.click_activated.emit(self.activated)
            self.refresh_icon()
        return super().event(a0)


class Star(utils.RLabel):
    clicked = pyqtSignal(int)

    def __init__(self, index):
        super().__init__()
        self.index = index
        self.setPixmap(QPixmap("assets/Icon_StarOff.png"))
        self.setCursor(QCursor(Qt.PointingHandCursor))

    def enterEvent(self, event):
        self.setPixmap(QPixmap("assets/Icon_StarOn.png"))
        self.parent().turn_on_stars_until_index(self.index)

    def mousePressEvent(self, event):
        self.clicked.emit(self.index)

    def turn_on(self):
        self.setPixmap(QPixmap("assets/Icon_StarOn.png"))

    def turn_off(self):
        self.setPixmap(QPixmap("assets/Icon_StarOff.png"))


class StarRatingBar(QWidget):

    def __init__(self, star_count: int = 5, parent=None, onclick=None):
        super().__init__(parent)
        self.rating = None

        def set_rating(index: int) -> None:
            self.rating = index

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.stars = []
        for i in range(1, star_count + 1):
            star = Star(i)
            if onclick is not None:
                star.clicked.connect(onclick)
            else:
                star.clicked.connect(set_rating)
            layout.addWidget(star)
            self.stars.append(star)
        self.setLayout(layout)

    def leaveEvent(self, event):
        if self.rating is None:
            self.turn_off_all_stars()
        else:
            self.turn_on_stars_until_index(self.rating)

    def turn_off_all_stars(self):
        for star in self.stars:
            star.turn_off()

    def turn_on_stars_until_index(self, index: int) -> None:
        for i, star in enumerate(self.stars, start=1):
            if i <= index:
                star.turn_on()
            else:
                star.turn_off()


class MenuButton(utils.RMenu):
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setStyleSheet(
            """
            QMenu {
                border: 5px solid black;
                border-radius: 10px;
                outline: 0;
                margin: -5px;
                }
            """)
        self.setContentsMargins(5, 0, 0, 0)


class Selector(MixpanelQToolButton):
    def __init__(
            self, mixpanel_tracker, parent=None, mixpanel_default_event_name=None, mixpanel_activated_event_name=None):
        super().__init__(
            parent=parent, mixpanel_tracker=mixpanel_tracker,
            mixpanel_default_event_name=mixpanel_default_event_name,
            mixpanel_activated_event_data=mixpanel_activated_event_name)
        self.dark_mode = False
        self.mixpanel_tracker = mixpanel_tracker
        self.set_style()
        self.setPopupMode(QToolButton.InstantPopup)

        self.menu = MenuButton(self)
        self.setMenu(self.menu)

    def set_style(self):
        self.setStyleSheet(
            """
            QToolButton {
                    border-radius: 13px;
                    width: 40px;
                    height: 25px;
                }
            QToolButton::menu-indicator { 
                image: url(assets/Icon_DownArrow_""" + ("dark" if self.dark_mode else "light") + """.png);
                }
            """)


class CasablancaCameraSelector(Selector):
    camera_selected = pyqtSignal(str)

    def __init__(
            self,
            mixpanel_tracker,
            parent=None,
            hide_keyboard_shortcut=False
    ):
        super().__init__(
            parent=parent,
            mixpanel_tracker=mixpanel_tracker,
            mixpanel_default_event_name="Opened Choose Camera dropdown",
            mixpanel_activated_event_name="Closed Choose Camera dropdown",

        )
        self.select_camera_icon = QIcon("assets/Icon_SelectCamera")
        self.setIcon(self.select_camera_icon)
        self._hide_keyboard_shortcut = hide_keyboard_shortcut
        self.camera_action_dict = {}
        self.camera_shortcut_dict = {}
        self.init_cameras()
        self.menu.aboutToShow.connect(self.refresh_camera_dropdown)

    def enterEvent(self, event) -> None:
        QToolTip.showText(QCursor.pos(), "Select camera source")

    def init_cameras(self):
        dict_new_camera = self._get_dict_latest_camera()
        self._hide_keyboard_shortcut = self._hide_keyboard_shortcut or (len(dict_new_camera.keys()) == 1)
        for index, camera_name in enumerate(dict_new_camera.keys()):
            self.set_camera_action(camera_name, index)

    def refresh_camera_dropdown(self):
        dict_new_camera = self._get_dict_latest_camera()

        camera_added = dict_new_camera.keys() - self.camera_action_dict.keys()
        camera_removed = self.camera_action_dict.keys() - dict_new_camera.keys()
        if camera_removed:
            for camera_name in camera_removed:
                self.menu.removeAction(self.camera_action_dict[camera_name])
                self.camera_action_dict.pop(camera_name)
                self.camera_shortcut_dict.pop(camera_name)
                self.mixpanel_tracker.track(f"Camera Removed: {camera_name}")

        if camera_added:
            for camera_name in camera_added:
                self.set_camera_action(camera_name, index=-1)
                self.mixpanel_tracker.track(f"Camera Added: {camera_name}")

    def set_camera_action(self, camera_name, index):
        camera_name_action = QAction(camera_name, self, checkable=True)
        self.camera_action_dict[camera_name] = camera_name_action
        camera_name_action.triggered.connect(
            lambda checked, camera=camera_name: self.camera_selected.emit(camera))
        camera_name_action.triggered.connect(
            lambda: self.mixpanel_tracker.track(event_name="Changed camera source"))
        self.menu.addAction(camera_name_action)
        if self._hide_keyboard_shortcut:
            return
        try:
            if index == -1:
                for i in range(1, 10):
                    if i not in self.camera_shortcut_dict.values():
                        _set_shortcut_to_action_widget(camera_name_action, getattr(Qt, f'Key_{i}'))
                        self.camera_shortcut_dict[camera_name] = i
                        break
            else:
                _set_shortcut_to_action_widget(camera_name_action, getattr(Qt, f'Key_{index + 1}'))
                self.camera_shortcut_dict[camera_name] = index + 1
        except AttributeError:
            ...

    def _get_dict_latest_camera(self):
        self.available_cameras = QCameraInfo.availableCameras()
        return {
            camera.description(): camera for camera in self.available_cameras
            if "Casablanca Virtual Camera" not in camera.description()
        }

    def set_to_dark_light_mode(self, dark_mode: bool):
        self.dark_mode = dark_mode
        self.setIcon(QIcon("assets/Icon_SelectCamera" + ("_dark" if self.dark_mode else "_light") + ".png"))
        self.set_style()


class CasablancaViewSelector(Selector):
    view_selected = pyqtSignal(str)

    def __init__(
            self,
            mixpanel_tracker,
            hide_comparison_view: bool = False,
            hide_head_only_view: bool = True,
            hide_keyboard_shortcuts: bool = False,
            parent=None):
        super().__init__(
            parent=parent,
            mixpanel_tracker=mixpanel_tracker,
            mixpanel_default_event_name="Opened Choose Displayed Image dropdown",
            mixpanel_activated_event_name="Closed Choose Displayed Image dropdown",
        )

        def set_shortcuts(action_widget, shortcut):
            if hide_keyboard_shortcuts:
                return
            _set_shortcut_to_action_widget(action_widget, shortcut)

        self.icon_png = "assets/Icon_ViewCasablanca"
        self.view_casablanca_png = "assets/Icon_ViewCasablanca"
        self.view_casablanca_icon = QIcon(self.view_casablanca_png)
        self.view_original_png = "assets/Icon_ViewOriginal"
        self.view_original_icon = QIcon(self.view_original_png)
        self.view_comparison_png = "assets/Icon_ViewComparison"
        self.view_comparison_icon = QIcon(self.view_comparison_png)
        self.view_head_only_png = "assets/Icon_ViewHeadOnly"
        self.view_head_only_icon = QIcon(self.view_head_only_png)
        self._hide_keyboard_shortcuts = hide_keyboard_shortcuts,

        self.set_style()
        self.setPopupMode(QToolButton.InstantPopup)
        self.setIcon(QIcon(self.icon_png + ("_dark" if self.dark_mode else "_light") + ".png"))

        self.view_casablanca_action = QAction(self.view_casablanca_icon, "Casablanca output", self)
        self.view_casablanca_action.setProperty("file_name", self.view_casablanca_png)
        self.view_casablanca_action.triggered.connect(self.view_casablanca_clicked)
        self.menu.addAction(self.view_casablanca_action)
        set_shortcuts(self.view_casablanca_action, Qt.Key_E)

        self.view_original_action = QAction(self.view_original_icon, "Source image", self)
        self.view_original_action.setProperty("file_name", self.view_original_png)
        self.view_original_action.triggered.connect(self.view_original_clicked)
        self.menu.addAction(self.view_original_action)
        set_shortcuts(self.view_original_action, Qt.Key_O)

        if not hide_comparison_view:
            self.view_comparison_action = QAction(self.view_comparison_icon, "Comparison", self)
            self.view_comparison_action.setProperty("file_name", self.view_comparison_png)
            self.view_comparison_action.triggered.connect(self.view_comparison_clicked)
            self.menu.addAction(self.view_comparison_action)
            set_shortcuts(self.view_comparison_action, Qt.Key_B)

        if not hide_head_only_view:
            self.view_head_only_action = QAction(self.view_head_only_icon, "Zoom in on face", self)
            self.view_head_only_action.setProperty("file_name", self.view_head_only_png)
            self.view_head_only_action.triggered.connect(self.view_head_only_clicked)
            self.menu.addAction(self.view_head_only_action)

    def enterEvent(self, event) -> None:
        QToolTip.showText(QCursor.pos(), "Select view")

    def view_casablanca_clicked(self):
        self.setIcon(self.view_casablanca_action.icon())
        self.icon_png = self.view_casablanca_png
        self.mixpanel_tracker.track("Selected view: Casablanca")
        self.view_selected.emit("Show Casablanca Output")

    def view_original_clicked(self):
        self.setIcon(self.view_original_action.icon())
        self.icon_png = self.view_original_png
        self.mixpanel_tracker.track("Selected view: Original")
        self.view_selected.emit("Show Camera Input")

    def view_comparison_clicked(self):
        self.setIcon(self.view_comparison_action.icon())
        self.icon_png = self.view_comparison_png
        self.mixpanel_tracker.track("Selected view: Comparison")
        self.view_selected.emit("Show Input and Output")

    def view_head_only_clicked(self):
        self.setIcon(self.view_head_only_action.icon())
        self.icon_png = self.view_head_only_png
        self.mixpanel_tracker.track("Selected view: Zoom in on Face")
        self.view_selected.emit("Show Zoom in on Face")

    def set_to_dark_light_mode(self, dark_mode: bool):
        self.dark_mode = dark_mode
        self.setIcon(QIcon(self.icon_png + ("_dark" if self.dark_mode else "_light") + ".png"))
        for action in self.menu.actions():
            if action.property("file_name") is not None:
                action.setIcon(
                    QIcon(action.property("file_name") + ("_dark" if self.dark_mode else "_light") + ".png"))
        self.set_style()


class MoreActionsSelector(MixpanelQToolButton):
    view_selected = pyqtSignal(str)

    def __init__(self, mixpanel_tracker, parent=None, hide_keyboard_shortcuts=False):
        super().__init__(
            parent=parent,
            mixpanel_tracker=mixpanel_tracker,
            mixpanel_default_event_name="Opened more settings dropdown menu",
            mixpanel_activated_event_name="Closed more settings dropdown menu",
        )
        self._hide_keyboard_shortcuts = hide_keyboard_shortcuts
        self.dark_mode = False
        self.icon_png = "assets/Icon_MoreSettings"
        self.icon = QIcon(self.icon_png + ("_dark" if self.dark_mode else "_light") + ".png")
        self.setIcon(self.icon)
        self.mixpanel_tracker = mixpanel_tracker
        self.setStyleSheet(
            """
            QToolButton {
                    border-radius: 13px;
                    width: 40px;
                    height: 25px;
                }
            QToolButton::menu-indicator { 
                image: url(assets/Icon_DownArrow.png);
                }
            """)
        self.setPopupMode(QToolButton.InstantPopup)

        self.menu = MenuButton(self)
        self.menu.setStyleSheet(
            """
            QMenu {
                border: 5px solid black;
                border-radius: 10px;
                outline: 0;
                margin: -5px;
                }
            """)

        self.setMenu(self.menu)
        self.menu.setContentsMargins(5, 10, 5, 10)

    def enterEvent(self, event) -> None:
        QToolTip.showText(QCursor.pos(), "More settings")

    def add_button(
            self,
            png_file: str,
            text: str,
            action: Callable,
            *,
            shortcut_key=None,
    ):
        new_action = QAction(QIcon(png_file), text, self)
        self._set_shortcut(new_action, shortcut_key)
        new_action.setProperty("file_name", png_file)
        new_action.triggered.connect(action)
        new_action.triggered.connect(
            lambda: self.mixpanel_tracker.track(event_name=f"Clicked '{new_action.text()}' button"),
        )
        self.menu.addAction(new_action)

    def add_toggle_button(
            self,
            png_file1: str,
            text1: str,
            alternative_on: bool,
            png_file2: str,
            text2: str,
            action: Callable,
            shortcut_key=None,
    ):

        if alternative_on:
            new_action = QAction(QIcon(png_file2 + ("_dark" if self.dark_mode else "_light") + ".png"), text2, self)
            self._set_shortcut(new_action, shortcut_key)
            new_action.setProperty("file_name", png_file2)
        else:
            new_action = QAction(QIcon(png_file1 + ("_dark" if self.dark_mode else "_light") + ".png"), text1, self)
            self._set_shortcut(new_action, shortcut_key)
            new_action.setProperty("file_name", png_file1)

        def toggle_icon():
            if new_action.text() == text1:
                new_action.setIcon(QIcon(png_file2 + ("_dark" if self.dark_mode else "_light") + ".png"))
                new_action.setText(text2)
                new_action.setProperty("file_name", png_file2)
            else:
                new_action.setIcon(QIcon(png_file1 + ("_dark" if self.dark_mode else "_light") + ".png"))
                new_action.setText(text1)
                new_action.setProperty("file_name", png_file1)

        new_action.triggered.connect(action)
        new_action.triggered.connect(
            lambda: self.mixpanel_tracker.track(event_name=f"Clicked '{new_action.text()}' button"))
        new_action.triggered.connect(toggle_icon)
        self.menu.addAction(new_action)

    def add_separator(self):
        self.menu.addSeparator()

    def add_gap(self):
        empty_action = QAction("", self)
        self.menu.addAction(empty_action)

    def set_to_dark_light_mode(self, dark_mode: bool):
        self.dark_mode = dark_mode
        self.icon = QIcon(self.icon_png + ("_dark" if self.dark_mode else "_light") + ".png")
        for action in self.menu.actions():
            if action.property("file_name") is not None:
                action.setIcon(QIcon(action.property("file_name") + ("_dark" if self.dark_mode else "_light") + ".png"))

    def reopen_menu(self):
        self.menu.popup(self.menu.pos())

    def _set_shortcut(self, action_widget, shortcut):
        if not shortcut or self._hide_keyboard_shortcuts:
            return
        _set_shortcut_to_action_widget(action_widget, shortcut)


class ImageOverlay(utils.RLabel):
    def __init__(self, image_path: str, parent=None):
        super().__init__(parent)
        self.pixmap = QPixmap(image_path)
        self.setPixmap(self.pixmap)

    def adjust_size(self, canvas_height: int):
        scaled_pixmap = self.pixmap.scaledToHeight(canvas_height // 12, Qt.SmoothTransformation)
        self.setPixmap(scaled_pixmap)


class VideoPlayer(QVBoxLayout):
    closed = pyqtSignal()

    def __init__(self, file_path: str, mixpanel_tracker: MixpanelTracker = None):
        super().__init__()
        self.mixpanel_tracker = mixpanel_tracker
        self.setAlignment(Qt.AlignCenter)

        self.video_label = VideoLabel(file_path=file_path, mixpanel_tracker=mixpanel_tracker)
        self.video_label.closed.connect(self.close)
        self.addWidget(self.video_label)

        self.slider_container = QHBoxLayout()
        self.play_pause_button = utils.RButton()
        self.play_pause_button.setFixedHeight(24)
        self.play_pause_button.setIconSize(QSize(16, 16))
        self.play_pause_button.setIcon(QWidget().style().standardIcon(QStyle.SP_MediaPlay))
        self.slider_container.addWidget(self.play_pause_button)
        self.media_player = QMediaPlayer(None, QMediaPlayer.VideoSurface)
        self.media_player.setMedia(QMediaContent(QUrl.fromLocalFile(os.path.abspath(file_path))))
        self.mute_button = utils.RButton()
        self.mute_button.setFixedHeight(24)
        self.mute_button.setIconSize(QSize(16, 16))
        self.mute_button.setIcon(QWidget().style().standardIcon(QStyle.SP_MediaVolume))
        self.slider_container.addWidget(self.mute_button)

        self.video_slider = VideoSlider()
        self.video_slider.slider_clicked.connect(self.set_position)
        self.slider_container.addWidget(self.video_slider)

        self.addLayout(self.slider_container)

        self.moved_timer = QTimer()
        self.moved_timer.timeout.connect(
            lambda: self.video_slider.setValue(int(self.video_label.video_fraction * 1000)))

        def align_video_to_sound():
            try:
                video_fraction = self.media_player.position() / self.media_player.duration()
            except ZeroDivisionError:
                video_fraction = 0
            self.video_label.video_fraction = video_fraction

        self.realign_timer = QTimer()
        self.realign_timer.timeout.connect(align_video_to_sound)

        self.video_label.clicked.connect(self.toggle_play_pause)
        self.video_slider.slider_clicked.connect(self.set_position)
        self.play_pause_button.clicked.connect(self.toggle_play_pause)
        self.mute_button.clicked.connect(self.toggle_mute)

        self.toggle_play_pause()

    def toggle_play_pause(self):
        if self.video_label.playing:
            self.video_label.pause()
            self.media_player.pause()
            self.moved_timer.stop()
            self.realign_timer.stop()
            self.play_pause_button.setIcon(QWidget().style().standardIcon(QStyle.SP_MediaPlay))
            self.mixpanel_tracker.track(event_name="Paused tutorial video")
        else:
            self.video_label.play()
            self.media_player.play()
            self.moved_timer.start(10)
            self.realign_timer.start(100)
            self.play_pause_button.setIcon(QWidget().style().standardIcon(QStyle.SP_MediaPause))
            self.mixpanel_tracker.track(event_name="Unpaused tutorial video")

    def toggle_mute(self):
        if self.media_player.isMuted():
            self.media_player.setMuted(False)
            self.mute_button.setIcon(QWidget().style().standardIcon(QStyle.SP_MediaVolume))
            self.mixpanel_tracker.track(event_name="Unmuted tutorial video")
        else:
            self.media_player.setMuted(True)
            self.mute_button.setIcon(QWidget().style().standardIcon(QStyle.SP_MediaVolumeMuted))
            self.mixpanel_tracker.track(event_name="Muted tutorial video")

    def hide(self):
        self.video_label.hide()
        self.video_slider.hide()
        self.play_pause_button.hide()
        self.mute_button.hide()

    def show(self):
        self.video_label.show()
        self.video_slider.show()
        self.play_pause_button.show()
        self.play_pause_button.activated = self.video_label.playing
        self.mute_button.show()
        self.mute_button.activated = self.media_player.isMuted()

    def close(self):
        self.video_label.pause()
        self.video_label.video_fraction = 0
        self.video_slider.setValue(0)
        self.media_player.stop()
        self.media_player.setPosition(0)
        self.moved_timer.stop()
        self.realign_timer.stop()
        self.play_pause_button.setIcon(QWidget().style().standardIcon(QStyle.SP_MediaPlay))
        self.closed.emit()

    def set_size(self, width: int, height: int):
        self.video_label.width = width
        self.video_label.height = height

    def set_position(self, position: float):
        position = max(0.0, position)
        self.video_label.video_fraction = position
        self.video_slider.setValue(int(position * 1000))
        self.media_player.setPosition(int(position * self.media_player.duration()))


class VideoLabel(utils.RLabel):
    closed = pyqtSignal()
    clicked = pyqtSignal()

    def __init__(self, file_path: str, parent=None, mixpanel_tracker: MixpanelTracker = None):
        super().__init__(parent)
        self.video = mp.VideoFileClip(file_path)
        self.video_fraction = 0.0
        self.playing = False
        self.width = 0
        self.height = 0

        self.button_box = QVBoxLayout(self)
        self.button_box.setAlignment(Qt.AlignRight | Qt.AlignTop)
        self.close_button = PngButton(png_file="assets/Icon_Close",
                                      mixpanel_event_name="Closed the tutorial",
                                      mixpanel_tracker=mixpanel_tracker)
        self.close_button.adjust_icon_to_mode(True)
        self.close_button.setStyleSheet("background-color: transparent;")
        self.button_box.addWidget(self.close_button)
        self.close_button.clicked.connect(self.close)
        self.advance_frame_timer = QTimer()
        self.advance_frame_timer.timeout.connect(self.advance_frame)

    def play(self):
        self.playing = True
        self.advance_frame_timer.start(int(1000 / self.video.fps))

    def pause(self):
        self.playing = False
        self.advance_frame_timer.stop()

    def advance_frame(self):
        self.video_fraction += 1 / self.video.duration / self.video.fps

    def close(self):
        self.closed.emit()

    def paintEvent(self, event):
        if self.video_fraction >= 1.0:
            self.close()
        image = self.video.get_frame(self.video_fraction * self.video.duration)
        qimage = QImage(image, image.shape[1], image.shape[0], QImage.Format_RGB888)
        pixmap = QPixmap(qimage).scaled(self.width, self.height, transformMode=Qt.SmoothTransformation)
        self.setPixmap(pixmap)

        super().paintEvent(event)

    def mousePressEvent(self, event):
        self.clicked.emit()


class VideoSlider(QSlider):
    slider_clicked = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(Qt.Horizontal, parent)

        self.setRange(0, 1000)
        self.setStyleSheet(
            """
            QSlider::groove:horizontal { 
                background-color: rgba(200, 200, 200, 150);
                height: 10px; 
                border-radius: 4px;
                }
            QSlider::handle:horizontal { 
                background-color: red; 
                border: 2px solid red; 
                width: 16px; 
                height: 20px; 
                line-height: 20px; 
                margin-top: -5px; 
                margin-bottom: -5px; 
                border-radius: 10px;
                }
            """)

    def mousePressEvent(self, event) -> None:
        self.slider_clicked.emit(event.pos().x() / self.size().width())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() & Qt.LeftButton:
            self.slider_clicked.emit(event.pos().x() / self.size().width())
        super().mousePressEvent(event)


class SurveyDialog(QDialog):
    def __init__(self, user_id: str, version: str, questions: List[Dict], feedback_u_id: str, parent=None):
        super().__init__(parent=parent)

        self.setWindowTitle("In app survey")
        self.setWindowFlag(Qt.WindowMinimizeButtonHint, True)
        self.setModal(True)
        self.resize(500, 250)

        self.question_codes = {
            "WarningInfo": 1,
            "YesNo": 2,
            "MultiSelect": 3,
            "SingleChoice": 4,
            "TextBox": 5,
            "10Star": 6,
            "5Star": 7,
        }
        self.user_id = user_id
        self.version = version
        self.feedback_u_id = feedback_u_id
        self.questions = questions
        self.question_index = 0
        self.current_question = self.questions[self.question_index]

        self.navigation_layout = QHBoxLayout()
        self.navigation_circles = []
        self.navigation_layout.addStretch()
        for i in range(len(self.questions)):
            circle = utils.RLabel("⬤")
            circle.setStyleSheet("font-size: 14px; padding: 0px; color: #d6d6d6;")
            self.navigation_circles.append(circle)
            self.navigation_layout.addWidget(circle)
        self.navigation_circles[0] \
            .setStyleSheet("font-size: 14px; padding: 0px; color: #848484;")
        self.navigation_layout.addStretch()

        self.question_label = utils.RLabel()
        self.question_label.setWordWrap(True)
        self.question_label.setOpenExternalLinks(True)

        self.textbox = utils.RTextEdit()
        self.textbox.setStyleSheet("QTextEdit {border: 1px solid gray;}")

        self.rating_box = QHBoxLayout()
        self.rating_box.addStretch()
        self.rating_bar_5 = StarRatingBar(star_count=5, parent=self, onclick=self.record_answer)
        self.rating_bar_10 = StarRatingBar(star_count=10, parent=self, onclick=self.record_answer)
        self.rating_box.addWidget(self.rating_bar_5)
        self.rating_box.addWidget(self.rating_bar_10)
        self.rating_box.addStretch()

        self.checkbox_column = QVBoxLayout()
        self.checkboxes = []

        self.button_row = QHBoxLayout()
        self.button_row.addStretch()

        self.yes_button = utils.RButton("Yes")
        self.yes_button.clicked.connect(lambda: self.record_answer(1))
        self.button_row.addWidget(self.yes_button)

        self.no_button = utils.RButton("No")
        self.no_button.clicked.connect(lambda: self.record_answer(2))
        self.button_row.addWidget(self.no_button)

        self.survey_button = utils.RButton("Go to survey")
        self.button_row.addWidget(self.survey_button)

        self.next_button = utils.RButton("Continue")
        self.next_button.clicked.connect(lambda: self.record_answer(None))
        self.button_row.addWidget(self.next_button)

        self.button_row.addStretch()
        main_layout = QVBoxLayout()

        main_layout.addLayout(self.navigation_layout)
        main_layout.addWidget(self.question_label)
        self.question_label.setAlignment(Qt.AlignLeft)
        main_layout.addWidget(self.textbox)
        main_layout.addLayout(self.rating_box)
        main_layout.addLayout(self.checkbox_column)
        main_layout.addStretch()
        main_layout.addLayout(self.button_row)
        self.update_displayed_question()
        self.setLayout(main_layout)

        self.exec_()

    def record_answer(self, answer):
        def select_next_question(response):
            for answer_option in self.current_question_answers:
                if answer_option["option"] == response:
                    if answer_option["following_q"]:
                        self.current_question = answer_option["following_q"]
                        break
            else:
                jump_to_next_question_line()

        def jump_to_next_question_line():
            self.question_index += 1
            if self.question_index < len(self.questions):
                self.navigation_circles[self.question_index - 1] \
                    .setStyleSheet("font-size: 14px; padding: 0px; color: #d6d6d6;")
                self.navigation_circles[self.question_index] \
                    .setStyleSheet("font-size: 14px; padding: 0px; color: #848484;")
                self.current_question = self.questions[self.question_index]
            else:
                self.current_question = None

        if self.current_question_type == self.question_codes["WarningInfo"]:
            jump_to_next_question_line()
        elif self.current_question_type == self.question_codes["YesNo"]:
            API.send_question_response(
                feedback_u_id=self.feedback_u_id, question_id=self.current_question_id,
                response_txt=None, response_num=answer)
            select_next_question(response=answer)
        elif self.current_question_type == self.question_codes["MultiSelect"]:
            answer = ",".join([str(i) for (i, checkbox) in enumerate(self.checkboxes, start=1) if checkbox.isChecked()])
            API.send_question_response(
                feedback_u_id=self.feedback_u_id, question_id=self.current_question_id,
                response_txt=answer, response_num=None)
            jump_to_next_question_line()
        elif self.current_question_type == self.question_codes["SingleChoice"]:
            answers = [(i, checkbox.text()) for i, checkbox
                       in enumerate(self.checkboxes, start=1) if checkbox.isChecked()]
            if len(answers) > 0:
                answer = answers[0]
                API.send_question_response(
                    feedback_u_id=self.feedback_u_id, question_id=self.current_question_id,
                    response_txt=None, response_num=answer[0])
                select_next_question(response=answer[1])
            else:
                jump_to_next_question_line()
        elif self.current_question_type == self.question_codes["TextBox"]:
            if self.textbox.toPlainText() == "":
                self.textbox.setPlaceholderText("Please enter a response.")
                return
            API.send_question_response(
                feedback_u_id=self.feedback_u_id, question_id=self.current_question_id,
                response_txt=self.textbox.toPlainText(), response_num=None)
            jump_to_next_question_line()
        elif self.current_question_type == self.question_codes["10Star"]:
            API.send_question_response(
                feedback_u_id=self.feedback_u_id, question_id=self.current_question_id,
                response_txt=None, response_num=answer)
            select_next_question(response=answer)
        elif self.current_question_type == self.question_codes["5Star"]:
            API.send_question_response(
                feedback_u_id=self.feedback_u_id, question_id=self.current_question_id,
                response_txt=None, response_num=answer)
            select_next_question(response=answer)
        self.update_displayed_question()

    def update_displayed_question(self):
        if self.current_question:
            self.current_question_id = self.current_question["id"]
            self.current_question_type = self.current_question["type"]
            self.current_question_text = self.current_question["title"]
            self.current_question_answers = self.current_question["answers"]
            if self.current_question_type == self.question_codes["WarningInfo"]:
                self.show_warning_info()
            elif self.current_question_type == self.question_codes["YesNo"]:
                self.show_yes_no_question()
            elif self.current_question_type == self.question_codes["MultiSelect"]:
                self.show_multi_select_question()
            elif self.current_question_type == self.question_codes["SingleChoice"]:
                self.show_single_choice_question()
            elif self.current_question_type == self.question_codes["TextBox"]:
                self.show_text_question()
            elif self.current_question_type == self.question_codes["10Star"]:
                self.show_rating_10_question()
            elif self.current_question_type == self.question_codes["5Star"]:
                self.show_rating_5_question()
            elif self.current_question_type == "Survey":
                self.show_survey()
            elif self.current_question_type == "ThankYou":
                self.show_thank_you()
        else:
            self.close()

    def show_warning_info(self):
        self.hide_all()
        self.question_label.setText(self.current_question_text)
        self.next_button.show()

    def show_yes_no_question(self):
        self.hide_all()
        self.question_label.setText(self.current_question_text)
        self.yes_button.show()
        self.no_button.show()

    def show_multi_select_question(self):
        self.hide_all()
        self.question_label.setText(self.current_question_text)
        for answer_option in self.current_question_answers:
            checkbox = QCheckBox(answer_option["option"])
            self.checkbox_column.addWidget(checkbox)
            self.checkboxes.append(checkbox)
        self.next_button.show()

    def show_single_choice_question(self):
        self.hide_all()
        self.question_label.setText(self.current_question_text)
        for answer_option in self.current_question_answers:
            checkbox = QRadioButton(answer_option["option"])
            checkbox.toggled.connect(self.deselect_other_checkboxes)
            self.checkbox_column.addWidget(checkbox)
            self.checkboxes.append(checkbox)
        self.next_button.show()

    def show_text_question(self):
        self.hide_all()
        self.question_label.setText(self.current_question_text)
        self.textbox.show()
        self.next_button.show()

    def show_rating_10_question(self):
        self.hide_all()
        self.question_label.setText(self.current_question_text)
        self.rating_bar_10.show()

    def show_rating_5_question(self):
        self.hide_all()
        self.question_label.setText(self.current_question_text)
        self.rating_bar_5.show()

    def show_survey(self):
        self.hide_all()
        self.question_label.setText("Please click \"Go to survey\" to be\ndirected to a brief browser-based survey.")
        self.survey_button.show()

        def start_survey():
            webbrowser.open(self.current_question_text)
            self.close()

        self.survey_button.clicked.connect(start_survey)

    def show_thank_you(self):
        self.hide_all()
        self.question_label.setText(self.current_question_text)

    def hide_all(self):
        self.question_label.setText("")
        self.textbox.setText("")
        self.textbox.hide()
        self.rating_bar_5.hide()
        self.rating_bar_10.hide()
        for checkbox in self.checkboxes:
            self.checkbox_column.removeWidget(checkbox)
        self.checkboxes = []
        self.yes_button.hide()
        self.no_button.hide()
        self.survey_button.hide()
        self.next_button.hide()

    def deselect_other_checkboxes(self):
        sender = self.sender()
        if sender.isChecked():
            for checkbox in self.checkboxes:
                if checkbox != sender:
                    checkbox.setChecked(False)


class InfoDialog(MixpanelQDialog):
    def __init__(self, parent, app_version, output_path, settings, is_paid_user, is_experimental_version,
                 developer_mode=False, mixpanel_tracker: MixpanelTracker = None):
        super().__init__(parent=parent, mixpanel_tracker=mixpanel_tracker,
                         mixpanel_close_event_name="Closed app details")
        self.app_version = app_version
        self.output_path = '\\'.join(output_path.split("/"))
        self.settings = settings
        self.is_paid_user = is_paid_user
        self.is_experimental_version = is_experimental_version
        self.developer_mode = developer_mode
        self.setWindowTitle("Casablanca")
        self.setModal(True)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowMinMaxButtonsHint & ~Qt.WindowContextHelpButtonHint)

        self.init_ui()
        self.setup_timer()

    def init_ui(self):
        layout = QVBoxLayout(self)

        self.version_label = self.create_label(
            f"Build version: <b>{self.app_version}"
            f"{' Alpha' if self.is_experimental_version else (' Pro' if self.is_paid_user else ' Free')}</b>")
        self.screenshot_path_label = self.create_label(f"Screenshot path: <b>{self.output_path}</b>")
        self.model_label = self.create_label(
            f"Selected model: <b>{'High Quality' if 'lsm' in self.settings.model_type else 'High Performance'}</b>")

        if self.developer_mode:
            settings_button = utils.RButton("Show settings", self)
            settings_button.clicked.connect(self.toggle_settings_visibility)

        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        scroll_widget = QWidget()
        key_box = QVBoxLayout(scroll_widget)
        self.key_labels = []

        for key, value in self.settings.data.items():
            key_label = self.create_label(f"{key}: <b>{value}</b>")
            key_label.setVisible(False)
            key_box.addWidget(key_label)
            self.key_labels.append(key_label)

        self.scroll_area.setWidget(scroll_widget)
        self.scroll_area.setVisible(False)

        layout.addWidget(self.version_label)
        layout.addWidget(self.screenshot_path_label)
        layout.addWidget(self.model_label)
        layout.addWidget(self.scroll_area)
        if self.developer_mode:
            layout.addWidget(settings_button)

        self.adjustSize()
        self.default_size = self.size()
        self.setFixedSize(self.size())

    def create_label(self, text):
        label = utils.RLabel(self)
        label.setText(text)
        label.setAlignment(Qt.AlignLeft)
        label.setWordWrap(False)
        return label

    def toggle_settings_visibility(self):

        for label in self.key_labels:
            label.setVisible(not label.isVisible())

        if self.sender().text() == "Show settings":
            self.sender().setText("Go back")
            self.hide_info_labels()
            self.scroll_area.setVisible(True)
            self.scroll_area.setFixedSize(572, 350)
        else:
            self.sender().setText("Show settings")
            self.scroll_area.setVisible(False)
            self.show_info_labels()

    def show_info_labels(self):
        for label in [self.version_label, self.screenshot_path_label, self.model_label]:
            label.setVisible(True)
        self.setFixedSize(self.default_size)

    def hide_info_labels(self):
        for label in [self.version_label, self.screenshot_path_label, self.model_label]:
            label.setVisible(False)
        self.adjustSize()
        self.setFixedSize(600, 450)

    def setup_timer(self):
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_settings)
        self.timer.start(500)

    def update_settings(self):
        for key, value in self.settings.data.items():
            for label in self.key_labels:
                if label.text().startswith(f"{key}:"):
                    if isinstance(value, list):
                        value_str = "[" + ', '.join(map(str, value)) + "]"
                        label.setText(f"{key}: <b>{value_str}</b>")
                    else:
                        label.setText(f"{key}: <b>{value}</b>")

    def closeEvent(self, event):
        super().closeEvent(event)
        self.timer.stop()
        event.accept()


def _set_shortcut_to_action_widget(action_widget, shortcut):
    if sys.platform == "darwin":
        action_widget.setShortcut(QKeySequence(Qt.SHIFT + Qt.ALT + shortcut))
    else:
        action_widget.setShortcut(QKeySequence(Qt.CTRL + Qt.ALT + shortcut))
    action_widget.setShortcutVisibleInContextMenu(True)
    action_widget.setShortcutContext(Qt.ApplicationShortcut)
