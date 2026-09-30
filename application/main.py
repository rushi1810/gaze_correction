import os
import sys
import stat

os.environ["PYTHONPATH"] = os.path.abspath(os.path.join(os.getcwd(), "Resources/python/" if sys.platform == "darwin" else "embeddable-python"))

if sys.platform == "darwin":
    def set_matplotlib_config():
        matplotlib_configdir = os.path.abspath(os.path.join("persistent", "tmp"))
        if not os.path.exists(matplotlib_configdir):
            os.makedirs(matplotlib_configdir, exist_ok=True)
            os.chmod(matplotlib_configdir, stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)
        os.environ["MPLCONFIGDIR"] = matplotlib_configdir

    set_matplotlib_config()

    from matplotlib import font_manager

    original_get_font = font_manager.get_font

    def patched_get_font(fontpath, hinting_factor=None):
        problematic_fonts = {
            "Apple Color Emoji.ttc",
            "LastResort.otf",
            "PingFangUI.ttc",
            "NISC18030.ttf"
        }
        if any(font in fontpath for font in problematic_fonts):
            print(f"Skipping unsupported font: {fontpath}")
            return None
        else:
            return original_get_font(fontpath, hinting_factor)

    font_manager.get_font = patched_get_font

    new_openssl_lib_path = "/usr/local/lib/casablanca/openssl/lib"
    current_dyld_lib_path = os.environ.get('DYLD_LIBRARY_PATH', '')
    os.environ['DYLD_LIBRARY_PATH'] = f"{new_openssl_lib_path}:{current_dyld_lib_path}"

import logging
import logging.config
import warnings
import datetime
import shutil
import faulthandler
import time

import logging.handlers
import queue
from logging.handlers import QueueListener
import atexit

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

logger = logging.getLogger(__name__)
warnings.filterwarnings("ignore", category=UserWarning, module="moviepy")
log_queue = queue.Queue()


def configure_logging():
    """
    Configure python logging.
    """

    os.makedirs("persistent", exist_ok=True)
    log_file = os.path.abspath(os.path.join("persistent", "app.log"))

    faulthandler_log = os.path.abspath(os.path.join("persistent", "faulthandler.log"))
    faulhandler_log_file = open(faulthandler_log, 'a')
    faulhandler_log_file.write(f"\nDate: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    faulthandler.enable(file=faulhandler_log_file)

    atexit.register(faulhandler_log_file.close)

    logging_cfg = {
        "version": 1,
        "formatters": {
            "with_ms": {
                "format": "[%(levelname)s|%(module)s|L%(lineno)d] %(asctime)s.%(msecs)03d: %(message)s",
                "datefmt": "%Y-%m-%dT%H:%M:%S%z"
            },
        },
        "handlers": {
            "console_handler": {
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
                "formatter": "with_ms",
            },
            "log_file_handler": {
                "level": "INFO",
                "formatter": "with_ms",
                "class": "logging.handlers.RotatingFileHandler",
                "filename": log_file,
                "mode": "a",
                "maxBytes": 100000,
                "backupCount": 1
            },
            "queue_handler": {
                "class": "logging.handlers.QueueHandler",
                "queue": log_queue,
                "formatter": "with_ms"
            }
        },
        "loggers": {
            # A logger for uncaught exception. Do not print into console to prevent scrolling away
            # stderr output, which otherwise cannot be intercepted (e.g. pytorch anomaly detection).
            "uncaught_exception": {
                "level": "INFO",
                "handlers": ["log_file_handler"],
                "propagate": 0,
            }
        },
        "root": {
            "level": "INFO",
            "handlers": ["queue_handler"]
        },
        "disable_existing_loggers": False
    }

    logging.config.dictConfig(logging_cfg)
    return log_file


def close_other_running_casablanca_instances():
    import psutil
    try:
        current_process = psutil.Process()
        (current_process_interpreter_path, current_process_script_name) = current_process.cmdline()[:2]
        for process in psutil.process_iter(attrs=['pid', 'name']):
            if process.info['name'] == 'python.exe' and process.info['pid'] != current_process.pid:
                try:
                    (other_process_interpreter_path, other_process_script_name) = process.cmdline()[:2]
                    if (current_process_script_name == other_process_script_name
                            and current_process_interpreter_path == other_process_interpreter_path):
                        logger.info("Another instance of Casablanca is already open. Closing previous instance.")
                        process.kill()
                        time.sleep(3)
                        return
                except ValueError:
                    pass
    except (psutil.AccessDenied, psutil.NoSuchProcess) as e:
        logger.error(f"Error while checking whether Casablanca is already running: {e}")


def apply_patch():
    if os.path.exists("tmp/updated.txt"):
        with open("tmp/updated.txt", "r") as f:
            is_updated_ = f.read()
        if is_updated_:
            for root, dirs, files in (os.walk("tmp")):
                trimmed_target_dir = root[len("tmp") + 1:]
                if len(trimmed_target_dir) > 0 and not os.path.exists(trimmed_target_dir):
                    os.mkdir(trimmed_target_dir)
                for file_name in files:
                    current_path = os.path.join(root, file_name).replace("\\", "/")
                    file_path = os.path.join(root[len("tmp") + 1:], file_name).replace("\\", "/")
                    if "updated.txt" not in file_path:
                        logger.info(f"Moving {current_path} to {file_path}")
                        shutil.move(current_path, file_path)
                        logger.info(f"Moved {current_path} to {file_path}")
            try:
                shutil.rmtree("tmp")
                logger.info(f"Update successful, updated to version {is_updated_}")
            except (IOError, PermissionError) as e:
                logger.error(f"Encountered an error while deleting tmp directory: {e}")
            return True
    else:
        logger.info("No update found in tmp folder, hence no update is performed")
        return False


def apply_components_patch():
    if os.path.exists("components"):
        try:
            from components.handle_components import distribute_components
            distribute_components()
            logger.info("Components updated")
            return True
        except ModuleNotFoundError:
            logger.info("No components found, hence no components update is performed")
            return False
        finally:
            try:
                shutil.rmtree("components")
            except (IOError, PermissionError) as e:
                logger.error(f"Encountered an error while deleting components directory: {e}")
    else:
        logger.info("No components found, hence no components update is performed")
        return False


def apply_rollback():
    if os.path.exists("rollback.txt"):
        with open("rollback.txt", "r") as f:
            version = f.read()
        if version:
            from application.rollback import RollbackCasablanca
            RollbackCasablanca.restore(target_version=version)
            os.remove("rollback.txt")
    else:
        logger.info("No rollback.txt found, hence no rollback is performed")


if __name__ == "__main__":
    log_file = configure_logging()
    log_listener = QueueListener(
        log_queue,
        logging.StreamHandler(),
        logging.FileHandler(log_file),
    )
    log_listener.start()
    atexit.register(log_listener.stop)
    if sys.platform != "darwin":
        close_other_running_casablanca_instances()
    apply_patch()
    apply_components_patch()
    apply_rollback()
    from application.main_cyt import main

    main()
