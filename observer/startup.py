#!/usr/bin/env python3
"""
Intelligent control / startup sequence

Wires observation path → MetaField digest → Aurora-facing status
even when no higher-level controller exists.

Stages:
  1. prepare runtime dirs
  2. bind CSI uplink (metafield_bridge owns UDP :4210)
  3. optional Throne live view (tails the same JSONL)
  4. optional MetaField consumer (FieldObservation → FieldMemoryEntry)
  5. Aurora digest loop (read-only stats + obs health; fail-closed)

Usage:

  python -m observer.startup
  python -m observer.startup --no-view
  python -m observer.startup --metafield-root ~/projects/metafield
  python -m observer.startup --udp 4210 --out /tmp/metafield/csi.jsonl
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = Path("/tmp/metafield/csi.jsonl")
DEFAULT_MEMORY = Path("/tmp/metafield/field_memory.jsonl")
DEFAULT_DIGEST = Path("/tmp/metafield/obs_digest.json")
DEFAULT_STATS = Path("/tmp/metafield/stats.json")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _kill(proc: subprocess.Popen | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    try:
        proc.terminate()
        try:
            proc.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=1.0)
    except Exception:
        pass


@dataclass
class Child:
    name: str
    proc: subprocess.Popen | None = None
    cmd: list[str] = field(default_factory=list)
    cwd: Path | None = None
    env: dict[str, str] = field(default_factory=dict)
    required: bool = True

    def alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def start(self) -> None:
        if self.alive():
            return
        env = os.environ.copy()
        env.update(self.env)
        self.proc = subprocess.Popen(
            self.cmd,
            cwd=str(self.cwd or ROOT),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        print(f"[control] start {self.name}  pid={self.proc.pid}", flush=True)

    def restart_if_dead(self) -> None:
        if self.alive():
            return
        code = self.proc.returncode if self.proc else "?"
        print(f"[control] {self.name} exited ({code}) — restarting", flush=True)
        self.start()


def _discover_metafield(explicit: Path | None) -> Path | None:
    if explicit and explicit.is_dir():
        return explicit
    env = os.environ.get("METAFIELD_ROOT")
    if env and Path(env).is_dir():
        return Path(env)
    candidate = ROOT.parent / "metafield"
    if candidate.is_dir():
        return candidate
    return None


def _write_digest(
    path: Path,
    *,
    children: list[Child],
    out_jsonl: Path,
    memory_jsonl: Path,
    packet_lines: int,
    memory_lines: int,
) -> dict[str, Any]:
    """Aurora-facing observation digest (file-based, fail-closed)."""
    child_state = {
        c.name: {
            "alive": c.alive(),
            "pid": c.proc.pid if c.proc and c.alive() else None,
            "required": c.required,
        }
        for c in children
    }
    healthy = all(c.alive() for c in children if c.required)

    # optional MetaField stats (Aurora mod schema)
    mf_stats: dict[str, Any] = {}
    if DEFAULT_STATS.exists():
        try:
            mf_stats = json.loads(DEFAULT_STATS.read_text())
        except Exception:
            mf_stats = {"health": "unreadable"}

    digest = {
        "schema_version": 1,
        "type": "OBS_PATH_DIGEST",
        "timestamp": _now(),
        "source": "throne-room.control",
        "aurora_rev": "file-digest-v1",
        "health": "ok" if healthy else "degraded",
        "obs_path": {
            "csi_jsonl": str(out_jsonl),
            "csi_lines": packet_lines,
            "memory_jsonl": str(memory_jsonl),
            "memory_lines": memory_lines,
            "udp_owner": "metafield_bridge",
        },
        "children": child_state,
        "metafield_stats": {
            "health": mf_stats.get("health", "no_export"),
            "traj": mf_stats.get("traj"),
            "live": mf_stats.get("live", False),
            "memory_size": (mf_stats.get("memory") or {}).get("size"),
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(digest, indent=2))
    return digest


def _count_lines(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        with path.open("rb") as f:
            return sum(1 for _ in f)
    except OSError:
        return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Throne Room intelligent startup — obs path through MetaField digest / Aurora"
    )
    parser.add_argument("--udp", type=int, default=4210, help="CSI UDP port (bridge owns it)")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="CSI FieldObservation JSONL")
    parser.add_argument(
        "--memory", type=Path, default=DEFAULT_MEMORY, help="FieldMemoryEntry JSONL"
    )
    parser.add_argument(
        "--digest", type=Path, default=DEFAULT_DIGEST, help="Aurora-facing digest JSON"
    )
    parser.add_argument("--metafield-root", type=Path, default=None)
    parser.add_argument("--no-view", action="store_true", help="Skip Throne live view")
    parser.add_argument(
        "--no-consumer", action="store_true", help="Skip MetaField optical_serial_consumer"
    )
    parser.add_argument(
        "--digest-interval", type=float, default=5.0, help="Seconds between Aurora digests"
    )
    args = parser.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.memory.parent.mkdir(parents=True, exist_ok=True)
    args.digest.parent.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "observer") + os.pathsep + env.get("PYTHONPATH", "")

    children: list[Child] = []

    # 1) CSI → MetaField FieldObservation JSONL (owns UDP)
    children.append(
        Child(
            name="metafield_bridge",
            cmd=[
                sys.executable,
                "-m",
                "observer.metafield_bridge",
                "--udp",
                str(args.udp),
                "--out",
                str(args.out),
            ],
            cwd=ROOT,
            env=env,
            required=True,
        )
    )

    # 2) Throne view tails the same JSONL (no second UDP bind)
    if not args.no_view:
        children.append(
            Child(
                name="throne_view",
                cmd=[
                    sys.executable,
                    str(ROOT / "observer" / "live_view.py"),
                    "--file",
                    str(args.out),
                    "--from-start",
                ],
                cwd=ROOT,
                env=env,
                required=False,
            )
        )

    # 3) MetaField digest consumer if repo present
    mf_root = _discover_metafield(args.metafield_root)
    if mf_root and not args.no_consumer:
        consumer = mf_root / "optical_serial_consumer.py"
        if consumer.exists():
            children.append(
                Child(
                    name="metafield_consumer",
                    cmd=[
                        sys.executable,
                        str(consumer),
                        "--file",
                        str(args.out),
                        "--follow",
                        "--save",
                        str(args.memory),
                    ],
                    cwd=mf_root,
                    env=env,
                    required=False,
                )
            )
            print(f"[control] MetaField root: {mf_root}", flush=True)
        else:
            print(f"[control] MetaField found but no consumer at {consumer}", flush=True)
    elif not args.no_consumer:
        print(
            "[control] MetaField root not found — obs path runs without memory promote\n"
            "          set METAFIELD_ROOT or --metafield-root",
            flush=True,
        )

    print("[control] startup sequence", flush=True)
    for c in children:
        c.start()
        time.sleep(0.3)

    stopping = False

    def _shutdown(signum: int, frame: Any) -> None:
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    last_digest = 0.0
    print(
        f"[control] running  bridge=:{args.udp}  out={args.out}  digest={args.digest}",
        flush=True,
    )

    try:
        while not stopping:
            for c in children:
                if c.required:
                    c.restart_if_dead()
                elif c.proc is not None and not c.alive():
                    # optional children: report once, do not tight-loop restart
                    pass

            now = time.time()
            if now - last_digest >= args.digest_interval:
                digest = _write_digest(
                    args.digest,
                    children=children,
                    out_jsonl=args.out,
                    memory_jsonl=args.memory,
                    packet_lines=_count_lines(args.out),
                    memory_lines=_count_lines(args.memory),
                )
                # Aurora mod tick if importable
                try:
                    if mf_root:
                        sys.path.insert(0, str(mf_root))
                        from aurora_mods.metafield_sensing.entrypoint import (  # type: ignore
                            on_sensing_tick,
                        )

                        on_sensing_tick()
                except Exception:
                    pass

                print(
                    f"[control] digest health={digest['health']}  "
                    f"csi_lines={digest['obs_path']['csi_lines']}  "
                    f"memory_lines={digest['obs_path']['memory_lines']}",
                    flush=True,
                )
                last_digest = now

            time.sleep(0.5)
    finally:
        print("[control] shutting down", flush=True)
        for c in reversed(children):
            _kill(c.proc)
        # final digest
        _write_digest(
            args.digest,
            children=children,
            out_jsonl=args.out,
            memory_jsonl=args.memory,
            packet_lines=_count_lines(args.out),
            memory_lines=_count_lines(args.memory),
        )
        print("[control] stopped", flush=True)


if __name__ == "__main__":
    main()
