"""Tests for the system monitor, using a fake nvidia-smi.   python tests/test_monitor.py"""

import os
import stat
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import fake_ollama  # noqa: E402

from plevel import monitor  # noqa: E402

SMI_OK = "NVIDIA GeForce GTX 1650, 37, 2048, 4096, 71, 34.50\n"
SMI_NA = "NVIDIA GeForce GTX 1650, [N/A], 2048, 4096, [N/A], [N/A]\n"


def fake_smi(body: str, code: int = 0) -> Path:
    d = Path(tempfile.mkdtemp())
    exe = d / "nvidia-smi"
    exe.write_text(f"#!/bin/sh\ncat <<'EOF'\n{body}EOF\nexit {code}\n")
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    return d


def test_parse():
    g = monitor.parse_nvidia_smi(SMI_OK)[0]
    assert g["name"] == "NVIDIA GeForce GTX 1650" and g["util"] == 37
    assert g["mem_used"] == 2048 and g["mem_total"] == 4096 and g["temp"] == 71 and g["power"] == 34.5
    g = monitor.parse_nvidia_smi(SMI_NA)[0]
    assert g["util"] is None and g["temp"] is None and g["mem_total"] == 4096
    assert monitor.parse_nvidia_smi("garbage") == []


def test_sample_gpu_with_fake_binary():
    old = os.environ["PATH"]
    try:
        os.environ["PATH"] = f"{fake_smi(SMI_OK)}:{old}"
        assert monitor.sample_gpu()["temp"] == 71
        os.environ["PATH"] = f"{fake_smi('error', 9)}:{old}"
        assert monitor.sample_gpu() is None
    finally:
        os.environ["PATH"] = old


def test_no_nvidia_smi_is_fine():
    old = os.environ["PATH"]
    try:
        os.environ["PATH"] = "/nonexistent"
        assert monitor.sample_gpu() is None
    finally:
        os.environ["PATH"] = old


def test_full_sample_and_ollama_ps():
    server, port = fake_ollama.start()
    try:
        s = monitor.sample(f"http://127.0.0.1:{port}", use_gpu=False)
    finally:
        server.shutdown()
    assert 0 < s["ram_pct"] <= 100 and s["ram_total"] > 0 and s["gpu"] is None
    assert s["cpu_temp"] is None or s["cpu_temp"] > 0
    assert s["ollama"] and s["ollama"][0]["name"] == "qwen2.5-coder:7b"
    assert s["ollama"][0]["gpu_pct"] == 60
    print("   sample:", {k: (round(v, 1) if isinstance(v, float) else v) for k, v in s.items() if k != "ollama"})


def test_thread_emits_and_stops():
    from PySide6.QtCore import QCoreApplication
    app = QCoreApplication.instance() or QCoreApplication([])
    got = []
    m = monitor.SystemMonitor("http://127.0.0.1:1", interval=0.2)
    m.stats.connect(got.append)
    m.start()
    import time
    end = time.time() + 5
    while len(got) < 2 and time.time() < end:
        app.processEvents()
        time.sleep(0.05)
    m.stop()
    assert m.wait(3000), "monitor thread did not stop"
    assert len(got) >= 2


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("ALL OK")
