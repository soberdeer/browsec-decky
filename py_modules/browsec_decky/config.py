"""Verified Browsec 1.2.2 single-server Xray and sing-box configuration."""

from __future__ import annotations

from typing import Any

from .api import VPNServer


SOCKS_HOST = "127.0.0.1"
SOCKS_PORT = 45361
VLESS_PORT = 63821
VLESS_PUBLIC_KEY = "koKaMgyyxUFwSa28okVxBsicQqXgkSi_sa-KblM2MUM"
VLESS_SHORT_ID = "bbb43890f4d92fd5"
TUN_INTERFACE = "browbox-decky"
CHECK_URLS = (
    "checkip.amazonaws.com",
    "api.ipify.org",
    "icanhazip.com",
    "ifconfig.me",
)


def build_browray_config(server: VPNServer, xray_uuid: str) -> dict[str, Any]:
    return {
        "log": {"loglevel": "warning"},
        "dns": {
            "hosts": {"domain:googleapis.cn": "googleapis.com"},
            "servers": ["1.1.1.1", "8.8.8.8", "8.8.4.4"],
        },
        "inbounds": [
            {
                "port": SOCKS_PORT,
                "listen": SOCKS_HOST,
                "tag": "inbound-socks",
                "protocol": "socks",
                "settings": {"udp": True},
                "sniffing": {
                    "enabled": True,
                    "destOverride": ["http", "tls", "quic"],
                    "metadataOnly": False,
                    "routeOnly": True,
                },
            },
        ],
        "outbounds": [
            {
                "protocol": "vless",
                "settings": {
                    "vnext": [
                        {
                            "port": VLESS_PORT,
                            "address": server.ip,
                            "users": [
                                {
                                    "id": xray_uuid,
                                    "encryption": "none",
                                    "flow": "xtls-rprx-vision",
                                    "security": "auto",
                                }
                            ],
                        }
                    ]
                },
                "streamSettings": {
                    "network": "tcp",
                    "security": "reality",
                    "realitySettings": {
                        "serverName": server.xsni,
                        "publicKey": VLESS_PUBLIC_KEY,
                        "shortId": VLESS_SHORT_ID,
                        "fingerprint": "random",
                        "spiderX": "",
                    },
                    "finalmask": {
                        "tcp": [
                            {
                                "type": "fragment",
                                "settings": {
                                    "packets": "tlshello",
                                    "length": "10-30",
                                    "delay": "5-10",
                                    "maxSplit": "15-25",
                                },
                            }
                        ]
                    },
                },
                "tag": "proxy-vless",
            },
            {"protocol": "freedom", "tag": "direct"},
            {"protocol": "blackhole", "tag": "block"},
        ],
        "routing": {
            "rules": [
                {
                    "type": "field",
                    "inboundTag": ["inbound-socks"],
                    "outboundTag": "proxy-vless",
                },
            ]
        },
    }


def build_browbox_config(server: VPNServer, include_ipv6: bool) -> dict[str, Any]:
    addresses = ["172.19.0.1/30"]
    if include_ipv6:
        addresses.append("fdfe:dcba:9876::1/126")

    return {
        "log": {"level": "info"},
        "dns": {
            "servers": [
                {
                    "tag": "dns-proxy",
                    "type": "udp",
                    "server": "1.1.1.1",
                    "server_port": 53,
                    "detour": "browray-socks",
                }
            ],
            "strategy": "ipv4_only",
            "cache_capacity": 10000,
            "reverse_mapping": True,
            "final": "dns-proxy",
        },
        "inbounds": [
            {
                "type": "tun",
                "interface_name": TUN_INTERFACE,
                "address": addresses,
                "auto_route": True,
                "strict_route": True,
                "mtu": 1420,
                "stack": "gvisor",
                "endpoint_independent_nat": True,
                "route_exclude_address": [
                    f"{server.ip}/128" if ":" in server.ip else f"{server.ip}/32"
                ],
            }
        ],
        "outbounds": [
            {
                "type": "socks",
                "tag": "browray-socks",
                "server": SOCKS_HOST,
                "server_port": SOCKS_PORT,
                "udp_fragment": True,
            },
            {"type": "direct", "tag": "direct"},
        ],
        "route": {
            "final": "browray-socks",
            "default_domain_resolver": {"server": "dns-proxy"},
            "auto_detect_interface": True,
            "rules": [
                {"port": 53, "action": "hijack-dns"},
                {"action": "sniff", "timeout": "300ms"},
                {
                    "network": "udp",
                    "port": [443, 8443, 2053],
                    "action": "reject",
                },
                {
                    "domain": [
                        "firebaseremoteconfig.googleapis.com",
                    ],
                    "action": "route",
                    "outbound": "direct",
                },
                {
                    "domain": "browsec.com",
                    "action": "route",
                    "outbound": "browray-socks",
                },
                {
                    "domain_keyword": list(CHECK_URLS),
                    "action": "route",
                    "outbound": "browray-socks",
                },
                {
                    "process_name": ["browray", "browbox"],
                    "action": "route",
                    "outbound": "direct",
                },
                {
                    "ip_cidr": [
                        "10.0.0.0/8",
                        "172.16.0.0/12",
                        "192.168.0.0/16",
                        "127.0.0.0/8",
                        "169.254.0.0/16",
                        "224.0.0.0/4",
                        "::1/128",
                        "fc00::/7",
                        "fe80::/10",
                    ],
                    "action": "route",
                    "outbound": "direct",
                },
                {
                    "domain_suffix": [".local", ".localhost", ".lan"],
                    "action": "route",
                    "outbound": "direct",
                },
            ],
        },
        "experimental": {},
    }
