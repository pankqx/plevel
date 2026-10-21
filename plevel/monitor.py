"""Live system stats: RAM, CPU, NVIDIA GPU (via nvidia-smi), temperatures, and where
Ollama has put the loaded model (GPU vs CPU). Sampled on a background thread.
"""

from __future__ import annotations

import subprocess

import psutil
from PySide6.QtCore import QThread, Signal

from .ollama_client import DEFAULT_HOST, make_client

GPU_QUERY = "name,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw"


def _num(s: str) -> float | None:
    s = s.strip()
    try:
        return float(s)
    except ValueError:
        return None  # "[N/A]", "[Not Supported]", ""


def parse_nvidia_smi(text: str) -> list[dict]:
    """Parse `nvidia-smi --query-gpu=... --format=csv,noheader,nounits` output."""
    gpus = []
    for line in text.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 5:
            continue
        gpus.append({
            "name": parts[0],
            "util": _num(parts[1]),
            "mem_used": _num(parts[2]),    # MiB
            "mem_total": _num(parts[3]),   # MiB
            "temp": _num(parts[4]),        # deg C
            "power": _num(parts[5]) if len(parts) > 5 else None,
        })
    return gpus


def sample_gpu() -> dict | None:
    """First NVIDIA GPU, or None if nvidia-smi is missing or fails."""
    try:
        out = subprocess.run(
            ["nvidia-smi", f"--query-gpu={GPU_QUERY}", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    gpus = parse_nvidia_smi(out.stdout)
    return gpus[0] if gpus else None


def cpu_temperature() -> float | None:
    try:
        temps = psutil.sensors_temperatures()
    except (AttributeError, OSError):
        return None
    if not temps:
        return None
    for key in ("coretemp", "k10temp", "zenpower", "cpu_thermal", "acpitz"):
        entries = temps.get(key)
        if not entries:
            continue
        # prefer the package sensor, else the hottest core
        for e in entries:
            if "package" in (e.label or "").lower():
                return e.current
        return max(e.current for e in entries)
    return None


def sample_ollama(host: str) -> list[dict]:
    """Models currently loaded in Ollama, with how much sits in GPU memory."""
    try:
        resp = make_client(host).ps()
    except Exception:
        return []
    models = resp["models"] if isinstance(resp, dict) else resp.models
    out = []
    for m in models:
        get = (lambda k, d=None: m.get(k, d)) if isinstance(m, dict) else (lambda k, d=None: getattr(m, k, d))
        size = get("size", 0) or 0
        vram = get("size_vram", 0) or 0
        out.append({
            "name": get("model") or get("name") or "?",
            "size": size,
            "size_vram": vram,
            "gpu_pct": round(100 * vram / size) if size else 0,
        })
    return out


def sample(host: str, use_gpu: bool = True) -> dict:
    vm = psutil.virtual_memory()
    return {
        "ram_used": (vm.total - vm.available) / 2**30,   # GiB
        "ram_total": vm.total / 2**30,
        "ram_pct": vm.percent,
        "cpu_pct": psutil.cpu_percent(interval=None),
        "cpu_temp": cpu_temperature(),
        "gpu": sample_gpu() if use_gpu else None,
        "ollama": sample_ollama(host),
    }


class SystemMonitor(QThread):
    stats = Signal(dict)

    def __init__(self, host: str = DEFAULT_HOST, interval: float = 2.0):
        super().__init__()
        self.host = host
        self.interval_ms = int(interval * 1000)
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        psutil.cpu_percent(interval=None)  # prime the counter
        have_gpu = True
        while not self._stop:
            try:
                s = sample(self.host, have_gpu)
                if have_gpu and s["gpu"] is None:
                    have_gpu = False  # no nvidia-smi: stop spawning it every tick
                self.stats.emit(s)
            except Exception:
                pass
            waited = 0
            while waited < self.interval_ms and not self._stop:
                self.msleep(100)
                waited += 100
