"""Headless smoke test:  QT_QPA_PLATFORM=offscreen python tests/test_smoke.py

Starts a fake Ollama server, drives the real window, and checks the full flow.
"""

import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import fake_ollama  # noqa: E402

server, port = fake_ollama.start(delay=0.005)
os.environ["OLLAMA_HOST"] = f"http://127.0.0.1:{port}"

from PySide6.QtWidgets import QApplication  # noqa: E402

from plevel.db import Database  # noqa: E402
from plevel.main_window import MainWindow  # noqa: E402
from plevel.theme import STYLESHEET  # noqa: E402


def wait(app, cond, timeout=10.0):
    end = time.time() + timeout
    while time.time() < end:
        app.processEvents()
        if cond():
            return True
        time.sleep(0.01)
    return False


def main():
    app = QApplication([])
    app.setStyleSheet(STYLESHEET)
    tmp = tempfile.mkdtemp()
    win = MainWindow(Database(Path(tmp) / "t.db"))
    win.qs.clear()
    win.show()

    assert wait(app, lambda: win.model_combo.count() == 2), "models did not load"
    assert win.model_combo.currentText() == "qwen2.5-coder:1.5b", "small model should be default"

    # send a message
    win.input.setPlainText("write add()")
    win.send()
    assert wait(app, lambda: len(win.messages) == 2 and win.worker and not win.worker.isRunning()), "reply"
    assert win.messages[1][0] == "assistant" and "def add" in win.messages[1][1]
    assert win.codes and "return a + b" in win.codes[0], "code block should be copyable"
    assert win.chat_list.count() == 1
    assert len(win.db.get_messages(win.chat_id)) == 2

    # attachments
    f = Path(tmp) / "x.py"
    f.write_text("print('hi')\n")
    win.attachments = [f]
    win.input.setPlainText("explain this")
    win.send()
    assert "File `x.py`" in win.messages[2][1] and "```python" in win.messages[2][1]
    assert wait(app, lambda: len(win.messages) == 4 and not win.worker.isRunning()), "second reply"

    # regenerate keeps count the same
    win.regenerate()
    assert wait(app, lambda: len(win.messages) == 4 and not win.worker.isRunning()
                and win.streaming_text is None), "regenerate"
    assert len(win.db.get_messages(win.chat_id)) == 4

    # stop mid-stream
    fake_ollama.Handler.delay = 0.05
    win.input.setPlainText("long answer")
    win.send()
    wait(app, lambda: (win.streaming_text or "") != "", 5)
    win.send_or_stop()
    assert wait(app, lambda: win.streaming_text is None and not win.worker.isRunning()), "stop"
    fake_ollama.Handler.delay = 0.005

    # new chat + search + reopen
    cid = win.chat_id
    win.new_chat()
    assert win.messages == [] and win.chat_id is None
    win.search_box.setText("add")
    assert win.chat_list.count() == 1
    win.search_box.setText("zzzz-no-match")
    assert win.chat_list.count() == 0
    win.search_box.setText("")
    win.open_chat(cid)
    assert len(win.messages) >= 4

    # screenshot for eyeballing
    app.processEvents()
    out = Path(tmp) / "shot.png"
    win.grab().save(str(out))
    print("screenshot:", out)

    win.close()
    server.shutdown()
    print("ALL OK")


if __name__ == "__main__":
    main()
