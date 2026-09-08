"""--full path insurance. Does not bind UDP :4210."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class StartupFullPathTests(unittest.TestCase):
    def test_check_full_paths_imports(self) -> None:
        from observer.startup import check_full_paths

        report = check_full_paths()
        self.assertTrue(report["ok"], msg=report)
        self.assertFalse(report["qwuack_binds_udp"])
        self.assertFalse(report["qwuack_required_child"])
        self.assertEqual(report["required_child"], "metafield_bridge")
        for name in (
            "metafield_bridge",
            "throne_view",
            "torch_display",
            "aurora_action",
            "qwuack_runtime",
            "agent_loop",
            "duck_gate",
        ):
            self.assertEqual(report["modules"][name]["import"], "ok", msg=report["modules"][name])

    def test_check_cli_exits_zero(self) -> None:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
        proc = subprocess.run(
            [sys.executable, "-m", "observer.startup", "--check", "--full"],
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr + proc.stdout)
        report = json.loads(proc.stdout)
        self.assertTrue(report["ok"])

    def test_seconds_smoke_does_not_require_qwuack(self) -> None:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
        env.pop("THRONE_TORCH", None)
        proc = subprocess.run(
            [
                sys.executable, "-m", "observer.startup",
                "--no-view", "--no-torch", "--no-consumer",
                "--seconds", "1.2",
                "--digest-interval", "0.4",
                "--udp", "14210",
                "--udp-bind", "127.0.0.1",
            ],
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr + proc.stdout)
        self.assertIn("startup sequence", proc.stdout)
        self.assertIn("shutting down", proc.stdout)
        self.assertNotIn("Qwuack follower enabled", proc.stdout)


if __name__ == "__main__":
    unittest.main()
