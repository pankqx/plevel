"""QT_QPA_PLATFORM=offscreen python tests/test_testdrive.py"""

import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import fake_ollama  # noqa: E402

server, port = fake_ollama.start(delay=0.002)
os.environ["OLLAMA_HOST"] = f"http://127.0.0.1:{port}"

from PySide6.QtWidgets import QApplication  # noqa: E402

from plevel import theme  # noqa: E402
from plevel import testdrive as td  # noqa: E402
from plevel.db import Database  # noqa: E402
from plevel.main_window import MainWindow  # noqa: E402
from plevel.render import split_segments, normalize_lists, md_to_html  # noqa: E402


def wait(app, cond, timeout=30.0):
    end = time.time() + timeout
    while time.time() < end:
        app.processEvents()
        if cond():
            return True
        time.sleep(0.01)
    return False


def test_graders():
    good = "```python\ndef is_palindrome(s):\n    t=[c.lower() for c in s if c.isalnum()]\n    return t==t[::-1]\n```"
    assert td.grade_palindrome(good)[0]
    assert not td.grade_palindrome("```python\ndef is_palindrome(s):\n    return s==s[::-1]\n```")[0]
    assert td.grade_bugfix("```python\ndef average(n):\n    return sum(n)/len(n) if n else 0\n```")[0]
    assert not td.grade_bugfix("```python\ndef average(n):\n    while True: pass\n```")[0]
    assert td.grade_math("391")[0] and not td.grade_math("381")[0]
    assert td.grade_bullets("- a\n- b\n- c")[0] and not td.grade_bullets("- a\n- b")[0]
    assert td.grade_honesty("That method does not exist in pandas.")[0]
    assert not td.grade_honesty("Just call df.auto_clean_everything() and it works.")[0]
    assert td.grade_document("```markdown\n# T\n## Goals\n- x\n```")[0]
    assert not td.grade_document("# T\n## Goals")[0]


def test_render():
    segs = split_segments("Intro\n\n```markdown\n# Doc\n```python\nx=1\n```\nend\n```\n\nafter")
    assert [s.kind for s in segs] == ["text", "doc", "text"], [s.kind for s in segs]
    assert "x=1" in segs[1].body
    open_seg = split_segments("hi\n```python\nprint(1)")
    assert open_seg[-1].kind == "code" and not open_seg[-1].closed
    assert "    - b" in normalize_lists("- a\n  - b")
    assert "<ul>" in md_to_html("- a\n  - b")


def main():
    test_graders()
    test_render()
    app = QApplication([])
    theme.load_fonts()
    app.setStyleSheet(theme.stylesheet())
    win = MainWindow(Database(Path(tempfile.mkdtemp()) / "t.db"))
    win.qs.clear()
    win.show()
    assert wait(app, lambda: win.model_combo.count() == 2)
    win.open_testdrive()
    dlg = win.testdrive
    dlg.start()
    assert wait(app, lambda: not dlg.running and len(dlg.results) == len(td.TESTS), 60), "run did not finish"
    assert any(r.skipped for r in dlg.results), "project test should be skipped"
    rep = dlg.report()
    assert "Plevel test drive report" in rep and "## Weaknesses" in rep
    assert dlg.export_btn.isEnabled()
    app.processEvents()
    dlg.grab().save(str(Path(tempfile.gettempdir()) / "testdrive.png"))
    dlg.close()
    win.close()
    server.shutdown()
    print("ALL OK")


if __name__ == "__main__":
    main()
