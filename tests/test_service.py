import asyncio
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parents[1] / "py_modules"))

from browsec_decky.service import BrowsecService


class PublicStateTests(unittest.TestCase):
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
            self.assertTrue(state["killSwitchEnabled"])
            self.assertFalse(state["killSwitchActive"])

    def test_kill_switch_is_enabled_by_default_and_can_be_disabled(self):
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

            self.assertTrue(service.public_state()["killSwitchEnabled"])
            state = asyncio.run(service.set_kill_switch(False))
            self.assertFalse(state["killSwitchEnabled"])

            reloaded = BrowsecService(
                plugin_dir=root,
                settings_path=root / "settings.json",
                runtime_dir=root / "runtime-2",
                emit_state=emit_state,
            )
            self.assertFalse(reloaded.public_state()["killSwitchEnabled"])
