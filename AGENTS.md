# AGENTS.md: guide for AI assistants working on Plevel

Plevel is a native Ubuntu desktop chat app (PySide6, Qt 6) for local Ollama models, built for
coding help on the owner's own projects. Everything runs on the user's machine. Owner: Pank (GitHub `pankqx`).

## Hard rules
- Commit with identity `pankqx <pankqx@gmail.com>` only. No `Co-Authored-By` trailers, no AI names in commits.
- Commit small and often. Push to `origin main` only after the tests pass.
- Keep it offline-first: no telemetry, no cloud calls. The only network target is the local Ollama (`127.0.0.1:11434`).
- Never block the UI thread. Anything slow (Ollama, project scan, nvidia-smi) runs in a `QThread` and reports by signal.
- Target hardware: GTX 1650 (4 GB), 16 GB RAM. Defaults must work with `qwen2.5-coder:1.5b`.

## Run and test
```
python -m venv .venv && .venv/bin/pip install -r requirements.txt
./run.sh                                   # start the app
QT_QPA_PLATFORM=offscreen python tests/test_smoke.py
QT_QPA_PLATFORM=offscreen python tests/test_context.py
QT_QPA_PLATFORM=offscreen python tests/test_monitor.py
QT_QPA_PLATFORM=offscreen python tests/test_testdrive.py
```
All four must print `ALL OK`. Tests use `tests/fake_ollama.py` (a fake server), so no model or GPU is needed.
Tests set `XDG_CONFIG_HOME` to a temp dir so they never touch real settings; keep that line.
For visual changes, render a screenshot with `widget.grab().save(...)` under the offscreen platform and look at it.

## Map of the code (`plevel/`)
| File | Job |
|---|---|
| `__main__.py` | Entry point: loads fonts, applies the stylesheet, opens the window. |
| `main_window.py` | `MainWindow`: sidebar (chat list + live monitor), header, composer, settings drawer, menus, and all app logic (send, regenerate, stop, projects, attachments, export). Workers: `PrepareWorker`, `IndexWorker`. |
| `chat_view.py` | `ChatView`: per-message widgets (user bubble, assistant message, code card, document card, welcome page). Single entry point: `ChatView.sync(messages, streaming, model, error)`. |
| `render.py` | `split_segments` (prose / code / ```markdown doc), `md_to_html`, `normalize_lists`, `highlight_html`, `suggest_filename`. |
| `theme.py` | Design tokens, `load_fonts()`, `stylesheet()`, `document_css()`. Change colours and spacing here, not inline. |
| `context.py` | Project-as-context: `git ls-files` scan, 40-line chunks, keyword scoring, token budget, `build_messages`. |
| `ollama_client.py` | `ModelListWorker`, `ChatWorker` (streaming), `TitleWorker`. |
| `monitor.py` | `SystemMonitor`: RAM, CPU, GPU via `nvidia-smi`, temperatures, Ollama model placement. |
| `db.py` | SQLite chat history (chats, messages; `project` column). |
| `testdrive.py` | Test Drive: 8 graded prompts, auto-graders, Markdown report export. |
| `assets/` | Bundled Inter and JetBrains Mono fonts (SIL OFL), icons. |

## Conventions and gotchas
- UI is native Qt widgets, not a web view (avoids Chromium sandbox issues on Ubuntu 24.04). Do not add QtWebEngine.
- Call `ChatView.sync(...)` to update the conversation; do not poke message widgets directly.
- Streaming re-renders on a 70 ms timer in `MainWindow`; keep per-token work cheap.
- Widgets are transparent by default; only `QMainWindow, QDialog` get the background colour. Give any new panel an `objectName` and style it in `theme.py`.
- Qt rich text supports only a CSS subset. Wrapping code uses `white-space: pre-wrap`; avoid `overflow`, flexbox, etc.
- Context budget: about 3.5 characters per token; answer reserve is `min(1200, num_ctx // 4)`; the project gets at most 55% of the window.
- Inter (variable) exposes only regular and bold in Qt, so do not rely on other weights.
- Keep `README.md` in step with user-visible changes, and add or extend a test for each fix.

## Good first changes
- New system-prompt presets (`SYSTEM_PRESETS` in `main_window.py`).
- New Test Drive cases (add a grader and a `Test(...)` entry in `testdrive.py`, extend `tests/test_testdrive.py`).
- Better context ranking in `context.py` (extend `tests/test_context.py`).
