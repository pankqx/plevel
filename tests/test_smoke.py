"""Headless smoke test:  QT_QPA_PLATFORM=offscreen python tests/test_smoke.py

Starts a fake Ollama server, drives the real window, and checks the full flow.
"""

import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# keep the test away from the real saved settings (last model, last project, ...)
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import fake_ollama  # noqa: E402

server, port = fake_ollama.start(delay=0.005)
os.environ["OLLAMA_HOST"] = f"http://127.0.0.1:{port}"

from PySide6.QtWidgets import QApplication  # noqa: E402

from plevel.db import Database  # noqa: E402
from plevel.main_window import MainWindow  # noqa: E402
from plevel import theme  # noqa: E402


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
    theme.load_fonts()
    app.setStyleSheet(theme.stylesheet())
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
    assert win.chat.code_blocks() and "return a + b" in win.chat.code_blocks()[0], "code block should be copyable"
    assert win.chat_rows() == 1
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
    assert win.chat_rows() == 1
    win.search_box.setText("zzzz-no-match")
    assert win.chat_list.count() == 0
    win.search_box.setText("")
    win.open_chat(cid)
    assert len(win.messages) >= 4

    # project folder context
    proj = Path(tmp) / "myapp"
    (proj / "app").mkdir(parents=True)
    (proj / "app" / "main.py").write_text("def secret_marker_function(x):\n    return x * 42\n")
    (proj / "app" / "other.py").write_text("def unrelated():\n    return 1\n")
    win.new_chat()
    win.set_project(str(proj))
    assert wait(app, lambda: win.project.file_count == 2), "project not indexed"
    assert win.project_btn.text() == "Project: myapp"
    win.input.setPlainText("what does secret_marker_function do?")
    win.send()
    assert wait(app, lambda: len(win.messages) == 2 and not win.worker.isRunning()
                and not win.prepare_worker.isRunning()), "project reply"
    sent = fake_ollama.Handler.last_chat["messages"]
    assert sent[0]["role"] == "system" and "secret_marker_function" in sent[0]["content"], sent[0]
    assert sent[-1]["content"].startswith("what does secret_marker_function")
    assert "app/main.py" in win.last_info["files"]
    assert "last question used" in win.context_label.text(), win.context_label.text()
    assert win.db.get_chat(win.chat_id)["project"] == str(proj.resolve())
    # reopening a chat without a project drops the project; reopening this one restores it
    pid = win.chat_id
    win.open_chat(cid)
    assert win.project is None and win.project_btn.text() == "Project: none"
    win.open_chat(pid)
    assert win.project is not None and win.project.name == "myapp"
    win.close_project()
    assert win.project is None and win.db.get_chat(pid)["project"] == ""

    # stop while the project is being read
    win.set_project(str(proj))
    assert wait(app, lambda: win.project.file_count == 2)
    win.input.setPlainText("another question")
    win.send()
    win.send_or_stop()          # pressed immediately, before the model starts
    assert wait(app, lambda: not win.prepare_worker.isRunning() and (win.worker is None or not win.worker.isRunning())
                and win.streaming_text is None), "stop during prepare"

    # live system monitor
    assert wait(app, lambda: win.sys_label.text() != "", 6), "monitor produced no stats"
    assert win.sys_widgets["ram"][0].text().startswith("RAM"), win.sys_widgets["ram"][0].text()
    assert "qwen2.5-coder:7b" in win.sys_model_label.text() and "60% GPU" in win.sys_model_label.text()
    print("   status bar:", win.sys_label.text())
    win.monitor_action.setChecked(False)
    assert win.monitor is None and win.sys_label.text() == ""
    win.monitor_action.setChecked(True)
    assert wait(app, lambda: win.sys_label.text() != "", 6)

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
