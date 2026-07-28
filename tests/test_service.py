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
            serialized = repr(asyncio.run(service.get_state()))
            self.assertNotIn("top-secret-token", serialized)
            self.assertNotIn("cf9b437a", serialized)
            self.assertIn("deck@example.com", serialized)

