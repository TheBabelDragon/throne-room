"""End-to-end runtime acceptance: ingest → promote → restart → reconcile."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from throne_runtime.artifacts.models import Isolation
from tests._artifact_test_util import make_service


class TestRuntimeAcceptance(unittest.TestCase):
    def test_full_lifecycle_with_restart(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "store"
            # 1–6: create, ingest, verify, quarantine, promote, audit
            svc = make_service(root)
            run = svc.create_run(
                project="Spacetime",
                subsystem="acceptance",
                run_type="e2e",
                source_commit="abc123",
            )
            payload = Path(td) / "artifact.bin"
            payload.write_bytes(b"acceptance-payload-v1")
            art = svc.ingest(run_id=run.run_id, path=payload)
            self.assertEqual(art.isolation, Isolation.QUARANTINED)
            self.assertTrue(art.content_hash)
            self.assertEqual(len(art.content_hash), 64)

            v = svc.verify(run.run_id)
            self.assertTrue(v["ok"])

            promo = svc.promote(art.artifact_id, target="VALIDATED", actor="acceptance")
            self.assertEqual(promo["decision"], "ALLOWED")

            audit = svc.audit(run.run_id)
            self.assertTrue(any(a["decision"] == "ALLOWED" for a in audit))

            loaded = svc.registry.get_artifact(art.artifact_id)
            self.assertEqual(loaded.isolation, Isolation.VALIDATED)
            self.assertTrue(Path(loaded.stored_location).is_file())

            # 7–9: restart service, recover, verify state
            svc2 = make_service(root)
            self.assertIsInstance(svc2.recovery_log, list)
            loaded2 = svc2.registry.get_artifact(art.artifact_id)
            self.assertIsNotNone(loaded2)
            self.assertEqual(loaded2.isolation, Isolation.VALIDATED)
            self.assertEqual(loaded2.content_hash, art.content_hash)
            self.assertTrue(Path(loaded2.stored_location).is_file())

            audit2 = svc2.audit(run.run_id)
            self.assertTrue(any(a["decision"] == "ALLOWED" for a in audit2))

            incomplete = svc2.promotion_gate.journal.list_incomplete()
            # No incomplete journal for successful promote
            self.assertEqual(
                [e for e in incomplete if e.artifact_id == art.artifact_id],
                [],
            )

            # 10: integrity
            self.assertEqual(svc2.registry.db.integrity_check(), "ok")
            st = svc2.registry.db.wal_status()
            self.assertEqual(st["journal_mode"].lower(), "wal")
            self.assertGreaterEqual(st["synchronous"], 2)


if __name__ == "__main__":
    unittest.main()
