import os
import sys

import PyQt5.QtWidgets as qt_widgets
import cv2
import numpy as np
from PyQt5.QtCore import QStandardPaths
from PyQt5.QtGui import QFont, QFontMetrics
from screeninfo import get_monitors


class CameraAlreadyInUseException(Exception):
    """Raised when trying to access a camera that is already in use"""
    pass


def draw_axes(image, r, tx, ty, size=100, thickness=1, colors=None):
    """
    Draws axes of the standard right-handed CS: x, y as on the screen, z axis looking away from the observer.
    :param image: image
    :param r: rotation matrix for post-multiplication.
    :param tx: translation x in pixels
    :param ty: translation y in pixels
    :param size: axis length as a number or a tuple
    :param colors: color for axes x, y, z.
    :param thickness: line thickness.
    """
    if type(size) in (int, float):
        size = (size,) * 3
    axes = np.array(((1, 0, 0), (0, 1, 0), (0, 0, 1)), dtype=np.float32)
    origin = np.array((tx, ty, 0), dtype=np.float32)
    axes = np.dot(axes, r) * np.array(size).reshape(3, 1) + origin

    if colors is None:
        colors = ((255, 0, 0), (0, 255, 0), (0, 0, 255)) \
            if image.dtype == np.uint8 else ((1, 0, 0), (0, 1, 0), (255, 0, 1))

    o = tuple(origin[:2].astype(int))
    # Draw z-axis last.
    for ai in range(3):
        a = tuple(axes[ai, :2].astype(int))
        cv2.line(image, o, a, colors[ai], thickness)

    return image


def angles_to_r3(ax, ay):
    """
    Make a 3D rotation matrices for post-multiplication from angles.
    See https://en.wikipedia.org/wiki/Rotation_matrix#General_rotations

    :param ax: rotation angle around x-axis in radians.
    :param ay: rotation angle around y-axis in radians.
    :return: rotation matrix
    """

    cax = np.cos(ax)
    sax = np.sin(ax)
    cay = np.cos(ay)
    say = np.sin(ay)

    rx = np.array((
        (1, 0, 0),
        (0, cax, sax),
        (0, -sax, cax)), dtype=np.float32)

    ry = np.array((
        (cay, 0, -say),
        (0, 1, 0),
        (say, 0, cay)), dtype=np.float32)

    return ry @ rx


def get_platfrom():
    if sys.platform == "darwin":
        return "darwin"
    return "win"


class classproperty(property):
    def __get__(self, owner_self, owner_cls):
        return self.fget(owner_cls)


def desktop_dir(*sub_directories, include_sub_directory=False):
    target_dir = QStandardPaths.standardLocations(QStandardPaths.DesktopLocation)[0]
    for directory in sub_directories:
        target_dir = os.path.join(str(target_dir), directory)
    dummy_file_name = 'dummy_dir_to_fool_os_to_create_dir.txt'
    if include_sub_directory:
        target_dir = os.path.join(target_dir, dummy_file_name)
    os.makedirs(os.path.dirname(target_dir), exist_ok=True)
    target_dir = target_dir.replace(dummy_file_name, '')
    return target_dir


class _FontManagerBase(qt_widgets.QWidget):
    """
        The `_FontManagerBase` class serves as a base class for managing the scaling of font sizes
        in Qt widgets. It is designed to be derived from other Qt widget classes to ensure consistent
        font scaling throughout the application.

        Attributes:
        - _CACHE_FONT_ADJUSTER (dict): A class-level dictionary cache to store adjusted font sizes
          based on their base sizes.
    """
    _CACHE_FONT_ADJUSTER = {}

    def __init__(self, *args, **kwargs):
        self._font_size = self._relative_font_creator(kwargs.pop('font_size', None))
        super().__init__(*args, **kwargs)
        self.setFont(QFont())

    def setFont(self, a0):
        """
        Overrides the setFont method to capture the latest user request and set the font size
        based on the desired scaled font size.

        Parameters:
        - a0 (QFont): The QFont object representing the font properties.

        This method sets the point size of the provided QFont object to the internally stored
        scaled font size (_font_size) and then calls the super method to set the font.

        """
        a0.setPointSizeF(self._font_size)
        return super().setFont(a0)

    @classmethod
    def _relative_font_creator(cls, base_size):
        """
        The `_relative_font_creator` method creates a QFont (Qt Font) object with a font size
        adjusted relative to the specified base size. This adjustment accounts for screen density
        to prevent fonts from appearing too small on high-density screens.

        Parameters:
        - base_size (float): The base font size specified by the user.

        Returns:
        float: The adjusted font size.

        The method iteratively adjusts the font size to match the height of the specified text on the screen.
        The adjusted font size is returned and stored in a cache dictionary for future use.

        """
        in_cache = cls._CACHE_FONT_ADJUSTER.get(base_size)
        if in_cache:
            return in_cache
        text_font = QFont()
        adjusted_font_size = base_size
        for i in range(100):
            text_font.setPointSizeF(adjusted_font_size)
            font_metrics = QFontMetrics(text_font)
            height = font_metrics.height()
            if height < base_size:
                adjusted_font_size += 0.1
            elif height > base_size:
                adjusted_font_size -= 0.1
            elif height == base_size:
                break
        cls._CACHE_FONT_ADJUSTER[base_size] = adjusted_font_size
        return adjusted_font_size


class RLabel(qt_widgets.QLabel, _FontManagerBase):

    def __init__(self, *args, **kwargs):
        kwargs['font_size'] = kwargs.get('font_size', 20)
        super().__init__(*args, **kwargs)


class RCombo(qt_widgets.QComboBox, _FontManagerBase):

    def __init__(self, *args, **kwargs):
        kwargs['font_size'] = kwargs.get('font_size', 18)
        super().__init__(*args, **kwargs)
        self.setStyleSheet(
            """
            QComboBox {
                border: 1px solid black;
                border-radius: 10px;
                padding: 1px 18px 1px 18px;
                min-width: 6em;
            }
            QComboBox QAbstractItemView {
                border: 5px solid black;
                outline: 0;
                margin: -5px;
                border-radius: 10px;
            }
            QComboBox::drop-down {background-color: transparent;}
            QComboBox::down-arrow {image: url(assets/Icon_DownArrow.png); width: 10 px; height: 10 px;}
            """)

    def showPopup(self):
        popup = self.view()
        popup.setFixedHeight(popup.sizeHintForRow(0) * self.count())
        super().showPopup()


class RButton(qt_widgets.QPushButton, _FontManagerBase):

    def __init__(self, *args, **kwargs):
        kwargs['font_size'] = kwargs.get('font_size', 18)
        super().__init__(*args, **kwargs)
        self.setStyleSheet(
            """
            QPushButton { 
                padding: 5px;
                border: 1px solid #1F1F1F;
                min-width: 75px;
                min-height: 20px;
                border-radius: 8px;
                color: black;
            }
            QPushButton:disabled {
                color: gray;
                border: 1px solid grey;
            }
            """)


class RToolBtn(qt_widgets.QToolButton, _FontManagerBase):

    def __init__(self, *args, **kwargs):
        kwargs['font_size'] = kwargs.get('font_size', 17)
        super().__init__(*args, **kwargs)


class RDialog(qt_widgets.QDialog, _FontManagerBase):

    def __init__(self, *args, **kwargs):
        kwargs['font_size'] = kwargs.get('font_size', 19)
        super().__init__(*args, **kwargs)


class RTextEdit(qt_widgets.QTextEdit, _FontManagerBase):

    def __init__(self, *args, **kwargs):
        kwargs['font_size'] = kwargs.get('font_size', 18)
        super().__init__(*args, **kwargs)


class RCheckButton(qt_widgets.QCheckBox, _FontManagerBase):

    def __init__(self, *args, **kwargs):
        kwargs['font_size'] = kwargs.get('font_size', 17)
        super().__init__(*args, **kwargs)


class RLineEdit(qt_widgets.QLineEdit, _FontManagerBase):

    def __init__(self, *args, **kwargs):
        kwargs['font_size'] = kwargs.get('font_size', 18)
        super().__init__(*args, **kwargs)


class RMenu(qt_widgets.QMenu, _FontManagerBase):

    def __init__(self, *args, **kwargs):
        kwargs['font_size'] = kwargs.get('font_size', 18)
        super().__init__(*args, **kwargs)


def screen_infos():
    return sorted([
        {
            "is_primary_screen": screen.is_primary,
            "width_px": screen.width,
            "height_px": screen.height,
            "width_cm": screen.width_mm / 10 if screen.width_mm is not None else 0,
            "height_cm": screen.height_mm / 10 if screen.height_mm is not None else 0,
            "x_start": screen.x,
            "y_start": screen.y, }
        for screen in get_monitors()], key=lambda x: x["width_px"], reverse=True)


def get_machine_guid():
    if sys.platform == "darwin":
        import subprocess
        try:
            result = subprocess.run(
                ["system_profiler", "SPHardwareDataType"],
                capture_output=True,
                text=True
            )
            for line in result.stdout.split("\n"):
                if "Hardware UUID" in line:
                    return line.split()[-1]
        except Exception as e:
            return f"Unknown: '{e}'"
        return "Unknown"
    else:
        import winreg
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography")
            guid, _ = winreg.QueryValueEx(key, "MachineGuid")
            winreg.CloseKey(key)
            return guid
        except Exception as e:
            return f"Error: {e}"


class RProgressBar(qt_widgets.QProgressBar, _FontManagerBase):

    def __init__(self, *args, **kwargs):
        kwargs['font_size'] = kwargs.get('font_size', 18)
        super().__init__(*args, **kwargs)


def warning_msg(title, body, parent, buttons = None):
    warn_box = qt_widgets.QMessageBox(parent)
    warn_box.setIcon(qt_widgets.QMessageBox.NoIcon)
    warn_box.setWindowTitle(title)
    warn_box.setText(body)

    if buttons is None:
        buttons = qt_widgets.QMessageBox.Ok

    warn_box.setStandardButtons(buttons)

    for button in warn_box.buttons():
        button.setStyleSheet("""
            QPushButton {
                padding: 7px 15px;
                border: 1px solid #1F1F1F;
                border-radius: 8px;
                color: black;
            }
        """)
    return warn_box.exec_()
