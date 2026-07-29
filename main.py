"""Decky Loader entrypoint for Browsec Decky."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import decky


PLUGIN_DIR = Path(__file__).resolve().parent
PY_MODULES = PLUGIN_DIR / "py_modules"
if str(PY_MODULES) not in sys.path:
    sys.path.insert(0, str(PY_MODULES))

from browsec_decky.service import BrowsecService  # noqa: E402


def _decky_directory(current_name: str, legacy_name: str) -> Path:
    value = getattr(decky, current_name, "") or getattr(decky, legacy_name, "")
    if not value:
        raise RuntimeError(f"Decky did not provide {current_name}")
    return Path(value)


class Plugin:
    service: BrowsecService

    async def _emit_state(self, state: dict) -> None:
        await decky.emit("state_changed", state)

    async def _main(self) -> None:
        self.service = BrowsecService(
            plugin_dir=PLUGIN_DIR,
            settings_path=_decky_directory(
                "DECKY_PLUGIN_SETTINGS_DIR",
                "DECKY_SETTINGS_DIR",
            )
            / "settings.json",
            runtime_dir=_decky_directory(
                "DECKY_PLUGIN_RUNTIME_DIR",
                "DECKY_RUNTIME_DIR",
            ),
            emit_state=self._emit_state,
        )
        self.loop = asyncio.get_running_loop()
        self.loop.create_task(self.service.initialize())
        decky.logger.info("Browsec Decky initialized")

    async def get_state(self) -> dict:
        return await self.service.get_state()

    async def login(self, email: str, password: str) -> dict:
        return await self.service.login(email, password)

    async def refresh(self) -> dict:
        return await self.service.refresh()

    async def select_country(self, country: str) -> dict:
        return await self.service.select_country(country)

    async def connect(self) -> dict:
        return await self.service.connect()

    async def disconnect(self) -> dict:
        return await self.service.disconnect()

    async def set_kill_switch(self, enabled: bool) -> dict:
        return await self.service.set_kill_switch(enabled)

    async def logout(self) -> dict:
        return await self.service.logout()

    async def _unload(self) -> None:
        await self.service.shutdown()
        decky.logger.info("Browsec Decky unloaded")

    async def _uninstall(self) -> None:
        await self.service.shutdown()
        self.service.storage.clear()
        decky.logger.info("Browsec Decky settings removed")
