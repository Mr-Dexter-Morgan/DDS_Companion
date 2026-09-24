from __future__ import annotations

import unittest
import uuid

from PySide6.QtCore import QCoreApplication

from dds_companion.gui.single_instance import SingleInstanceCoordinator, default_server_name


class SingleInstanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def test_default_server_name_is_stable_and_namespaced(self):
        first = default_server_name()
        second = default_server_name()
        self.assertEqual(first, second)
        self.assertTrue(first.startswith("DDS-DiscordDataSnatcher-"))

    def test_second_instance_notifies_primary_instead_of_claiming(self):
        name = f"DDS-test-{uuid.uuid4().hex}"
        primary = SingleInstanceCoordinator(name, connect_timeout_ms=100)
        secondary = SingleInstanceCoordinator(name, connect_timeout_ms=100)
        activations: list[bool] = []
        primary.activation_requested.connect(lambda: activations.append(True))
        self.addCleanup(primary.close)
        self.addCleanup(secondary.close)

        self.assertTrue(primary.claim_or_notify())
        self.assertFalse(secondary.claim_or_notify())

        for _ in range(20):
            self.app.processEvents()
            if activations:
                break
        self.assertEqual(activations, [True])


if __name__ == "__main__":
    unittest.main()
