from __future__ import annotations

import unittest

from dds_companion.services.discord_probe import _parse_tasklist_csv


class DiscordProbeTests(unittest.TestCase):
    def test_parse_tasklist_detects_stable_canary_and_ptb(self):
        output = (
            '"Discord.exe","1234","Console","1","120,000 K"\n'
            '"DiscordCanary.exe","2222","Console","1","100,000 K"\n'
            '"DiscordPTB.exe","3333","Console","1","90,000 K"\n'
            '"explorer.exe","4444","Console","1","80,000 K"\n'
        )
        self.assertEqual(
            _parse_tasklist_csv(output),
            ("Discord.exe", "DiscordCanary.exe", "DiscordPTB.exe"),
        )

    def test_parse_tasklist_ignores_no_tasks_info_line(self):
        self.assertEqual(
            _parse_tasklist_csv('INFO: No tasks are running which match the specified criteria.\n'),
            (),
        )


if __name__ == "__main__":
    unittest.main()
