"""Leak-prevention firewall owned exclusively by Browsec Decky."""

from __future__ import annotations

import ipaddress
import os
import subprocess
from pathlib import Path


NFT_PATHS = (
    Path("/usr/bin/nft"),
    Path("/usr/sbin/nft"),
    Path("/sbin/nft"),
)
TABLE_FAMILY = "inet"
TABLE_NAME = "browsec_decky"
TUN_INTERFACE = "browbox-decky"
VLESS_PORT = 63821


class KillSwitchError(RuntimeError):
    """An nftables failure safe to display without exposing credentials."""


class NftKillSwitch:
    def __init__(self, nft_path: Path | None = None) -> None:
        self.nft_path = nft_path or self._find_nft()
        self.active = False

    @staticmethod
    def _find_nft() -> Path | None:
        for path in NFT_PATHS:
            if path.is_file() and os.access(path, os.X_OK):
                return path
        return None

    @property
    def available(self) -> bool:
        return self.nft_path is not None

    def _run(
        self,
        arguments: list[str],
        *,
        script: str | None = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        if self.nft_path is None:
            raise KillSwitchError(
                "Kill switch requires nftables, but /usr/bin/nft was not found"
            )
        try:
            result = subprocess.run(
                [str(self.nft_path), *arguments],
                input=script,
                capture_output=True,
                check=False,
                text=True,
                timeout=5,
                env={
                    "LANG": "C.UTF-8",
                    "LC_ALL": "C",
                    "PATH": "/usr/bin:/usr/sbin:/bin:/sbin",
                },
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise KillSwitchError(
                f"Could not control the kill switch ({type(exc).__name__}: {exc})"
            ) from exc
        if check and result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            if detail:
                detail = f": {detail[:1024]}"
            raise KillSwitchError(
                f"nftables rejected the Browsec kill-switch rules{detail}"
            )
        return result

    def table_exists(self) -> bool:
        if not self.available:
            return False
        result = self._run(
            ["list", "table", TABLE_FAMILY, TABLE_NAME],
            check=False,
        )
        return result.returncode == 0

    @staticmethod
    def _initial_rules(
        transport_ip: ipaddress.IPv4Address | ipaddress.IPv6Address,
    ) -> str:
        ipv4_element = str(transport_ip) if transport_ip.version == 4 else None
        ipv6_element = str(transport_ip) if transport_ip.version == 6 else None
        ipv4_set = (
            f"elements = {{ {ipv4_element} }};" if ipv4_element else ""
        )
        ipv6_set = (
            f"elements = {{ {ipv6_element} }};" if ipv6_element else ""
        )
        return f"""
table {TABLE_FAMILY} {TABLE_NAME} {{
    set transport_ipv4 {{
        type ipv4_addr;
        {ipv4_set}
    }}

    set transport_ipv6 {{
        type ipv6_addr;
        {ipv6_set}
    }}

    chain output {{
        type filter hook output priority -10; policy drop;

        oifname "lo" accept
        oifname "{TUN_INTERFACE}" accept
        ip daddr @transport_ipv4 tcp dport {VLESS_PORT} accept
        ip6 daddr @transport_ipv6 tcp dport {VLESS_PORT} accept
        udp sport 68 udp dport 67 accept
        udp sport 546 udp dport 547 accept
        icmpv6 type {{ nd-router-solicit, nd-neighbor-solicit, nd-neighbor-advert }} accept
    }}

    chain forward {{
        type filter hook forward priority -10; policy drop;

        iifname "{TUN_INTERFACE}" accept
        oifname "{TUN_INTERFACE}" accept
    }}
}}
""".strip()

    @staticmethod
    def _update_rules(
        transport_ip: ipaddress.IPv4Address | ipaddress.IPv6Address,
    ) -> str:
        commands = [
            f"flush set {TABLE_FAMILY} {TABLE_NAME} transport_ipv4",
            f"flush set {TABLE_FAMILY} {TABLE_NAME} transport_ipv6",
        ]
        set_name = (
            "transport_ipv4" if transport_ip.version == 4 else "transport_ipv6"
        )
        commands.append(
            f"add element {TABLE_FAMILY} {TABLE_NAME} {set_name} "
            f"{{ {transport_ip} }}"
        )
        return "\n".join(commands)

    def enable(self, transport_ip: str) -> None:
        try:
            address = ipaddress.ip_address(transport_ip)
        except ValueError as exc:
            raise KillSwitchError(
                "The VPN server address is invalid; kill switch was not enabled"
            ) from exc

        if self.table_exists():
            script = self._update_rules(address)
        else:
            script = self._initial_rules(address)
        self._run(["-f", "-"], script=script)
        self.active = True

    def disable(self) -> None:
        if not self.table_exists():
            self.active = False
            return
        self._run(["delete", "table", TABLE_FAMILY, TABLE_NAME])
        self.active = False
