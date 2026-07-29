"""Root-owned lifecycle manager for the bundled Browsec networking runtime."""

from __future__ import annotations

import asyncio
import fcntl
import hashlib
import ipaddress
import json
import os
import signal
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Awaitable, Callable

from .api import VPNServer, _https_opener
from .config import build_browbox_config, build_browray_config
from .firewall import KillSwitchError, NftKillSwitch


BINARY_HASHES = {
    "browray": "b2c525e082cf2fef460499c88838d355f0b9bfb5a00bdb3eaa99b6af63825006",
    "browbox": "68aeab83cc4ab2659a5b92232261a20746ccdafc3b3d1e19b2d63247eec3bbf7",
}
PUBLIC_IP_URLS = (
    "https://checkip.amazonaws.com",
    "https://api.ipify.org",
    "https://icanhazip.com",
)


class RuntimeErrorSafe(RuntimeError):
    """A runtime failure whose message contains no credentials."""


StateCallback = Callable[[str, str | None], Awaitable[None]]


class TunnelRuntime:
    def __init__(
        self,
        plugin_dir: Path,
        runtime_dir: Path,
        on_state: StateCallback,
    ) -> None:
        self.plugin_dir = plugin_dir.resolve()
        self.runtime_dir = runtime_dir.resolve()
        self.bin_dir = self.plugin_dir / "bin"
        self.on_state = on_state
        self.browray: asyncio.subprocess.Process | None = None
        self.browbox: asyncio.subprocess.Process | None = None
        self._log_tasks: list[asyncio.Task[None]] = []
        self._watch_task: asyncio.Task[None] | None = None
        self._lock_handle: Any = None
        self._stopping = False
        self.public_ip: str | None = None
        self._public_ip_error: str | None = None
        self.kill_switch = NftKillSwitch()
        self._transport_server: VPNServer | None = None
        self._verification_signature: tuple[Any, ...] | None = None
        self._verification_result: tuple[bool, str | None] | None = None

    @property
    def kill_switch_active(self) -> bool:
        return self.kill_switch.active

    @property
    def kill_switch_available(self) -> bool:
        return self.kill_switch.available

    @staticmethod
    async def _run_firewall_operation(
        operation: Callable[..., None],
        *arguments: str,
    ) -> None:
        """Finish an nftables transaction before honoring cancellation."""

        task = asyncio.create_task(
            asyncio.to_thread(operation, *arguments)
        )
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            await task
            raise

    async def enable_kill_switch(self) -> None:
        if self._transport_server is None:
            raise RuntimeErrorSafe(
                "Connect to a Browsec server before enabling the kill switch"
            )
        try:
            await self._run_firewall_operation(
                self.kill_switch.enable,
                self._transport_server.ip,
            )
        except KillSwitchError as exc:
            raise RuntimeErrorSafe(str(exc)) from exc

    async def disable_kill_switch(self) -> None:
        try:
            await self._run_firewall_operation(self.kill_switch.disable)
        except KillSwitchError as exc:
            raise RuntimeErrorSafe(str(exc)) from exc

    async def reset_stale_kill_switch(self) -> None:
        """Restore networking after a Decky/plugin restart."""

        await self.disable_kill_switch()

    def runtime_status(self) -> tuple[bool, str | None]:
        if os.name != "posix" or not Path("/proc").is_dir():
            return False, "Browsec Decky requires SteamOS or another Linux system"
        if os.geteuid() != 0:
            return False, "Decky must run this plugin with root privileges"

        signature: list[Any] = []
        for name in BINARY_HASHES:
            path = self.bin_dir / name
            try:
                stat = path.lstat()
                signature.append(
                    (
                        name,
                        stat.st_dev,
                        stat.st_ino,
                        stat.st_size,
                        stat.st_mtime_ns,
                        stat.st_mode,
                    )
                )
            except FileNotFoundError:
                signature.append((name, None))
        current_signature = tuple(signature)
        if (
            current_signature == self._verification_signature
            and self._verification_result is not None
        ):
            return self._verification_result

        for name, expected in BINARY_HASHES.items():
            path = self.bin_dir / name
            if not path.is_file():
                result = (False, f"The bundled {name} runtime is missing")
                break
            if path.is_symlink():
                result = (
                    False,
                    f"The bundled {name} runtime must not be a symbolic link",
                )
                break
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest != expected:
                result = (
                    False,
                    f"The bundled {name} runtime failed integrity verification",
                )
                break
            if not os.access(path, os.X_OK):
                result = (False, f"The bundled {name} runtime is not executable")
                break
        else:
            result = (True, None)
        self._verification_signature = current_signature
        self._verification_result = result
        return result

    def _acquire_lock(self) -> None:
        lock_path = Path("/run/browsec-decky.lock")
        handle = lock_path.open("a+", encoding="utf-8")
        os.chmod(lock_path, 0o600)
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            handle.close()
            raise RuntimeErrorSafe("Another Browsec Decky tunnel is already running") from exc
        handle.seek(0)
        handle.truncate()
        handle.write(str(os.getpid()))
        handle.flush()
        self._lock_handle = handle

    def _release_lock(self) -> None:
        if self._lock_handle is None:
            return
        try:
            fcntl.flock(self._lock_handle.fileno(), fcntl.LOCK_UN)
        finally:
            self._lock_handle.close()
            self._lock_handle = None

    def _desktop_conflict(self) -> bool:
        own_pids = {
            process.pid
            for process in (self.browray, self.browbox)
            if process is not None and process.returncode is None
        }
        for entry in Path("/proc").iterdir():
            if not entry.name.isdigit() or int(entry.name) in own_pids:
                continue
            try:
                raw = (entry / "cmdline").read_bytes()
                executable = Path(os.readlink(entry / "exe")).name
            except (FileNotFoundError, PermissionError, ProcessLookupError, OSError):
                continue
            command = raw.replace(b"\0", b" ").decode("utf-8", "replace").lower()
            if (
                executable in {"browray", "browbox"}
                or "/browray " in command
                or "/browbox " in command
            ):
                return True

        interfaces = Path("/sys/class/net")
        if interfaces.is_dir():
            for interface in interfaces.iterdir():
                if interface.name.startswith("browbox") and interface.name != "browbox-decky":
                    return True
        return False

    async def _cleanup_stale_owned_processes(self) -> None:
        """Kill only orphaned processes launched with this plugin's configs."""

        expected = {
            str((self.bin_dir / "browray").resolve()): str(
                self.runtime_dir / "browray-config.json"
            ),
            str((self.bin_dir / "browbox").resolve()): str(
                self.runtime_dir / "browbox-config.json"
            ),
        }
        stale: list[int] = []
        for entry in Path("/proc").iterdir():
            if not entry.name.isdigit() or int(entry.name) == os.getpid():
                continue
            try:
                executable = os.readlink(entry / "exe")
                arguments = [
                    value.decode("utf-8", "replace")
                    for value in (entry / "cmdline").read_bytes().split(b"\0")
                    if value
                ]
                pid = int(entry.name)
            except (FileNotFoundError, PermissionError, ProcessLookupError, OSError):
                continue
            config = expected.get(executable)
            try:
                owns_process_group = os.getpgid(pid) == pid
            except ProcessLookupError:
                continue
            if config in arguments and owns_process_group:
                stale.append(pid)

        for pid in stale:
            try:
                os.killpg(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        if stale:
            await asyncio.sleep(0.5)
        for pid in stale:
            try:
                os.killpg(pid, 0)
            except ProcessLookupError:
                continue
            try:
                os.killpg(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

    def _write_config(self, name: str, value: dict[str, Any]) -> Path:
        self.runtime_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.runtime_dir, 0o700)
        path = self.runtime_dir / name
        temporary = self.runtime_dir / f".{name}.tmp"
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW,
            0o600,
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(value, handle, separators=(",", ":"))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
            os.chmod(path, 0o600)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
        return path

    async def _consume_logs(
        self,
        process: asyncio.subprocess.Process,
        ready: asyncio.Event,
        marker: bytes,
    ) -> None:
        stream = process.stdout
        if stream is None:
            return
        while True:
            line = await stream.readline()
            if not line:
                return
            if marker.lower() in line.lower():
                ready.set()

    async def _wait_ready(
        self,
        process: asyncio.subprocess.Process,
        ready: asyncio.Event,
        name: str,
        timeout: float = 15,
    ) -> None:
        wait_ready = asyncio.create_task(ready.wait())
        wait_exit = asyncio.create_task(process.wait())
        try:
            done, _pending = await asyncio.wait(
                (wait_ready, wait_exit),
                timeout=timeout,
                return_when=asyncio.FIRST_COMPLETED,
            )
        finally:
            for task in (wait_ready, wait_exit):
                if not task.done():
                    task.cancel()
            await asyncio.gather(
                wait_ready,
                wait_exit,
                return_exceptions=True,
            )
        if wait_ready in done and ready.is_set():
            return
        if wait_exit in done:
            raise RuntimeErrorSafe(f"{name} stopped while starting")
        raise RuntimeErrorSafe(f"{name} did not become ready in time")

    async def _spawn(
        self,
        executable: Path,
        *arguments: str,
    ) -> asyncio.subprocess.Process:
        return await asyncio.create_subprocess_exec(
            str(executable),
            *arguments,
            cwd=str(self.runtime_dir),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            start_new_session=True,
            env={
                "HOME": str(self.runtime_dir),
                "LANG": "C.UTF-8",
                "PATH": "/usr/bin:/bin",
            },
        )

    @staticmethod
    def _fetch_public_ip_sync() -> tuple[str | None, str | None]:
        opener = _https_opener()
        failures: list[str] = []
        for url in PUBLIC_IP_URLS:
            host = urllib.parse.urlsplit(url).hostname or url
            try:
                request = urllib.request.Request(
                    url,
                    headers={
                        "Accept": "text/plain",
                        "Cache-Control": "no-cache",
                        "User-Agent": "Browsec-Decky/1.0.0",
                    },
                )
                with opener.open(request, timeout=6) as response:
                    value = response.read(128).decode("ascii", "strict").strip()
                return str(ipaddress.ip_address(value)), None
            except (ValueError, UnicodeError) as exc:
                failures.append(f"{host}: invalid response ({type(exc).__name__})")
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                reason: Any = (
                    exc.reason if isinstance(exc, urllib.error.URLError) else exc
                )
                failures.append(f"{host}: {type(reason).__name__}: {reason}")
        return None, "; ".join(failures)

    async def _fetch_public_ip(self) -> str | None:
        public_ip, error = await asyncio.to_thread(self._fetch_public_ip_sync)
        self._public_ip_error = error
        return public_ip

    async def start(
        self,
        server: VPNServer,
        xray_uuid: str,
        include_ipv6: bool = False,
    ) -> str:
        if self.is_running:
            if self.public_ip:
                return self.public_ip
            raise RuntimeErrorSafe("The VPN is already connecting")

        self._verification_signature = None
        available, reason = self.runtime_status()
        if not available:
            raise RuntimeErrorSafe(reason or "The VPN runtime is unavailable")
        self._acquire_lock()
        try:
            await self._cleanup_stale_owned_processes()
            if self._desktop_conflict():
                raise RuntimeErrorSafe(
                    "Close Browsec Desktop before connecting Browsec Decky"
                )

            browray_config = self._write_config(
                "browray-config.json",
                build_browray_config(server, xray_uuid),
            )
            browbox_config = self._write_config(
                "browbox-config.json",
                build_browbox_config(server, include_ipv6),
            )
            self._transport_server = server

            await self.enable_kill_switch()
            await self.on_state("connecting", None)

            ray_ready = asyncio.Event()
            self.browray = await self._spawn(
                self.bin_dir / "browray",
                "-config",
                str(browray_config),
            )
            ray_log = asyncio.create_task(
                self._consume_logs(self.browray, ray_ready, b"started")
            )
            self._log_tasks.append(ray_log)
            await self._wait_ready(self.browray, ray_ready, "Browsec Xray")

            box_ready = asyncio.Event()
            self.browbox = await self._spawn(
                self.bin_dir / "browbox",
                "run",
                "--disable-color",
                "-c",
                str(browbox_config),
            )
            box_log = asyncio.create_task(
                self._consume_logs(self.browbox, box_ready, b"sing-box started")
            )
            self._log_tasks.append(box_log)
            await self._wait_ready(self.browbox, box_ready, "Browsec tunnel")

            await asyncio.sleep(1)
            after_ip = await self._fetch_public_ip()
            if after_ip is None:
                details = (
                    f" ({self._public_ip_error})"
                    if self._public_ip_error
                    else ""
                )
                raise RuntimeErrorSafe(
                    "The tunnel started, but its public IP could not be verified"
                    f"{details}"
                )
            self.public_ip = after_ip
            await self.on_state("connected", None)
            self._watch_task = asyncio.create_task(self._watch_processes())
            return after_ip
        except asyncio.CancelledError:
            await self.stop()
            raise
        except Exception:
            await self.stop()
            raise

    @property
    def is_running(self) -> bool:
        return any(
            process is not None and process.returncode is None
            for process in (self.browray, self.browbox)
        )

    async def _watch_processes(self) -> None:
        processes = [
            process
            for process in (self.browray, self.browbox)
            if process is not None
        ]
        if len(processes) != 2:
            return
        waits = [asyncio.create_task(process.wait()) for process in processes]
        try:
            await asyncio.wait(waits, return_when=asyncio.FIRST_COMPLETED)
            if not self._stopping:
                await self.stop(
                    release_kill_switch=False,
                    emit_state=False,
                )
                protection = (
                    " Kill switch is blocking traffic."
                    if self.kill_switch_active
                    else ""
                )
                await self.on_state(
                    "disconnected",
                    f"The VPN process exited unexpectedly.{protection}",
                )
        finally:
            for task in waits:
                task.cancel()

    async def _terminate(self, process: asyncio.subprocess.Process | None) -> None:
        if process is None or process.returncode is not None:
            return
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        try:
            await asyncio.wait_for(process.wait(), timeout=5)
        except asyncio.TimeoutError:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            await process.wait()

    async def stop(
        self,
        *,
        release_kill_switch: bool = True,
        emit_state: bool = True,
    ) -> None:
        if self._stopping:
            return
        self._stopping = True
        try:
            current_task = asyncio.current_task()
            if self._watch_task is not None and self._watch_task is not current_task:
                self._watch_task.cancel()
                await asyncio.gather(self._watch_task, return_exceptions=True)
            self._watch_task = None
            await self._terminate(self.browbox)
            await self._terminate(self.browray)
            self.browbox = None
            self.browray = None
            for task in self._log_tasks:
                task.cancel()
            if self._log_tasks:
                await asyncio.gather(*self._log_tasks, return_exceptions=True)
            self._log_tasks.clear()
            self.public_ip = None
            for name in ("browbox-config.json", "browray-config.json"):
                try:
                    (self.runtime_dir / name).unlink()
                except FileNotFoundError:
                    pass
            self._release_lock()
            if release_kill_switch:
                await self.disable_kill_switch()
                self._transport_server = None
            if emit_state:
                await self.on_state("disconnected", None)
        finally:
            self._stopping = False
