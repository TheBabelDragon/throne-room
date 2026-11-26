"""Registry persistence across process restart."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from throne_runtime.artifacts.manifest import attach_manifest_hash
from throne_runtime.artifacts.models import RunManifest
from throne_runtime.artifacts.registry import Registry


class TestRegistry(unittest.TestCase):
    def test_survives_reopen(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "registry.sqlite3"
            reg = Registry(db)
            m = RunManifest(
                run_id="run-persist",
                project="P",
                subsystem="s",
                run_type="t",
                created_at="2026-01-01T00:00:00Z",
            )
            attach_manifest_hash(m)
            reg.put_run(m)
            del reg
            reg2 = Registry(db)
            loaded = reg2.get_run("run-persist")
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.run_id, "run-persist")


if __name__ == "__main__":
    unittest.main()
