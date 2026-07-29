import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).parents[1] / "py_modules"))

from browsec_decky.firewall import KillSwitchError, NftKillSwitch


def completed(
    arguments,
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
):
    return subprocess.CompletedProcess(arguments, returncode, stdout, stderr)


class KillSwitchTests(unittest.TestCase):
    def test_new_ipv4_rules_block_by_default_and_allow_only_tunnel_transport(self):
        calls = [
            completed([], returncode=1),
            completed([]),
        ]
        with patch("browsec_decky.firewall.subprocess.run", side_effect=calls) as run:
            switch = NftKillSwitch(Path("/usr/bin/nft"))
            switch.enable("203.0.113.8")

        script = run.call_args_list[1].kwargs["input"]
        self.assertIn("table inet browsec_decky", script)
        self.assertIn("policy drop", script)
        self.assertIn('oifname "browbox-decky" accept', script)
        self.assertIn('iifname "browbox-decky" accept', script)
        self.assertIn("type filter hook forward", script)
        self.assertIn("elements = { 203.0.113.8 }", script)
        self.assertIn("tcp dport 63821 accept", script)
        self.assertNotIn("0.0.0.0/0", script)
        self.assertTrue(switch.active)

    def test_existing_rules_are_updated_atomically_for_ipv6_transport(self):
        calls = [
            completed([]),
            completed([]),
        ]
        with patch("browsec_decky.firewall.subprocess.run", side_effect=calls) as run:
            switch = NftKillSwitch(Path("/usr/bin/nft"))
            switch.enable("2001:db8::7")

        script = run.call_args_list[1].kwargs["input"]
        self.assertIn("flush set inet browsec_decky transport_ipv4", script)
        self.assertIn("flush set inet browsec_decky transport_ipv6", script)
        self.assertIn(
            "add element inet browsec_decky transport_ipv6 { 2001:db8::7 }",
            script,
        )

    def test_disable_removes_only_the_plugin_table(self):
        calls = [
            completed([]),
            completed([]),
        ]
        with patch("browsec_decky.firewall.subprocess.run", side_effect=calls) as run:
            switch = NftKillSwitch(Path("/usr/bin/nft"))
            switch.active = True
            switch.disable()

        command = run.call_args_list[1].args[0]
        self.assertEqual(
            command,
            [
                "/usr/bin/nft",
                "delete",
                "table",
                "inet",
                "browsec_decky",
            ],
        )
        self.assertFalse(switch.active)

    def test_invalid_server_never_reaches_nftables(self):
        with patch("browsec_decky.firewall.subprocess.run") as run:
            switch = NftKillSwitch(Path("/usr/bin/nft"))
            with self.assertRaisesRegex(KillSwitchError, "invalid"):
                switch.enable("203.0.113.8; flush ruleset")
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
