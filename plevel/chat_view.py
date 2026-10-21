"""Chat widgets: auto-height prose, code cards, message bubbles, welcome page.

Every message is made of real widgets (not one big HTML page), so long lines
wrap, code blocks get their own Copy/Save buttons, and a streaming reply only
re-renders the piece that is changing.
"""

from __future__ import annotations

import math
import time
from pathlib import Path

from PySide6.QtCore import QEasingCurve, QPointF, QPropertyAnimation, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QBrush, QColor, QDesktopServices, QFont, QFontMetrics, QLinearGradient, QPainter,
    QPainterPath, QPalette, QPen,
)
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QGraphicsOpacityEffect, QGridLayout, QHBoxLayout,
    QLabel, QPushButton, QScrollArea, QSizePolicy, QStackedLayout, QTextBrowser, QTextEdit,
    QVBoxLayout, QWidget,
)

from . import theme
from .render import (
    DOC_LANGS, highlight_html, md_to_html, split_segments, suggest_filename,
)

CARET = f'<span style="color:{theme.ACCENT2};"> ▍</span>'
COLUMN_MAX = 860


def ghost_button(text: str, tip: str = "") -> QPushButton:
    b = QPushButton(text)
    b.setObjectName("ghost")
    b.setCursor(Qt.PointingHandCursor)
    if tip:
        b.setToolTip(tip)
    return b


def fade_in(widget: QWidget, ms: int = 260) -> None:
    effect = QGraphicsOpacityEffect(widget)
    effect.setOpacity(0.0)
    widget.setGraphicsEffect(effect)
    anim = QPropertyAnimation(effect, b"opacity", widget)
    anim.setDuration(ms)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setEasingCurve(QEasingCurve.OutCubic)
    anim.finished.connect(lambda: widget.setGraphicsEffect(None))
    widget._fade = anim  # keep a reference
    anim.start()


# ------------------------------------------------------------------ text
class AutoBrowser(QTextBrowser):
    """Rich-text view that is exactly as tall as its content and wraps to its width."""

    def __init__(self, max_height: int = 0, css: str | None = None, parent=None):
        super().__init__(parent)
        self.max_height = max_height
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setOpenLinks(False)
        self.setOpenExternalLinks(False)
        self.setLineWrapMode(QTextEdit.WidgetWidth)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.document().setDocumentMargin(0)
        self.viewport().setAutoFillBackground(False)
        pal = self.viewport().palette()
        pal.setColor(QPalette.Base, Qt.transparent)
        pal.setColor(QPalette.Window, Qt.transparent)
        self.viewport().setPalette(pal)
        if css:
            self.document().setDefaultStyleSheet(css)
        self.document().documentLayout().documentSizeChanged.connect(self._fit)
        self.anchorClicked.connect(lambda url: QDesktopServices.openUrl(url))
        self.setFixedHeight(22)

    def _fit(self, *_):
        h = int(math.ceil(self.document().size().height())) + 2
        if self.max_height and h > self.max_height:
            self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            h = self.max_height
        else:
            self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        if h != self.height():
            self.setFixedHeight(h)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._fit()

    def wheelEvent(self, e):
        if self.max_height and self.verticalScrollBar().maximum() > 0:
            super().wheelEvent(e)
        else:
            e.ignore()  # let the chat scroll instead


# ----------------------------------------------------------------- cards
class _CardBase(QFrame):
    copied = Signal()

    def __init__(self, object_name: str, user_text: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName(object_name)
        self.raw = ""
        self.lang = ""
        self.user_text = user_text
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(16, 8, 16, 12)
        self.lay.setSpacing(6)
        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        self.label = QLabel("")
        self.label.setObjectName("section")
        head.addWidget(self.label)
        head.addStretch(1)
        self.save_btn = ghost_button("Save", "Save to a file")
        self.save_btn.clicked.connect(self._save)
        self.copy_btn = ghost_button("Copy")
        self.copy_btn.clicked.connect(self._copy)
        head.addWidget(self.save_btn)
        head.addWidget(self.copy_btn)
        self.lay.addLayout(head)

    def _copy(self):
        QApplication.clipboard().setText(self.raw)
        self.copy_btn.setText("Copied ✓")
        QTimer.singleShot(1400, lambda: self.copy_btn.setText("Copy"))
        self.copied.emit()

    def _save(self):
        name = suggest_filename(self.lang, self.user_text)
        path, _ = QFileDialog.getSaveFileName(self, "Save file", str(Path.home() / name))
        if path:
            Path(path).write_text(self.raw, encoding="utf-8")


class CodeCard(_CardBase):
    def __init__(self, user_text: str = "", max_height: int = 0, parent=None):
        super().__init__("codecard", user_text, parent)
        self.body = AutoBrowser(max_height)
        self.lay.addWidget(self.body)

    def set_code(self, code: str, lang: str):
        if (code, lang) == (self.raw, self.lang):
            return
        self.raw, self.lang = code, lang
        self.label.setText((lang or "code").upper())
        self.body.setHtml(highlight_html(code, lang))


class DocCard(_CardBase):
    """A ```markdown block: shown as a formatted document, Copy gives the raw Markdown."""

    def __init__(self, user_text: str = "", base_px: int = 14, parent=None):
        super().__init__("doccard", user_text, parent)
        self.lang = "md"
        self.body = AutoBrowser(0, theme.document_css(base_px))
        self.lay.addWidget(self.body)
        self.label.setText("MARKDOWN DOCUMENT")

    def set_doc(self, text: str, caret: bool = False):
        if text == self.raw and not caret:
            return
        self.raw = text
        self.body.setHtml(md_to_html(text, CARET if caret else ""))


# ------------------------------------------------------------- segments
class SegmentView(QWidget):
    """Shows one message body as a stack of prose / code / document widgets."""

    def __init__(self, user_text: str = "", code_max_height: int = 0, base_px: int = 14, parent=None):
        super().__init__(parent)
        self.user_text = user_text
        self.code_max_height = code_max_height
        self.base_px = base_px
        self.css = theme.document_css(base_px)
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(0, 0, 0, 0)
        self.lay.setSpacing(10)
        self.widgets: list[QWidget] = []
        self.kinds: list[str] = []
        self.keys: list[tuple | None] = []

    def update_text(self, text: str, caret: bool = False):
        segs = split_segments(text)
        for i, seg in enumerate(segs):
            last = i == len(segs) - 1
            car = caret and last
            key = (seg.kind, seg.body, seg.lang, car)
            if i < len(self.widgets) and self.kinds[i] == seg.kind:
                if self.keys[i] != key:
                    self._apply(self.widgets[i], seg, car)
                    self.keys[i] = key
                continue
            self._truncate(i)
            w = self._make(seg.kind)
            self.lay.addWidget(w)
            self.widgets.append(w)
            self.kinds.append(seg.kind)
            self.keys.append(key)
            self._apply(w, seg, car)
        self._truncate(len(segs))

    def _make(self, kind: str) -> QWidget:
        if kind == "code":
            return CodeCard(self.user_text, self.code_max_height)
        if kind == "doc":
            return DocCard(self.user_text, self.base_px)
        return AutoBrowser(0, self.css)

    @staticmethod
    def _apply(w: QWidget, seg, caret: bool):
        if seg.kind == "code":
            w.set_code(seg.body, seg.lang)
        elif seg.kind == "doc":
            w.set_doc(seg.body, caret)
        else:
            w.setHtml(md_to_html(seg.body, CARET if caret else ""))

    def _truncate(self, n: int):
        while len(self.widgets) > n:
            w = self.widgets.pop()
            self.kinds.pop()
            self.keys.pop()
            self.lay.removeWidget(w)
            w.setParent(None)
            w.deleteLater()

    def code_blocks(self) -> list[str]:
        return [w.raw for w in self.widgets if isinstance(w, (CodeCard, DocCard))]


# -------------------------------------------------------------- visuals
class AvatarLabel(QWidget):
    def __init__(self, letter: str = "P", size: int = 30, parent=None):
        super().__init__(parent)
        self.letter = letter
        self.setFixedSize(size, size)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        g = QLinearGradient(0, 0, self.width(), self.height())
        g.setColorAt(0, QColor(theme.ACCENT))
        g.setColorAt(1, QColor(theme.ACCENT2))
        p.setBrush(QBrush(g))
        p.setPen(Qt.NoPen)
        p.drawEllipse(0, 0, self.width(), self.height())
        f = QFont(self.font())
        f.setBold(True)
        f.setPixelSize(int(self.height() * 0.5))
        p.setFont(f)
        p.setPen(QColor("white"))
        p.drawText(self.rect(), Qt.AlignCenter, self.letter)


class TypingDots(QWidget):
    """Three softly pulsing dots shown while waiting for the first token."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(46, 18)
        self._t = QTimer(self)
        self._t.setInterval(60)
        self._t.timeout.connect(self.update)

    def showEvent(self, e):
        self._t.start()
        super().showEvent(e)

    def hideEvent(self, e):
        self._t.stop()
        super().hideEvent(e)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        now = time.time() * 3.2
        for i in range(3):
            a = 0.25 + 0.75 * (0.5 + 0.5 * math.sin(now - i * 0.9))
            c = QColor(theme.ACCENT2 if i == 1 else theme.ACCENT)
            c.setAlphaF(a)
            p.setBrush(c)
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPointF(8 + i * 15, 9), 4.2, 4.2)


class GradientLabel(QWidget):
    """Big wordmark whose accent gradient slowly drifts."""

    def __init__(self, text: str, px: int = 56, parent=None):
        super().__init__(parent)
        self.text = text
        self.px = px
        self.phase = 0.0
        self._t = QTimer(self)
        self._t.setInterval(40)
        self._t.timeout.connect(self._tick)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.setFixedHeight(int(px * 1.35))

    def _font(self) -> QFont:
        f = QFont("Inter Variable")
        f.setPixelSize(self.px)
        f.setWeight(QFont.Bold)
        return f

    def sizeHint(self):
        return QFontMetrics(self._font()).boundingRect(self.text).size().expandedTo(self.minimumSize())

    def showEvent(self, e):
        self._t.start()
        super().showEvent(e)

    def hideEvent(self, e):
        self._t.stop()
        super().hideEvent(e)

    def _tick(self):
        self.phase = (self.phase + 0.008) % 1.0
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        f = self._font()
        fm = QFontMetrics(f)
        w = fm.horizontalAdvance(self.text)
        x = (self.width() - w) / 2
        path = QPainterPath()
        path.addText(x, fm.ascent() + (self.height() - fm.height()) / 2, f, self.text)
        span = max(w, 1)
        g = QLinearGradient(x + self.phase * span * 2 - span, 0, x + self.phase * span * 2 + span, 0)
        g.setSpread(QLinearGradient.ReflectSpread)
        g.setColorAt(0, QColor(theme.ACCENT))
        g.setColorAt(1, QColor(theme.ACCENT2))
        p.fillPath(path, QBrush(g))


# ------------------------------------------------------------- messages
class UserBubble(QFrame):
    """Gradient-tinted bubble, drawn by hand so one corner can be sharper."""

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        rad, small = 18.0, 6.0
        path = QPainterPath()
        path.moveTo(r.left() + rad, r.top())
        path.lineTo(r.right() - rad, r.top())
        path.arcTo(r.right() - 2 * rad, r.top(), 2 * rad, 2 * rad, 90, -90)
        path.lineTo(r.right(), r.bottom() - small)
        path.arcTo(r.right() - 2 * small, r.bottom() - 2 * small, 2 * small, 2 * small, 0, -90)
        path.lineTo(r.left() + rad, r.bottom())
        path.arcTo(r.left(), r.bottom() - 2 * rad, 2 * rad, 2 * rad, 270, -90)
        path.lineTo(r.left(), r.top() + rad)
        path.arcTo(r.left(), r.top(), 2 * rad, 2 * rad, 180, -90)
        path.closeSubpath()
        g = QLinearGradient(r.topLeft(), r.bottomRight())
        g.setColorAt(0, QColor(124, 108, 255, 88))
        g.setColorAt(1, QColor(34, 211, 238, 46))
        p.fillPath(path, QBrush(g))
        p.setPen(QPen(QColor(124, 108, 255, 110), 1))
        p.drawPath(path)


class UserMessage(QWidget):
    def __init__(self, text: str, base_px: int = 14, parent=None):
        super().__init__(parent)
        self.raw = text
        self.has_code = "```" in text
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.addStretch(1)
        self.bubble = UserBubble()
        self.bubble.setObjectName("userBubble")
        bl = QVBoxLayout(self.bubble)
        bl.setContentsMargins(16, 11, 16, 11)
        self.view = SegmentView(user_text=text, code_max_height=240, base_px=base_px)
        bl.addWidget(self.view)
        row.addWidget(self.bubble)
        self.view.update_text(text)
        self.base_px = base_px

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._fit_width()

    def _fit_width(self):
        max_w = max(int(self.width() * 0.84), 160)
        if self.has_code:
            w = max_w
        else:
            f = QFont("Inter Variable")
            f.setPixelSize(self.base_px)
            fm = QFontMetrics(f)
            longest = max((fm.horizontalAdvance(line) for line in self.raw.split("\n")), default=40)
            w = min(max_w, longest + 32 + 28)
        self.bubble.setFixedWidth(max(w, 90))


class AssistantMessage(QWidget):
    regenerate_requested = Signal()
    copied = Signal()

    def __init__(self, model: str, user_text: str = "", base_px: int = 14, parent=None):
        super().__init__(parent)
        self.raw = ""
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(14)
        av = QVBoxLayout()
        av.setContentsMargins(0, 2, 0, 0)
        av.addWidget(AvatarLabel("P", 30))
        av.addStretch(1)
        row.addLayout(av)

        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(6)
        self.name = QLabel(model)
        self.name.setObjectName("tiny")
        col.addWidget(self.name)
        self.dots = TypingDots()
        col.addWidget(self.dots)
        self.view = SegmentView(user_text=user_text, base_px=base_px)
        col.addWidget(self.view)

        self.actions = QWidget()
        al = QHBoxLayout(self.actions)
        al.setContentsMargins(0, 0, 0, 0)
        al.setSpacing(2)
        self.copy_btn = ghost_button("Copy", "Copy the whole answer")
        self.copy_btn.clicked.connect(self._copy)
        self.regen_btn = ghost_button("↻  Regenerate", "Ask again with the same question")
        self.regen_btn.clicked.connect(self.regenerate_requested)
        al.addWidget(self.copy_btn)
        al.addWidget(self.regen_btn)
        al.addStretch(1)
        col.addWidget(self.actions)
        row.addLayout(col, 1)
        self.actions.setVisible(False)
        self.dots.setVisible(False)

    def _copy(self):
        QApplication.clipboard().setText(self.raw)
        self.copy_btn.setText("Copied ✓")
        QTimer.singleShot(1400, lambda: self.copy_btn.setText("Copy"))
        self.copied.emit()

    def set_text(self, text: str, streaming: bool):
        self.raw = text
        self.view.update_text(text, caret=streaming)
        self.dots.setVisible(streaming and not text.strip())
        self.actions.setVisible(not streaming and bool(text.strip()))

    def set_regen_visible(self, visible: bool):
        self.regen_btn.setVisible(visible)


class ErrorCard(QFrame):
    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self.setObjectName("errorcard")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        self.label = QLabel(text)
        self.label.setWordWrap(True)
        self.label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.label.setStyleSheet(f"color: {theme.DANGER};")
        lay.addWidget(self.label)


# -------------------------------------------------------------- welcome
class SuggestionCard(QFrame):
    clicked = Signal()

    def __init__(self, title: str, subtitle: str, parent=None):
        super().__init__(parent)
        self.setObjectName("suggest")
        self.setCursor(Qt.PointingHandCursor)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(3)
        t = QLabel(title)
        t.setObjectName("title")
        s = QLabel(subtitle)
        s.setObjectName("muted")
        s.setWordWrap(True)
        lay.addWidget(t)
        lay.addWidget(s)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(e)


SUGGESTIONS = [
    ("Explain an error", "Paste a traceback and get the cause and the fix",
     "Explain this error and how to fix it:\n\n"),
    ("Review my code", "Bugs, risks and cleaner alternatives",
     "Review this code for bugs and improvements:\n\n```\n\n```"),
    ("Write a function", "Describe it in a sentence, get working code",
     "Write a Python function that "),
    ("Fix my git mess", "Exact commands, with a warning before anything risky",
     "I made a mistake in git. Give me the exact commands to "),
]


class WelcomePage(QWidget):
    prompt_chosen = Signal(str)
    testdrive_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.addStretch(2)
        self.hero = GradientLabel("Plevel", 58)
        outer.addWidget(self.hero)
        tag = QLabel("Your private coding copilot. Runs on this laptop, works offline.")
        tag.setObjectName("muted")
        tag.setAlignment(Qt.AlignCenter)
        tag.setStyleSheet("font-size: 15px;")
        outer.addWidget(tag)
        outer.addSpacing(26)

        wrap = QHBoxLayout()
        wrap.addStretch(1)
        grid_host = QWidget()
        grid_host.setMaximumWidth(640)
        grid_host.setMinimumWidth(420)
        grid = QGridLayout(grid_host)
        grid.setSpacing(12)
        for i, (title, sub, prompt) in enumerate(SUGGESTIONS):
            c = SuggestionCard(title, sub)
            c.clicked.connect(lambda p=prompt: self.prompt_chosen.emit(p))
            grid.addWidget(c, i // 2, i % 2)
        wrap.addWidget(grid_host, 100)
        wrap.addStretch(1)
        outer.addLayout(wrap)

        outer.addSpacing(14)
        row = QHBoxLayout()
        row.addStretch(1)
        td = ghost_button("Not sure what it can do?  Take the test drive  →")
        td.clicked.connect(self.testdrive_requested)
        row.addWidget(td)
        row.addStretch(1)
        outer.addLayout(row)

        self.note = QLabel("")
        self.note.setWordWrap(True)
        self.note.setAlignment(Qt.AlignCenter)
        self.note.setStyleSheet(f"color: {theme.DANGER}; font-size: 13px;")
        outer.addWidget(self.note)
        outer.addStretch(3)

    def set_error(self, text: str):
        self.note.setText(text or "")


# ------------------------------------------------------------- chat view
class ChatView(QWidget):
    prompt_chosen = Signal(str)
    regenerate_requested = Signal()
    testdrive_requested = Signal()

    def __init__(self, base_px: int = 14, parent=None):
        super().__init__(parent)
        self.base_px = base_px
        self.items: list[tuple[str, str, QWidget]] = []
        self.stream: AssistantMessage | None = None
        self.error_card: ErrorCard | None = None
        self._stick = True
        self._last: tuple = ([], None, "")

        self.stack = QStackedLayout(self)
        self.welcome = WelcomePage()
        self.welcome.prompt_chosen.connect(self.prompt_chosen)
        self.welcome.testdrive_requested.connect(self.testdrive_requested)
        self.stack.addWidget(self.welcome)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        host = QWidget()
        host.setObjectName("canvas")
        hl = QHBoxLayout(host)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.addStretch(1)
        self.column = QWidget()
        self.column.setMaximumWidth(COLUMN_MAX)
        self.col_lay = QVBoxLayout(self.column)
        self.col_lay.setContentsMargins(30, 18, 30, 24)
        self.col_lay.setSpacing(24)
        self.col_lay.addStretch(1)
        hl.addWidget(self.column, 100)
        hl.addStretch(1)
        self.scroll.setWidget(host)
        self.stack.addWidget(self.scroll)

        bar = self.scroll.verticalScrollBar()
        bar.rangeChanged.connect(self._on_range)
        bar.valueChanged.connect(self._on_value)

    # ---- scrolling ----------------------------------------------------
    def _on_range(self, _lo, hi):
        if self._stick:
            self.scroll.verticalScrollBar().setValue(hi)

    def _on_value(self, v):
        bar = self.scroll.verticalScrollBar()
        self._stick = v >= bar.maximum() - 48

    def scroll_to_bottom(self):
        self._stick = True
        bar = self.scroll.verticalScrollBar()
        bar.setValue(bar.maximum())
        QTimer.singleShot(0, lambda: bar.setValue(bar.maximum()))

    # ---- content ------------------------------------------------------
    def set_base_px(self, px: int):
        self.base_px = px
        for _, _, w in self.items:
            self._remove(w)
        self.items.clear()
        if self.stream:
            self._remove(self.stream)
            self.stream = None
        msgs, streaming, model = self._last
        self.sync(msgs, streaming, model)

    def _remove(self, w: QWidget):
        self.col_lay.removeWidget(w)
        w.setParent(None)
        w.deleteLater()

    def _last_user_text(self, messages, upto: int) -> str:
        for role, content in reversed(messages[:upto]):
            if role == "user":
                return content
        return ""

    def _make_message(self, role: str, content: str, model: str, messages, idx: int) -> QWidget:
        if role == "user":
            return UserMessage(content, self.base_px)
        w = AssistantMessage(model, self._last_user_text(messages, idx), self.base_px)
        w.regenerate_requested.connect(self.regenerate_requested)
        w.set_text(content, False)
        return w

    def sync(self, messages: list[tuple[str, str]], streaming: str | None, model: str,
             error: str | None = None, animate: bool = True):
        self._last = (list(messages), streaming, model)
        # how much of what is on screen still matches
        n_ok = 0
        while n_ok < len(self.items) and n_ok < len(messages) and self.items[n_ok][:2] == tuple(messages[n_ok]):
            n_ok += 1

        promote = (self.stream is not None and streaming is None and n_ok == len(self.items)
                   and len(messages) == n_ok + 1 and messages[-1][0] == "assistant")
        changed = n_ok < len(self.items) or len(messages) > n_ok

        if self.stream is not None and not promote and (streaming is None or changed):
            self._remove(self.stream)
            self.stream = None
        if self.stream is not None:
            self.col_lay.removeWidget(self.stream)
        if self.error_card is not None:
            self.col_lay.removeWidget(self.error_card)

        if promote:
            w = self.stream
            self.stream = None
            w.set_text(messages[-1][1], False)
            self.items.append(("assistant", messages[-1][1], w))
            self.col_lay.insertWidget(len(self.items) - 1, w)
        else:
            while len(self.items) > n_ok:
                _, _, w = self.items.pop()
                self._remove(w)
            for idx in range(n_ok, len(messages)):
                role, content = messages[idx]
                w = self._make_message(role, content, model, messages, idx)
                self.items.append((role, content, w))
                self.col_lay.insertWidget(len(self.items) - 1, w)
                if animate and idx == len(messages) - 1 and len(messages) - n_ok <= 2:
                    fade_in(w)

        if streaming is not None:
            if self.stream is None:
                self.stream = AssistantMessage(model, self._last_user_text(messages, len(messages)), self.base_px)
                self.stream.regenerate_requested.connect(self.regenerate_requested)
                if animate:
                    fade_in(self.stream)
            self.col_lay.insertWidget(len(self.items), self.stream)
            self.stream.set_text(streaming, True)

        if self.error_card is not None and not error:
            self._remove(self.error_card)
            self.error_card = None
        if error:
            if self.error_card is None:
                self.error_card = ErrorCard(error)
            else:
                self.error_card.label.setText(error)
            pos = len(self.items) + (1 if self.stream else 0)
            self.col_lay.insertWidget(pos, self.error_card)

        # only the newest finished answer offers Regenerate
        last_assistant = None
        for idx, (role, _, w) in enumerate(self.items):
            if role == "assistant":
                last_assistant = idx
        for idx, (role, _, w) in enumerate(self.items):
            if role == "assistant":
                w.set_regen_visible(idx == last_assistant and idx == len(self.items) - 1)

        self.welcome.set_error(error or "")
        empty = not self.items and self.stream is None
        self.stack.setCurrentWidget(self.welcome if empty else self.scroll)

    def code_blocks(self) -> list[str]:
        out: list[str] = []
        for _, _, w in self.items:
            view = getattr(w, "view", None)
            if view:
                out += view.code_blocks()
        if self.stream:
            out += self.stream.view.code_blocks()
        return out
