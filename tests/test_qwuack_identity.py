"""Qwuack identity is immutable configuration, not a state engine."""

from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError

from agent.engine import seed_field
from agent.schemas import Channel
from qwuack.identity import HABITAT_CAPABILITIES, QWUACK, QwuackIdentity


class IdentityTests(unittest.TestCase):
    def test_name_and_species(self) -> None:
        self.assertEqual(QWUACK.name, "Qwuack")
        self.assertEqual(QWUACK.species, "duck")
        self.assertEqual(QWUACK.habitat, "lake")
        self.assertEqual(QWUACK.role, "embodied_field_agent")

    def test_frozen(self) -> None:
        with self.assertRaises(FrozenInstanceError):
            QWUACK.name = "Goose"  # type: ignore[misc]

    def test_does_not_encode_world_facts(self) -> None:
        self.assertFalse(hasattr(QWUACK, "lake_temperature"))
        self.assertFalse(hasattr(QWUACK, "duck_position"))
        self.assertFalse(hasattr(QWUACK, "lake_has_water"))

    def test_identity_cannot_mutate_field(self) -> None:
        field = seed_field()
        before = list(field.data)
        energy = field.sum(Channel.Energy)
        self.assertFalse(hasattr(QWUACK, "write"))
        self.assertFalse(hasattr(QwuackIdentity, "write"))
        self.assertFalse(hasattr(QWUACK, "apply"))
        self.assertEqual(field.sum(Channel.Energy), energy)
        self.assertEqual(field.data, before)

    def test_habitat_is_not_god_mode(self) -> None:
        self.assertNotIn("act.device", HABITAT_CAPABILITIES)
        self.assertTrue(QWUACK.allows_action("PROBE"))
        self.assertFalse(QWUACK.allows_capability("act.device"))

    def test_custom_copy_stays_frozen(self) -> None:
        other = QwuackIdentity(name="Qwuack", species="duck")
        self.assertEqual(other.name, "Qwuack")
        with self.assertRaises(FrozenInstanceError):
            other.habitat = "ocean"  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
