#!/usr/bin/env python3
"""Intelligent control / startup sequence — multi-process conductor."""

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

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "observer") not in sys.path:
    sys.path.insert(0, str(ROOT / "observer"))


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
    except OSError:
        pass


@dataclass
class Child:
    name: str
    proc: subprocess.Popen | None = None
    cmd: list[str] = field(default_factory=list)
    cwd: Path | None = None
    env: dict[str, str] = field(default_factory=dict)
    required: bool = True
    inherit_stdio: bool = False

    def alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def start(self) -> None:
        if self.alive():
            return
        env = os.environ.copy()
        env.update(self.env)
        std = None if self.inherit_stdio else subprocess.DEVNULL
        self.proc = subprocess.Popen(
            self.cmd,
            cwd=str(self.cwd or ROOT),
            env=env,
            stdout=std,
            stderr=std,
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


def _count_lines(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        with path.open("rb") as f:
            return sum(1 for _ in f)
    except OSError:
        return 0


def _tail_packets(path: Path, max_lines: int = 200) -> list[dict]:
    if not path.exists():
        return []
    try:
        with path.open("rb") as f:
            f.seek(0, 2)
            size = f.tell()
            data = b""
            block = 65536
            while size > 0 and len(data) < max_lines * 256:
                read = min(block, size)
                size -= read
                f.seek(size)
                data = f.read(read) + data
            lines = data.splitlines()[-max_lines:]
    except OSError:
        return []
    out: list[dict] = []
    for raw in lines:
        try:
            obj = json.loads(raw.decode("utf-8", errors="replace"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out


def _update_cubes(ensemble: Any, packets: list[dict]) -> dict:
    for pkt in packets:
        body = str(pkt.get("body_id") or "")
        if not body:
            continue
        regions: dict[str, float] = {}
        for r in pkt.get("field_regions") or []:
            if not isinstance(r, dict):
                continue
            name = str(r.get("region") or "")
            try:
                regions[name] = float(r.get("observed") or 0.0)
            except (TypeError, ValueError):
                continue
        if regions:
            ensemble.observe(body, regions)
    ensemble.decay_all(0.997)
    return ensemble.snapshot()


def _write_digest(
    path: Path,
    *,
    children: list[Child],
    out_jsonl: Path,
    memory_jsonl: Path,
    packet_lines: int,
    memory_lines: int,
    field_snap: dict | None = None,
    host_snap: dict | None = None,
    measurement: dict | None = None,
) -> dict[str, Any]:
    child_state = {
        c.name: {
            "alive": c.alive(),
            "pid": c.proc.pid if c.proc and c.alive() else None,
            "required": c.required,
        }
        for c in children
    }
    healthy = all(c.alive() for c in children if c.required)

    mf_stats: dict[str, Any] = {}
    if DEFAULT_STATS.exists():
        try:
            mf_stats = json.loads(DEFAULT_STATS.read_text())
        except Exception:
            mf_stats = {"health": "unreadable"}

    if host_snap and host_snap.get("stressed"):
        healthy = False

    digest = {
        "schema_version": 1,
        "type": "OBS_PATH_DIGEST",
        "timestamp": _now(),
        "source": "throne-room.control",
        "aurora_rev": "file-digest-v2+pressure+host",
        "health": "ok" if healthy else "degraded",
        "obs_path": {
            "csi_jsonl": str(out_jsonl),
            "csi_lines": packet_lines,
            "memory_jsonl": str(memory_jsonl),
            "memory_lines": memory_lines,
            "udp_owner": "metafield_bridge",
        },
        "children": child_state,
        "field": field_snap or {},
        "host": host_snap or {},
        "measurement": measurement or {},
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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Throne Room intelligent startup — multi-process conductor"
    )
    parser.add_argument("--udp", type=int, default=4210)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--memory", type=Path, default=DEFAULT_MEMORY)
    parser.add_argument("--digest", type=Path, default=DEFAULT_DIGEST)
    parser.add_argument("--metafield-root", type=Path, default=None)
    parser.add_argument("--no-view", action="store_true")
    parser.add_argument(
        "--torch", action="store_true",
        help="Launch torch display popup (matplotlib HUD)",
    )
    parser.add_argument(
        "--no-torch", action="store_true",
        help="Disable torch even if THRONE_TORCH=1",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Auto throne-up: torch display + Aurora action (cautious) + view + bridge",
    )
    parser.add_argument("--no-consumer", action="store_true")
    parser.add_argument("--digest-interval", type=float, default=2.5)
    parser.add_argument("--action", action="store_true")
    parser.add_argument(
        "--action-mode", choices=("observe", "cautious", "auto"), default="cautious",
    )
    parser.add_argument("--action-file-only", action="store_true")
    args = parser.parse_args()

    if args.full:
        args.torch = True
        args.action = True
        print("[control] --full → torch + Aurora action + view + bridge", flush=True)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.memory.parent.mkdir(parents=True, exist_ok=True)
    args.digest.parent.mkdir(parents=True, exist_ok=True)

    try:
        from measurement import FINE_LEN, SAMPLE_HZ, WINDOW_S, standard_banner
    except ImportError:
        from observer.measurement import FINE_LEN, SAMPLE_HZ, WINDOW_S, standard_banner  # type: ignore

    try:
        from field_cube import FieldCubeEnsemble
    except ImportError:
        from observer.field_cube import FieldCubeEnsemble  # type: ignore

    try:
        from host_guard import snapshot as host_snapshot
    except ImportError:
        from observer.host_guard import snapshot as host_snapshot  # type: ignore

    print(f"[control] {standard_banner()}", flush=True)

    ensemble = FieldCubeEnsemble()
    measurement_meta = {
        "sample_hz": SAMPLE_HZ,
        "window_s": WINDOW_S,
        "fine_len": FINE_LEN,
    }

    env = os.environ.copy()
    env["PYTHONPATH"] = (
        str(ROOT) + os.pathsep + str(ROOT / "observer") + os.pathsep + env.get("PYTHONPATH", "")
    )

    children: list[Child] = []

    children.append(
        Child(
            name="metafield_bridge",
            cmd=[
                sys.executable, "-m", "observer.metafield_bridge",
                "--udp", str(args.udp), "--out", str(args.out),
            ],
            cwd=ROOT, env=env, required=True,
        )
    )

    if not args.no_view:
        children.append(
            Child(
                name="throne_view",
                cmd=[
                    sys.executable, str(ROOT / "observer" / "live_view.py"),
                    "--file", str(args.out), "--from-start",
                ],
                cwd=ROOT, env=env, required=False,
            )
        )

    want_torch = (args.torch or os.environ.get("THRONE_TORCH") == "1") and not args.no_torch
    if want_torch:
        children.append(
            Child(
                name="torch_display",
                cmd=[
                    sys.executable, "-m", "visualization.torch_display",
                    "--file", str(args.out), "--digest", str(args.digest), "--hz", "36",
                ],
                cwd=ROOT, env=env, required=False, inherit_stdio=True,
            )
        )
        print("[control] torch display popup enabled", flush=True)

    mf_root = _discover_metafield(args.metafield_root)
    if mf_root and not args.no_consumer:
        consumer = mf_root / "optical_serial_consumer.py"
        if consumer.exists():
            children.append(
                Child(
                    name="metafield_consumer",
                    cmd=[
                        sys.executable, str(consumer),
                        "--file", str(args.out), "--follow", "--save", str(args.memory),
                    ],
                    cwd=mf_root, env=env, required=False,
                )
            )
            print(f"[control] MetaField root: {mf_root}", flush=True)
        else:
            print(f"[control] MetaField found but no consumer at {consumer}", flush=True)
    elif not args.no_consumer:
        print(
            "[control] MetaField root not found — set METAFIELD_ROOT or --metafield-root",
            flush=True,
        )

    if args.action:
        action_cmd = [
            sys.executable, "-m", "aurora.action_layer",
            "--digest", str(args.digest), "--csi", str(args.out),
            "--mode", args.action_mode,
        ]
        if args.action_file_only:
            action_cmd.append("--file-only")
        children.append(
            Child(
                name="aurora_action",
                cmd=action_cmd, cwd=ROOT, env=env, required=False,
            )
        )
        print(
            f"[control] Aurora action  mode={args.action_mode}  file_only={args.action_file_only}",
            flush=True,
        )

    print("[control] startup sequence", flush=True)
    for c in children:
        c.start()
        time.sleep(0.25)

    stopping = False

    def _shutdown(signum: int, frame: Any) -> None:
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    last_digest = 0.0
    reported_dead: set[str] = set()
    aurora_tick = None
    aurora_tick_failed = False
    if mf_root:
        if str(mf_root) not in sys.path:
            sys.path.insert(0, str(mf_root))
        try:
            from aurora_mods.metafield_sensing.entrypoint import (  # type: ignore
                on_sensing_tick as aurora_tick,
            )
        except Exception as e:
            print(f"[control] Aurora metafield_sensing not loaded: {e}", flush=True)
            aurora_tick_failed = True

    print(
        f"[control] running  bridge=:{args.udp}  out={args.out}  digest={args.digest}",
        flush=True,
    )

    try:
        while not stopping:
            for c in children:
                if c.required:
                    c.restart_if_dead()
                elif c.proc is not None and not c.alive() and c.name not in reported_dead:
                    print(f"[control] optional {c.name} exited ({c.proc.returncode})", flush=True)
                    reported_dead.add(c.name)

            now = time.time()
            if now - last_digest >= args.digest_interval:
                packets = _tail_packets(args.out, max_lines=min(400, FINE_LEN))
                field_snap = _update_cubes(ensemble, packets)
                hs = host_snapshot()
                host_snap = {
                    "cpu_pct": round(hs.cpu_pct, 1),
                    "mem_pct": round(hs.mem_pct, 1),
                    "stressed": hs.stressed,
                    "advice": hs.advice,
                }
                digest = _write_digest(
                    args.digest,
                    children=children,
                    out_jsonl=args.out,
                    memory_jsonl=args.memory,
                    packet_lines=_count_lines(args.out),
                    memory_lines=_count_lines(args.memory),
                    field_snap=field_snap,
                    host_snap=host_snap,
                    measurement=measurement_meta,
                )
                if aurora_tick is not None and not aurora_tick_failed:
                    try:
                        aurora_tick()
                    except Exception as e:
                        print(f"[control] Aurora tick error: {e}", flush=True)
                        aurora_tick_failed = True

                print(
                    f"[control] digest health={digest['health']}  "
                    f"csi={digest['obs_path']['csi_lines']}  "
                    f"mem={digest['obs_path']['memory_lines']}  "
                    f"pressure={field_snap.get('pressure', 0):.3f}  "
                    f"host={host_snap['advice']}  "
                    f"bodies={field_snap.get('n_bodies', 0)}",
                    flush=True,
                )
                last_digest = now

            time.sleep(0.4)
    finally:
        print("[control] shutting down", flush=True)
        for c in reversed(children):
            _kill(c.proc)
        _write_digest(
            args.digest,
            children=children,
            out_jsonl=args.out,
            memory_jsonl=args.memory,
            packet_lines=_count_lines(args.out),
            memory_lines=_count_lines(args.memory),
            measurement=measurement_meta,
        )
        print("[control] stopped", flush=True)


if __name__ == "__main__":
    main()
