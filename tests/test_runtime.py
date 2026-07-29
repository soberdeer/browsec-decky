import asyncio
import socket
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).parents[1] / "py_modules"))

from browsec_decky.api import VPNServer
from browsec_decky.runtime import TunnelRuntime


class Response:
    def __init__(self, value: bytes):
        self.value = value

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc_value, _traceback):
        return False

    def read(self, _limit: int) -> bytes:
        return self.value


class PublicIPTests(unittest.TestCase):
    def test_public_ip_check_uses_verified_https_opener_and_fallback(self):
        class Opener:
            def __init__(self):
                self.requests = []

            def open(self, request, timeout):
                self.requests.append((request, timeout))
                if len(self.requests) == 1:
                    raise urllib.error.URLError(
                        socket.gaierror(-2, "host not found")
                    )
                return Response(b"203.0.113.7\n")

        opener = Opener()
        with patch("browsec_decky.runtime._https_opener", return_value=opener):
            public_ip, error = TunnelRuntime._fetch_public_ip_sync()

        self.assertEqual(public_ip, "203.0.113.7")
        self.assertIsNone(error)
        self.assertEqual(len(opener.requests), 2)
        self.assertEqual(opener.requests[0][1], 6)
        self.assertEqual(
            opener.requests[0][0].get_header("Cache-control"),
            "no-cache",
        )

    def test_public_ip_check_reports_each_failure(self):
        class Opener:
            def open(self, request, timeout):
                del timeout
                raise urllib.error.URLError(
                    socket.gaierror(-2, request.host)
                )

        with patch("browsec_decky.runtime._https_opener", return_value=Opener()):
            public_ip, error = TunnelRuntime._fetch_public_ip_sync()

        self.assertIsNone(public_ip)
        self.assertIn("checkip.amazonaws.com: gaierror:", error or "")
        self.assertIn("api.ipify.org: gaierror:", error or "")
        self.assertIn("icanhazip.com: gaierror:", error or "")


class KillSwitchLifecycleTests(unittest.TestCase):
    def test_unexpected_stop_preserves_switch_but_normal_stop_removes_it(self):
        class Switch:
            available = True
            active = True

            def __init__(self):
                self.disable_calls = 0

            def disable(self):
                self.disable_calls += 1
                self.active = False

        async def exercise():
            async def on_state(_status, _error):
                return None

            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                runtime = TunnelRuntime(root, root / "runtime", on_state)
                switch = Switch()
                runtime.kill_switch = switch

                await runtime.stop(
                    release_kill_switch=False,
                    emit_state=False,
                )
                self.assertTrue(switch.active)
                self.assertEqual(switch.disable_calls, 0)

                await runtime.stop()
                self.assertFalse(switch.active)
                self.assertEqual(switch.disable_calls, 1)

        asyncio.run(exercise())

    def test_live_enable_allows_only_the_current_transport_server(self):
        class Switch:
            available = True
            active = False

            def __init__(self):
                self.server = None

            def enable(self, server):
                self.server = server
                self.active = True

        async def exercise():
            async def on_state(_status, _error):
                return None

            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                runtime = TunnelRuntime(root, root / "runtime", on_state)
                switch = Switch()
                runtime.kill_switch = switch
                runtime._transport_server = VPNServer(
                    ip="203.0.113.8",
                    xsni="example.org",
                    country_code="nl",
                    country_name="Netherlands",
                )

                await runtime.enable_kill_switch()
                self.assertTrue(switch.active)
                self.assertEqual(switch.server, "203.0.113.8")

        asyncio.run(exercise())


if __name__ == "__main__":
    unittest.main()
