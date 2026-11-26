"""Integration: concurrent safety, full flow."""

from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path

from tests._artifact_test_util import make_service


class TestIntegration(unittest.TestCase):
    def test_concurrent_ingest(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            svc = make_service(root)
            run = svc.create_run(project="P", subsystem="s", run_type="t")
            errors: list[BaseException] = []

            def worker(i: int) -> None:
                try:
                    f = root / f"f{i}.txt"
                    f.write_text(f"content-{i}")
                    svc.ingest(run_id=run.run_id, path=f)
                except BaseException as e:
                    errors.append(e)

            threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            self.assertEqual(errors, [])
            arts = svc.list_artifacts(run.run_id)
            self.assertEqual(len(arts), 8)

    def test_import_does_not_require_network(self):
        import throne_runtime.artifacts  # noqa: F401


if __name__ == "__main__":
    unittest.main()
