import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parents[1] / "py_modules"))

from browsec_decky.storage import SecureStorage


class StorageTests(unittest.TestCase):
    def test_save_is_private_and_atomic(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state" / "settings.json"
            storage = SecureStorage(path)
            storage.save({"access_token": "secret"})
            self.assertEqual(storage.load(), {"access_token": "secret"})
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
            self.assertEqual(os.stat(path.parent).st_mode & 0o777, 0o700)
            self.assertEqual(json.loads(path.read_text()), {"access_token": "secret"})

            storage.clear()
            self.assertFalse(path.exists())

