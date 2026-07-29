import io
import sys
import socket
import unittest
import urllib.error
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parents[1] / "py_modules"))

from browsec_decky.api import (
    BrowsecAPIError,
    _http_error_message,
    authentication_token,
    normalize_servers,
    validate_account,
)


class AccountTests(unittest.TestCase):
    def test_valid_premium_account(self):
        account = {
            "premium": True,
            "email": "deck@example.com",
            "credentials": {
                "access_token": "a" * 32,
                "xray_uuid": "cf9b437a-b26d-416a-9400-51e76ec8b0ca",
            },
        }
        self.assertEqual(
            validate_account(account),
            (
                "deck@example.com",
                "a" * 32,
                "cf9b437a-b26d-416a-9400-51e76ec8b0ca",
            ),
        )

    def test_free_account_is_rejected(self):
        with self.assertRaisesRegex(BrowsecAPIError, "Premium"):
            validate_account({"premium": False})

    def test_login_token_can_be_top_level_or_nested(self):
        self.assertEqual(authentication_token({"access_token": "a" * 16}), "a" * 16)
        self.assertEqual(
            authentication_token({"credentials": {"access_token": "b" * 16}}),
            "b" * 16,
        )


class ServerTests(unittest.TestCase):
    def test_invalid_servers_are_discarded_and_valid_servers_are_sorted(self):
        payload = {
            "countries": {
                "nl": {
                    "premium_servers": [
                        {
                            "ip": ["203.0.113.2", "not-an-ip", "203.0.113.1"],
                            "xsni": ["two.example", "bad.example", "one.example"],
                            "source_ip_lrc": [2, 7, 1],
                            "availability": {"xray": [20, 1, 10]},
                        }
                    ]
                }
            }
        }
        servers = normalize_servers(payload)["nl"]
        self.assertEqual([server.ip for server in servers], ["203.0.113.1", "203.0.113.2"])
        self.assertEqual(servers[0].xsni, "one.example")
        self.assertEqual(servers[0].source_ip_lrc, 1)


class FailingOpener:
    def open(self, _request, timeout):
        self.timeout = timeout
        raise urllib.error.URLError(socket.gaierror(-2, "host not found"))


class NetworkErrorTests(unittest.TestCase):
    def test_request_uses_official_desktop_http_identity(self):
        class InspectingOpener:
            def open(self, request, timeout):
                self.request = request
                raise urllib.error.HTTPError(
                    request.full_url,
                    401,
                    "Unauthorized",
                    {},
                    io.BytesIO(b'{"ok":false,"error_code":9}'),
                )

        opener = InspectingOpener()
        api = __import__(
            "browsec_decky.api",
            fromlist=["BrowsecAPI"],
        ).BrowsecAPI(
            api_urls=("https://d5.example/api/",),
            opener=opener,
        )
        with self.assertRaises(BrowsecAPIError) as raised:
            api.login("deck@example.com", "password")
        self.assertEqual(raised.exception.status_code, 401)
        self.assertEqual(opener.request.get_header("User-agent"), "axios/1.16.1")
        self.assertEqual(
            opener.request.get_header("Accept"),
            "application/json, text/plain, */*",
        )

    def test_http_error_includes_numeric_browsec_error_code(self):
        message = _http_error_message(
            401,
            {"ok": False, "error_code": 9},
            b'{"ok":false,"error_code":9}',
        )
        self.assertEqual(
            message,
            'Browsec API HTTP 401: {"ok":false,"error_code":9}',
        )

    def test_network_failures_identify_each_host_without_secrets(self):
        opener = FailingOpener()
        api = __import__(
            "browsec_decky.api",
            fromlist=["BrowsecAPI"],
        ).BrowsecAPI(
            api_urls=("https://d5.example/api/", "https://d6.example/api/"),
            opener=opener,
        )
        with self.assertRaises(BrowsecAPIError) as raised:
            api.login("deck@example.com", "do-not-display")
        message = str(raised.exception)
        self.assertIn("d5.example: gaierror:", message)
        self.assertIn("d6.example: gaierror:", message)
        self.assertNotIn("do-not-display", message)
        self.assertEqual(opener.timeout, 12)
