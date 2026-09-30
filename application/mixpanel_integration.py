import json
import logging
import os.path
import platform
import time
from typing import Optional

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QMouseEvent
from PyQt5.QtWidgets import QMenu

from application import utils
from application._platform.factory.os_factory import Factory
from application.api import API

MIXPANEL_LOG_LEVEL = logging.INFO + 5
MIXPANEL_DEBUG_LEVEL = logging.INFO + 6
logging.addLevelName(MIXPANEL_LOG_LEVEL, "MIXPANEL")
logging.addLevelName(MIXPANEL_DEBUG_LEVEL, "MIXPANEL(DEBUG)")

logger = logging.getLogger("mixpanel")
logger.setLevel(MIXPANEL_LOG_LEVEL)


class MixpanelTracker:
    started_casablanca_was_sent = False

    def __init__(self, user_id: Optional[str] = None, developer_mode=False, session_id=""):
        with open("application/version.json") as f:
            self.version_file = json.load(f)
            self.app_version = self.version_file["version"]
        self.user_id = user_id
        self.session_id = session_id
        self.call_id = None
        self.developer_mode = developer_mode

        self.supress_events = False
        if self.session_id:
            self.track(
                "Started Casablanca",
                {
                    "hardware": Factory.available_processors(),
                    "always_launch_when_virtual_camera_is_selected": os.path.exists("persistent/always_launch.txt")})

    def __del__(self):
        if self.session_id:
            self.track("Stopped Casablanca", {
                "$os": platform.system()
            })
            self.supress_events = True

    def track(self, event_name: str, properties: Optional[dict] = None, meta: Optional[dict] = None):
        if self.supress_events:
            return
        if self.developer_mode or self.user_id.startswith("0"):
            logger.setLevel(MIXPANEL_DEBUG_LEVEL)
            logger.log(MIXPANEL_DEBUG_LEVEL, f"{event_name}")
            return
        properties = properties or {}
        properties['time'] = int(time.time())
        properties["$os"] = platform.system()
        properties["$app_version"] = self.app_version
        properties["$session_id"] = self.session_id
        properties["$call_id"] = self.call_id
        logger.setLevel(MIXPANEL_LOG_LEVEL)
        logger.log(MIXPANEL_LOG_LEVEL, f"{event_name}")
        API.send_event(event_name, properties, self.session_id)


class MixpanelQPushButton(utils.RButton):
    def __init__(self, text: str = "", parent=None, mixpanel_tracker: Optional[MixpanelTracker] = None,
                 mixpanel_event_name: Optional[str] = None, mixpanel_event_data: Optional[dict] = None):
        super().__init__(text, parent)

        self.mixpanel_event_name = mixpanel_event_name
        self.mixpanel_event_data = mixpanel_event_data
        self.mixpanel_tracker = mixpanel_tracker

    def mousePressEvent(self, event) -> None:
        self.mixpanel_tracker.track(self.mixpanel_event_name, self.mixpanel_event_data)
        return super().mousePressEvent(event)


class MixpanelQToolButton(utils.RToolBtn):
    def __init__(
            self,
            parent=None,
            mixpanel_tracker: Optional[MixpanelTracker] = None,
            mixpanel_default_event_name: Optional[str] = None,
            mixpanel_default_event_data: Optional[dict] = None,
            mixpanel_activated_event_name: Optional[str] = None,
            mixpanel_activated_event_data: Optional[dict] = None,
    ):

        super().__init__(parent)

        self.mixpanel_default_event_name = mixpanel_default_event_name
        self.mixpanel_default_event_data = mixpanel_default_event_data

        self.mixpanel_activated_event_name = mixpanel_activated_event_name
        self.mixpanel_activated_event_data = mixpanel_activated_event_data

        self.mixpanel_tracker = mixpanel_tracker

    def setMenu(self, menu: QMenu) -> None:
        menu.aboutToHide.connect(self.menu_hide)
        menu.aboutToShow.connect(self.menu_show)
        return super().setMenu(menu)

    def menu_hide(self):
        if self.mixpanel_tracker is not None and self.mixpanel_activated_event_name is not None:
            self.mixpanel_tracker.track(self.mixpanel_activated_event_name, self.mixpanel_activated_event_data)

    def menu_show(self):
        if self.mixpanel_tracker is not None and self.mixpanel_default_event_name is not None:
            self.mixpanel_tracker.track(self.mixpanel_default_event_name, self.mixpanel_default_event_data)


class MixpanelQDialog(utils.RDialog):
    def __init__(
            self,
            parent=None,
            mixpanel_tracker: Optional[MixpanelTracker] = None,
            mixpanel_close_event_name: Optional[str] = None,
            mixpanel_close_event_data: Optional[dict] = None,
    ):
        super().__init__(parent)
        self.mixpanel_close_event_name = mixpanel_close_event_name
        self.mixpanel_close_event_data = mixpanel_close_event_data
        self.mixpanel_tracker = mixpanel_tracker

    def closeEvent(self, event) -> None:
        if self.mixpanel_tracker is not None and self.mixpanel_close_event_name is not None:
            self.mixpanel_tracker.track(self.mixpanel_close_event_name, self.mixpanel_close_event_data)
        return super().closeEvent(event)


class MixpanelQComboBox(utils.RCombo):
    def __init__(
            self,
            parent=None,
            mixpanel_tracker: Optional[MixpanelTracker] = None,
            mixpanel_open_event_name: Optional[str] = None,
            mixpanel_open_event_data: Optional[dict] = None,
            mixpanel_close_event_name: Optional[str] = None,
            mixpanel_close_event_data: Optional[dict] = None,
            mixpanel_select_event_name: Optional[str] = None,
            mixpanel_select_event_data: Optional[dict] = None,
            automatically_fill_data_with_view_name: bool = False,
            ignore_first_change: bool = True,
            *,
            dropdown_is_about_to_visible_callback=None,
    ):
        super().__init__(parent)
        self._dropdown_is_about_to_visible_callback = dropdown_is_about_to_visible_callback
        self.mixpanel_open_event_name = mixpanel_open_event_name
        self.mixpanel_open_event_data = mixpanel_open_event_data or {}
        self.mixpanel_close_event_name = mixpanel_close_event_name
        self.mixpanel_close_event_data = mixpanel_close_event_data or {}
        self.mixpanel_select_event_name = mixpanel_select_event_name
        self.mixpanel_select_event_data = mixpanel_select_event_data or {}
        self.automatically_fill_data_with_view_name = automatically_fill_data_with_view_name
        self.ignore_first_change = ignore_first_change
        self.mixpanel_tracker = mixpanel_tracker
        self.last_index = self.currentIndex()
        self.last_index_update = True
        self.currentIndexChanged.connect(self.index_changed)

    def showPopup(self) -> None:
        self._dropdown_is_about_to_visible_callback and self._dropdown_is_about_to_visible_callback()
        super().showPopup()
        if self.mixpanel_tracker is not None and self.mixpanel_open_event_name is not None:
            self.mixpanel_tracker.track(self.mixpanel_open_event_name, self.mixpanel_open_event_data)

    def hidePopup(self) -> None:
        super().hidePopup()
        if self.mixpanel_tracker is not None and self.mixpanel_close_event_name is not None:
            self.mixpanel_tracker.track(self.mixpanel_close_event_name, self.mixpanel_close_event_data)

    def index_changed(self):
        if self.ignore_first_change == True:
            self.ignore_first_change = False
            return
        if self.mixpanel_tracker is not None and self.mixpanel_select_event_name is not None:
            if self.automatically_fill_data_with_view_name:
                self.mixpanel_select_event_data["selected"] = self.currentText()
            self.mixpanel_tracker.track(self.mixpanel_select_event_name, self.mixpanel_select_event_data)


class MixpanelQLabel(utils.RLabel):
    def __init__(self, parent=None, mixpanel_tracker: Optional[MixpanelTracker] = None,
                 mixpanel_left_click_event_name: Optional[str] = None,
                 mixpanel_left_click_event_data: Optional[dict] = None,
                 mixpanel_right_click_event_name: Optional[str] = None,
                 mixpanel_right_click_event_data: Optional[dict] = None):
        super().__init__(parent=parent)
        self.mixpanel_left_click_event_name = mixpanel_left_click_event_name
        self.mixpanel_left_click_event_data = mixpanel_left_click_event_data

        self.mixpanel_right_click_event_name = mixpanel_right_click_event_name
        self.mixpanel_right_click_event_data = mixpanel_right_click_event_data

        self.mixpanel_tracker = mixpanel_tracker

    def mousePressEvent(self, event: QMouseEvent) -> None:
        super().mousePressEvent(event)
        if event.button() == Qt.LeftButton:
            if self.mixpanel_tracker is not None and self.mixpanel_left_click_event_name is not None:
                self.mixpanel_tracker.track(self.mixpanel_left_click_event_name, self.mixpanel_left_click_event_data)
        elif event.button() == Qt.RightButton:
            if self.mixpanel_tracker is not None and self.mixpanel_right_click_event_name is not None:
                self.mixpanel_tracker.track(self.mixpanel_right_click_event_name, self.mixpanel_right_click_event_data)
