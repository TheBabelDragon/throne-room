#!/usr/bin/env python3
"""
Throne Room — torch display popup (closed-loop HUD)

  1. CSI subcarriers
  2. Body energy map (rich spatial + labels + action flash)
  3. Live dynamics (energy · spread · pressure · pred · residual)
     + Aurora action markers on the time series
  4. Aurora / field / host / process chips + loop state

Closed-loop flexes:
  - vertical action marks on dynamics when Aurora journals
  - body ring flash when an intent targets that body
  - residual-driven pressure glow
  - loop chip CLOSED when bridge + aurora + digest are live

Usage:
  python -m visualization.torch_display
  python -m observer.startup --torch
  python -m observer.startup --full
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
import time
from collections import deque
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

try:
    import numpy as np
except ImportError:
    print("[torch-display] pip install numpy matplotlib", file=sys.stderr)
    sys.exit(1)

import matplotlib


def _configure_backend() -> str:
    for b in ("TkAgg", "QtAgg", "Qt5Agg", "GTK4Agg", "GTK3Agg"):
        try:
            matplotlib.use(b, force=True)
            return b
        except Exception:
            continue
    matplotlib.use("Agg", force=True)
    return "Agg"


_BACKEND = _configure_backend()

import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import Circle, FancyBboxPatch

try:
    from observer.measurement import DISPLAY_LEN, standard_banner
except ImportError:
    DISPLAY_LEN = 1200

    def standard_banner() -> str:
        return "measurement: default"

try:
    from visualization.body_field import body_energy_field
except ImportError:
    body_energy_field = None

DEFAULT_CSI = Path("/tmp/metafield/csi.jsonl")
DEFAULT_DIGEST = Path("/tmp/metafield/obs_digest.json")
DEFAULT_ACTIONS = Path("/tmp/metafield/aurora_actions.jsonl")
DEFAULT_HEAD = Path("/tmp/metafield/throne_head.pt")

_THRONE_CMAP = LinearSegmentedColormap.from_list(
    "throne",
    ["#0b0d10", "#1a1040", "#3d1a6e", "#c44dff", "#ff6b9d", "#ffe066", "#ffffff"],
)


def _tail_new_lines(path: Path, offset: int) -> tuple[list[str], int]:
    if not path.exists():
        return [], offset
    try:
        with path.open("r", encoding="utf-8") as f:
            f.seek(offset)
            data = f.read()
            new_off = f.tell()
        if not data:
            return [], new_off
        return [ln for ln in data.splitlines() if ln.strip().startswith("{")], new_off
    except OSError:
        return [], offset


def _parse_packet(data: dict) -> dict | None:
    if data.get("type") == "wifi_csi" or ("csi" in data and "node" in data):
        node = str(data.get("node") or "csi")
        csi = [float(x) for x in (data.get("csi") or [])[:64]]
        mean = float(np.mean(csi)) if csi else 0.0
        peak = float(np.max(csi)) if csi else 0.0
        energy = float(np.sqrt(np.mean(np.square(csi)))) if csi else 0.0
        spread = float(np.std(csi)) if len(csi) > 1 else 0.0
        try:
            rssi_n = max(0.0, min(1.0, (float(data.get("rssi")) + 90.0) / 60.0))
        except (TypeError, ValueError):
            rssi_n = 0.0
        return {
            "body_id": node,
            "csi": csi,
            "regions": {
                "rssi": rssi_n,
                "csi_mean": mean,
                "csi_peak": peak,
                "csi_energy": energy,
                "csi_spread": min(1.0, spread * 2.0),
            },
            "conf": 0.95,
        }

    if "field_regions" in data and "body_id" in data:
        regions: dict[str, float] = {}
        for r in data.get("field_regions") or []:
            if not isinstance(r, dict):
                continue
            try:
                regions[str(r.get("region") or "")] = float(r.get("observed") or 0.0)
            except (TypeError, ValueError):
                continue
        csi = []
        mod = data.get("modality") or {}
        if isinstance(mod, dict):
            wc = mod.get("wifi_csi") or {}
            if isinstance(wc, dict):
                csi = [float(x) for x in (wc.get("csi") or [])[:64]]
        confs = [
            float(r.get("confidence", 1.0))
            for r in (data.get("field_regions") or [])
            if isinstance(r, dict)
        ]
        return {
            "body_id": str(data["body_id"]),
            "csi": csi,
            "regions": regions,
            "conf": float(np.mean(confs) if confs else 1.0),
        }

    if "body_id" in data and "region" in data:
        try:
            val = float(data.get("value", 0.0))
        except (TypeError, ValueError):
            return None
        return {
            "body_id": str(data["body_id"]),
            "csi": [],
            "regions": {str(data["region"]): val},
            "conf": float(data.get("confidence", 1.0)),
        }
    return None


def _soft_blob(grid: np.ndarray, cx: float, cy: float, strength: float, sigma: float) -> None:
    h, w = grid.shape
    xs = (np.arange(w) + 0.5) / w
    ys = (np.arange(h) + 0.5) / h
    X, Y = np.meshgrid(xs, ys)
    g = np.exp(-((X - cx) ** 2 + (Y - cy) ** 2) / (2 * sigma * sigma))
    grid += strength * g


class TorchDisplay:
    def __init__(
        self,
        *,
        file: Path | None,
        udp_port: int | None,
        digest: Path,
        actions: Path,
        field_head: Path | None,
        head_threshold: float,
        size: int = 56,
        hz: float = 36.0,
    ) -> None:
        self.file = file
        self.udp_port = udp_port
        self.digest = digest
        self.actions = actions
        self.size = max(24, size)
        self.tick_dt = 1.0 / max(8.0, min(60.0, hz))
        self._file_off = 0
        self._action_off = 0
        self._running = True
        self._frame = 0
        self._t0 = time.time()

        self.bodies: dict[str, dict] = {}
        self.last_csi: list[float] = []
        self.last_body = "—"
        self.hist_mean: deque = deque(maxlen=DISPLAY_LEN)
        self.hist_energy: deque = deque(maxlen=DISPLAY_LEN)
        self.hist_spread: deque = deque(maxlen=DISPLAY_LEN)
        self.hist_pred: deque = deque(maxlen=DISPLAY_LEN)
        self.hist_resid: deque = deque(maxlen=DISPLAY_LEN)
        self.hist_pressure: deque = deque(maxlen=DISPLAY_LEN)
        self.action_marks: deque = deque(maxlen=48)
        self._action_vlines: list = []
        self._body_flash: dict[str, float] = {}
        self._loop_closed = False
        self._last_action_t = 0.0
        self.pkt_count = 0
        self._rate = 0.0
        self._rate_t = time.time()
        self._rate_n = 0
        self._last_pressure = 0.0
        self._prev_grid: np.ndarray | None = None

        self._anchors: dict[str, tuple[float, float]] = {}

        self.head = None
        if field_head is not None and Path(field_head).exists():
            try:
                from visualization.field_head import ThroneFieldHead

                self.head = ThroneFieldHead(field_head, threshold=head_threshold)
            except Exception as e:
                print(f"[torch-display] field head not loaded: {e}")

        self._sock = None
        if udp_port is not None:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                self._sock.bind(("0.0.0.0", udp_port))
            except OSError as e:
                print(
                    f"[torch-display] UDP :{udp_port} busy ({e}) — tail JSONL instead",
                    flush=True,
                )
                self._sock.close()
                self._sock = None
            else:
                self._sock.settimeout(0.005)

        self.fig = plt.figure(figsize=(14, 10), facecolor="#0b0d10")
        try:
            self.fig.canvas.manager.set_window_title("Throne Room · torch display")
        except Exception:
            pass
        gs = self.fig.add_gridspec(
            2, 2, hspace=0.30, wspace=0.24, left=0.05, right=0.98, top=0.93, bottom=0.05
        )
        self.ax_csi = self.fig.add_subplot(gs[0, 0])
        self.ax_map = self.fig.add_subplot(gs[0, 1])
        self.ax_hist = self.fig.add_subplot(gs[1, 0])
        self.ax_aurora = self.fig.add_subplot(gs[1, 1])

        for ax in (self.ax_csi, self.ax_map, self.ax_hist, self.ax_aurora):
            ax.set_facecolor("#0e1116")
            ax.tick_params(colors="#7a8a9a", labelsize=7)
            for spine in ax.spines.values():
                spine.set_color("#2a3340")

        self.bars = self.ax_csi.bar(
            np.arange(32), np.zeros(32), color="#4cc9f0", width=0.85,
            edgecolor="#0b0d10", linewidth=0.3,
        )
        self.ax_csi.set_xlim(-0.5, 31.5)
        self.ax_csi.set_ylim(0, 1.08)
        self.ax_csi.set_title("1 · CSI subcarriers", color="#e8eef5", fontsize=11, pad=8)
        self.csi_txt = self.ax_csi.text(
            0.02, 0.98, "waiting…", transform=self.ax_csi.transAxes,
            ha="left", va="top", fontsize=8, family="monospace", color="#cfe8ff",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="#141a24", alpha=0.9, edgecolor="#2a3340"),
        )

        z = np.zeros((self.size, self.size), dtype=np.float32)
        self.im_map = self.ax_map.imshow(
            z, cmap=_THRONE_CMAP, vmin=0, vmax=1, origin="lower",
            extent=[0, 1, 0, 1], interpolation="bilinear", aspect="equal",
        )
        self.ax_map.set_title("2 · body energy field", color="#e8eef5", fontsize=11, pad=8)
        self.fig.colorbar(self.im_map, ax=self.ax_map, fraction=0.046, pad=0.04)
        self.map_txt = self.ax_map.text(
            0.02, 0.98, "bodies: 0", transform=self.ax_map.transAxes,
            ha="left", va="top", fontsize=8, family="monospace", color="#cfe8ff",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="#141a24", alpha=0.9, edgecolor="#2a3340"),
        )
        self._map_rings: list[Circle] = []
        self._map_labels: list = []
        for _ in range(12):
            ring = Circle((0.5, 0.5), 0.04, fill=False, edgecolor="#ffe066", lw=1.6, alpha=0, zorder=6)
            self.ax_map.add_patch(ring)
            self._map_rings.append(ring)
            lab = self.ax_map.text(
                0.5, 0.5, "", color="#f0f4fa", fontsize=7, ha="center", va="bottom",
                alpha=0, zorder=7, family="monospace",
            )
            self._map_labels.append(lab)

        self.ax_hist.set_title("3 · live dynamics", color="#e8eef5", fontsize=11, pad=8)
        self.ax_hist.set_xlim(0, 96)
        self.ax_hist.set_ylim(0, 1.08)
        self.ax_hist.grid(True, alpha=0.12, color="#8899aa")
        (self.ln_mean,) = self.ax_hist.plot([], [], color="#00d4aa", lw=2.2, label="mean", solid_capstyle="round")
        (self.ln_energy,) = self.ax_hist.plot([], [], color="#4cc9f0", lw=1.8, label="energy")
        (self.ln_spread,) = self.ax_hist.plot([], [], color="#f4a261", lw=1.5, label="spread")
        (self.ln_pressure,) = self.ax_hist.plot([], [], color="#c77dff", lw=2.2, label="pressure")
        (self.ln_pred,) = self.ax_hist.plot([], [], color="#ffe066", lw=1.4, alpha=0.9, label="pred", ls="--")
        (self.ln_resid,) = self.ax_hist.plot([], [], color="#ff4d6d", lw=1.5, label="|resid|", alpha=0.85)
        self.fill_energy = self.ax_hist.fill_between([], [], color="#4cc9f0", alpha=0.18, zorder=1)
        self.fill_pressure = self.ax_hist.fill_between([], [], color="#c77dff", alpha=0.22, zorder=1)
        self.ax_hist.legend(
            loc="upper left", fontsize=6, framealpha=0.55,
            facecolor="#141a24", labelcolor="#ccc", ncol=3,
        )

        self.ax_aurora.set_title("4 · Aurora · field · host · processes", color="#e8eef5", fontsize=11, pad=8)
        self.ax_aurora.set_xlim(0, 10)
        self.ax_aurora.set_ylim(0, 8)
        self.ax_aurora.set_xticks([])
        self.ax_aurora.set_yticks([])
        self.aurora_txt = self.ax_aurora.text(
            0.03, 0.98, "", transform=self.ax_aurora.transAxes,
            ha="left", va="top", fontsize=8.5, family="monospace",
            color="#cfe8ff", linespacing=1.45,
        )
        self._chip_patches: list[FancyBboxPatch] = []
        self._chip_labels: list = []
        chip_xy = [
            (0.05, 0.22), (0.36, 0.22), (0.67, 0.22),
            (0.05, 0.10), (0.36, 0.10), (0.67, 0.10),
            (0.36, 0.01),
        ]
        for i, (cx, cy) in enumerate(chip_xy):
            box = FancyBboxPatch(
                (cx, cy),
                0.28, 0.09,
                boxstyle="round,pad=0.02,rounding_size=0.02",
                transform=self.ax_aurora.transAxes,
                facecolor="#1a2030", edgecolor="#333", lw=1, alpha=0.95,
            )
            self.ax_aurora.add_patch(box)
            self._chip_patches.append(box)
            lab = self.ax_aurora.text(
                cx + 0.14, cy + 0.045, "",
                transform=self.ax_aurora.transAxes,
                ha="center", va="center", fontsize=7, family="monospace", color="#8899aa",
            )
            self._chip_labels.append(lab)

        bits = ["live"]
        if self.head:
            bits.append("head")
        self.fig.suptitle(
            f"THRONE ROOM  ·  {' + '.join(bits)}  ·  {hz:.0f} Hz HUD",
            fontsize=13, color="#f0f4fa", fontweight="bold",
        )
        self.status = self.fig.text(
            0.5, 0.008, "", ha="center", fontsize=8, family="monospace", color="#7a8a9a"
        )
        self.fig.canvas.mpl_connect("close_event", lambda e: setattr(self, "_running", False))

    def _anchor_for(self, body_id: str) -> tuple[float, float]:
        if body_id not in self._anchors:
            h = abs(hash(body_id))
            self._anchors[body_id] = (
                0.11 + (h % 1000) / 1000.0 * 0.78,
                0.11 + ((h // 1000) % 1000) / 1000.0 * 0.78,
            )
        return self._anchors[body_id]

    def _ingest(self, pkt: dict) -> None:
        body = pkt["body_id"]
        st = self.bodies.setdefault(
            body, {"regions": {}, "conf": 1.0, "last": time.time(), "n": 0}
        )
        st["regions"].update(pkt["regions"])
        st["conf"] = pkt["conf"]
        st["last"] = time.time()
        st["n"] += 1
        if pkt["csi"]:
            self.last_csi = pkt["csi"]
            self.last_body = body
        self.pkt_count += 1
        self._rate_n += 1

        regs = st["regions"]
        mean = float(regs.get("csi_mean", 0.0))
        energy = float(regs.get("csi_energy", mean))
        spread = float(regs.get("csi_spread", 0.0))
        peak = float(regs.get("csi_peak", mean))
        rssi = float(regs.get("rssi", 0.0))
        self.hist_mean.append(mean)
        self.hist_energy.append(energy)
        self.hist_spread.append(spread)

        if self.head is not None:
            n_bodies = float(len(self.bodies))
            mean_conf = float(np.mean([b["conf"] for b in self.bodies.values()] or [1.0]))
            out = self.head.update([
                mean, energy, spread, peak, rssi,
                min(1.0, n_bodies / 6.0), mean_conf, min(1.0, self._rate / 20.0),
            ])
            self.hist_pred.append(float(out["pred"]))
            self.hist_resid.append(float(out["abs_residual"]))
        else:
            self.hist_pred.append(0.0)
            self.hist_resid.append(0.0)

    def _poll_sources(self) -> None:
        if self.file is not None:
            lines, self._file_off = _tail_new_lines(self.file, self._file_off)
            for line in lines:
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                pkt = _parse_packet(data)
                if pkt:
                    self._ingest(pkt)

        if self._sock is not None:
            try:
                while True:
                    data, _ = self._sock.recvfrom(65535)
                    for line in data.decode("utf-8", errors="replace").splitlines():
                        if not line.strip():
                            continue
                        try:
                            obj = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        pkt = _parse_packet(obj)
                        if pkt:
                            self._ingest(pkt)
            except socket.timeout:
                pass
            except OSError:
                pass

        alines, self._action_off = _tail_new_lines(self.actions, self._action_off)
        for line in alines:
            try:
                act = json.loads(line)
            except json.JSONDecodeError:
                continue
            tnow = time.time()
            atype = str(act.get("type") or act.get("action") or "?")
            body = act.get("body_id")
            body_s = str(body) if body else None
            pri = float(act.get("priority") or 0)
            self.action_marks.append({
                "t": tnow,
                "type": atype,
                "priority": pri,
                "reason": str(act.get("reason") or "")[:40],
                "body_id": body_s,
            })
            self._last_action_t = tnow
            if body_s:
                self._body_flash[body_s] = tnow + 2.5

    def _body_field(self) -> np.ndarray:
        if body_energy_field is not None:
            grid = body_energy_field(
                self.bodies, self._anchors, size=self.size,
                prev=self._prev_grid, blend=0.22,
            )
        else:
            grid = np.zeros((self.size, self.size), dtype=np.float32)
            now = time.time()
            for bid, st in self.bodies.items():
                age = now - st["last"]
                fade = 1.0 if age < 1.5 else (0.55 if age < 5 else (0.2 if age < 12 else 0.06))
                regs = st["regions"]
                energy = float(regs.get("csi_energy", regs.get("csi_mean", 0.0)))
                spread = float(regs.get("csi_spread", 0.15))
                peak = float(regs.get("csi_peak", energy))
                strength = max(energy, peak * 0.85) * fade
                if strength < 0.02:
                    continue
                cx, cy = self._anchor_for(bid)
                sigma = 0.05 + 0.12 * min(1.0, spread + 0.15)
                _soft_blob(grid, cx, cy, strength, sigma)
                _soft_blob(grid, cx, cy, strength * 0.45, sigma * 0.45)
                _soft_blob(grid, cx, cy, strength * 0.2, sigma * 1.6)
            grid = (
                grid
                + np.roll(grid, 1, 0) * 0.15
                + np.roll(grid, -1, 0) * 0.15
                + np.roll(grid, 1, 1) * 0.15
                + np.roll(grid, -1, 1) * 0.15
            ) / 1.6
            mx = float(grid.max())
            if mx > 1.0:
                grid /= mx
        self._prev_grid = grid.copy()
        return grid

    def _update_map_markers(self, now: float) -> None:
        ranked = sorted(
            self.bodies.items(),
            key=lambda kv: kv[1]["last"],
            reverse=True,
        )[:12]
        for i, ring in enumerate(self._map_rings):
            lab = self._map_labels[i]
            if i >= len(ranked):
                ring.set_alpha(0)
                lab.set_alpha(0)
                continue
            bid, st = ranked[i]
            cx, cy = self._anchor_for(bid)
            age = now - st["last"]
            energy = float(st["regions"].get("csi_energy", st["regions"].get("csi_mean", 0)))
            flash = self._body_flash.get(bid, 0) > now
            a = 1.0 if flash else (0.95 if age < 2 else (0.55 if age < 8 else 0.25))
            ring.center = (cx, cy)
            ring.set_radius(0.025 + 0.07 * min(1.0, energy) + (0.04 if flash else 0))
            ring.set_alpha(a)
            if flash:
                ring.set_edgecolor("#ff4d6d")
                ring.set_linewidth(2.4)
            else:
                ring.set_edgecolor("#ffe066" if age < 2 else ("#4cc9f0" if age < 8 else "#666"))
                ring.set_linewidth(1.6)
            short = bid if len(bid) <= 10 else bid[:9] + "…"
            lab.set_position((cx, cy + 0.035 + 0.07 * min(1.0, energy) + (0.03 if flash else 0)))
            lab.set_text(f"{short}\n{energy:.2f}" + (" ★" if flash else ""))
            lab.set_alpha(a)
            lab.set_color("#ffb3c1" if flash else "#f0f4fa")

    def _set_chips(self, children: dict, host: dict) -> None:
        order = [
            ("bridge", "metafield_bridge"),
            ("view", "throne_view"),
            ("torch", "torch_display"),
            ("memory", "metafield_consumer"),
            ("aurora", "aurora_action"),
            ("host", None),
            ("loop", "LOOP"),
        ]
        for i, (label, key) in enumerate(order):
            box = self._chip_patches[i]
            lab = self._chip_labels[i]
            if key is None:
                stressed = bool(host.get("stressed"))
                advice = str(host.get("advice") or "ok")
                up = not stressed
                text = f"host:{advice}"
            elif key == "LOOP":
                up = self._loop_closed
                text = "loop:CLOSED" if up else "loop:OPEN"
            else:
                st = children.get(key) or {}
                up = bool(st.get("alive"))
                text = f"{label}:{'UP' if up else '—'}"
            box.set_facecolor("#14322a" if up else "#2a1520")
            box.set_edgecolor("#2ecc71" if up else "#555")
            if key == "LOOP" and up:
                box.set_facecolor("#1a3a4a")
                box.set_edgecolor("#4cc9f0")
            lab.set_text(text)
            lab.set_color("#a8ffce" if up else "#8899aa")
            if key == "LOOP" and up:
                lab.set_color("#cfe8ff")

    def _local_pressure(self) -> float:
        if not self.bodies:
            return 0.0
        now = time.time()
        heats = []
        for st in self.bodies.values():
            if now - st["last"] > 12:
                continue
            regs = st["regions"]
            e = float(regs.get("csi_energy", regs.get("csi_mean", 0.0)))
            p = float(regs.get("csi_peak", e))
            heats.append(max(e, p * 0.9))
        if not heats:
            return 0.0
        total = sum(heats)
        peak = max(heats)
        active = sum(1 for h in heats if h > 0.12)
        score = (total / max(1, len(heats))) * 0.45 + peak * 0.40 + min(1.0, active / 4.0) * 0.15
        return float(max(0.0, min(1.0, score)))

    def tick(self) -> None:
        if not self._running:
            return
        self._frame += 1
        self._poll_sources()

        now = time.time()
        if now - self._rate_t >= 0.5:
            self._rate = self._rate_n / max(1e-6, now - self._rate_t)
            self._rate_t = now
            self._rate_n = 0

        csi = self.last_csi[:32]
        if len(csi) < 32:
            csi = list(csi) + [0.0] * (32 - len(csi))
        for rect, h in zip(self.bars, csi):
            rect.set_height(float(np.clip(h, 0, 1)))
            rect.set_color("#ff4d6d" if h > 0.75 else ("#ffe066" if h > 0.45 else "#4cc9f0"))
        surprise = bool(self.head and getattr(self.head, "ready", False) and getattr(self.head, "surprise", False))
        self.csi_txt.set_text(
            f"body {self.last_body}\n"
            f"{self._rate:.1f} Hz  pkts {self.pkt_count}"
            + ("  SURPRISE" if surprise else "")
        )

        grid = self._body_field()
        self.im_map.set_data(grid)
        peak = float(grid.max())
        self.im_map.set_clim(0.0, max(0.35, peak * 1.05 + 1e-6))
        active = sum(1 for b in self.bodies.values() if now - b["last"] < 5)
        self.map_txt.set_text(f"bodies {len(self.bodies)}  live {active}  peak {peak:.2f}")
        self._update_map_markers(now)

        digest: dict = {}
        if self.digest.exists():
            try:
                digest = json.loads(self.digest.read_text())
            except Exception:
                digest = {}
        dig_p = float((digest.get("field") or {}).get("pressure") or 0.0)
        local_p = self._local_pressure()
        pressure = 0.55 * local_p + 0.45 * dig_p
        self._last_pressure = 0.72 * self._last_pressure + 0.28 * pressure
        self.hist_pressure.append(self._last_pressure)

        def _set(line, hist, window: int = 96):
            if not hist:
                return
            ys = np.asarray(hist, dtype=float)
            n = min(window, len(ys))
            line.set_data(np.arange(n), ys[-n:])

        _set(self.ln_mean, self.hist_mean)
        _set(self.ln_energy, self.hist_energy)
        _set(self.ln_spread, self.hist_spread)
        _set(self.ln_pressure, self.hist_pressure)
        _set(self.ln_pred, self.hist_pred)
        _set(self.ln_resid, self.hist_resid)

        n_show = max(40, min(96, len(self.hist_mean)))
        self.ax_hist.set_xlim(0, n_show)
        try:
            self.fill_energy.remove()
            self.fill_pressure.remove()
        except Exception:
            pass
        if self.hist_energy:
            ye = np.asarray(self.hist_energy, dtype=float)[-n_show:]
            xe = np.arange(len(ye))
            self.fill_energy = self.ax_hist.fill_between(xe, 0, ye, color="#4cc9f0", alpha=0.18, zorder=1)
        if self.hist_pressure:
            yp = np.asarray(self.hist_pressure, dtype=float)[-n_show:]
            xp = np.arange(len(yp))
            self.fill_pressure = self.ax_hist.fill_between(xp, 0, yp, color="#c77dff", alpha=0.22, zorder=1)

        for ln in self._action_vlines:
            try:
                ln.remove()
            except Exception:
                pass
        self._action_vlines = []
        if self.hist_mean and self.action_marks:
            for act in list(self.action_marks)[-8:]:
                age = now - act["t"]
                if age > 25:
                    continue
                x = n_show - age * 4.0
                if x < 0 or x > n_show:
                    continue
                color = {
                    "probe": "#ffe066",
                    "attention": "#4cc9f0",
                    "scale_down": "#f4a261",
                    "hold": "#ff4d6d",
                }.get(act["type"], "#c77dff")
                vl = self.ax_hist.axvline(x, color=color, lw=1.4, alpha=0.75, zorder=5)
                self._action_vlines.append(vl)

        resid = 0.0
        if self.hist_resid:
            resid = float(self.hist_resid[-1])
        if resid > 0.18 or (self.head and getattr(self.head, "surprise", False)):
            try:
                self.fill_pressure.set_alpha(0.22 + min(0.35, resid * 0.8))
            except Exception:
                pass
        else:
            try:
                self.fill_pressure.set_alpha(0.22)
            except Exception:
                pass

        health = digest.get("health", "—")
        children = digest.get("children") or {}
        host = digest.get("host") or {}
        field = digest.get("field") or {}

        bridge_up = bool((children.get("metafield_bridge") or {}).get("alive"))
        aurora_up = bool((children.get("aurora_action") or {}).get("alive"))
        recent_act = (now - self._last_action_t) < 30.0
        self._loop_closed = bool(
            bridge_up and (aurora_up or recent_act) and health in {"ok", "degraded"}
        )

        self._set_chips(children, host)

        head_line = "head: off"
        if self.head:
            if getattr(self.head, "ready", False):
                head_line = (
                    f"head pred={getattr(self.head, 'last_pred', 0):.2f} "
                    f"|r|={getattr(self.head, 'last_abs_residual', 0):.3f}"
                    + (" SURPRISE" if getattr(self.head, "surprise", False) else "")
                )
            else:
                head_line = "head: warming"

        acts = list(self.action_marks)[-4:]
        act_lines = "\n".join(
            f"  {a['type']:10s} p={a['priority']:.2f} {a['reason']}" for a in acts
        ) or "  (no actions)"

        loop_s = "CLOSED" if self._loop_closed else "OPEN"
        self.aurora_txt.set_text(
            f"loop {loop_s}   health {health}   pressure {self._last_pressure:.3f}   bodies {field.get('n_bodies', len(self.bodies))}\n"
            f"host cpu={host.get('cpu_pct', '—')}%  mem={host.get('mem_pct', '—')}%  {host.get('advice', '—')}\n"
            f"{head_line}\n"
            f"actions:\n{act_lines}"
        )

        elapsed = now - self._t0
        self.status.set_text(
            f"t={elapsed:.0f}s  frame={self._frame}  ui≈{1.0/self.tick_dt:.0f}Hz  "
            f"in={self._rate:.1f}pkt/s  pressure={self._last_pressure:.3f}  last={self.last_body}"
        )

    def run(self) -> None:
        if _BACKEND == "Agg":
            print("[torch-display] no GUI backend — need Tk/Qt on a desktop session", flush=True)
            print("[torch-display] tip: run on a machine with DISPLAY, or `python -m visualization.torch_display` in a terminal that can open windows", flush=True)
            return
        print(f"[torch-display] backend={_BACKEND}  tick={self.tick_dt*1000:.0f}ms", flush=True)
        print(f"[torch-display] {standard_banner()}", flush=True)
        if self.file:
            print(f"[torch-display] tail {self.file}", flush=True)
        if self._sock:
            print(f"[torch-display] UDP :{self.udp_port}", flush=True)

        plt.show(block=False)
        self.fig.canvas.draw()
        try:
            while self._running and plt.fignum_exists(self.fig.number):
                t0 = time.time()
                self.tick()
                self.fig.canvas.draw_idle()
                spent = time.time() - t0
                plt.pause(max(0.001, self.tick_dt - spent))
        except KeyboardInterrupt:
            pass
        finally:
            self._running = False
            if self._sock:
                try:
                    self._sock.close()
                except OSError:
                    pass
            try:
                plt.close(self.fig)
            except Exception:
                pass
            print("[torch-display] closed", flush=True)


def main() -> None:
    p = argparse.ArgumentParser(description="Throne Room torch display — closed-loop HUD")
    p.add_argument("--file", "-f", type=Path, default=None)
    p.add_argument("--udp", type=int, nargs="?", const=4210, default=None)
    p.add_argument("--digest", type=Path, default=DEFAULT_DIGEST)
    p.add_argument("--actions", type=Path, default=DEFAULT_ACTIONS)
    p.add_argument("--field-head", nargs="?", const=str(DEFAULT_HEAD), default=None)
    p.add_argument("--head-threshold", type=float, default=0.30)
    p.add_argument("--size", type=int, default=56, help="Body field resolution")
    p.add_argument("--hz", type=float, default=36.0, help="UI refresh target Hz")
    a = p.parse_args()

    if a.file is None and a.udp is None:
        if DEFAULT_CSI.exists():
            a.file = DEFAULT_CSI
        else:
            a.udp = 4210

    TorchDisplay(
        file=a.file,
        udp_port=a.udp,
        digest=a.digest,
        actions=a.actions,
        field_head=Path(a.field_head) if a.field_head else None,
        head_threshold=a.head_threshold,
        size=a.size,
        hz=a.hz,
    ).run()


if __name__ == "__main__":
    main()
