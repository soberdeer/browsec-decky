import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parents[1] / "py_modules"))

from browsec_decky.api import VPNServer
from browsec_decky.config import build_browbox_config, build_browray_config


SERVER = VPNServer(
    ip="203.0.113.8",
    xsni="example.org",
    country_code="nl",
    country_name="Netherlands",
)


class ConfigTests(unittest.TestCase):
    def test_xray_secrets_are_inserted_only_in_backend_config(self):
        config = build_browray_config(
            SERVER,
            "cf9b437a-b26d-416a-9400-51e76ec8b0ca",
        )
        remote = config["outbounds"][0]
        self.assertEqual(remote["settings"]["vnext"][0]["address"], SERVER.ip)
        self.assertEqual(
            remote["settings"]["vnext"][0]["users"][0]["id"],
            "cf9b437a-b26d-416a-9400-51e76ec8b0ca",
        )
        self.assertEqual(
            remote["streamSettings"]["realitySettings"]["serverName"],
            SERVER.xsni,
        )

    def test_tun_routes_all_traffic_and_excludes_transport_server(self):
        config = build_browbox_config(SERVER, include_ipv6=False)
        tun = config["inbounds"][0]
        self.assertTrue(tun["auto_route"])
        self.assertTrue(tun["strict_route"])
        self.assertEqual(tun["route_exclude_address"], ["203.0.113.8/32"])
        self.assertEqual(config["route"]["final"], "browray-socks")

    def test_ipv6_tunnel_address_is_enabled_for_release_connections(self):
        config = build_browbox_config(SERVER, include_ipv6=True)
        self.assertEqual(
            config["inbounds"][0]["address"],
            ["172.19.0.1/30", "fdfe:dcba:9876::1/126"],
        )
