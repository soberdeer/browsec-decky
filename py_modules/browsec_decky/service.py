"""Stateful, secret-safe service exposed to the Decky frontend."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Awaitable, Callable

from .api import (
    BrowsecAPI,
    BrowsecAPIError,
    VPNServer,
    authentication_token,
    normalize_servers,
    validate_account,
)
from .runtime import RuntimeErrorSafe, TunnelRuntime
from .storage import SecureStorage


EmitCallback = Callable[[dict[str, Any]], Awaitable[None]]


class BrowsecService:
    def __init__(
        self,
        plugin_dir: Path,
        settings_path: Path,
        runtime_dir: Path,
        emit_state: EmitCallback,
        api: BrowsecAPI | None = None,
    ) -> None:
        self.api = api or BrowsecAPI()
        self.storage = SecureStorage(settings_path)
        self.emit_state = emit_state
        self.lock = asyncio.Lock()
        self.status = "disconnected"
        self.error: str | None = None
        self.servers: dict[str, list[VPNServer]] = {}
        self.settings = self._load_settings()
        self.runtime = TunnelRuntime(plugin_dir, runtime_dir, self._runtime_state)
        self._connect_task: asyncio.Task[Any] | None = None

    def _load_settings(self) -> dict[str, Any]:
        raw = self.storage.load()
        result: dict[str, Any] = {}
        for key in ("email", "access_token", "xray_uuid", "selected_country"):
            value = raw.get(key)
            if isinstance(value, str):
                result[key] = value
        return result

    def _save_settings(self) -> None:
        allowed = {
            key: value
            for key, value in self.settings.items()
            if key
            in {
                "email",
                "access_token",
                "xray_uuid",
                "selected_country",
            }
        }
        self.storage.save(allowed)

    def _clear_expired_session(self) -> None:
        self.settings = {}
        self.servers = {}
        self._save_settings()

    @property
    def logged_in(self) -> bool:
        return all(
            self.settings.get(key)
            for key in ("email", "access_token", "xray_uuid")
        )

    def public_state(self) -> dict[str, Any]:
        available, runtime_error = self.runtime.runtime_status()
        countries = [
            {
                "code": code,
                "name": servers[0].country_name,
                "availability": servers[0].availability,
            }
            for code, servers in self.servers.items()
            if servers
        ]
        countries.sort(key=lambda item: str(item["name"]))
        return {
            "loggedIn": self.logged_in,
            "email": self.settings.get("email") if self.logged_in else None,
            "premium": self.logged_in,
            "status": self.status,
            "error": self.error or (runtime_error if not available else None),
            "runtimeReady": available,
            "selectedCountry": self.settings.get("selected_country"),
            "countries": countries,
            "publicIp": self.runtime.public_ip,
            "killSwitchActive": self.runtime.kill_switch_active,
            "killSwitchAvailable": self.runtime.kill_switch_available,
        }

    async def _emit(self) -> None:
        await self.emit_state(self.public_state())

    async def _runtime_state(self, status: str, error: str | None) -> None:
        self.status = status
        self.error = error
        await self._emit()

    async def initialize(self) -> None:
        try:
            await self.runtime.reset_stale_kill_switch()
        except RuntimeErrorSafe as exc:
            self.error = str(exc)
            await self._emit()
            return
        if not self.logged_in:
            await self._emit()
            return
        try:
            async with self.lock:
                await self._refresh_locked()
        except BrowsecAPIError as exc:
            if exc.status_code in (401, 403):
                self._clear_expired_session()
                self.error = "Your Browsec session expired. Sign in again."
            else:
                self.error = str(exc)
        await self._emit()

    async def get_state(self) -> dict[str, Any]:
        return self.public_state()

    async def login(self, email: str, password: str) -> dict[str, Any]:
        async with self.lock:
            self.error = None
            try:
                authentication = await asyncio.to_thread(
                    self.api.login,
                    email,
                    password,
                )
                initial_token = authentication_token(authentication)
                account = await asyncio.to_thread(self.api.get_account, initial_token)
                account_email, token, xray_uuid = validate_account(account)
                self.settings = {
                    "email": account_email,
                    "access_token": token,
                    "xray_uuid": xray_uuid,
                }
                self._save_settings()
                await self._refresh_locked()
            except (BrowsecAPIError, RuntimeErrorSafe) as exc:
                self.error = str(exc)
            await self._emit()
            return self.public_state()

    async def _refresh_locked(self) -> None:
        token = self.settings.get("access_token")
        if not token:
            raise BrowsecAPIError("Sign in to Browsec first")
        account = await asyncio.to_thread(self.api.get_account, token)
        email, refreshed_token, xray_uuid = validate_account(account)
        country = await asyncio.to_thread(self.api.detect_user_country)
        payload = await asyncio.to_thread(
            self.api.get_servers,
            refreshed_token,
            country,
        )
        self.servers = normalize_servers(payload)
        selected = self.settings.get("selected_country")
        if selected not in self.servers:
            selected = next(iter(sorted(self.servers)))
        self.settings.update(
            {
                "email": email,
                "access_token": refreshed_token,
                "xray_uuid": xray_uuid,
                "selected_country": selected,
            }
        )
        self._save_settings()
        self.error = None

    async def refresh(self) -> dict[str, Any]:
        async with self.lock:
            try:
                await self._refresh_locked()
            except BrowsecAPIError as exc:
                self.error = str(exc)
            await self._emit()
            return self.public_state()

    async def select_country(self, country: str) -> dict[str, Any]:
        async with self.lock:
            if self.status != "disconnected":
                self.error = "Disconnect before changing the VPN location"
            elif country not in self.servers:
                self.error = "That VPN location is not available"
            else:
                self.settings["selected_country"] = country
                self._save_settings()
                self.error = None
            await self._emit()
            return self.public_state()

    async def connect(self) -> dict[str, Any]:
        current_task = asyncio.current_task()
        if current_task is None:
            raise RuntimeError("Connect must run inside an asyncio task")

        async with self.lock:
            if (
                self._connect_task is not None
                and not self._connect_task.done()
                and self._connect_task is not current_task
            ):
                return self.public_state()
            self.error = None
            try:
                if not self.logged_in:
                    raise BrowsecAPIError("Sign in to Browsec first")
                if not self.servers:
                    await self._refresh_locked()
                country = self.settings.get("selected_country")
                candidates = self.servers.get(country or "", [])
                if not candidates:
                    raise BrowsecAPIError("No server is available for this location")
                xray_uuid = self.settings.get("xray_uuid")
                if not xray_uuid:
                    raise BrowsecAPIError("The Browsec Xray credential is missing")
            except (BrowsecAPIError, RuntimeErrorSafe) as exc:
                self.status = "disconnected"
                self.error = str(exc)
                await self._emit()
                return self.public_state()

            self._connect_task = current_task

        last_error: Exception | None = None
        cancelled = False
        try:
            for server in candidates[:3]:
                try:
                    await self.runtime.start(
                        server,
                        xray_uuid,
                        include_ipv6=True,
                    )
                    last_error = None
                    break
                except RuntimeErrorSafe as exc:
                    last_error = exc
        except asyncio.CancelledError:
            cancelled = True
            try:
                await self.runtime.stop()
            except RuntimeErrorSafe as exc:
                last_error = exc
        except Exception:
            last_error = RuntimeErrorSafe(
                "The VPN connection failed unexpectedly"
            )

        async with self.lock:
            if self._connect_task is current_task:
                self._connect_task = None
            if cancelled:
                self.status = "disconnected"
                self.error = str(last_error) if last_error else None
            elif last_error is not None:
                self.status = "disconnected"
                self.error = str(last_error)
            await self._emit()
            return self.public_state()

    async def _cancel_connection(self) -> None:
        task = self._connect_task
        current_task = asyncio.current_task()
        if task is None or task is current_task or task.done():
            return
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    async def disconnect(self) -> dict[str, Any]:
        await self._cancel_connection()
        async with self.lock:
            try:
                await self.runtime.stop()
                self.error = None
            except RuntimeErrorSafe as exc:
                self.status = "disconnected"
                self.error = str(exc)
            await self._emit()
            return self.public_state()

    async def logout(self) -> dict[str, Any]:
        await self._cancel_connection()
        async with self.lock:
            stop_error: str | None = None
            try:
                await self.runtime.stop()
            except RuntimeErrorSafe as exc:
                stop_error = str(exc)
            token = self.settings.get("access_token")
            self.settings = {}
            self.servers = {}
            self.storage.clear()
            if token:
                await asyncio.to_thread(self.api.destroy_token, token)
            self.error = stop_error
            await self._emit()
            return self.public_state()

    async def shutdown(self) -> None:
        await self._cancel_connection()
        async with self.lock:
            await self.runtime.stop()
