import html
import json
import multiprocessing
import os
import platform
import sys
import urllib.parse
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer

from PyQt5.QtCore import QUrl
from PyQt5.QtGui import QDesktopServices

from application.settings import Settings


class _AuthHandler(BaseHTTPRequestHandler):
    """
    This is a simple HTTP server that accepts only GET and OPTIONS requests. The HTTP server is called by the browser
    when the login process finishes.

    The intention is to inform the application that the login was successful. The script on the pages passes the
    access_token and refresh_token as query parameters to the application.
    """

    def __init__(self, *args, **kwargs):
        self.login_success_flag = kwargs.pop('login_success_flag')
        super().__init__(*args, **kwargs)

    def _set_headers(self):
        self.send_response(400 if 'error' in self.path else 200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_OPTIONS(self):
        self._set_headers()

    def do_GET(self):
        self._set_headers()
        if 'error' in self.path:
            self.login_success_flag.value = -1
            self.wfile.write(
                b"Login was successful!\nAn issue occurred with the login process please return back to app and try again!")
            return
        parsed_path = urllib.parse.urlparse(self.path)
        query_params = urllib.parse.parse_qs(html.unescape(parsed_path.query))
        _save_login_info(
            query_params.get('access_token')[0],
            query_params.get('refresh_token')[0],
            query_params.get('email')[0],
        )
        self.login_success_flag.value = 1
        self.wfile.write(b"Login was successful!\nClose this tab and return to the Casablanca application")


def _save_login_info(access_token, refresh_token, email):
    """
    This function is responsible for saving user login information to disk after a user logs in using
    Single Sign-On (SSO). This function saves the access token, refresh token, and email address to ensure that the
    user's session can be managed and persisted across application restarts.
    """
    if not os.path.exists("persistent"):
        os.makedirs("persistent")
    with open("persistent/tokens.json", "w") as token_file:
        json.dump(
            {
                'access_token': access_token,
                'refresh_token': refresh_token
            },
            token_file,
        )
    Settings.save_email_from_sso(email)


def _handler_factory(login_success_flag):
    """
    This function's responsibility is to get the is_successful flag from the main process and pass it to the
    instance of the HTTP server.
    """

    def create_handler(*args, **kwargs):
        kwargs['login_success_flag'] = login_success_flag
        return _AuthHandler(*args, **kwargs)

    return create_handler


def _server_subprocess(is_done_var):
    """
    This function is responsible for initiating the HTTP server on the specified port.
    """
    port = 8784
    httpd = HTTPServer(('', port), _handler_factory(is_done_var))
    httpd.serve_forever()


def launch_for_google(
        *,
        app_version: str,
        hardware_info: str,
):
    _launch_url(
        f'https://api2.casablanca.ai/api/sso/google/application/?{_build_query_param(app_version, hardware_info)}'
    )


def launch_for_microsoft(
        *,
        app_version: str,
        hardware_info: str,
):
    _launch_url(
        f'https://api2.casablanca.ai/api/sso/microsoft/application/?{_build_query_param(app_version, hardware_info)}'
    )


def _launch_url(url):
    QDesktopServices.openUrl(QUrl(url))


def _build_query_param(
        app_version,
        hardware_info,
):
    mac_address = uuid.UUID(int=uuid.getnode()).hex[-12:]
    os_version = platform.mac_ver()[0] if sys.platform == "darwin" else platform.win32_ver()[0]
    return '&'.join([
        f'app_version={app_version}',
        f'operating_system={sys.platform}',
        f'mac={mac_address}',
        f'hardware_info={hardware_info}',
        f'os_version={os_version}',
    ])


def start():
    """
    This function initiates the HTTP server in a subprocess and returns the process itself along with a flag.
    """
    login_success_flag = multiprocessing.Value('i', 0, lock=True)
    sub_process = multiprocessing.Process(target=_server_subprocess, args=(login_success_flag,))
    sub_process.start()
    return sub_process, login_success_flag
