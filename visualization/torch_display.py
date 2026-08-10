#!/usr/bin/env python3
"""
Throne Room — torch display popup (Echo-class 4-panel HUD)

Live surface over real FieldObservation / wifi_csi streams.

  1. CSI subcarriers
  2. Body energy map
  3. Time history (mean · energy · spread · pred · residual)
  4. Aurora + field pressure + host

Usage:
  python -m visualization.torch_display
  python -m visualization.torch_display --file /tmp/metafield/csi.jsonl
  python -m visualization.torch_display --field-head /tmp/metafield/throne_head.pt
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
    print(
        "[torch-display] needs numpy + matplotlib:\n"
        "  pip install numpy matplotlib",
        file=sys.stderr,
    )
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
from matplotlib.patches import Rectangle

try:
    from observer.measurement import DISPLAY_LEN, standard_banner
except ImportError:
    DISPLAY_LEN = 1200

    def standard_banner() -> str:
        return "measurement: default"


DEFAULT_CSI = Path("/tmp/metafield/csi.jsonl")
DEFAULT_DIGEST = Path("/tmp/metafield/obs_digest.json")
DEFAULT_ACTIONS = Path("/tmp/metafield/aurora_actions.jsonl")
DEFAULT_HEAD = Path("/tmp/metafield/throne_head.pt")


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
        lines = [ln for ln in data.splitlines() if ln.strip().startswith("{")]
        return lines, new_off
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
        rssi = data.get("rssi")
        try:
            rssi_n = max(0.0, min(1.0, (float(rssi) + 90.0) / 60.0))
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
            name = str(r.get("region") or "")
            try:
                regions[name] = float(r.get("observed") or 0.0)
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
        size: int = 16,
    ) -> None:
        self.file = file
        self.udp_port = udp_port
        self.digest = digest
        self.actions = actions
        self.size = size
        self._file_off = 0
        self._action_off = 0
        self._running = True
        self._frame = 0

        self.bodies: dict[str, dict] = {}
        self.last_csi: list[float] = []
        self.last_body = "\u2014"
        self.hist_mean: deque = deque(maxlen=DISPLAY_LEN)
        self.hist_energy: deque = deque(maxlen=DISPLAY_LEN)
        self.hist_spread: deque = deque(maxlen=DISPLAY_LEN)
        self.hist_pred: deque = deque(maxlen=DISPLAY_LEN)
        self.hist_resid: deque = deque(maxlen=DISPLAY_LEN)
        self.hist_pressure: deque = deque(maxlen=DISPLAY_LEN)
        self.action_marks: deque = deque(maxlen=24)
        self.pkt_count = 0
        self._rate = 0.0
        self._rate_t = time.time()
        self._rate_n = 0

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
                    f"[torch-display] UDP :{udp_port} bind failed ({e}) \u2014 "
                    "use --file /tmp/metafield/csi.jsonl while bridge owns the port",
                    flush=True,
                )
                self._sock.close()
                self._sock = None
            else:
                self._sock.settimeout(0.01)

        self.fig = plt.figure(figsize=(13, 9.5), facecolor="#0b0d10")
        try:
            self.fig.canvas.manager.set_window_title("Throne Room \u00b7 torch display")
        except Exception:
            pass
        gs = self.fig.add_gridspec(
            2, 2, hspace=0.34, wspace=0.28, left=0.06, right=0.98, top=0.92, bottom=0.06
        )
        self.ax_csi = self.fig.add_subplot(gs[0, 0])
        self.ax_map = self.fig.add_subplot(gs[0, 1])
        self.ax_hist = self.fig.add_subplot(gs[1, 0])
        self.ax_aurora = self.fig.add_subplot(gs[1, 1])

        for ax in (self.ax_csi, self.ax_map, self.ax_hist, self.ax_aurora):
            ax.set_facecolor("#12151a")
            ax.tick_params(colors="#8899aa")
            for spine in ax.spines.values():
                spine.set_color("#333")

        self.bars = self.ax_csi.bar(np.arange(32), np.zeros(32), color="#4cc9f0", width=0.85)
        self.ax_csi.set_xlim(-0.5, 31.5)
        self.ax_csi.set_ylim(0, 1.05)
        self.ax_csi.set_title("1 \u00b7 CSI subcarriers", color="#e8eef5", fontsize=11)
        self.csi_txt = self.ax_csi.text(
            0.02, 0.98, "waiting\u2026", transform=self.ax_csi.transAxes,
            ha="left", va="top", fontsize=8, family="monospace", color="#cfe8ff",
            bbox=dict(boxstyle="round,pad=0.25", facecolor="#1a2030", alpha=0.85),
        )

        z = np.zeros((size, size), dtype=np.float32)
        self.im_map = self.ax_map.imshow(
            z, cmap="magma", vmin=0, vmax=1, origin="lower", extent=[0, 1, 0, 1]
        )
        self.ax_map.set_title("2 \u00b7 body energy map", color="#e8eef5", fontsize=11)
        self.fig.colorbar(self.im_map, ax=self.ax_map, fraction=0.046, pad=0.04)
        self.map_txt = self.ax_map.text(
            0.02, 0.98, "bodies: 0", transform=self.ax_map.transAxes,
            ha="left", va="top", fontsize=8, family="monospace", color="#cfe8ff",
            bbox=dict(boxstyle="round,pad=0.25", facecolor="#1a2030", alpha=0.85),
        )

        self.ax_hist.set_title(
            "3 \u00b7 mean \u00b7 energy \u00b7 spread \u00b7 pressure \u00b7 pred", color="#e8eef5", fontsize=11
        )
        self.ax_hist.set_xlim(0, min(300, DISPLAY_LEN))
        self.ax_hist.set_ylim(0, 1.05)
        (self.ln_mean,) = self.ax_hist.plot([], [], color="#00d4aa", lw=2.0, label="mean")
        (self.ln_energy,) = self.ax_hist.plot([], [], color="#4cc9f0", lw=1.6, label="energy")
        (self.ln_spread,) = self.ax_hist.plot([], [], color="#f4a261", lw=1.4, label="spread")
        (self.ln_pressure,) = self.ax_hist.plot([], [], color="#c77dff", lw=1.6, label="pressure")
        (self.ln_pred,) = self.ax_hist.plot([], [], color="#ffe066", lw=1.4, alpha=0.9, label="pred")
        (self.ln_resid,) = self.ax_hist.plot([], [], color="#ff4d6d", lw=1.5, label="|resid|")
        self.ax_hist.legend(
            loc="upper left", fontsize=6, framealpha=0.5,
            facecolor="#1a2030", labelcolor="#ccc",
        )

        self.ax_aurora.set_title("4 \u00b7 Aurora + field + host", color="#e8eef5", fontsize=11)
        self.ax_aurora.set_xlim(0, 10)
        self.ax_aurora.set_ylim(0, 6)
        self.ax_aurora.set_xticks([])
        self.ax_aurora.set_yticks([])
        self.aurora_txt = self.ax_aurora.text(
            0.03, 0.97, "", transform=self.ax_aurora.transAxes,
            ha="left", va="top", fontsize=9, family="monospace",
            color="#cfe8ff", linespacing=1.45,
        )
        self._escape_patch = Rectangle(
            (0, 0), 1, 1, transform=self.ax_aurora.transAxes, fill=False, lw=0
        )
        self.ax_aurora.add_patch(self._escape_patch)

        bits = ["csi"]
        if self.head:
            bits.append("torch-head")
        if self._sock is not None:
            bits.append(f"udp:{udp_port}")
        if file:
            bits.append("jsonl")
        self.fig.suptitle(
            f"THRONE ROOM  \u00b7  {' + '.join(bits)}  \u00b7  torch display",
            fontsize=13, color="#f0f4fa", fontweight="bold",
        )
        self.status = self.fig.text(
            0.5, 0.01, "", ha="center", fontsize=8, family="monospace", color="#8899aa"
        )
        self.fig.canvas.mpl_connect("close_event", lambda e: setattr(self, "_running", False))

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
        mean = float(regs.get("csi_mean", regs.get("intensity", 0.0)))
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
            feats = [
                mean, energy, spread, peak, rssi,
                min(1.0, n_bodies / 6.0), mean_conf, min(1.0, self._rate / 20.0),
            ]
            out = self.head.update(feats)
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
                    text = data.decode("utf-8", errors="replace")
                    for line in text.splitlines():
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
            self.action_marks.append({
                "t": time.time(),
                "type": str(act.get("type") or act.get("action") or "?"),
                "priority": float(act.get("priority") or 0),
                "reason": str(act.get("reason") or "")[:48],
            })

    def _body_grid(self) -> np.ndarray:
        grid = np.zeros((self.size, self.size), dtype=np.float32)
        if not self.bodies:
            return grid
        ids = sorted(self.bodies.keys())
        n = len(ids)
        cols = max(1, int(np.ceil(np.sqrt(n))))
        rows = max(1, int(np.ceil(n / cols)))
        cell_h = self.size / rows
        cell_w = self.size / cols
        now = time.time()
        for i, bid in enumerate(ids):
            st = self.bodies[bid]
            age = now - st["last"]
            fade = 1.0 if age < 2 else (0.4 if age < 8 else 0.15)
            regs = st["regions"]
            val = float(regs.get("csi_energy", regs.get("csi_mean", regs.get("intensity", 0.0))))
            r, c = divmod(i, cols)
            r0 = int(r * cell_h)
            r1 = int(min(self.size, (r + 1) * cell_h))
            c0 = int(c * cell_w)
            c1 = int(min(self.size, (c + 1) * cell_w))
            grid[r0:r1, c0:c1] = val * fade
        return grid

    def tick(self) -> None:
        if not self._running:
            return
        self._frame += 1
        self._poll_sources()

        now = time.time()
        if now - self._rate_t >= 1.0:
            self._rate = self._rate_n / (now - self._rate_t)
            self._rate_t = now
            self._rate_n = 0

        csi = self.last_csi[:32]
        if len(csi) < 32:
            csi = list(csi) + [0.0] * (32 - len(csi))
        for rect, h in zip(self.bars, csi):
            rect.set_height(float(np.clip(h, 0, 1)))
            rect.set_color("#ff4d6d" if h > 0.75 else ("#ffe066" if h > 0.45 else "#4cc9f0"))
        surprise = bool(self.head and self.head.ready and self.head.surprise)
        self.csi_txt.set_text(
            f"body {self.last_body}\npkts {self.pkt_count}  {self._rate:.1f} Hz"
            + ("  SURPRISE" if surprise else "")
        )

        grid = self._body_grid()
        self.im_map.set_data(grid)
        self.im_map.set_clim(0.0, max(0.25, float(grid.max()) + 1e-9))
        active = sum(1 for b in self.bodies.values() if now - b["last"] < 5)
        self.map_txt.set_text(f"bodies {len(self.bodies)}  active {active}")

        digest: dict = {}
        if self.digest.exists():
            try:
                digest = json.loads(self.digest.read_text())
            except Exception:
                digest = {}
        pressure = float((digest.get("field") or {}).get("pressure") or 0.0)
        self.hist_pressure.append(pressure)

        def _set(line, hist):
            if hist:
                ys = np.asarray(hist, dtype=float)
                n = min(300, len(ys))
                line.set_data(np.arange(n), ys[-n:])

        _set(self.ln_mean, self.hist_mean)
        _set(self.ln_energy, self.hist_energy)
        _set(self.ln_spread, self.hist_spread)
        _set(self.ln_pressure, self.hist_pressure)
        _set(self.ln_pred, self.hist_pred)
        _set(self.ln_resid, self.hist_resid)
        self.ax_hist.set_xlim(0, max(40, min(300, len(self.hist_mean))))

        health = digest.get("health", "\u2014")
        children = digest.get("children") or {}
        alive = ", ".join(
            f"{k}:{'up' if v.get('alive') else 'down'}" for k, v in list(children.items())[:4]
        )
        host = digest.get("host") or {}
        host_line = (
            f"host cpu={host.get('cpu_pct', '\u2014')}%  mem={host.get('mem_pct', '\u2014')}%  "
            f"{host.get('advice', '\u2014')}"
        )
        head_line = "head: off"
        if self.head:
            if self.head.ready:
                head_line = (
                    f"head pred={self.head.last_pred:.2f}  "
                    f"|r|={self.head.last_abs_residual:.3f}"
                    + ("  SURPRISE" if self.head.surprise else "")
                )
            else:
                head_line = "head: warming"

        acts = list(self.action_marks)[-5:]
        act_lines = "\n".join(
            f"  {a['type']:10s} p={a['priority']:.2f}  {a['reason']}" for a in acts
        ) or "  (no actions yet)"

        self.aurora_txt.set_text(
            f"digest health: {health}\n"
            f"pressure: {pressure:.3f}\n"
            f"children: {alive or '\u2014'}\n"
            f"{host_line}\n"
            f"{head_line}\n"
            f"recent actions:\n{act_lines}"
        )

        self.status.set_text(
            f"frame={self._frame}  bodies={len(self.bodies)}  "
            f"rate={self._rate:.1f}Hz  pkts={self.pkt_count}  "
            f"pressure={pressure:.3f}  last={self.last_body}"
        )

    def run(self) -> None:
        if _BACKEND == "Agg":
            print(
                "[torch-display] no GUI backend (need Tk/Qt).\n"
                "  On headless: SSH with X11 or run on the desktop host.",
                flush=True,
            )
            return
        print(f"[torch-display] backend={_BACKEND}", flush=True)
        print(f"[torch-display] {standard_banner()}", flush=True)
        if self.file:
            print(f"[torch-display] tail {self.file}", flush=True)
        if self._sock:
            print(f"[torch-display] UDP :{self.udp_port}", flush=True)

        plt.show(block=False)
        self.fig.canvas.draw()
        try:
            while self._running and plt.fignum_exists(self.fig.number):
                self.tick()
                self.fig.canvas.draw_idle()
                plt.pause(0.05)
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
    p = argparse.ArgumentParser(description="Throne Room torch display popup")
    p.add_argument("--file", "-f", type=Path, default=None)
    p.add_argument("--udp", type=int, nargs="?", const=4210, default=None)
    p.add_argument("--digest", type=Path, default=DEFAULT_DIGEST)
    p.add_argument("--actions", type=Path, default=DEFAULT_ACTIONS)
    p.add_argument(
        "--field-head", nargs="?", const=str(DEFAULT_HEAD), default=None,
        help="Optional torch checkpoint (load once, numpy forward)",
    )
    p.add_argument("--head-threshold", type=float, default=0.30)
    p.add_argument("--size", type=int, default=16)
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
    ).run()


if __name__ == "__main__":
    main()
