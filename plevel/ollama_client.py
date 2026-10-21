"""Talks to the local Ollama server. Streaming runs on a background thread."""

from __future__ import annotations

import os

import ollama
from PySide6.QtCore import QObject, QThread, Signal

DEFAULT_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
if not DEFAULT_HOST.startswith("http"):
    DEFAULT_HOST = "http://" + DEFAULT_HOST


def make_client(host: str = DEFAULT_HOST) -> ollama.Client:
    return ollama.Client(host=host)


def list_models(host: str = DEFAULT_HOST) -> list[str]:
    """Return installed model names, or raise on connection failure."""
    resp = make_client(host).list()
    models = resp["models"] if isinstance(resp, dict) else resp.models
    names = []
    for m in models:
        name = m["model"] if isinstance(m, dict) else (getattr(m, "model", None) or m.name)
        names.append(name)
    return sorted(names)


class ModelListWorker(QThread):
    done = Signal(list)
    failed = Signal(str)

    def __init__(self, host: str = DEFAULT_HOST):
        super().__init__()
        self.host = host

    def run(self):
        try:
            self.done.emit(list_models(self.host))
        except Exception as exc:  # connection refused, etc.
            self.failed.emit(str(exc))


class ChatWorker(QThread):
    """Streams one assistant reply. Call stop() to cancel."""

    token = Signal(str)
    finished_ok = Signal(str)
    failed = Signal(str)

    def __init__(self, model: str, messages: list[dict], options: dict,
                 host: str = DEFAULT_HOST):
        super().__init__()
        self.model = model
        self.messages = messages
        self.options = options
        self.host = host
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        parts: list[str] = []
        try:
            stream = make_client(self.host).chat(
                model=self.model,
                messages=self.messages,
                options=self.options,
                stream=True,
            )
            for chunk in stream:
                if self._stop:
                    break
                msg = chunk["message"] if isinstance(chunk, dict) else chunk.message
                piece = msg["content"] if isinstance(msg, dict) else msg.content
                if piece:
                    parts.append(piece)
                    self.token.emit(piece)
        except Exception as exc:
            if parts:
                # keep what we got, but report the interruption
                self.failed.emit(f"{exc}\n\n(Partial reply kept.)")
                self.finished_ok.emit("".join(parts))
            else:
                self.failed.emit(str(exc))
            return
        self.finished_ok.emit("".join(parts))


class TitleWorker(QThread):
    """Asks the model for a short chat title (best effort)."""

    title = Signal(str)

    def __init__(self, model: str, first_user_message: str, host: str = DEFAULT_HOST):
        super().__init__()
        self.model = model
        self.text = first_user_message
        self.host = host

    def run(self):
        try:
            resp = make_client(self.host).chat(
                model=self.model,
                messages=[{
                    "role": "user",
                    "content": "Write a title of at most 5 words for a chat that starts with the "
                               "message below. Reply with only the title, no quotes.\n\n"
                               + self.text[:600],
                }],
                options={"temperature": 0.2, "num_predict": 16},
            )
            msg = resp["message"] if isinstance(resp, dict) else resp.message
            text = msg["content"] if isinstance(msg, dict) else msg.content
            text = text.strip().strip('"\'').splitlines()[0][:60]
            if text:
                self.title.emit(text)
        except Exception:
            pass
