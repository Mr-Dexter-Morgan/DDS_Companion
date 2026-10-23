from __future__ import annotations

import subprocess
import unittest
from unittest.mock import patch

from dds_companion.services.discord_probe import _parse_tasklist_csv, probe_discord_process


class DiscordProbeTests(unittest.TestCase):
    def test_parse_tasklist_detects_stable_canary_and_ptb(self):
        output = (
            b'"Discord.exe","1234","Console","1","120,000 K"\n'
            b'"DiscordCanary.exe","2222","Console","1","100,000 K"\n'
            b'"DiscordPTB.exe","3333","Console","1","90,000 K"\n'
            b'"explorer.exe","4444","Console","1","80,000 K"\n'
        )
        self.assertEqual(
            _parse_tasklist_csv(output),
            ("Discord.exe", "DiscordCanary.exe", "DiscordPTB.exe"),
        )

    def test_parse_tasklist_ignores_no_tasks_info_line(self):
        self.assertEqual(
            _parse_tasklist_csv(b'INFO: No tasks are running which match the specified criteria.\n'),
            (),
        )

    def test_parse_tasklist_ignores_non_utf8_bytes_after_image_name(self):
        output = b'"Discord.exe","16036","Console","1","156\xff740 \x8a\x81"\n'
        self.assertEqual(_parse_tasklist_csv(output), ("Discord.exe",))

    @patch("dds_companion.services.discord_probe.os.name", "nt")
    @patch("dds_companion.services.discord_probe.subprocess.run")
    def test_probe_treats_missing_stdout_as_unknown_not_not_running(self, run):
        run.return_value = subprocess.CompletedProcess(
            args=["tasklist"], returncode=0, stdout=None, stderr=None
        )
        result = probe_discord_process()
        self.assertEqual(result.state, "UNKNOWN")
        self.assertIn("stdout unavailable", result.summary)

    @patch("dds_companion.services.discord_probe.os.name", "nt")
    @patch("dds_companion.services.discord_probe.subprocess.run")
    def test_probe_treats_nonzero_tasklist_exit_as_unknown(self, run):
        run.return_value = subprocess.CompletedProcess(
            args=["tasklist"], returncode=5, stdout=b"", stderr=b"access denied"
        )
        result = probe_discord_process()
        self.assertEqual(result.state, "UNKNOWN")
        self.assertIn("exit 5", result.summary)

    @patch("dds_companion.services.discord_probe.os.name", "nt")
    @patch("dds_companion.services.discord_probe.subprocess.run")
    def test_probe_uses_binary_capture_and_detects_discord(self, run):
        run.return_value = subprocess.CompletedProcess(
            args=["tasklist"], returncode=0,
            stdout=b'"Discord.exe","16036","Console","1","156\xff740 \x8a\x81"\n',
            stderr=b"",
        )
        result = probe_discord_process()
        self.assertEqual(result.state, "RUNNING")
        self.assertEqual(result.detected_processes, ("Discord.exe",))
        self.assertFalse(run.call_args.kwargs["text"])


if __name__ == "__main__":
    unittest.main()
