from __future__ import annotations

import unittest
from unittest import mock

import llm_report_tray


class TraySingletonTests(unittest.TestCase):
    def test_second_tray_does_not_start_another_bot(self) -> None:
        with (
            mock.patch.object(llm_report_tray, "configure_logging"),
            mock.patch.object(llm_report_tray.llm_report_core, "load_environment"),
            mock.patch.object(llm_report_tray, "_claim_tray_instance", return_value=False),
            mock.patch.object(llm_report_tray, "BotSupervisor") as supervisor,
        ):
            self.assertEqual(llm_report_tray.main(), 0)

        supervisor.assert_not_called()


if __name__ == "__main__":
    unittest.main()
