"""Main window: sidebar (history + live monitor), chat column, composer, settings drawer."""

from __future__ import annotations

import time
from datetime import date, datetime, timedelta
from pathlib import Path

from PySide6.QtCore import QSettings, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QFrame, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMainWindow, QMenu, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton,
    QSlider, QVBoxLayout, QWidget,
)

from . import APP_NAME, __version__, theme
from .chat_view import COLUMN_MAX, AvatarLabel, ChatView
from .context import Project, build_messages
from .db import Database
from .monitor import SystemMonitor
from .ollama_client import DEFAULT_HOST, ChatWorker, ModelListWorker, TitleWorker

DEFAULT_SYSTEM_PROMPT = (
    "You are an expert programming assistant helping a developer with their own projects. "
    "Be concise and practical. Give working code in fenced code blocks with the language "
    "named, explain only what is needed, and point out bugs or risks you notice. "
    "If you are not sure something exists (a function, a library, a file), say so instead of guessing."
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
    "Technical writer": (
        "You write clear project documentation (README, design docs, specs). Use headings and "
        "short paragraphs. Ask one or two clarifying questions first if key details are missing."
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

GREEN, AMBER, RED = theme.GREEN, theme.AMBER, theme.DANGER


def level_color(pct: float | None, warn: float = 75, hot: float = 90) -> str:
    if pct is None:
        return GREEN
    return RED if pct >= hot else AMBER if pct >= warn else GREEN


# ------------------------------------------------------------ workers
class PrepareWorker(QThread):
    """Rescans the project and builds the final message list off the UI thread."""

    ready = Signal(list, dict)
    failed = Signal(str)

    def __init__(self, project, system: str, history: list, num_ctx: int):
        super().__init__()
        self.project = project
        self.system = system
        self.history = history
        self.num_ctx = num_ctx

    def run(self):
        try:
            if self.project:
                self.project.refresh()
            msgs, info = build_messages(self.system, self.history, self.project, self.num_ctx)
            self.ready.emit(msgs, info)
        except Exception as exc:
            self.failed.emit(str(exc))


class IndexWorker(QThread):
    done = Signal(int)
    failed = Signal(str)

    def __init__(self, project):
        super().__init__()
        self.project = project

    def run(self):
        try:
            self.done.emit(self.project.refresh())
        except Exception as exc:
            self.failed.emit(str(exc))


# ------------------------------------------------------------- composer
class InputBox(QPlainTextEdit):
    """Grows with its text. Enter sends, Shift+Enter inserts a newline."""

    focus_changed = Signal(bool)

    def __init__(self, on_send):
        super().__init__()
        self.setObjectName("composerEdit")
        self._on_send = on_send
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setPlaceholderText("Ask anything about your code…   (Enter to send, Shift+Enter for a new line)")
        self.document().documentLayout().documentSizeChanged.connect(self._fit)
        self._fit()

    def _fit(self, *_):
        lines = max(1.0, self.document().size().height())
        h = int(lines * self.fontMetrics().lineSpacing() + self.document().documentMargin() * 2 + 6)
        self.setFixedHeight(max(34, min(h, 220)))

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and not (event.modifiers() & Qt.ShiftModifier):
            self._on_send()
            return
        super().keyPressEvent(event)

    def focusInEvent(self, e):
        self.focus_changed.emit(True)
        super().focusInEvent(e)

    def focusOutEvent(self, e):
        self.focus_changed.emit(False)
        super().focusOutEvent(e)


def _centered(widget: QWidget, max_width: int = COLUMN_MAX) -> QWidget:
    """Put a widget in a column that lines up with the chat column."""
    host = QWidget()
    lay = QHBoxLayout(host)
    lay.setContentsMargins(30, 0, 30, 0)
    widget.setMaximumWidth(max_width)
    lay.addStretch(1)
    lay.addWidget(widget, 100)
    lay.addStretch(1)
    return host


class MainWindow(QMainWindow):
    reply_done = Signal(str, float, str)   # answer text, tokens/second, model name

    def __init__(self, db: Database | None = None):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME}")
        self.resize(1360, 860)
        self.setMinimumSize(900, 600)

        self.db = db or Database()
        self.qs = QSettings("plevel", "plevel")
        self.host = DEFAULT_HOST

        self.chat_id: int | None = None
        self.messages: list[tuple[str, str]] = []
        self.attachments: list[Path] = []
        self.worker: ChatWorker | None = None
        self.model_worker: ModelListWorker | None = None
        self.title_worker: TitleWorker | None = None
        self.streaming_text: str | None = None
        self.token_count = 0
        self.t_start = 0.0
        self.ollama_error: str | None = None
        self.installed_models: list[str] = []
        self.project: Project | None = None
        self.index_worker: IndexWorker | None = None
        self.prepare_worker: PrepareWorker | None = None
        self.monitor: SystemMonitor | None = None
        self.testdrive = None
        self.pending_model = ""
        self.last_info: dict | None = None
        self._cancel_prepare = False
        self._bar_colors: dict[str, str] = {}
        self.last_stats: dict | None = None

        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.setInterval(70)
        self._render_timer.timeout.connect(self._render)

        self._build_ui()
        self._build_menu()
        self._restore_settings()
        self.reload_chat_list()
        self.refresh_models()
        last = self.qs.value("last_project", "")
        if last and Path(last).is_dir():
            self.set_project(last, persist=False)
        self._update_title()
        self._render()

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        root = QWidget()
        h = QHBoxLayout(root)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        h.addWidget(self._build_sidebar())
        h.addWidget(self._build_center(), 1)
        h.addWidget(self._build_drawer())
        self.setCentralWidget(root)
        self.statusBar().hide()

    def _build_sidebar(self) -> QWidget:
        side = QFrame()
        side.setObjectName("sidebar")
        side.setFixedWidth(272)
        lay = QVBoxLayout(side)
        lay.setContentsMargins(14, 16, 14, 14)
        lay.setSpacing(10)

        brand = QHBoxLayout()
        brand.setSpacing(10)
        brand.addWidget(AvatarLabel("P", 30))
        name = QLabel(APP_NAME)
        name.setObjectName("title")
        name.setStyleSheet("font-size: 17px;")
        brand.addWidget(name)
        brand.addStretch(1)
        lay.addLayout(brand)
        lay.addSpacing(6)

        new_btn = QPushButton("＋   New chat")
        new_btn.setObjectName("primary")
        new_btn.setCursor(Qt.PointingHandCursor)
        new_btn.clicked.connect(self.new_chat)
        lay.addWidget(new_btn)

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search chats")
        self.search_box.textChanged.connect(self.reload_chat_list)
        lay.addWidget(self.search_box)

        self.chat_list = QListWidget()
        self.chat_list.itemClicked.connect(self._on_chat_clicked)
        self.chat_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.chat_list.setTextElideMode(Qt.ElideRight)
        self.chat_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.chat_list.customContextMenuRequested.connect(self._chat_context_menu)
        lay.addWidget(self.chat_list, 1)

        # ---- live system monitor -------------------------------------
        sec = QLabel("SYSTEM · LIVE")
        sec.setObjectName("section")
        lay.addWidget(sec)
        self.sys_widgets: dict[str, tuple[QLabel, QProgressBar]] = {}
        for key in ("ram", "cpu", "gpu", "vram"):
            lbl = QLabel("…")
            lbl.setObjectName("tiny")
            lbl.setTextFormat(Qt.RichText)
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setTextVisible(False)
            bar.setFixedHeight(4)
            box = QVBoxLayout()
            box.setSpacing(3)
            box.addWidget(lbl)
            box.addWidget(bar)
            lay.addLayout(box)
            self.sys_widgets[key] = (lbl, bar)
        self.sys_model_label = QLabel("")
        self.sys_model_label.setObjectName("tiny")
        self.sys_model_label.setWordWrap(True)
        self.sys_model_label.setTextFormat(Qt.RichText)
        lay.addWidget(self.sys_model_label)
        self.sys_label = QLabel("")   # compact one-liner, kept for tooltips and tests
        self.sys_label.setVisible(False)
        lay.addWidget(self.sys_label)
        return side

    def _build_center(self) -> QWidget:
        center = QWidget()
        center.setObjectName("canvas")
        lay = QVBoxLayout(center)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # ---- header ---------------------------------------------------
        head = QWidget()
        head.setObjectName("header")
        hl = QHBoxLayout(head)
        hl.setContentsMargins(26, 14, 20, 8)
        hl.setSpacing(8)
        self.title_label = QLabel("New chat")
        self.title_label.setObjectName("title")
        hl.addWidget(self.title_label, 1)

        self.model_combo = QComboBox()
        self.model_combo.setMinimumWidth(210)
        self.model_combo.setToolTip("Which local model answers")
        self.model_combo.currentTextChanged.connect(self._on_model_changed)
        hl.addWidget(self.model_combo)
        refresh = QPushButton("⟳")
        refresh.setObjectName("icon")
        refresh.setToolTip("Re-read the installed models from Ollama")
        refresh.setCursor(Qt.PointingHandCursor)
        refresh.clicked.connect(self.refresh_models)
        hl.addWidget(refresh)

        self.project_btn = QPushButton("Project: none")
        self.project_btn.setObjectName("pill")
        self.project_btn.setCursor(Qt.PointingHandCursor)
        self.project_btn.setToolTip("Give the model your code: it reads the folder and picks "
                                    "the files relevant to each question")
        pmenu = QMenu(self)
        pmenu.addAction("Open project folder…", self.open_project_dialog)
        pmenu.addAction("Re-scan project", self.rescan_project)
        pmenu.addAction("Close project", self.close_project)
        self.project_btn.setMenu(pmenu)
        hl.addWidget(self.project_btn)

        self.regen_btn = QPushButton("↻")
        self.regen_btn.setObjectName("icon")
        self.regen_btn.setToolTip("Regenerate the last answer")
        self.regen_btn.setCursor(Qt.PointingHandCursor)
        self.regen_btn.clicked.connect(self.regenerate)
        hl.addWidget(self.regen_btn)
        self.settings_btn = QPushButton("⚙")
        self.settings_btn.setObjectName("icon")
        self.settings_btn.setToolTip("Settings: system prompt, temperature, context length")
        self.settings_btn.setCheckable(True)
        self.settings_btn.setCursor(Qt.PointingHandCursor)
        self.settings_btn.clicked.connect(self._toggle_settings)
        hl.addWidget(self.settings_btn)
        lay.addWidget(head)

        # ---- conversation ---------------------------------------------
        self.chat = ChatView(14)
        self.chat.prompt_chosen.connect(self._use_prompt)
        self.chat.regenerate_requested.connect(self.regenerate)
        self.chat.testdrive_requested.connect(self.open_testdrive)
        lay.addWidget(self.chat, 1)

        # ---- composer -------------------------------------------------
        foot = QWidget()
        fl = QVBoxLayout(foot)
        fl.setContentsMargins(0, 4, 0, 14)
        fl.setSpacing(6)

        self.attach_label = QLabel("")
        self.attach_label.setObjectName("muted")
        self.attach_label.setVisible(False)
        fl.addWidget(_centered(self.attach_label))
        self.context_label = QLabel("")
        self.context_label.setObjectName("muted")
        self.context_label.setWordWrap(True)
        self.context_label.setVisible(False)
        fl.addWidget(_centered(self.context_label))

        self.composer = QFrame()
        self.composer.setObjectName("composer")
        cl = QVBoxLayout(self.composer)
        cl.setContentsMargins(16, 10, 10, 10)
        cl.setSpacing(6)
        self.input = InputBox(self.send_or_stop)
        self.input.focus_changed.connect(self._composer_focus)
        cl.addWidget(self.input)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.attach_btn = QPushButton("＋  Attach file")
        self.attach_btn.setObjectName("attach")
        self.attach_btn.setCursor(Qt.PointingHandCursor)
        self.attach_btn.setToolTip("Add a code file to your next message")
        self.attach_btn.clicked.connect(self.attach_files)
        row.addWidget(self.attach_btn)
        row.addStretch(1)
        self.send_btn = QPushButton("↑")
        self.send_btn.setObjectName("send")
        self.send_btn.setFixedSize(38, 38)
        self.send_btn.setCursor(Qt.PointingHandCursor)
        self.send_btn.setToolTip("Send (Enter)")
        self.send_btn.clicked.connect(self.send_or_stop)
        row.addWidget(self.send_btn)
        cl.addLayout(row)
        fl.addWidget(_centered(self.composer))

        self.status_label = QLabel("")
        self.status_label.setObjectName("tiny")
        self.status_label.setAlignment(Qt.AlignCenter)
        fl.addWidget(self.status_label)
        lay.addWidget(foot)
        return center

    def _build_drawer(self) -> QWidget:
        self.settings_panel = QFrame()
        self.settings_panel.setObjectName("drawer")
        self.settings_panel.setFixedWidth(310)
        self.settings_panel.setVisible(False)
        lay = QVBoxLayout(self.settings_panel)
        lay.setContentsMargins(18, 18, 18, 16)
        lay.setSpacing(8)

        h = QLabel("Settings")
        h.setObjectName("title")
        lay.addWidget(h)
        lay.addSpacing(4)

        sec = QLabel("SYSTEM PROMPT")
        sec.setObjectName("section")
        lay.addWidget(sec)
        self.preset_combo = QComboBox()
        self.preset_combo.addItem("Choose a preset…")
        self.preset_combo.addItems(SYSTEM_PRESETS.keys())
        self.preset_combo.currentIndexChanged.connect(self._on_preset)
        lay.addWidget(self.preset_combo)
        self.system_edit = QPlainTextEdit()
        self.system_edit.setObjectName("sysedit")
        self.system_edit.setPlaceholderText("Instructions the model follows in this chat")
        self.system_edit.setMinimumHeight(150)
        self.system_edit.textChanged.connect(self._on_system_changed)
        lay.addWidget(self.system_edit, 1)

        lay.addSpacing(6)
        self.temp_label = QLabel()
        lay.addWidget(self.temp_label)
        self.temp_slider = QSlider(Qt.Horizontal)
        self.temp_slider.setRange(0, 20)  # 0.0 - 2.0
        self.temp_slider.valueChanged.connect(self._on_temp)
        lay.addWidget(self.temp_slider)
        hint = QLabel("0.2 for code and facts, 0.8 for ideas")
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        lay.addWidget(hint)

        lay.addSpacing(6)
        self.ctx_label = QLabel()
        lay.addWidget(self.ctx_label)
        self.ctx_slider = QSlider(Qt.Horizontal)
        self.ctx_slider.setRange(2, 32)  # x1024
        self.ctx_slider.valueChanged.connect(self._on_ctx)
        lay.addWidget(self.ctx_slider)
        hint2 = QLabel("Bigger = sees more of your code, but uses more memory and starts answering later")
        hint2.setObjectName("muted")
        hint2.setWordWrap(True)
        lay.addWidget(hint2)

        lay.addSpacing(10)
        host = QLabel(f"Ollama at {self.host}")
        host.setObjectName("tiny")
        lay.addWidget(host)
        return self.settings_panel

    def _build_menu(self):
        mb = self.menuBar()
        file_menu = mb.addMenu("&File")
        file_menu.addAction(QAction("New chat", self, shortcut=QKeySequence.New, triggered=self.new_chat))
        file_menu.addAction(QAction("Open project folder…", self, shortcut="Ctrl+Shift+O",
                                    triggered=self.open_project_dialog))
        file_menu.addAction(QAction("Attach file…", self, shortcut="Ctrl+O", triggered=self.attach_files))
        file_menu.addAction(QAction("Export chat as Markdown…", self, shortcut="Ctrl+E",
                                    triggered=self.export_chat))
        file_menu.addSeparator()
        file_menu.addAction(QAction("Quit", self, shortcut=QKeySequence.Quit, triggered=self.close))

        view_menu = mb.addMenu("&View")
        view_menu.addAction(QAction("Focus input", self, shortcut="Ctrl+L", triggered=self.input.setFocus))
        view_menu.addAction(QAction("Stop generating", self, shortcut="Esc", triggered=self._escape))
        view_menu.addAction(QAction("Toggle settings", self, shortcut="Ctrl+,",
                                    triggered=lambda: self._toggle_settings(not self.settings_panel.isVisible())))
        view_menu.addAction(QAction("Bigger text", self, shortcut="Ctrl+=", triggered=lambda: self._zoom(1)))
        view_menu.addAction(QAction("Smaller text", self, shortcut="Ctrl+-", triggered=lambda: self._zoom(-1)))

        self.auto_title_action = QAction("Auto-title chats with the model", self, checkable=True)
        self.auto_title_action.setToolTip("Uses one extra short model call per new chat")
        self.monitor_action = QAction("Live system monitor", self, checkable=True)
        self.monitor_action.setToolTip("RAM, CPU, GPU and temperatures, refreshed every 2 seconds")
        self.monitor_action.toggled.connect(self._set_monitor)
        opts = mb.addMenu("&Options")
        opts.addAction(self.auto_title_action)
        opts.addAction(self.monitor_action)

        help_menu = mb.addMenu("&Help")
        help_menu.addAction(QAction("Model test drive…", self, shortcut="Ctrl+T", triggered=self.open_testdrive))
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
        self.monitor_action.setChecked(self.qs.value("monitor", "true") == "true")
        self.chat.base_px = int(self.qs.value("font_px", 14))

    def closeEvent(self, event):
        self.qs.setValue("geometry", self.saveGeometry())
        self.qs.setValue("temperature", self.temperature())
        self.qs.setValue("num_ctx", self.num_ctx())
        self.qs.setValue("system_prompt", self.system_edit.toPlainText())
        self.qs.setValue("auto_title", "true" if self.auto_title_action.isChecked() else "false")
        self.qs.setValue("font_px", self.chat.base_px)
        self.qs.setValue("last_model", self.model_combo.currentText())
        self.qs.setValue("monitor", "true" if self.monitor_action.isChecked() else "false")
        self.qs.setValue("last_project", str(self.project.root) if self.project else "")
        if self.testdrive:
            self.testdrive.close()
        if self.monitor:
            self.monitor.stop()
            self.monitor.wait(3000)
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(3000)
        for w in (self.prepare_worker, self.index_worker):
            if w and w.isRunning():
                w.wait(3000)
        self.db.close()
        super().closeEvent(event)

    def temperature(self) -> float:
        return self.temp_slider.value() / 10

    def num_ctx(self) -> int:
        return self.ctx_slider.value() * 1024

    def _on_temp(self, v: int):
        self.temp_label.setText(f"Temperature  ·  {v / 10:.1f}")

    def _on_ctx(self, v: int):
        self.ctx_label.setText(f"Context length  ·  {v * 1024:,} tokens")

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

    def _composer_focus(self, focused: bool):
        self.composer.setProperty("focused", focused)
        self.composer.style().unpolish(self.composer)
        self.composer.style().polish(self.composer)

    def _zoom(self, delta: int):
        self.chat.set_base_px(max(11, min(22, self.chat.base_px + delta)))

    def _escape(self):
        if self._busy():
            self.send_or_stop()

    def _use_prompt(self, text: str):
        self.input.setPlainText(text)
        self.input.setFocus()
        cur = self.input.textCursor()
        cur.movePosition(cur.MoveOperation.End)
        self.input.setTextCursor(cur)

    def _about(self):
        QMessageBox.about(
            self, f"About {APP_NAME}",
            f"<b>{APP_NAME} {__version__}</b><br>A private chat app for your local Ollama models, "
            f"built for coding help.<br>Everything stays on this computer.",
        )

    def open_testdrive(self):
        from .testdrive import TestDriveDialog
        if self.testdrive is None:
            self.testdrive = TestDriveDialog(self)
        self.testdrive.show()
        self.testdrive.raise_()
        self.testdrive.activateWindow()

    def run_prompt(self, text: str) -> bool:
        """Start a fresh chat with `text` (used by the test drive). False if busy."""
        if self._busy():
            return False
        self.new_chat()
        self.input.setPlainText(text)
        self.send()
        return True

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
            "Start it with:  sudo systemctl start ollama   (then click ⟳ to refresh)\n\n"
            f"Details: {err}"
        )
        self.status_label.setText("Ollama not reachable")
        self._render()

    def _on_model_changed(self, name: str):
        if self.chat_id is not None and name:
            self.db.update_chat(self.chat_id, model=name)

    # -------------------------------------------------------------- chats
    def chat_rows(self) -> int:
        """Number of real chats in the list (section headers not counted)."""
        return sum(1 for i in range(self.chat_list.count())
                   if self.chat_list.item(i).data(Qt.UserRole) is not None)

    @staticmethod
    def _group_name(ts: float) -> str:
        d = datetime.fromtimestamp(ts).date()
        today = date.today()
        if d >= today:
            return "TODAY"
        if d == today - timedelta(days=1):
            return "YESTERDAY"
        if d > today - timedelta(days=7):
            return "PREVIOUS 7 DAYS"
        return "OLDER"

    def reload_chat_list(self):
        self.chat_list.clear()
        searching = bool(self.search_box.text().strip())
        group = None
        for row in self.db.list_chats(self.search_box.text()):
            if not searching:
                g = self._group_name(row["updated"])
                if g != group:
                    group = g
                    header = QListWidgetItem(g)
                    header.setFlags(Qt.NoItemFlags)
                    self.chat_list.addItem(header)
            item = QListWidgetItem(row["title"])
            item.setData(Qt.UserRole, row["id"])
            item.setToolTip(row["title"])
            self.chat_list.addItem(item)
            if row["id"] == self.chat_id:
                self.chat_list.setCurrentItem(item)

    def _update_title(self):
        title = "New chat"
        if self.chat_id is not None:
            chat = self.db.get_chat(self.chat_id)
            if chat:
                title = chat["title"]
        self.title_label.setText(title)

    def new_chat(self):
        if self._busy():
            return
        self.chat_id = None
        self.messages = []
        self.attachments = []
        self.last_info = None
        self._update_attach_label()
        self._update_context_label()
        self.chat_list.clearSelection()
        self.system_edit.blockSignals(True)
        self.system_edit.setPlainText(self.default_system)
        self.system_edit.blockSignals(False)
        self._update_title()
        self._render()
        self.input.setFocus()

    def _on_chat_clicked(self, item: QListWidgetItem):
        cid = item.data(Qt.UserRole)
        if cid is None or self._busy():
            return
        self.open_chat(cid)

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
        self.last_info = None
        proj = chat["project"]
        if proj and Path(proj).is_dir():
            if not self.project or str(self.project.root) != str(Path(proj).resolve()):
                self.set_project(proj, persist=False)
        elif self.project:
            self._drop_project()
        self._update_context_label()
        self._update_title()
        self._render(scroll_bottom=True)

    def _chat_context_menu(self, pos):
        item = self.chat_list.itemAt(pos)
        if not item or item.data(Qt.UserRole) is None:
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
                self._update_title()
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
        if (self.worker and self.worker.isRunning()) or \
                (self.prepare_worker and self.prepare_worker.isRunning()):
            self.status_label.setText("Wait for the reply to finish, or press Stop (Esc).")
            return True
        return False

    def send_or_stop(self):
        if self.prepare_worker and self.prepare_worker.isRunning():
            self._cancel_prepare = True
            self.send_btn.setEnabled(False)
            self.status_label.setText("Stopping…")
            return
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
                model=model, system_prompt=self.system_edit.toPlainText(), title=title,
                project=str(self.project.root) if self.project else "")
            self.reload_chat_list()
            self._update_title()
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

    def _start_generation(self, model: str):
        self.streaming_text = ""
        self.ollama_error = None
        self.token_count = 0
        self.t_start = time.time()
        self._cancel_prepare = False
        self.pending_model = model
        self._set_generating(True)
        self.status_label.setText("Reading project…" if self.project else "Thinking…")
        self.prepare_worker = PrepareWorker(
            self.project, self.system_edit.toPlainText(), list(self.messages), self.num_ctx())
        self.prepare_worker.ready.connect(self._on_prepared)
        self.prepare_worker.failed.connect(self._on_prepare_failed)
        self.prepare_worker.start()
        self._render(scroll_bottom=True)

    def _on_prepared(self, msgs: list, info: dict):
        if self._cancel_prepare:
            self.streaming_text = None
            self._set_generating(False)
            self.status_label.setText("Stopped")
            self._render()
            return
        self.last_info = info
        self._update_context_label()
        options = {"temperature": self.temperature(), "num_ctx": self.num_ctx()}
        self.worker = ChatWorker(self.pending_model, msgs, options, self.host)
        self.worker.token.connect(self._on_token)
        self.worker.finished_ok.connect(self._on_finished)
        self.worker.failed.connect(self._on_failed)
        self.worker.start()
        self.status_label.setText("Thinking…")

    def _on_prepare_failed(self, err: str):
        self.streaming_text = None
        self._set_generating(False)
        self.ollama_error = f"Could not prepare the request: {err}"
        self.status_label.setText("Error while reading project")
        self._render()

    def _set_generating(self, on: bool):
        self.send_btn.setText("■" if on else "↑")
        self.send_btn.setToolTip("Stop (Esc)" if on else "Send (Enter)")
        self.send_btn.setProperty("busy", on)
        self.send_btn.setEnabled(True)
        self.send_btn.style().unpolish(self.send_btn)
        self.send_btn.style().polish(self.send_btn)
        self.regen_btn.setEnabled(not on)
        self.model_combo.setEnabled(not on)

    def _on_token(self, piece: str):
        self.streaming_text = (self.streaming_text or "") + piece
        self.token_count += 1
        if not self._render_timer.isActive():
            self._render_timer.start()

    def _on_finished(self, full: str):
        elapsed = max(time.time() - self.t_start, 0.001)
        tps = self.token_count / elapsed
        self.streaming_text = None
        if full.strip():
            self.messages.append(("assistant", full))
            if self.chat_id is not None:
                self.db.add_message(self.chat_id, "assistant", full)
        self._set_generating(False)
        self.status_label.setText(
            f"{self.token_count} tokens in {elapsed:.1f}s  ·  {tps:.1f} tokens/second")
        self._render()
        self.reload_chat_list()
        self.reply_done.emit(full, tps, self.pending_model)
        if (self.auto_title_action.isChecked() and len(self.messages) == 2
                and self.chat_id is not None):
            self.title_worker = TitleWorker(self.model_combo.currentText(), self.messages[0][1], self.host)
            cid = self.chat_id
            self.title_worker.title.connect(lambda t, cid=cid: self._set_title(cid, t))
            self.title_worker.start()

    def _set_title(self, chat_id: int, title: str):
        self.db.update_chat(chat_id, title=title)
        self.reload_chat_list()
        if chat_id == self.chat_id:
            self._update_title()

    def _on_failed(self, err: str):
        # If some text arrived, finished_ok follows and finishes the UI reset.
        self.ollama_error = f"Request failed: {err}"
        if not self.streaming_text:
            self.streaming_text = None
            self._set_generating(False)
            self._render()
        self.status_label.setText("Error: " + err.splitlines()[0][:120])

    # ------------------------------------------------------------ project
    def open_project_dialog(self):
        if self._busy():
            return
        start = str(self.project.root.parent) if self.project else str(Path.home())
        path = QFileDialog.getExistingDirectory(self, "Choose project folder", start)
        if path:
            self.set_project(path)

    def set_project(self, path: str, persist: bool = True):
        p = Path(path)
        if not p.is_dir():
            self.status_label.setText(f"Folder not found: {path}")
            return
        self.project = Project(p)
        self.last_info = None
        self.project_btn.setText(f"Project: {self.project.name}")
        self.project_btn.setToolTip(str(self.project.root))
        if persist and self.chat_id is not None:
            self.db.update_chat(self.chat_id, project=str(self.project.root))
        self._start_index()

    def _start_index(self):
        if not self.project:
            return
        proj = self.project
        self.context_label.setText(f"Scanning {proj.name}…")
        self.context_label.setVisible(True)
        self.index_worker = IndexWorker(proj)
        self.index_worker.done.connect(lambda n, proj=proj: self._on_indexed(proj, n))
        self.index_worker.failed.connect(lambda e: self.status_label.setText("Project scan failed: " + e))
        self.index_worker.start()

    def _on_indexed(self, proj: Project, n: int):
        if proj is self.project:
            self._update_context_label()
            self.status_label.setText(f"Project {proj.name}: {n} files indexed")

    def rescan_project(self):
        if self.project and not self._busy():
            self._start_index()

    def close_project(self):
        if self._busy():
            return
        if self.chat_id is not None:
            self.db.update_chat(self.chat_id, project="")
        self._drop_project()

    def _drop_project(self):
        self.project = None
        self.last_info = None
        self.project_btn.setText("Project: none")
        self.project_btn.setToolTip("Give the model your code")
        self._update_context_label()

    def _update_context_label(self):
        proj = self.project
        if not proj:
            self.context_label.setVisible(False)
            return
        if proj.file_count == 0:
            self.context_label.setText(
                f"Project {proj.name}: no readable code files found in this folder.")
            self.context_label.setToolTip("")
            self.context_label.setVisible(True)
            return
        text = f"Project {proj.name}: {proj.file_count} files (~{proj.total_tokens / 1000:.0f}k tokens)"
        notes = []
        if proj.skipped_large:
            notes.append(f"{proj.skipped_large} large files skipped")
        if proj.truncated:
            notes.append("folder too big, only part indexed")
        info = self.last_info
        tip = ""
        if info:
            nf = len(info["files"])
            text += (f"  ·  last question used {info['chunks']} snippet{'s' if info['chunks'] != 1 else ''} "
                     f"from {nf} file{'s' if nf != 1 else ''} "
                     f"(~{info['project_tokens'] / 1000:.1f}k of {info['num_ctx'] // 1024}k tokens)")
            if info["history_dropped"]:
                notes.append(f"{info['history_dropped']} older messages left out to fit")
            tip = "Files used:\n" + "\n".join(info["files"]) if info["files"] else ""
        if notes:
            text += "  ·  " + ", ".join(notes)
        self.context_label.setText(text)
        self.context_label.setToolTip(tip)
        self.context_label.setVisible(True)

    # ------------------------------------------------------------ monitor
    def _set_monitor(self, on: bool):
        if on and not self.monitor:
            self.monitor = SystemMonitor(self.host, 2.0)
            self.monitor.stats.connect(self._on_stats)
            self.monitor.start()
        elif not on and self.monitor:
            self.monitor.stop()
            self.monitor.wait(3000)
            self.monitor = None
            self.sys_label.setText("")
            for lbl, bar in self.sys_widgets.values():
                lbl.setText("monitor off")
                bar.setValue(0)
            self.sys_model_label.setText("")

    def _set_bar(self, key: str, text: str, pct: float, color: str):
        lbl, bar = self.sys_widgets[key]
        lbl.setText(text)
        bar.setValue(int(max(0, min(100, pct))))
        if self._bar_colors.get(key) != color:
            self._bar_colors[key] = color
            bar.setStyleSheet(f"QProgressBar::chunk {{ background-color: {color}; border-radius: 2px; }}")

    @staticmethod
    def _temp_html(t: float | None, warn: float, hot: float) -> str:
        if t is None:
            return f'<span style="color:{theme.SUBTLE};">temp n/a</span>'
        return f'<span style="color:{level_color(t, warn, hot)};">{t:.0f}°C</span>'

    def _on_stats(self, st: dict):
        self.last_stats = st
        self._set_bar("ram", f"RAM  {st['ram_used']:.1f} / {st['ram_total']:.1f} GB  ·  {st['ram_pct']:.0f}%",
                      st["ram_pct"], level_color(st["ram_pct"], 80, 92))
        cpu_t = st["cpu_temp"]
        self._set_bar("cpu", f"CPU  {st['cpu_pct']:.0f}%  ·  {self._temp_html(cpu_t, 85, 95)}",
                      st["cpu_pct"], level_color(st["cpu_pct"], 85, 97))
        g = st["gpu"]
        compact = f"RAM {st['ram_pct']:.0f}%  ·  CPU {st['cpu_pct']:.0f}%"
        if cpu_t is not None:
            compact += f" {cpu_t:.0f}°C"
        if g:
            util = g["util"] or 0
            power = f"  ·  {g['power']:.0f} W" if g.get("power") else ""
            self._set_bar("gpu", f"GPU  {util:.0f}%  ·  {self._temp_html(g['temp'], 78, 87)}{power}",
                          util, level_color(util, 85, 97))
            if g["mem_total"]:
                pct = 100 * (g["mem_used"] or 0) / g["mem_total"]
                self._set_bar("vram", f"VRAM  {(g['mem_used'] or 0) / 1024:.1f} / {g['mem_total'] / 1024:.1f} GB",
                              pct, level_color(pct, 85, 95))
                compact += f"  ·  GPU {util:.0f}%"
                if g["temp"] is not None:
                    compact += f" {g['temp']:.0f}°C"
                compact += f"  ·  VRAM {(g['mem_used'] or 0) / 1024:.1f}/{g['mem_total'] / 1024:.1f} GB"
        else:
            self._set_bar("gpu", "GPU  not detected (nvidia-smi not found)", 0, GREEN)
            self._set_bar("vram", "VRAM  n/a", 0, GREEN)
        self.sys_label.setText(compact)

        models = st.get("ollama") or []
        if models:
            lines = []
            for m in models:
                gpu_pct = m["gpu_pct"]
                where = ("all on GPU" if gpu_pct >= 100 else
                         "all on CPU (slow)" if gpu_pct == 0 else
                         f"{gpu_pct}% GPU / {100 - gpu_pct}% CPU (slower)")
                lines.append(f"Loaded: <b>{m['name']}</b>, {where}")
            self.sys_model_label.setText("<br>".join(lines))
        else:
            self.sys_model_label.setText("No model loaded yet. It loads on your first message.")

    # ----------------------------------------------------------- rendering
    def _render(self, scroll_bottom: bool = False):
        err = self.ollama_error if self.streaming_text is None else None
        self.chat.sync(self.messages, self.streaming_text,
                       self.model_combo.currentText() or "assistant", error=err)
        if scroll_bottom:
            self.chat.scroll_to_bottom()
