"""Main window: history sidebar, chat view, input box, settings panel."""

from __future__ import annotations

import os
import time
from pathlib import Path

from PySide6.QtCore import QSettings, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QFont, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QFrame, QHBoxLayout, QInputDialog,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMenu,
    QMessageBox, QPlainTextEdit, QPushButton, QSlider, QSplitter, QTextBrowser,
    QVBoxLayout, QWidget,
)

from . import APP_NAME, __version__
from .db import Database
from .ollama_client import (
    DEFAULT_HOST, ChatWorker, ModelListWorker, TitleWorker,
)
from .render import render_conversation

DEFAULT_SYSTEM_PROMPT = (
    "You are an expert programming assistant helping a developer with their own projects. "
    "Be concise and practical. Give working code in fenced code blocks with the language "
    "named, explain only what is needed, and point out bugs or risks you notice."
)

SYSTEM_PRESETS = {
    "Coding assistant": DEFAULT_SYSTEM_PROMPT,
    "Code reviewer": (
        "You are a strict but friendly code reviewer. Review the code the user shares for "
        "bugs, security issues, readability and performance. List problems in order of "
        "importance and show a fixed version of the code."
    ),
    "Debugger": (
        "You are a debugging partner. Ask for missing details only if essential. Explain the "
        "most likely root cause of the error first, then give the smallest fix."
    ),
    "Git & GitHub helper": (
        "You are an expert in Git and GitHub. Give exact commands, explain what each does, "
        "and warn before anything that rewrites history or deletes data."
    ),
    "Python tutor": (
        "You are a patient Python tutor. Explain step by step with small examples and "
        "finish with one short exercise."
    ),
}

MAX_ATTACH_BYTES = 200_000
LANG_BY_EXT = {
    ".py": "python", ".js": "javascript", ".ts": "typescript", ".tsx": "tsx", ".jsx": "jsx",
    ".java": "java", ".c": "c", ".h": "c", ".cpp": "cpp", ".cs": "csharp", ".go": "go",
    ".rs": "rust", ".kt": "kotlin", ".html": "html", ".css": "css", ".json": "json",
    ".md": "markdown", ".sh": "bash", ".sql": "sql", ".yml": "yaml", ".yaml": "yaml",
    ".xml": "xml", ".php": "php", ".rb": "ruby", ".swift": "swift", ".toml": "toml",
}


class InputBox(QPlainTextEdit):
    """Enter sends, Shift+Enter inserts a newline."""

    def __init__(self, on_send):
        super().__init__()
        self._on_send = on_send
        self.setPlaceholderText("Ask about your code…  (Enter to send, Shift+Enter for a new line)")
        self.setFixedHeight(84)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and not (event.modifiers() & Qt.ShiftModifier):
            self._on_send()
            return
        super().keyPressEvent(event)


class MainWindow(QMainWindow):
    def __init__(self, db: Database | None = None):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} {__version__}")
        self.resize(1280, 800)

        self.db = db or Database()
        self.qs = QSettings("plevel", "plevel")
        self.host = DEFAULT_HOST

        self.chat_id: int | None = None
        self.messages: list[tuple[str, str]] = []
        self.codes: list[str] = []
        self.attachments: list[Path] = []
        self.worker: ChatWorker | None = None
        self.model_worker: ModelListWorker | None = None
        self.title_worker: TitleWorker | None = None
        self.streaming_text: str | None = None
        self.token_count = 0
        self.t_start = 0.0
        self.ollama_error: str | None = None
        self.installed_models: list[str] = []

        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.setInterval(70)
        self._render_timer.timeout.connect(self._render)

        self._build_ui()
        self._build_menu()
        self._restore_settings()
        self.reload_chat_list()
        self.refresh_models()
        self._render()

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._build_sidebar())
        splitter.addWidget(self._build_center())
        splitter.addWidget(self._build_settings_panel())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([260, 780, 280])
        self.setCentralWidget(splitter)
        self.status_label = QLabel("")
        self.statusBar().addWidget(self.status_label, 1)

    def _build_sidebar(self) -> QWidget:
        side = QFrame()
        side.setObjectName("sidebar")
        side.setMinimumWidth(200)
        side.setMaximumWidth(380)
        lay = QVBoxLayout(side)
        lay.setContentsMargins(10, 10, 10, 10)

        title = QLabel(APP_NAME)
        title.setObjectName("heading")
        f = title.font()
        f.setPointSize(f.pointSize() + 3)
        title.setFont(f)
        lay.addWidget(title)

        new_btn = QPushButton("+  New chat")
        new_btn.setObjectName("primary")
        new_btn.clicked.connect(self.new_chat)
        lay.addWidget(new_btn)

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search chats…")
        self.search_box.textChanged.connect(self.reload_chat_list)
        lay.addWidget(self.search_box)

        self.chat_list = QListWidget()
        self.chat_list.itemClicked.connect(self._on_chat_clicked)
        self.chat_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.chat_list.customContextMenuRequested.connect(self._chat_context_menu)
        lay.addWidget(self.chat_list, 1)
        return side

    def _build_center(self) -> QWidget:
        center = QWidget()
        lay = QVBoxLayout(center)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        top = QWidget()
        top_l = QHBoxLayout(top)
        top_l.setContentsMargins(12, 8, 12, 8)
        top_l.addWidget(QLabel("Model"))
        self.model_combo = QComboBox()
        self.model_combo.setMinimumWidth(220)
        self.model_combo.currentTextChanged.connect(self._on_model_changed)
        top_l.addWidget(self.model_combo)
        refresh = QPushButton("Refresh")
        refresh.setToolTip("Re-read the installed models from Ollama")
        refresh.clicked.connect(self.refresh_models)
        top_l.addWidget(refresh)
        top_l.addStretch(1)
        self.regen_btn = QPushButton("Regenerate")
        self.regen_btn.clicked.connect(self.regenerate)
        top_l.addWidget(self.regen_btn)
        self.settings_btn = QPushButton("Settings")
        self.settings_btn.setCheckable(True)
        self.settings_btn.setChecked(True)
        self.settings_btn.clicked.connect(self._toggle_settings)
        top_l.addWidget(self.settings_btn)
        lay.addWidget(top)

        self.view = QTextBrowser()
        self.view.setObjectName("chat")
        self.view.setOpenLinks(False)
        self.view.setOpenExternalLinks(False)
        self.view.anchorClicked.connect(self._on_anchor)
        lay.addWidget(self.view, 1)

        bottom = QWidget()
        b_l = QVBoxLayout(bottom)
        b_l.setContentsMargins(12, 8, 12, 12)
        self.attach_label = QLabel("")
        self.attach_label.setObjectName("muted")
        self.attach_label.setVisible(False)
        b_l.addWidget(self.attach_label)

        row = QHBoxLayout()
        self.input = InputBox(self.send_or_stop)
        row.addWidget(self.input, 1)
        btns = QVBoxLayout()
        self.attach_btn = QPushButton("Attach file")
        self.attach_btn.setToolTip("Add a code file to your next message")
        self.attach_btn.clicked.connect(self.attach_files)
        btns.addWidget(self.attach_btn)
        self.send_btn = QPushButton("Send")
        self.send_btn.setObjectName("primary")
        self.send_btn.clicked.connect(self.send_or_stop)
        btns.addWidget(self.send_btn)
        row.addLayout(btns)
        b_l.addLayout(row)
        lay.addWidget(bottom)
        return center

    def _build_settings_panel(self) -> QWidget:
        self.settings_panel = QFrame()
        self.settings_panel.setObjectName("settings")
        self.settings_panel.setMinimumWidth(240)
        self.settings_panel.setMaximumWidth(380)
        lay = QVBoxLayout(self.settings_panel)
        lay.setContentsMargins(12, 12, 12, 12)

        h = QLabel("Settings")
        h.setObjectName("heading")
        lay.addWidget(h)

        lay.addWidget(QLabel("System prompt"))
        self.preset_combo = QComboBox()
        self.preset_combo.addItem("Presets…")
        self.preset_combo.addItems(SYSTEM_PRESETS.keys())
        self.preset_combo.currentIndexChanged.connect(self._on_preset)
        lay.addWidget(self.preset_combo)
        self.system_edit = QPlainTextEdit()
        self.system_edit.setPlaceholderText("Instructions the model follows in this chat")
        self.system_edit.setMinimumHeight(140)
        self.system_edit.textChanged.connect(self._on_system_changed)
        lay.addWidget(self.system_edit)

        self.temp_label = QLabel()
        lay.addWidget(self.temp_label)
        self.temp_slider = QSlider(Qt.Horizontal)
        self.temp_slider.setRange(0, 20)  # 0.0 - 2.0
        self.temp_slider.valueChanged.connect(self._on_temp)
        lay.addWidget(self.temp_slider)
        hint = QLabel("0.2 for code and facts, 0.8 for ideas")
        hint.setObjectName("muted")
        lay.addWidget(hint)

        self.ctx_label = QLabel()
        lay.addWidget(self.ctx_label)
        self.ctx_slider = QSlider(Qt.Horizontal)
        self.ctx_slider.setRange(2, 32)  # x1024
        self.ctx_slider.valueChanged.connect(self._on_ctx)
        lay.addWidget(self.ctx_slider)
        hint2 = QLabel("Bigger = remembers more code, uses more RAM")
        hint2.setObjectName("muted")
        hint2.setWordWrap(True)
        lay.addWidget(hint2)

        lay.addStretch(1)
        host = QLabel(f"Ollama: {self.host}")
        host.setObjectName("muted")
        lay.addWidget(host)
        return self.settings_panel

    def _build_menu(self):
        mb = self.menuBar()
        file_menu = mb.addMenu("&File")
        act = QAction("New chat", self, shortcut=QKeySequence.New, triggered=self.new_chat)
        file_menu.addAction(act)
        file_menu.addAction(QAction("Attach file…", self, shortcut="Ctrl+O", triggered=self.attach_files))
        file_menu.addAction(QAction("Export chat as Markdown…", self, shortcut="Ctrl+E",
                                    triggered=self.export_chat))
        file_menu.addSeparator()
        file_menu.addAction(QAction("Quit", self, shortcut=QKeySequence.Quit, triggered=self.close))

        view_menu = mb.addMenu("&View")
        view_menu.addAction(QAction("Focus input", self, shortcut="Ctrl+L", triggered=self.input.setFocus))
        view_menu.addAction(QAction("Toggle settings panel", self, shortcut="Ctrl+,",
                                    triggered=lambda: self._toggle_settings(not self.settings_panel.isVisible())))
        view_menu.addAction(QAction("Bigger text", self, shortcut="Ctrl+=", triggered=lambda: self._zoom(1)))
        view_menu.addAction(QAction("Smaller text", self, shortcut="Ctrl+-", triggered=lambda: self._zoom(-1)))

        self.auto_title_action = QAction("Auto-title chats with the model", self, checkable=True)
        self.auto_title_action.setToolTip("Uses one extra short model call per new chat")
        mb.addMenu("&Options").addAction(self.auto_title_action)

        help_menu = mb.addMenu("&Help")
        help_menu.addAction(QAction("About", self, triggered=self._about))

    # ----------------------------------------------------------- settings
    def _restore_settings(self):
        geo = self.qs.value("geometry")
        if geo:
            self.restoreGeometry(geo)
        self.temp_slider.setValue(int(float(self.qs.value("temperature", 0.2)) * 10))
        self.ctx_slider.setValue(int(int(self.qs.value("num_ctx", 8192)) / 1024))
        self._on_temp(self.temp_slider.value())
        self._on_ctx(self.ctx_slider.value())
        self.default_system = self.qs.value("system_prompt", DEFAULT_SYSTEM_PROMPT)
        self.system_edit.setPlainText(self.default_system)
        self.auto_title_action.setChecked(self.qs.value("auto_title", "false") == "true")
        self.view.setFont(QFont(self.view.font().family(), int(self.qs.value("font_size", 11))))

    def closeEvent(self, event):
        self.qs.setValue("geometry", self.saveGeometry())
        self.qs.setValue("temperature", self.temperature())
        self.qs.setValue("num_ctx", self.num_ctx())
        self.qs.setValue("system_prompt", self.system_edit.toPlainText())
        self.qs.setValue("auto_title", "true" if self.auto_title_action.isChecked() else "false")
        self.qs.setValue("font_size", self.view.font().pointSize())
        self.qs.setValue("last_model", self.model_combo.currentText())
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(3000)
        self.db.close()
        super().closeEvent(event)

    def temperature(self) -> float:
        return self.temp_slider.value() / 10

    def num_ctx(self) -> int:
        return self.ctx_slider.value() * 1024

    def _on_temp(self, v: int):
        self.temp_label.setText(f"Temperature: {v / 10:.1f}")

    def _on_ctx(self, v: int):
        self.ctx_label.setText(f"Context length: {v * 1024:,} tokens")

    def _on_preset(self, idx: int):
        if idx <= 0:
            return
        self.system_edit.setPlainText(SYSTEM_PRESETS[self.preset_combo.currentText()])
        self.preset_combo.setCurrentIndex(0)

    def _on_system_changed(self):
        if self.chat_id is not None:
            self.db.update_chat(self.chat_id, system_prompt=self.system_edit.toPlainText())

    def _toggle_settings(self, show: bool):
        self.settings_panel.setVisible(bool(show))
        self.settings_btn.setChecked(bool(show))

    def _zoom(self, delta: int):
        f = self.view.font()
        f.setPointSize(max(8, min(24, f.pointSize() + delta)))
        self.view.setFont(f)
        self._render()

    def _about(self):
        QMessageBox.about(
            self, f"About {APP_NAME}",
            f"<b>{APP_NAME} {__version__}</b><br>A local chat app for your Ollama models, "
            f"built for coding help.<br>Everything stays on this computer.",
        )

    # ------------------------------------------------------------- models
    def refresh_models(self):
        self.status_label.setText("Connecting to Ollama…")
        self.model_worker = ModelListWorker(self.host)
        self.model_worker.done.connect(self._on_models)
        self.model_worker.failed.connect(self._on_models_failed)
        self.model_worker.start()

    def _on_models(self, names: list[str]):
        self.ollama_error = None
        self.installed_models = names
        current = self.model_combo.currentText() or self.qs.value("last_model", "")
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        self.model_combo.addItems(names)
        if current in names:
            self.model_combo.setCurrentText(current)
        elif names:
            # prefer the small model for quick answers on a 4 GB GPU
            small = [n for n in names if "1.5b" in n or ":1b" in n or ":3b" in n]
            self.model_combo.setCurrentText((small or names)[0])
        self.model_combo.blockSignals(False)
        self.status_label.setText(f"Connected  ·  {len(names)} model(s) installed")
        if not names:
            self.ollama_error = "Ollama is running but has no models. Run:  ollama pull qwen2.5-coder:7b"
        self._render()

    def _on_models_failed(self, err: str):
        self.ollama_error = (
            f"Can't reach Ollama at {self.host}.\n"
            "Start it with:  sudo systemctl start ollama   (then click Refresh)\n\n"
            f"Details: {err}"
        )
        self.status_label.setText("Ollama not reachable")
        self._render()

    def _on_model_changed(self, name: str):
        if self.chat_id is not None and name:
            self.db.update_chat(self.chat_id, model=name)

    # -------------------------------------------------------------- chats
    def reload_chat_list(self):
        self.chat_list.clear()
        for row in self.db.list_chats(self.search_box.text()):
            item = QListWidgetItem(row["title"])
            item.setData(Qt.UserRole, row["id"])
            self.chat_list.addItem(item)
            if row["id"] == self.chat_id:
                self.chat_list.setCurrentItem(item)

    def new_chat(self):
        if self._busy():
            return
        self.chat_id = None
        self.messages = []
        self.attachments = []
        self._update_attach_label()
        self.chat_list.clearSelection()
        self.system_edit.blockSignals(True)
        self.system_edit.setPlainText(self.default_system)
        self.system_edit.blockSignals(False)
        self._render()
        self.input.setFocus()

    def _on_chat_clicked(self, item: QListWidgetItem):
        if self._busy():
            return
        self.open_chat(item.data(Qt.UserRole))

    def open_chat(self, chat_id: int):
        chat = self.db.get_chat(chat_id)
        if not chat:
            return
        self.chat_id = chat_id
        self.messages = [(m["role"], m["content"]) for m in self.db.get_messages(chat_id)]
        self.system_edit.blockSignals(True)
        self.system_edit.setPlainText(chat["system_prompt"])
        self.system_edit.blockSignals(False)
        if chat["model"] in self.installed_models:
            self.model_combo.blockSignals(True)
            self.model_combo.setCurrentText(chat["model"])
            self.model_combo.blockSignals(False)
        self._render(scroll_bottom=True)

    def _chat_context_menu(self, pos):
        item = self.chat_list.itemAt(pos)
        if not item:
            return
        menu = QMenu(self)
        rename = menu.addAction("Rename")
        delete = menu.addAction("Delete")
        chosen = menu.exec(self.chat_list.mapToGlobal(pos))
        cid = item.data(Qt.UserRole)
        if chosen == rename:
            text, ok = QInputDialog.getText(self, "Rename chat", "Title:", text=item.text())
            if ok and text.strip():
                self.db.update_chat(cid, title=text.strip()[:80])
                self.reload_chat_list()
        elif chosen == delete:
            if QMessageBox.question(self, "Delete chat", f"Delete “{item.text()}”?") == QMessageBox.Yes:
                if self._busy() and cid == self.chat_id:
                    return
                self.db.delete_chat(cid)
                if cid == self.chat_id:
                    self.new_chat()
                self.reload_chat_list()

    def export_chat(self):
        if not self.messages:
            QMessageBox.information(self, "Export", "This chat is empty.")
            return
        chat = self.db.get_chat(self.chat_id) if self.chat_id else None
        name = (chat["title"] if chat else "chat").replace("/", "-")
        path, _ = QFileDialog.getSaveFileName(self, "Export chat", f"{name}.md", "Markdown (*.md)")
        if not path:
            return
        lines = [f"# {name}", ""]
        for role, content in self.messages:
            lines += [f"## {'You' if role == 'user' else 'Assistant'}", "", content, ""]
        Path(path).write_text("\n".join(lines), encoding="utf-8")
        self.status_label.setText(f"Exported to {path}")

    # --------------------------------------------------------- attachments
    def attach_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Attach code files")
        for p in paths:
            path = Path(p)
            if path.stat().st_size > MAX_ATTACH_BYTES:
                QMessageBox.warning(self, "File too large",
                                    f"{path.name} is over {MAX_ATTACH_BYTES // 1000} KB. "
                                    "Attach a smaller file or paste the relevant part.")
                continue
            if path not in self.attachments:
                self.attachments.append(path)
        self._update_attach_label()

    def _update_attach_label(self):
        if self.attachments:
            self.attach_label.setText("Attached: " + ", ".join(p.name for p in self.attachments)
                                      + "   (sent with your next message)")
            self.attach_label.setVisible(True)
        else:
            self.attach_label.setVisible(False)

    def _read_attachments(self) -> str:
        blocks = []
        for path in self.attachments:
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                blocks.append(f"(Could not read {path.name}: {exc})")
                continue
            lang = LANG_BY_EXT.get(path.suffix.lower(), "")
            blocks.append(f"File `{path.name}`:\n```{lang}\n{text.rstrip()}\n```")
        return "\n\n".join(blocks)

    # ------------------------------------------------------------ sending
    def _busy(self) -> bool:
        if self.worker and self.worker.isRunning():
            self.status_label.setText("Wait for the reply to finish, or press Stop.")
            return True
        return False

    def send_or_stop(self):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.send_btn.setEnabled(False)
            self.status_label.setText("Stopping…")
            return
        self.send()

    def send(self):
        text = self.input.toPlainText().strip()
        files = self._read_attachments()
        if not text and not files:
            return
        model = self.model_combo.currentText()
        if not model:
            QMessageBox.warning(self, "No model", self.ollama_error or "No model selected yet.")
            return
        content = (text + "\n\n" + files).strip() if files else text

        if self.chat_id is None:
            title = (text or self.attachments[0].name).splitlines()[0][:40]
            self.chat_id = self.db.create_chat(
                model=model, system_prompt=self.system_edit.toPlainText(), title=title)
            self.reload_chat_list()
        self.db.add_message(self.chat_id, "user", content)
        self.messages.append(("user", content))
        self.input.clear()
        self.attachments = []
        self._update_attach_label()
        self._start_generation(model)

    def regenerate(self):
        if self._busy() or not self.messages:
            return
        if self.messages[-1][0] == "assistant":
            self.messages.pop()
            self.db.delete_last_message(self.chat_id)
        if not self.messages or self.messages[-1][0] != "user":
            return
        self._start_generation(self.model_combo.currentText())

    def _api_messages(self) -> list[dict]:
        msgs = []
        system = self.system_edit.toPlainText().strip()
        if system:
            msgs.append({"role": "system", "content": system})
        msgs += [{"role": r, "content": c} for r, c in self.messages]
        return msgs

    def _start_generation(self, model: str):
        self.streaming_text = ""
        self.ollama_error = None
        self.token_count = 0
        self.t_start = time.time()
        self._set_generating(True)
        options = {"temperature": self.temperature(), "num_ctx": self.num_ctx()}
        self.worker = ChatWorker(model, self._api_messages(), options, self.host)
        self.worker.token.connect(self._on_token)
        self.worker.finished_ok.connect(self._on_finished)
        self.worker.failed.connect(self._on_failed)
        self.worker.start()
        self._render(scroll_bottom=True)

    def _set_generating(self, on: bool):
        self.send_btn.setText("Stop" if on else "Send")
        self.send_btn.setObjectName("danger" if on else "primary")
        self.send_btn.setEnabled(True)
        self.send_btn.style().unpolish(self.send_btn)
        self.send_btn.style().polish(self.send_btn)
        self.regen_btn.setEnabled(not on)
        self.model_combo.setEnabled(not on)
        self.status_label.setText("Generating…" if on else self.status_label.text())

    def _on_token(self, piece: str):
        self.streaming_text = (self.streaming_text or "") + piece
        self.token_count += 1
        if not self._render_timer.isActive():
            self._render_timer.start()

    def _on_finished(self, full: str):
        elapsed = max(time.time() - self.t_start, 0.001)
        self.streaming_text = None
        if full.strip():
            self.messages.append(("assistant", full))
            if self.chat_id is not None:
                self.db.add_message(self.chat_id, "assistant", full)
        self._set_generating(False)
        self.status_label.setText(
            f"Done  ·  {self.token_count} tokens in {elapsed:.1f}s  "
            f"({self.token_count / elapsed:.1f} tok/s)")
        self._render()
        self.reload_chat_list()
        if (self.auto_title_action.isChecked() and len(self.messages) == 2
                and self.chat_id is not None):
            self.title_worker = TitleWorker(self.model_combo.currentText(), self.messages[0][1], self.host)
            cid = self.chat_id
            self.title_worker.title.connect(lambda t, cid=cid: self._set_title(cid, t))
            self.title_worker.start()

    def _set_title(self, chat_id: int, title: str):
        self.db.update_chat(chat_id, title=title)
        self.reload_chat_list()

    def _on_failed(self, err: str):
        # If some text arrived, finished_ok follows and finishes the UI reset.
        self.ollama_error = f"Request failed: {err}"
        if not self.streaming_text:
            self.streaming_text = None
            self._set_generating(False)
            self._render()
        self.status_label.setText("Error: " + err.splitlines()[0][:120])

    # ----------------------------------------------------------- rendering
    def _render(self, scroll_bottom: bool = False):
        sb = self.view.verticalScrollBar()
        near_bottom = sb.value() >= sb.maximum() - 40
        prev = sb.value()

        if not self.messages and self.streaming_text is None:
            self.view.setHtml(self._welcome_html())
            self.codes = []
            return
        html_doc, self.codes = render_conversation(
            self.messages, self.streaming_text, self.model_combo.currentText() or "assistant")
        if self.ollama_error and self.streaming_text is None:
            html_doc = html_doc.replace(
                "</body>",
                f'<p style="color:#ef6b6b;white-space:pre-wrap;">{_esc(self.ollama_error)}</p></body>')
        self.view.setHtml(html_doc)
        if scroll_bottom or near_bottom:
            sb.setValue(sb.maximum())
        else:
            sb.setValue(prev)

    def _welcome_html(self) -> str:
        msg = ""
        if self.ollama_error:
            msg = f'<p style="color:#ef6b6b;white-space:pre-wrap;">{_esc(self.ollama_error)}</p>'
        return (
            '<html><body style="color:#8b93a1;">'
            '<h2 style="color:#e6e6e6;">What are you building today?</h2>'
            "<p>Ask a coding question, paste an error, or use <b>Attach file</b> to share a source file.</p>"
            "<ul><li>Pick a model above (1.5b is fast, 7b is smarter)</li>"
            "<li>Use <b>Settings</b> for the system prompt, temperature and context length</li>"
            "<li>Click <b>Copy</b> on any code block to copy it</li></ul>"
            f"{msg}</body></html>"
        )

    def _on_anchor(self, url: QUrl):
        s = url.toString()
        if s.startswith("copy:"):
            try:
                code = self.codes[int(s.split(":", 1)[1])]
            except (ValueError, IndexError):
                return
            QApplication.clipboard().setText(code)
            self.status_label.setText("Code copied to clipboard")
        elif s.startswith(("http://", "https://")):
            from PySide6.QtGui import QDesktopServices
            QDesktopServices.openUrl(url)


def _esc(s: str) -> str:
    import html
    return html.escape(s)
