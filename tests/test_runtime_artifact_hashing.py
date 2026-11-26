"""SHA-256 determinism and deduplication."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from throne_runtime.artifacts.hashing import sha256_bytes, sha256_file, sha256_json
from throne_runtime.artifacts.storage import LocalBlobStorage


class TestHashing(unittest.TestCase):
    def test_deterministic(self):
        self.assertEqual(sha256_bytes(b"hello"), sha256_bytes(b"hello"))
        self.assertEqual(
            sha256_json({"b": 1, "a": 2}),
            sha256_json({"a": 2, "b": 1}),
        )

    def test_dedup(self):
        with tempfile.TemporaryDirectory() as td:
            store = LocalBlobStorage(Path(td))
            h1 = store.put_bytes(b"same-content")
            h2 = store.put_bytes(b"same-content")
            self.assertEqual(h1, h2)
            self.assertTrue(store.verify(h1))

    def test_corrupted_blob_fails_verify(self):
        with tempfile.TemporaryDirectory() as td:
            store = LocalBlobStorage(Path(td))
            h = store.put_bytes(b"original")
            p = store.get_path(h)
            p.write_bytes(b"tampered")
            self.assertFalse(store.verify(h))


if __name__ == "__main__":
    unittest.main()
