"""Isolation tier directories."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from throne_runtime.artifacts.isolation import IsolationManager
from throne_runtime.artifacts.models import Isolation


class TestIsolation(unittest.TestCase):
    def test_tiers_created(self):
        with tempfile.TemporaryDirectory() as td:
            mgr = IsolationManager(Path(td))
            for iso in Isolation:
                self.assertTrue(mgr.tier_dir(iso).is_dir())


if __name__ == "__main__":
    unittest.main()
