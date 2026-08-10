#!/usr/bin/env python3
"""Throne Room torch display — uses body_field for rich energy map."""
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
from matplotlib.patches import Rectangle

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

def _tail_new_lines(path: Path, offset: int):
    if not path.exists():
        return [], offset
    try:
        with path.open("r", encoding="utf-8") as f:
            f.seek(offset)
            data = f.read()
            return [ln for ln in data.splitlines() if ln.strip().startswith("{")], f.tell()
    except OSError:
        return [], offset

def _parse_packet(data: dict):
    if data.get("type") == "wifi_csi" or ("csi" in data and "node" in data):
        csi = [float(x) for x in (data.get("csi") or [])[:64]]
        mean = float(np.mean(csi)) if csi else 0.0
        peak = float(np.max(csi)) if csi else 0.0
        energy = float(np.sqrt(np.mean(np.square(csi)))) if csi else 0.0
        spread = float(np.std(csi)) if len(csi) > 1 else 0.0
        try:
            rssi_n = max(0.0, min(1.0, (float(data.get("rssi")) + 90.0) / 60.0))
        except (TypeError, ValueError):
            rssi_n = 0.0
        return {"body_id": str(data.get("node") or "csi"), "csi": csi,
                "regions": {"rssi": rssi_n, "csi_mean": mean, "csi_peak": peak,
                            "csi_energy": energy, "csi_spread": min(1.0, spread * 2.0)}, "conf": 0.95}
    if "field_regions" in data and "body_id" in data:
        regions = {}
        for r in data.get("field_regions") or []:
            if isinstance(r, dict):
                try:
                    regions[str(r.get("region") or "")] = float(r.get("observed") or 0.0)
                except (TypeError, ValueError):
                    pass
        csi = []
        mod = data.get("modality") or {}
        if isinstance(mod, dict):
            wc = mod.get("wifi_csi") or {}
            if isinstance(wc, dict):
                csi = [float(x) for x in (wc.get("csi") or [])[:64]]
        return {"body_id": str(data["body_id"]), "csi": csi, "regions": regions, "conf": 1.0}
    return None

class TorchDisplay:
    def __init__(self, *, file, udp_port, digest, actions, field_head, head_threshold, size=48, hz=30.0):
        self.file, self.udp_port, self.digest, self.actions = file, udp_port, digest, actions
        self.size = max(24, size)
        self.tick_dt = 1.0 / max(8.0, min(60.0, hz))
        self._file_off = self._action_off = 0
        self._running = True
        self._frame = 0
        self.bodies = {}
        self._anchors = {}
        self.last_csi = []
        self.last_body = "-"
        self.hist_mean = deque(maxlen=DISPLAY_LEN)
        self.hist_energy = deque(maxlen=DISPLAY_LEN)
        self.hist_spread = deque(maxlen=DISPLAY_LEN)
        self.hist_pred = deque(maxlen=DISPLAY_LEN)
        self.hist_resid = deque(maxlen=DISPLAY_LEN)
        self.hist_pressure = deque(maxlen=DISPLAY_LEN)
        self.action_marks = deque(maxlen=24)
        self.pkt_count = 0
        self._rate = 0.0
        self._rate_t = time.time()
        self._rate_n = 0
        self.head = None
        if field_head and Path(field_head).exists():
            try:
                from visualization.field_head import ThroneFieldHead
                self.head = ThroneFieldHead(field_head, threshold=head_threshold)
            except Exception as e:
                print(f"[torch-display] head: {e}")
        self._sock = None
        if udp_port is not None:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                self._sock.bind(("0.0.0.0", udp_port))
                self._sock.settimeout(0.005)
            except OSError as e:
                print(f"[torch-display] UDP busy ({e}) — use --file", flush=True)
                self._sock.close()
                self._sock = None
        self.fig = plt.figure(figsize=(14, 10), facecolor="#0b0d10")
        try:
            self.fig.canvas.manager.set_window_title("Throne Room · torch display")
        except Exception:
            pass
        gs = self.fig.add_gridspec(2, 2, hspace=0.30, wspace=0.24, left=0.05, right=0.98, top=0.93, bottom=0.05)
        self.ax_csi, self.ax_map = self.fig.add_subplot(gs[0, 0]), self.fig.add_subplot(gs[0, 1])
        self.ax_hist, self.ax_aurora = self.fig.add_subplot(gs[1, 0]), self.fig.add_subplot(gs[1, 1])
        for ax in (self.ax_csi, self.ax_map, self.ax_hist, self.ax_aurora):
            ax.set_facecolor("#0e1116")
            ax.tick_params(colors="#7a8a9a", labelsize=7)
        self.bars = self.ax_csi.bar(np.arange(32), np.zeros(32), color="#4cc9f0", width=0.85)
        self.ax_csi.set_xlim(-0.5, 31.5); self.ax_csi.set_ylim(0, 1.08)
        self.ax_csi.set_title("1 · CSI subcarriers", color="#e8eef5")
        self.csi_txt = self.ax_csi.text(0.02, 0.98, "waiting…", transform=self.ax_csi.transAxes, ha="left", va="top", fontsize=8, family="monospace", color="#cfe8ff")
        z = np.zeros((self.size, self.size), dtype=np.float32)
        self.im_map = self.ax_map.imshow(z, cmap="magma", vmin=0, vmax=1, origin="lower", extent=[0, 1, 0, 1], interpolation="bilinear")
        self.ax_map.set_title("2 · body energy field", color="#e8eef5")
        self.fig.colorbar(self.im_map, ax=self.ax_map, fraction=0.046, pad=0.04)
        self.map_txt = self.ax_map.text(0.02, 0.98, "bodies: 0", transform=self.ax_map.transAxes, ha="left", va="top", fontsize=8, family="monospace", color="#cfe8ff")
        self.ax_hist.set_title("3 · live dynamics", color="#e8eef5")
        self.ax_hist.set_xlim(0, 150); self.ax_hist.set_ylim(0, 1.08)
        self.ax_hist.grid(True, alpha=0.12)
        (self.ln_mean,) = self.ax_hist.plot([], [], color="#00d4aa", lw=2.2, label="mean")
        (self.ln_energy,) = self.ax_hist.plot([], [], color="#4cc9f0", lw=1.8, label="energy")
        (self.ln_spread,) = self.ax_hist.plot([], [], color="#f4a261", lw=1.5, label="spread")
        (self.ln_pressure,) = self.ax_hist.plot([], [], color="#c77dff", lw=2.0, label="pressure")
        (self.ln_pred,) = self.ax_hist.plot([], [], color="#ffe066", lw=1.4, ls="--", label="pred")
        (self.ln_resid,) = self.ax_hist.plot([], [], color="#ff4d6d", lw=1.5, label="|resid|")
        self.ax_hist.legend(loc="upper left", fontsize=6, framealpha=0.5, facecolor="#141a24", labelcolor="#ccc", ncol=3)
        self.ax_aurora.set_title("4 · Aurora · field · host · processes", color="#e8eef5")
        self.ax_aurora.set_xlim(0, 10); self.ax_aurora.set_ylim(0, 8)
        self.ax_aurora.set_xticks([]); self.ax_aurora.set_yticks([])
        self.aurora_txt = self.ax_aurora.text(0.03, 0.97, "", transform=self.ax_aurora.transAxes, ha="left", va="top", fontsize=9, family="monospace", color="#cfe8ff", linespacing=1.5)
        self.fig.suptitle(f"THRONE ROOM  ·  live  ·  {hz:.0f} Hz HUD", fontsize=13, color="#f0f4fa", fontweight="bold")
        self.status = self.fig.text(0.5, 0.008, "", ha="center", fontsize=8, family="monospace", color="#7a8a9a")
        self.fig.canvas.mpl_connect("close_event", lambda e: setattr(self, "_running", False))

    def _ingest(self, pkt):
        body = pkt["body_id"]
        st = self.bodies.setdefault(body, {"regions": {}, "conf": 1.0, "last": time.time(), "n": 0})
        st["regions"].update(pkt["regions"]); st["conf"] = pkt["conf"]; st["last"] = time.time(); st["n"] += 1
        if pkt["csi"]:
            self.last_csi = pkt["csi"]; self.last_body = body
        self.pkt_count += 1; self._rate_n += 1
        regs = st["regions"]
        mean = float(regs.get("csi_mean", 0.0))
        energy = float(regs.get("csi_energy", mean))
        spread = float(regs.get("csi_spread", 0.0))
        self.hist_mean.append(mean); self.hist_energy.append(energy); self.hist_spread.append(spread)
        if self.head is not None:
            out = self.head.update([mean, energy, spread, float(regs.get("csi_peak", mean)), float(regs.get("rssi", 0)), min(1.0, len(self.bodies)/6.0), 1.0, min(1.0, self._rate/20.0)])
            self.hist_pred.append(float(out["pred"])); self.hist_resid.append(float(out["abs_residual"]))
        else:
            self.hist_pred.append(0.0); self.hist_resid.append(0.0)

    def _poll(self):
        if self.file is not None:
            lines, self._file_off = _tail_new_lines(self.file, self._file_off)
            for line in lines:
                try:
                    pkt = _parse_packet(json.loads(line))
                    if pkt: self._ingest(pkt)
                except json.JSONDecodeError:
                    pass
        if self._sock is not None:
            try:
                while True:
                    data, _ = self._sock.recvfrom(65535)
                    for line in data.decode("utf-8", errors="replace").splitlines():
                        if not line.strip(): continue
                        try:
                            pkt = _parse_packet(json.loads(line))
                            if pkt: self._ingest(pkt)
                        except json.JSONDecodeError:
                            pass
            except (socket.timeout, OSError):
                pass
        alines, self._action_off = _tail_new_lines(self.actions, self._action_off)
        for line in alines:
            try:
                act = json.loads(line)
                self.action_marks.append({"type": str(act.get("type") or act.get("action") or "?"), "priority": float(act.get("priority") or 0), "reason": str(act.get("reason") or "")[:40]})
            except json.JSONDecodeError:
                pass

    def _grid(self):
        if body_energy_field is not None:
            return body_energy_field(self.bodies, self._anchors, size=self.size)
        return np.zeros((self.size, self.size), dtype=np.float32)

    def tick(self):
        if not self._running: return
        self._frame += 1
        self._poll()
        now = time.time()
        if now - self._rate_t >= 0.5:
            self._rate = self._rate_n / max(1e-6, now - self._rate_t)
            self._rate_t = now; self._rate_n = 0
        csi = (self.last_csi + [0.0]*32)[:32]
        for rect, h in zip(self.bars, csi):
            rect.set_height(float(np.clip(h, 0, 1)))
            rect.set_color("#ff4d6d" if h > 0.75 else ("#ffe066" if h > 0.45 else "#4cc9f0"))
        self.csi_txt.set_text(f"body {self.last_body}\n{self._rate:.1f} Hz  pkts {self.pkt_count}")
        grid = self._grid()
        self.im_map.set_data(grid)
        self.im_map.set_clim(0.0, max(0.35, float(grid.max()) * 1.05 + 1e-6))
        active = sum(1 for b in self.bodies.values() if now - b["last"] < 5)
        self.map_txt.set_text(f"bodies {len(self.bodies)}  live {active}  peak {float(grid.max()):.2f}")
        digest = {}
        if self.digest.exists():
            try: digest = json.loads(self.digest.read_text())
            except Exception: pass
        pressure = float((digest.get("field") or {}).get("pressure") or 0.0)
        self.hist_pressure.append(pressure)
        def _set(line, hist, w=150):
            if hist:
                ys = np.asarray(hist, dtype=float); n = min(w, len(ys))
                line.set_data(np.arange(n), ys[-n:])
        for ln, h in ((self.ln_mean, self.hist_mean), (self.ln_energy, self.hist_energy), (self.ln_spread, self.hist_spread), (self.ln_pressure, self.hist_pressure), (self.ln_pred, self.hist_pred), (self.ln_resid, self.hist_resid)):
            _set(ln, h)
        self.ax_hist.set_xlim(0, max(40, min(150, len(self.hist_mean))))
        host = digest.get("host") or {}
        children = digest.get("children") or {}
        alive = ", ".join(f"{k}:{'up' if v.get('alive') else 'down'}" for k, v in list(children.items())[:5])
        acts = list(self.action_marks)[-4:]
        act_lines = "\n".join(f"  {a['type']:10s} p={a['priority']:.2f} {a['reason']}" for a in acts) or "  (no actions)"
        self.aurora_txt.set_text(
            f"health {digest.get('health', '-')}   pressure {pressure:.3f}\n"
            f"host cpu={host.get('cpu_pct', '-')}% mem={host.get('mem_pct', '-')}% {host.get('advice', '-')}\n"
            f"children: {alive or '-'}\nactions:\n{act_lines}"
        )
        self.status.set_text(f"frame={self._frame}  ui≈{1.0/self.tick_dt:.0f}Hz  in={self._rate:.1f}pkt/s  pressure={pressure:.3f}  last={self.last_body}")

    def run(self):
        if _BACKEND == "Agg":
            print("[torch-display] need Tk/Qt GUI backend", flush=True); return
        print(f"[torch-display] backend={_BACKEND}  {self.tick_dt*1000:.0f}ms", flush=True)
        print(f"[torch-display] {standard_banner()}", flush=True)
        plt.show(block=False); self.fig.canvas.draw()
        try:
            while self._running and plt.fignum_exists(self.fig.number):
                t0 = time.time(); self.tick(); self.fig.canvas.draw_idle()
                plt.pause(max(0.001, self.tick_dt - (time.time() - t0)))
        except KeyboardInterrupt:
            pass
        finally:
            self._running = False
            if self._sock:
                try: self._sock.close()
                except OSError: pass
            try: plt.close(self.fig)
            except Exception: pass
            print("[torch-display] closed", flush=True)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--file", "-f", type=Path, default=None)
    p.add_argument("--udp", type=int, nargs="?", const=4210, default=None)
    p.add_argument("--digest", type=Path, default=DEFAULT_DIGEST)
    p.add_argument("--actions", type=Path, default=DEFAULT_ACTIONS)
    p.add_argument("--field-head", nargs="?", const=str(DEFAULT_HEAD), default=None)
    p.add_argument("--head-threshold", type=float, default=0.30)
    p.add_argument("--size", type=int, default=48)
    p.add_argument("--hz", type=float, default=30.0)
    a = p.parse_args()
    if a.file is None and a.udp is None:
        a.file = DEFAULT_CSI if DEFAULT_CSI.exists() else None
        if a.file is None: a.udp = 4210
    TorchDisplay(file=a.file, udp_port=a.udp, digest=a.digest, actions=a.actions,
                 field_head=Path(a.field_head) if a.field_head else None,
                 head_threshold=a.head_threshold, size=a.size, hz=a.hz).run()

if __name__ == "__main__":
    main()
