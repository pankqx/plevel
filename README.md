# Plevel

A native Ubuntu desktop app for chatting with your local [Ollama](https://ollama.com) models, built for coding help. Everything runs on your own machine: no cloud, no accounts, works offline.

## Features

- Model dropdown that reads your installed Ollama models, with a Refresh button
- Streaming replies (text appears as it is generated) and a **Stop** button
- Markdown rendering with syntax-highlighted code blocks and a **Copy** button on each one
- Saved chat history (SQLite), search across all chats, rename and delete
- System prompt box with presets (coding assistant, code reviewer, debugger, Git helper, Python tutor)
- Temperature and context-length sliders
- **Attach file**: send source files with your message (up to 200 KB each)
- **Project folder**: point Plevel at a code folder; for each question it picks the most relevant snippets and sends them to the model (see below)
- **Live system monitor**: RAM, CPU, NVIDIA GPU load, VRAM and temperatures, plus whether the loaded model runs on the GPU or CPU
- Regenerate the last answer, export a chat to Markdown, text zoom
- Optional auto-titling of chats with the model (Options menu)

## Install (Ubuntu 22.04 / 24.04)

Ollama must already be installed with at least one model:

```bash
ollama list          # should show your models
```

Then:

```bash
git clone https://github.com/pankqx/plevel.git
cd plevel
sudo apt install -y python3-venv libxcb-cursor0
./install.sh
./run.sh
```

`install.sh` creates a `.venv`, installs the dependencies and adds **Plevel** to your application menu, so afterwards you can just search for it in Activities.

## Using it

| Do this | How |
|---|---|
| New chat | `Ctrl+N` or the **New chat** button |
| Send | `Enter` (`Shift+Enter` for a new line) |
| Stop a reply | Press the red **Stop** button |
| Attach code | **Attach file** or `Ctrl+O`, then send |
| Copy code | Click **Copy** above the code block |
| Export chat | `Ctrl+E` |
| Hide/show settings | `Ctrl+,` |
| Text size | `Ctrl+=` / `Ctrl+-` |

### Project folder context

Click **Project** (top bar) or `Ctrl+Shift+O` and choose a folder. Plevel then:

1. Scans it in the background (uses `git ls-files`, so `.gitignore` is respected; skips `node_modules`, `.venv`, build output, lock files, binaries and files over 300 KB).
2. For every question, scores ~40-line chunks of code by how well they match the words in your question (file names you mention count a lot, e.g. *"what does main_window.py do"*), and picks the best ones that fit.
3. Adds a file list and the snippets to the system prompt, and trims the oldest chat messages if needed so everything fits the context window.

The line above the input box shows what was used for your last question; hover it to see the files.

What to expect:

- **It does not read the whole project.** It sees a few thousand tokens of the most relevant code per question. Mention file or function names for better results.
- **It re-reads your files from disk on every question**, so edits you make are picked up immediately. Nothing is "learned" or remembered between questions beyond the chat history.
- **The context length slider matters.** At 8192 tokens roughly 3,500 tokens (about 12 KB of code) go to project snippets; at 16384 about 8,000. Bigger windows use more VRAM/RAM and make the first reply slower.
- Each chat remembers its project folder, and the last project is reopened at startup.
- Matching is keyword-based, not semantic: if your question shares no words with the code, the right file can be missed. Name the file or function.

### Live system monitor

The bottom bar and the **System (live)** panel show RAM, CPU load and temperature, GPU load and temperature, VRAM, and where Ollama placed the loaded model. If it says *"60% GPU / 40% CPU (slower)"*, the model did not fit in VRAM; use a smaller model or a smaller context length. Temperatures turn amber and then red when they get high. GPU numbers come from `nvidia-smi` (installed with the NVIDIA driver); CPU temperature needs the `coretemp` sensor, which Ubuntu provides on Intel laptops. Turn it off under **Options** if you don't want it (polling `nvidia-smi` can keep a hybrid-graphics GPU awake, which costs a little battery).

### Picking a model and settings

- `qwen2.5-coder:1.5b` is fast and fits a 4 GB GPU entirely. Use it for quick questions and small snippets.
- `qwen2.5-coder:7b` gives noticeably better code but needs more memory; on a 4 GB GPU part of it runs on the CPU, so it is slower.
- **Temperature** 0.2 for code, 0.7 to 0.8 for brainstorming.
- **Context length** is how much of the conversation and attached code the model can see. 8192 is a good default; raise it for big files, but it uses more RAM.
- Put the project context in the system prompt, for example: *"I'm building a Flask app with SQLite; answer with Python 3.12 code."*

## Troubleshooting

- **"Can't reach Ollama"**: run `sudo systemctl start ollama`, then click **Refresh**. If Ollama listens elsewhere, start Plevel with `OLLAMA_HOST=http://host:11434 ./run.sh`.
- **Window does not open, mentions `xcb`**: `sudo apt install libxcb-cursor0`.
- **Slow replies**: check the System panel (or `ollama ps`) to see whether the model runs on GPU or CPU, and try the 1.5b model. Large project context makes the first token slower because the model must read all of it first.
- **Out of memory**: lower the context length or switch to a smaller model.

Chats are stored in `~/.local/share/plevel/chats.db`. Delete that file to wipe all history.

## Development

```bash
.venv/bin/python -m plevel                                          # run
QT_QPA_PLATFORM=offscreen .venv/bin/python tests/test_smoke.py      # headless UI test with a fake Ollama server
.venv/bin/python tests/test_context.py                              # project indexing and retrieval
QT_QPA_PLATFORM=offscreen .venv/bin/python tests/test_monitor.py    # system monitor with a fake nvidia-smi
```

Layout:

```
plevel/
  main_window.py   UI: sidebar, chat view, settings, attachments, project, monitor panel
  context.py       project scan, keyword retrieval, token budgeting
  monitor.py       RAM / CPU / GPU / temperature sampling
  ollama_client.py streaming worker threads
  render.py        markdown + code highlighting -> HTML
  db.py            SQLite chat storage
  theme.py         dark stylesheet
tests/             fake Ollama server, smoke test, context and monitor tests
```
