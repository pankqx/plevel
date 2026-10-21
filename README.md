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

### Picking a model and settings

- `qwen2.5-coder:1.5b` is fast and fits a 4 GB GPU entirely. Use it for quick questions and small snippets.
- `qwen2.5-coder:7b` gives noticeably better code but needs more memory; on a 4 GB GPU part of it runs on the CPU, so it is slower.
- **Temperature** 0.2 for code, 0.7 to 0.8 for brainstorming.
- **Context length** is how much of the conversation and attached code the model can see. 8192 is a good default; raise it for big files, but it uses more RAM.
- Put the project context in the system prompt, for example: *"I'm building a Flask app with SQLite; answer with Python 3.12 code."*

## Troubleshooting

- **"Can't reach Ollama"**: run `sudo systemctl start ollama`, then click **Refresh**. If Ollama listens elsewhere, start Plevel with `OLLAMA_HOST=http://host:11434 ./run.sh`.
- **Window does not open, mentions `xcb`**: `sudo apt install libxcb-cursor0`.
- **Slow replies**: check `ollama ps` to see whether the model runs on GPU or CPU, and try the 1.5b model.
- **Out of memory**: lower the context length or switch to a smaller model.

Chats are stored in `~/.local/share/plevel/chats.db`. Delete that file to wipe all history.

## Development

```bash
.venv/bin/python -m plevel                              # run
QT_QPA_PLATFORM=offscreen .venv/bin/python tests/test_smoke.py   # headless test with a fake Ollama server
```

Layout:

```
plevel/
  main_window.py   UI: sidebar, chat view, settings, attachments
  ollama_client.py streaming worker threads
  render.py        markdown + code highlighting -> HTML
  db.py            SQLite chat storage
  theme.py         dark stylesheet
tests/             fake Ollama server and smoke test
```
