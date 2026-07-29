import asyncio
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parents[1] / "py_modules"))

from browsec_decky.api import BrowsecAPIError, VPNServer
from browsec_decky.service import BrowsecService


class PublicStateTests(unittest.TestCase):
    def test_expired_startup_session_is_cleared_once(self):
        async def emit_state(_state):
            return None

        class ExpiredAPI:
            def get_account(self, _token):
                raise BrowsecAPIError(
                    "Browsec API HTTP 401: rejected",
                    status_code=401,
                )

        class Runtime:
            public_ip = None
            kill_switch_active = False
            kill_switch_available = True

            async def reset_stale_kill_switch(self):
                return None

            def runtime_status(self):
                return True, None

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings_path = root / "settings.json"
            settings_path.write_text(
                (
                    '{"access_token":"expired-token-value",'
                    '"email":"deck@example.com",'
                    '"kill_switch_enabled":false,'
                    '"selected_country":"nl",'
                    '"xray_uuid":"cf9b437a-b26d-416a-9400-51e76ec8b0ca"}'
                ),
                encoding="utf-8",
            )
            service = BrowsecService(
                plugin_dir=root,
                settings_path=settings_path,
                runtime_dir=root / "runtime",
                emit_state=emit_state,
                api=ExpiredAPI(),
            )
            service.runtime = Runtime()

            asyncio.run(service.initialize())

            state = service.public_state()
            self.assertFalse(state["loggedIn"])
            self.assertNotIn("killSwitchEnabled", state)
            self.assertEqual(
                state["error"],
                "Your Browsec session expired. Sign in again.",
            )
            saved = settings_path.read_text(encoding="utf-8")
            self.assertNotIn("expired-token-value", saved)
            self.assertNotIn("xray_uuid", saved)
            self.assertNotIn("kill_switch_enabled", saved)

    def test_backend_state_never_exposes_credentials(self):
        async def emit_state(_state):
            return None

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            service = BrowsecService(
                plugin_dir=root,
                settings_path=root / "settings.json",
                runtime_dir=root / "runtime",
                emit_state=emit_state,
            )
            service.settings = {
                "email": "deck@example.com",
                "access_token": "top-secret-token",
                "xray_uuid": "cf9b437a-b26d-416a-9400-51e76ec8b0ca",
                "selected_country": "nl",
            }
            state = asyncio.run(service.get_state())
            serialized = repr(state)
            self.assertNotIn("top-secret-token", serialized)
            self.assertNotIn("cf9b437a", serialized)
            self.assertIn("deck@example.com", serialized)
            self.assertNotIn("killSwitchEnabled", state)
            self.assertFalse(state["killSwitchActive"])

    def test_legacy_kill_switch_disable_setting_is_ignored(self):
        async def emit_state(_state):
            return None

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings_path = root / "settings.json"
            settings_path.write_text(
                '{"kill_switch_enabled":false}',
                encoding="utf-8",
            )
            service = BrowsecService(
                plugin_dir=root,
                settings_path=settings_path,
                runtime_dir=root / "runtime",
                emit_state=emit_state,
            )

            self.assertNotIn("kill_switch_enabled", service.settings)
            self.assertNotIn("killSwitchEnabled", service.public_state())

    def test_disconnect_cancels_connection_in_progress(self):
        async def exercise():
            emitted = []

            async def emit_state(state):
                emitted.append(state)

            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                service = BrowsecService(
                    plugin_dir=root,
                    settings_path=root / "settings.json",
                    runtime_dir=root / "runtime",
                    emit_state=emit_state,
                )

                class Runtime:
                    public_ip = None
                    kill_switch_active = False
                    kill_switch_available = True

                    def __init__(self):
                        self.started = asyncio.Event()
                        self.cancelled = False
                        self.stop_calls = 0
                        self.running = False
                        self.start_calls = 0

                    @property
                    def is_running(self):
                        return self.running

                    def runtime_status(self):
                        return True, None

                    async def start(self, *_args, **_kwargs):
                        self.start_calls += 1
                        self.running = True
                        await service._runtime_state("connecting", None)
                        self.started.set()
                        try:
                            await asyncio.Event().wait()
                        except asyncio.CancelledError:
                            self.cancelled = True
                            raise

                    async def stop(self):
                        self.stop_calls += 1
                        self.running = False
                        await service._runtime_state("disconnected", None)

                runtime = Runtime()
                service.runtime = runtime
                service.settings = {
                    "email": "deck@example.com",
                    "access_token": "a" * 32,
                    "xray_uuid": "cf9b437a-b26d-416a-9400-51e76ec8b0ca",
                    "selected_country": "nl",
                }
                service.servers = {
                    "nl": [
                        VPNServer(
                            ip="203.0.113.8",
                            xsni="example.org",
                            country_code="nl",
                            country_name="Netherlands",
                        )
                    ]
                }

                connection = asyncio.create_task(service.connect())
                await asyncio.wait_for(runtime.started.wait(), timeout=1)
                state = await asyncio.wait_for(service.disconnect(), timeout=1)
                await asyncio.wait_for(connection, timeout=1)

                self.assertTrue(runtime.cancelled)
                self.assertGreaterEqual(runtime.stop_calls, 1)
                self.assertEqual(runtime.start_calls, 1)
                self.assertEqual(state["status"], "disconnected")
                self.assertIsNone(state["error"])
                self.assertTrue(
                    any(item["status"] == "connecting" for item in emitted)
                )

        asyncio.run(exercise())
