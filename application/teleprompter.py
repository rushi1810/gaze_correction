import time
from functools import partial

from PyQt5 import QtGui
from PyQt5.QtCore import Qt, QTimer, QSize, QPropertyAnimation, QEasingCurve
from PyQt5.QtGui import QIcon, QKeySequence
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QSizePolicy, QStyle, QSlider, QMessageBox, QWidget, QScrollArea, \
    QBoxLayout, QLabel, QShortcut

from application import utils
from application.mixpanel_integration import MixpanelTracker, MixpanelQDialog
from application.widgets.qt_widgets import PngButton


class WordSliderWidget(QScrollArea):
    _ANIMATION_DURATION = 700
    _SLICE_FACTOR = 5

    def __init__(self, words, parent=None):
        super().__init__(parent)
        self.words = words
        self.current_index = 0

        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFrameShape(QScrollArea.NoFrame)
        self.setWidgetResizable(True)

        self.container = QWidget()
        self.layout = QVBoxLayout(self.container)
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.label = QLabel()
        self.label.setTextInteractionFlags(Qt.NoTextInteraction)
        self.label.setFixedHeight(150)
        self.label.setStyleSheet("font-size: 20pt; vertical-align: middle;")
        self.layout.addWidget(self.label)

        self.setWidget(self.container)

        self.animation = QPropertyAnimation(self.horizontalScrollBar(), b"value")
        self.animation.setDuration(self._ANIMATION_DURATION)
        self.animation.setEasingCurve(QEasingCurve.OutCubic)

        self.update_text()

    def update_text(self):
        parts = []
        for i, word in enumerate(self.words):
            if i == self.current_index:
                parts.append(f"<span style='font-weight:bold;'>{word}</span>")
            else:
                parts.append(f"<span style='color:#555;'>{word}</span>")
        self.label.setText(" ".join(parts))
        self.label.adjustSize()
        self.center_current_word()

    def highlight_index(self, index):
        self.current_index = index
        self.update_text()

    def center_current_word(self):
        font_metrics = self.label.fontMetrics()
        spacing = font_metrics.width(' ')
        offset = 0

        for i in range(len(self.words)):
            word = self.words[i]
            word_width = font_metrics.width(word)
            if i < self.current_index:
                offset += word_width + spacing
            elif i == self.current_index:
                offset += word_width // 2
                break

        scroll_target = max(0, offset - self.viewport().width() // 2)
        self.animate_to(scroll_target)

    def animate_to(self, pos):
        self.animation.stop()
        self.animation.setStartValue(self.horizontalScrollBar().value())
        self.animation.setEndValue(pos)
        self.animation.start()


class DraggableScrollArea(QScrollArea):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setWidgetResizable(True)
        self._is_dragging = False
        self._drag_start_x = 0
        self._scroll_start_x = 0

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._is_dragging = True
            self._drag_start_x = event.pos().x()
            self._scroll_start_x = self.horizontalScrollBar().value()

    def mouseMoveEvent(self, event):
        if self._is_dragging:
            delta = event.pos().x() - self._drag_start_x
            self.horizontalScrollBar().setValue(self._scroll_start_x - delta)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._is_dragging = False


class JumpSlider(QSlider):
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            new_val = QStyle.sliderValueFromPosition(
                self.minimum(), self.maximum(), event.x(), self.width(), upsideDown=False)
            self.setValue(new_val)
            event.accept()
            self.sliderMoved.emit(new_val)
            self.sliderReleased.emit()
        super().mousePressEvent(event)


class TextCollectionWindow(MixpanelQDialog):

    def __init__(
            self,
            parent=None,
            mixpanel_tracker: MixpanelTracker = None,
            mixpanel_close_event_name: str = "Teleprompter menu",
            geometry_coordinates=None,
            text2edit=None,
            settings=None,
            note_id=None,
            is_last_changes_committed=True
    ):
        super().__init__(
            parent=parent,
            mixpanel_tracker=mixpanel_tracker,
            mixpanel_close_event_name=mixpanel_close_event_name,
        )
        self.setWindowFlag(Qt.WindowMinimizeButtonHint, True)
        self._settings = settings
        self._mixpanel_tracker = mixpanel_tracker
        self.main_layout = QVBoxLayout()
        self.setWindowFlag(Qt.WindowMinimizeButtonHint, True)
        self.setWindowTitle("Teleprompter")
        self._geometry_coordinates = geometry_coordinates
        self.heading = utils.RLabel("Please add the text you want to read out")
        heading_font = QtGui.QFont()
        self.heading.setFont(heading_font)
        self.heading.setAlignment(Qt.AlignCenter)
        self.main_layout.addWidget(self.heading)

        self.template_title = utils.RLineEdit(self)
        self.template_title.setPlaceholderText("Enter title for template")
        self.template_title.setStyleSheet("border: 1px solid; border-radius:5px; padding: 5px;")
        self.main_layout.addWidget(self.template_title)

        self.textbox = utils.RTextEdit(self)
        text2edit and self.textbox.setText(text2edit)
        self.textbox.setPlaceholderText("Paste your text here")
        self.textbox.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.textbox.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.textbox.setStyleSheet("border: 1px solid; border-radius:5px; padding: 5px;")
        self.textbox.textChanged.connect(self.clear_error_label)
        self.textbox.textChanged.connect(self.on_text_changed)
        self.template_title.textChanged.connect(self.on_text_changed)
        self.main_layout.addWidget(self.textbox)

        self.error_label = utils.RLabel("")
        self.error_label.setStyleSheet("color: red;")
        self.error_label.setAlignment(Qt.AlignCenter)
        self.main_layout.addWidget(self.error_label)

        self.submit_button = utils.RButton("Start Teleprompter", self)
        self.submit_button.clicked.connect(self.start_teleprompter)

        self.save_button = utils.RButton("Save as Template", self)
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self.save_template)

        submit_button_layout = QHBoxLayout()
        submit_button_layout.addStretch()
        submit_button_layout.addWidget(self.submit_button)
        submit_button_layout.addStretch()
        submit_button_layout.addWidget(self.save_button)
        submit_button_layout.addStretch()

        self.template_scroll_area = DraggableScrollArea(self)
        self.template_scroll_area.setWidgetResizable(True)
        self.template_scroll_content = QWidget()
        self.template_scroll_layout = QHBoxLayout(self.template_scroll_content)
        self.template_scroll_layout.setAlignment(Qt.AlignLeft)
        self.template_scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.template_scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.template_scroll_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.template_scroll_area.setWidget(self.template_scroll_content)
        self.main_layout.addWidget(self.template_scroll_area)

        self.main_layout.addLayout(submit_button_layout)

        self.setLayout(self.main_layout)

        self.current_edit_template_id = None
        self.load_templates()

        if note_id is not None:
            for template in getattr(self._settings, "teleprompter_templates", []):
                if template["id"] == note_id:
                    self.template_title.setText(template["title"])
                    self.textbox.setText(template["text"])
                    self.current_edit_template_id = template["id"]
                    self.save_button.setText("Edit Template")
                    self.save_button.setEnabled(not is_last_changes_committed)
                    self.load_templates()
                    break

    def on_text_changed(self):
        self.save_button.setEnabled(True)

    def start_teleprompter(self):
        self.error_label.setText("")
        feedback = self.textbox.toPlainText().strip()
        if not feedback:
            utils.warning_msg("Validation Error", "Title and text cannot be empty.", self)
            return
        self.error_label.setText("")
        self.close()
        dialog = TeleprompterWindow(
            feedback,
            parent=self,
            mixpanel_tracker=self._mixpanel_tracker,
            geometry_coordinates=self._geometry_coordinates,
            settings=self._settings,
            note_id=self.current_edit_template_id,
            is_last_changes_committed=not self.save_button.isEnabled(),
        )
        dialog.setGeometry(*self._geometry_coordinates)
        dialog.exec_()

    def clear_error_label(self):
        self.error_label.setText("")
        self.save_button.setVisible(bool(self.textbox.toPlainText().strip()))

    def save_template(self):
        title = self.template_title.text().strip()
        text = self.textbox.toPlainText().strip()
        if not title or not text:
            if self.save_button.isEnabled():
                utils.warning_msg("Validation Error", "Title and text cannot be empty.", self)
            return

        if self.current_edit_template_id is not None:
            self.edit_template(self.current_edit_template_id)
            return

        timestamp = int(time.time())
        entry = {
            "id": timestamp,
            "title": title,
            "text": text,
            "added_date": time.strftime("%Y-%m-%d %H:%M"),
            "last_change": timestamp
        }
        self.current_edit_template_id = timestamp
        self.save_button.setText("Edit Template")
        self.save_button.setEnabled(False)
        self._settings.teleprompter_templates = getattr(self._settings, "teleprompter_templates", [])
        self._settings.teleprompter_templates.append(entry)
        self._settings.save()
        self.load_templates()

    def edit_template(self, template_id):
        self.current_edit_template_id = template_id
        for template in self._settings.teleprompter_templates:
            if template["id"] == template_id:
                new_title = self.template_title.text().strip()
                new_text = self.textbox.toPlainText().strip()
                if not new_title or not new_text:
                    if self.save_button.isEnabled():
                        utils.warning_msg("Validation Error", "Title and text cannot be empty.", self)
                    return
                template["title"] = new_title
                template["text"] = new_text
                template["last_change"] = int(time.time())
                self._settings.save()
                self.load_templates()
                self.save_button.setEnabled(False)
                return

    def load_templates(self):
        for i in reversed(range(self.template_scroll_layout.count())):
            item = self.template_scroll_layout.itemAt(i).widget()
            if item:
                item.setParent(None)

        self.template_scroll_layout.setDirection(QBoxLayout.LeftToRight)

        templates = sorted(getattr(self._settings, "teleprompter_templates", []), key=lambda x: -x["last_change"])

        for template in templates:
            is_selected = template["id"] == self.current_edit_template_id
            border_color = "#007BFF" if is_selected else "#ccc"
            if self._settings.dark_mode:
                border_color = "#E0E0E0" if is_selected else "#000000"
            card = QWidget(self)
            card.setFixedSize(200, 100)
            card.setStyleSheet(f"""
                background-color: {"#424447" if self._settings.dark_mode else "white"};
                border: 0.5px solid {border_color};
                border-radius: 8px;
                padding: 4px 2px;
            """)

            layout = QVBoxLayout(card)
            layout.setContentsMargins(8, 8, 4, 4)
            layout.setSpacing(4)

            title_label = utils.RLabel(
                template["title"][:30] if len(template["title"]) > 30 else template["title"],
                parent=self,
            )
            title_label.setStyleSheet("padding: 0px; border: none;")
            layout.addWidget(title_label)

            info_label = utils.RLabel(
                time.strftime("%Y-%m-%d %H:%M", time.localtime(template["last_change"])),
                parent=self,
            )
            info_label.setStyleSheet("color: gray; font-size: 8pt; padding: 0px; border: none;")
            layout.addWidget(info_label)

            button_row = QHBoxLayout(self)
            btn_use = utils.RButton("Use", font_size=14)
            btn_use.setStyleSheet("padding: 8px;")
            btn_use.clicked.connect(partial(self.use_template, template))

            btn_delete = PngButton(
                png_file="assets/Icon_Trash",
                tooltip_message="Delete Template",
                mixpanel_event_name="Delete Teleprompter Template",
                mixpanel_tracker=self.mixpanel_tracker,
            )

            btn_delete.clicked.connect(partial(self.delete_template, template["id"]))

            button_row.addWidget(btn_use)
            button_row.addStretch()
            button_row.addWidget(btn_delete)

            layout.addLayout(button_row)
            self.template_scroll_layout.addWidget(card)

    def use_template(self, template):
        if self.textbox.toPlainText().strip() and self.save_button.isEnabled():
            confirm = utils.warning_msg(
                "Overwrite Text",
                "You have unsaved changes. Do you want to overwrite them?",
                self,
                buttons=QMessageBox.Yes | QMessageBox.No,
            )
            if confirm != QMessageBox.Yes:
                return
        self.template_title.setText(template["title"])
        self.textbox.setText(template["text"])
        self.current_edit_template_id = template["id"]
        self.save_button.setText("Edit Template")
        self.save_button.setEnabled(False)
        self.save_button.clicked.disconnect()
        self.save_button.clicked.connect(partial(self.edit_template, template["id"]))
        self.load_templates()

    def delete_template(self, template_id):
        self._settings.teleprompter_templates = [
            template for template in self._settings.teleprompter_templates if template["id"] != template_id
        ]
        self._settings.save()
        self.load_templates()


class TeleprompterWindow(MixpanelQDialog):
    def __init__(
            self,
            paragraph,
            parent=None,
            mixpanel_tracker: MixpanelTracker = None,
            geometry_coordinates=None,
            settings=None,
            note_id=None,
            is_last_changes_committed=True,
    ):
        super().__init__(
            parent=parent,
            mixpanel_tracker=mixpanel_tracker,
            mixpanel_close_event_name="Teleprompter Menu",
        )
        self.setWindowFlag(Qt.WindowMinimizeButtonHint, True)
        self.space_shortcut = QShortcut(QKeySequence(Qt.Key_Space), self)
        self.space_shortcut.activated.connect(self.toggle_pause)
        self.left_shortcut = QShortcut(QKeySequence(Qt.Key_Left), self)
        self.left_shortcut.activated.connect(self.rewind)
        self.right_shortcut = QShortcut(QKeySequence(Qt.Key_Right), self)
        self.right_shortcut.activated.connect(self.fast_forward)
        self._note_id = note_id
        self._is_last_changes_committed = is_last_changes_committed
        self._settings = settings
        self._mixpanel_tracker = mixpanel_tracker
        self._geometry_coordinates = geometry_coordinates
        self.setWindowTitle("Teleprompter mode")
        self._paragraph = paragraph
        self.words = paragraph.strip().split()
        self.word_index = 0
        self.is_paused = False
        self.in_countdown = True
        self.countdown = 3
        self._speed_dict = {
            "60 Words per Minute": 1000,
            "90 Words per Minute": 666,
            "120 Words per Minute": 500,
            "150 Words per Minute": 400,
            "180 Words per Minute": 333,
            "200 Words per Minute": 300,
        }

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.show_next_word)

        self.countdown_timer = QTimer(self)
        self.countdown_timer.timeout.connect(self.update_countdown)

        self.fast_forward_timer = QTimer(self)
        self.fast_forward_timer.timeout.connect(self.fast_forward)

        self.rewind_timer = QTimer(self)
        self.rewind_timer.timeout.connect(self.rewind)

        self.word_display = WordSliderWidget(self.words, self)
        self.countdown_label = utils.RLabel("3", self)
        self.countdown_label.setAlignment(Qt.AlignCenter)
        color = "white" if self._settings.dark_mode else "blue"
        self.countdown_label.setStyleSheet(f"font-size: 24pt; color: {color};")

        self.slider = JumpSlider(Qt.Horizontal)
        self.slider.setMinimum(0)
        self.slider.setMaximum(len(self.words) - 1)
        self.slider.setSingleStep(1)
        self.slider.setPageStep(3)
        self.slider.sliderReleased.connect(self.jump_to_word)
        self.slider.sliderPressed.connect(self.pause_for_slider)
        self.pause_from_slider = False

        self.speed_box = utils.RCombo(self)
        self.speed_box.addItems(list(self._speed_dict.keys()))
        self.speed_box.currentIndexChanged.connect(self.change_speed)
        if self._settings.speed4teleprompter in self._speed_dict.keys():
            self.speed_box.setCurrentText(self._settings.speed4teleprompter)

        style = self.style()

        self.pause_run_toggle_btn = utils.RButton("Pause", self)
        self.pause_run_toggle_btn.setIcon(style.standardIcon(QStyle.SP_MediaPause))
        self.pause_run_toggle_btn.clicked.connect(self.toggle_pause)

        self.forward_btn = utils.RButton(self)
        self.forward_btn.setIcon(style.standardIcon(QStyle.SP_MediaSeekForward))
        self.forward_btn.pressed.connect(lambda: self.fast_forward_timer.start(150))
        self.forward_btn.released.connect(self.fast_forward_timer.stop)
        self.forward_btn.clicked.connect(lambda: self.jump_words(5))

        self.backward_btn = utils.RButton(self)
        self.backward_btn.setIcon(style.standardIcon(QStyle.SP_MediaSeekBackward))
        self.backward_btn.pressed.connect(lambda: self.rewind_timer.start(150))
        self.backward_btn.released.connect(self.rewind_timer.stop)
        self.backward_btn.clicked.connect(lambda: self.jump_words(-5))

        self.replay_btn = utils.RButton("Replay", self)
        self.replay_btn.clicked.connect(self.replay)

        self.exit_btn = utils.RButton("Exit", self)
        self.exit_btn.setIcon(style.standardIcon(QStyle.SP_DialogCloseButton))
        self.exit_btn.clicked.connect(self.exit)

        self.edit_btn = utils.RButton("Edit Text", self)
        self.edit_btn.clicked.connect(self.edit_text)

        top = QVBoxLayout()
        top.addWidget(self.countdown_label)
        top.addWidget(self.word_display)
        top.addWidget(self.slider)
        top.addWidget(self.speed_box)

        controls = QHBoxLayout()
        controls.addWidget(self.backward_btn)
        controls.addWidget(self.pause_run_toggle_btn)
        controls.addWidget(self.forward_btn)
        controls.addWidget(self.replay_btn)

        bottom = QHBoxLayout()
        bottom.addWidget(self.exit_btn)
        bottom.addStretch()
        bottom.addWidget(self.edit_btn)

        layout = QVBoxLayout()
        layout.addLayout(top)
        layout.addLayout(controls)
        layout.addLayout(bottom)
        self.setLayout(layout)
        self.resize(500, 300)
        self.enable_controllers(False)
        self.countdown_timer.start(1000)

    def update_countdown(self):
        if self.is_paused:
            return
        self.countdown -= 1
        if self.countdown > 0:
            self.countdown_label.setText(str(self.countdown))
        elif self.countdown == 0:
            self.countdown_label.setText("Go")
        else:
            self.countdown_timer.stop()
            self.countdown_label.setVisible(False)
            self.in_countdown = False
            self.start_reading()

    def start_reading(self):
        self.enable_controllers(True)
        self.change_speed()
        self.timer.start()
        self.is_paused = False
        self.pause_run_toggle_btn.setText("Pause")
        self.pause_run_toggle_btn.setIcon(self.style().standardIcon(QStyle.SP_MediaPause))

    def show_next_word(self):
        if self.word_index < len(self.words):
            self.word_display.highlight_index(self.word_index)
            self.word_index += 1
            self.update_slider_position()
        else:
            self.timer.stop()
            self.word_display.highlight_index(-1)
            self.pause_run_toggle_btn.setText("Finished")
            self.pause_run_toggle_btn.setIcon(QIcon())
            self.pause_run_toggle_btn.setEnabled(False)
            self.slider.setValue(len(self.words) - 1)
            self.enable_controllers(False)

    def change_speed(self):
        current_text = self.speed_box.currentText()
        self._settings.speed4teleprompter = current_text
        self.word_delay_ms = self._speed_dict.get(current_text, 1000)
        self.timer.setInterval(self.word_delay_ms)

    def toggle_pause(self):
        if self.pause_run_toggle_btn.text() == "Finished":
            return

        if self.is_paused:
            self.pause_run_toggle_btn.setText("Pause")
            self.pause_run_toggle_btn.setIcon(self.style().standardIcon(QStyle.SP_MediaPause))
            if self.in_countdown:
                self.countdown_timer.start(1000)
            else:
                self.timer.start()
            self.is_paused = False
        else:
            self.pause_run_toggle_btn.setText("Resume")
            self.pause_run_toggle_btn.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
            self.countdown_timer.stop()
            self.timer.stop()
            self.is_paused = True

    def fast_forward(self):
        if self.in_countdown:
            return
        if self.word_index < len(self.words) - 1:
            self.word_index = min(self.word_index + 1, len(self.words) - 1)
            self.word_display.highlight_index(self.word_index)
            self.update_slider_position()

    def rewind(self):
        if self.in_countdown:
            return
        if self.word_index > 0:
            self.word_index = max(self.word_index - 1, 0)
            self.word_display.highlight_index(self.word_index)
            self.update_slider_position()

    def enable_controllers(self, enable):
        self.slider.setEnabled(enable)
        self.forward_btn.setEnabled(enable)
        self.backward_btn.setEnabled(enable)

    def replay(self):
        self.enable_controllers(False)
        self.countdown = 3
        self.in_countdown = True
        self.word_index = 0
        self.word_display.highlight_index(self.word_index)
        self.countdown_label.setText("3")
        self.countdown_label.setVisible(True)
        self.countdown_timer.start(1000)
        self.timer.stop()
        self.is_paused = False
        self.pause_run_toggle_btn.setText("Pause")
        self.pause_run_toggle_btn.setEnabled(True)
        self.pause_run_toggle_btn.setIcon(self.style().standardIcon(QStyle.SP_MediaPause))
        self.slider.setValue(0)

    def exit(self):
        self.countdown_timer.stop()
        self.timer.stop()
        self.close()

    def edit_text(self):
        self.exit()
        dialog = TextCollectionWindow(
            parent=self,
            mixpanel_tracker=self._mixpanel_tracker,
            mixpanel_close_event_name="Teleprompter menu edit mode",
            geometry_coordinates=self._geometry_coordinates,
            text2edit=self._paragraph,
            settings=self._settings,
            note_id=self._note_id,
            is_last_changes_committed=self._is_last_changes_committed,
        )
        dialog.setGeometry(*self._geometry_coordinates)
        dialog.exec_()

    def update_slider_position(self):
        self.slider.blockSignals(True)
        self.slider.setValue(self.word_index)
        self.slider.blockSignals(False)

    def jump_to_word(self):
        self.word_index = self.slider.value()
        if 0 <= self.word_index < len(self.words):
            self.word_display.highlight_index(self.word_index)
        if self.pause_from_slider:
            self.toggle_pause()
            self.pause_from_slider = False

    def pause_for_slider(self):
        if not self.is_paused and not self.in_countdown:
            self.pause_from_slider = True
            self.toggle_pause()

    def jump_words(self, offset):
        if self.in_countdown:
            return
        self.word_index = max(0, min(self.word_index + offset, len(self.words) - 1))
        self.word_display.highlight_index(self.word_index)
        self.update_slider_position()
