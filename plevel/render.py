"""Turns chat messages into HTML that Qt's QTextBrowser can display.

Code blocks get syntax highlighting (Pygments, inline styles) and a Copy link
of the form  copy:<index>  which the UI intercepts.
"""

from __future__ import annotations

import html
import re

import markdown
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import TextLexer, get_lexer_by_name, guess_lexer
from pygments.util import ClassNotFound

# Colors (kept in sync with theme.py)
USER_BG = "#1f2a44"
ASSISTANT_BG = "#1b1d23"
CODE_BG = "#0f1115"
CODE_HEADER_BG = "#262a33"
TEXT = "#e6e6e6"
MUTED = "#8b93a1"
ACCENT = "#6ea8fe"

_FENCE = re.compile(r"```[ \t]*([\w+#.-]*)[ \t]*\n(.*?)(?:```|\Z)", re.DOTALL)
_FORMATTER = HtmlFormatter(noclasses=True, nowrap=True, style="monokai")
_MD = markdown.Markdown(extensions=["tables", "sane_lists"], output_format="html")


def _lexer(lang: str, code: str):
    if lang:
        try:
            return get_lexer_by_name(lang)
        except ClassNotFound:
            pass
    try:
        return guess_lexer(code) if len(code) > 40 else TextLexer()
    except ClassNotFound:
        return TextLexer()


def _code_block(lang: str, code: str, index: int) -> str:
    code = code.rstrip("\n")
    body = highlight(code, _lexer(lang, code), _FORMATTER)
    label = html.escape(lang or "code")
    return (
        f'<table width="100%" cellspacing="0" cellpadding="6" '
        f'style="margin:8px 0;background-color:{CODE_BG};">'
        f'<tr><td style="background-color:{CODE_HEADER_BG};color:{MUTED};">{label}</td>'
        f'<td align="right" style="background-color:{CODE_HEADER_BG};">'
        f'<a href="copy:{index}" style="color:{ACCENT};text-decoration:none;">Copy</a></td></tr>'
        f'<tr><td colspan="2"><pre style="margin:0;color:{TEXT};'
        f'font-family:\'JetBrains Mono\',\'DejaVu Sans Mono\',monospace;">{body}</pre></td></tr>'
        f"</table>"
    )


def render_markdown(text: str, codes: list[str]) -> str:
    """Render one message body. Fenced code is appended to `codes` (for Copy)."""
    out: list[str] = []
    pos = 0
    for m in _FENCE.finditer(text):
        before = text[pos:m.start()]
        if before.strip():
            _MD.reset()
            out.append(_MD.convert(before))
        codes.append(m.group(2).rstrip("\n"))
        out.append(_code_block(m.group(1), m.group(2), len(codes) - 1))
        pos = m.end()
    rest = text[pos:]
    if rest.strip():
        _MD.reset()
        out.append(_MD.convert(rest))
    return "".join(out)


def _bubble(who: str, bg: str, body_html: str) -> str:
    return (
        f'<table width="100%" cellspacing="0" cellpadding="10" style="margin:6px 0;">'
        f'<tr><td style="background-color:{bg};">'
        f'<div style="color:{MUTED};font-size:11px;">{who}</div>'
        f"{body_html}</td></tr></table>"
    )


def render_conversation(messages: list[tuple[str, str]], streaming: str | None = None,
                        model: str = "assistant") -> tuple[str, list[str]]:
    """messages: list of (role, content). Returns (html, code_blocks)."""
    codes: list[str] = []
    parts: list[str] = []
    for role, content in messages:
        if role == "system":
            continue
        if role == "user":
            # show attachments' text compactly: escape and keep newlines
            parts.append(_bubble("You", USER_BG, render_markdown(content, codes)))
        else:
            parts.append(_bubble(html.escape(model), ASSISTANT_BG, render_markdown(content, codes)))
    if streaming is not None:
        body = render_markdown(streaming, codes) if streaming else f'<i style="color:{MUTED};">thinking…</i>'
        parts.append(_bubble(html.escape(model), ASSISTANT_BG, body))
    doc = (
        f'<html><body style="color:{TEXT};font-size:14px;">'
        + "".join(parts)
        + "</body></html>"
    )
    return doc, codes
