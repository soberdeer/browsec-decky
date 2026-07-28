import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parents[1] / "py_modules"))

from browsec_decky.api import (
    BrowsecAPIError,
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
