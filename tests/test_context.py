"""Tests for project indexing and context building.   python tests/test_context.py"""

import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from plevel.context import Project, build_messages, est_tokens, query_terms  # noqa: E402


def write(root: Path, rel: str, text: str):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def make_project() -> Path:
    root = Path(tempfile.mkdtemp()) / "shop"
    write(root, "app/main.py",
          "def handle_login(request):\n    password = request.form['password']\n"
          "    if not validate_password(password):\n        return error('bad password')\n")
    write(root, "app/payments.py",
          "import stripe\n\ndef charge_card(amount, token):\n    return stripe.Charge.create(amount=amount)\n")
    write(root, "README.md", "# Shop\nA small flask shop.\n")
    write(root, "requirements.txt", "flask\nstripe\n")
    write(root, "node_modules/leftpad/index.js", "module.exports = function leftpad() {}\n")
    write(root, "package-lock.json", '{"lock": true}')
    (root / "logo.png").write_bytes(b"\x89PNG\0\0\0binary")
    return root


def test_scan_and_ignore():
    p = Project(make_project())
    p.refresh()
    paths = p.paths()
    assert "app/main.py" in paths and "README.md" in paths
    assert not any("node_modules" in x for x in paths)
    assert "package-lock.json" not in paths and "logo.png" not in paths


def test_git_ignore_respected():
    root = make_project()
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    write(root, ".gitignore", "secret.txt\n")
    write(root, "secret.txt", "api_key = 1234")
    write(root, "app/secret_notes.md", "visible note")
    p = Project(root)
    p.refresh()
    assert "secret.txt" not in p.paths()
    assert "app/secret_notes.md" in p.paths()


def test_retrieval_relevance():
    p = Project(make_project())
    p.refresh()
    msgs, info = build_messages("sys", [("user", "How does the login handler validate the password?")], p, 8192)
    assert "app/main.py" in info["files"] and "app/payments.py" not in info["files"], info
    assert "handle_login" in msgs[0]["content"]

    msgs, info = build_messages("sys", [("user", "what does payments.py do?")], p, 8192)
    assert "app/payments.py" in info["files"], info


def test_refresh_sees_edits():
    root = make_project()
    p = Project(root)
    p.refresh()
    time.sleep(0.02)
    write(root, "app/main.py", "def brand_new_function_xyz():\n    pass\n")
    p.refresh()
    msgs, info = build_messages("sys", [("user", "explain brand_new_function_xyz")], p, 8192)
    assert "brand_new_function_xyz" in msgs[0]["content"]
    (root / "app/payments.py").unlink()
    p.refresh()
    assert "app/payments.py" not in p.paths()


def test_budget_and_history_trimming():
    root = Path(tempfile.mkdtemp()) / "big"
    for i in range(60):
        write(root, f"src/mod{i}.py", "\n".join(f"def helper_{i}_{j}(): return {j}" for j in range(120)))
    p = Project(root)
    p.refresh()
    history = []
    for i in range(30):
        history += [("user", f"question {i} " + "word " * 200), ("assistant", "answer " * 200)]
    history.append(("user", "explain helper_3_5 in mod3.py"))
    for ctx in (2048, 4096, 8192):
        msgs, info = build_messages("You are helpful.", history, p, ctx)
        assert info["total_tokens"] <= ctx - min(1200, ctx // 4), (ctx, info)
        assert msgs[-1]["content"].startswith("explain helper_3_5"), "latest question must be kept"
        assert info["history_dropped"] > 0
        if ctx >= 4096:
            assert "src/mod3.py" in info["files"], (ctx, info)
    print("   budget ok; 8192-ctx project tokens:", info["project_tokens"])


def test_no_project_still_trims():
    history = [("user", "x " * 3000), ("assistant", "y " * 3000), ("user", "short question")]
    msgs, info = build_messages("sys", history, None, 2048)
    assert msgs[-1]["content"] == "short question"
    assert info["history_dropped"] >= 1


def test_query_terms():
    t = query_terms("Why does getUserName fail in user_service.py?")
    assert "getusername" in t and "user" in t and "name" in t and "service" in t


def test_speed_on_large_repo():
    root = Path(tempfile.mkdtemp()) / "huge"
    body = "\n".join(f"    value_{k} = compute(item, {k})  # some typical line of code" for k in range(200))
    for i in range(1500):
        write(root, f"pkg{i % 30}/module_{i}.py", f"def func_{i}(item):\n{body}\n")
    p = Project(root)
    t0 = time.time()
    n = p.refresh()
    t_index = time.time() - t0
    t0 = time.time()
    p.refresh()
    t_again = time.time() - t0
    t0 = time.time()
    build_messages("sys", [("user", "where is func_777 defined and how does it work")], p, 8192)
    t_query = time.time() - t0
    print(f"   {n} files / {p.total_tokens:,} tokens: first scan {t_index:.2f}s, "
          f"re-scan {t_again:.2f}s, one question {t_query:.2f}s")
    assert t_query < 8


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("ALL OK")
