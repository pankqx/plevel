"""Turns model replies into pieces the UI can display well.

* split_segments(): reply text -> prose / code / document segments. Written to cope
  with half-finished replies while they stream (an unclosed ``` fence is fine).
* md_to_html(): Markdown -> HTML that Qt's rich text widget renders nicely.
* highlight_html(): syntax-highlighted code that wraps instead of scrolling sideways.
* suggest_filename(): a sensible default name for the Save button.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass

import markdown
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import TextLexer, get_lexer_by_name, guess_lexer
from pygments.styles import get_style_by_name
from pygments.util import ClassNotFound

from .theme import MONO_CSS, TEXT

DOC_LANGS = {"markdown", "md"}
PLAIN_LANGS = {"text", "txt", "plaintext", "plain", "output", "console", "log", ""}

_OPEN = re.compile(r"^\s{0,3}(`{3,})\s*([\w+#.\-]*)[^\n]*$")
_CLOSE = re.compile(r"^\s{0,3}`{3,}\s*$")


@dataclass
class Segment:
    kind: str            # "text" | "code" | "doc"
    body: str
    lang: str = ""
    closed: bool = True


def split_segments(text: str) -> list[Segment]:
    """Split a reply into prose and fenced blocks (code or ```markdown documents)."""
    segs: list[Segment] = []
    buf: list[str] = []
    in_fence = False
    lang = ""
    depth = 0

    def flush_text():
        body = "\n".join(buf).strip("\n")
        if body.strip():
            segs.append(Segment("text", body))
        buf.clear()

    for line in text.split("\n"):
        if not in_fence:
            m = _OPEN.match(line)
            if m:
                flush_text()
                in_fence, lang, depth = True, m.group(2).lower(), 0
            else:
                buf.append(line)
            continue
        # inside a fence
        if _CLOSE.match(line):
            if lang in DOC_LANGS and depth > 0:
                depth -= 1
                buf.append(line)
                continue
            segs.append(_fence_segment(lang, "\n".join(buf), True))
            buf.clear()
            in_fence = False
            continue
        if lang in DOC_LANGS and _OPEN.match(line) and _OPEN.match(line).group(2):
            depth += 1  # a code block nested inside a markdown document
        buf.append(line)

    if in_fence:
        segs.append(_fence_segment(lang, "\n".join(buf), False))
    else:
        flush_text()
    return segs


def _fence_segment(lang: str, body: str, closed: bool) -> Segment:
    body = body.strip("\n")
    return Segment("doc" if lang in DOC_LANGS else "code", body, lang, closed)


# ---------------------------------------------------------------- markdown
_MD = markdown.Markdown(extensions=["tables", "sane_lists", "nl2br"], output_format="html")


_LIST_LINE = re.compile(r"^(\s+)([-*+]|\d+[.)])\s+\S")


def normalize_lists(text: str) -> str:
    """Small models indent nested lists by 2 or 3 spaces; Markdown needs 4. Fix that."""
    lines = text.split("\n")
    indents = [len(m.group(1).replace("\t", "    ")) for ln in lines if (m := _LIST_LINE.match(ln))]
    if not indents:
        return text
    unit = min(indents)
    if unit <= 0 or unit == 4:
        return text
    out = []
    for ln in lines:
        m = _LIST_LINE.match(ln)
        if m:
            n = len(m.group(1).replace("\t", "    "))
            level = max(1, round(n / unit))
            ln = " " * (4 * level) + ln.lstrip()
        out.append(ln)
    return "\n".join(out)


def md_to_html(text: str, caret: str = "") -> str:
    _MD.reset()
    out = _MD.convert(normalize_lists(text))
    out = out.replace("<table>", '<table border="0" cellspacing="0" cellpadding="8" width="100%">')
    if caret:
        # put the typing caret at the end of the last paragraph, heading or list item
        m = _TAIL.search(out)
        out = out[:m.start(1)] + caret + out[m.start(1):] if m else out + caret
    return out


_TAIL = re.compile(r"(</(?:p|li|h[1-6])>)(?:\s*</(?:ul|ol)>)*\s*$")


# --------------------------------------------------------------- highlight
def _style():
    for name in ("one-dark", "github-dark", "monokai"):
        try:
            return get_style_by_name(name)
        except ClassNotFound:
            continue
    return get_style_by_name("default")


_FORMATTER = HtmlFormatter(noclasses=True, nowrap=True, style=_style())


def _lexer(lang: str, code: str):
    lang = (lang or "").lower()
    if lang in PLAIN_LANGS:
        return TextLexer()
    try:
        return get_lexer_by_name(lang)
    except ClassNotFound:
        pass
    try:
        return guess_lexer(code) if len(code) > 60 else TextLexer()
    except ClassNotFound:
        return TextLexer()


def highlight_html(code: str, lang: str = "", base_px: int = 13) -> str:
    """Highlighted code as HTML. `pre-wrap` makes long lines wrap instead of scrolling."""
    body = highlight(code, _lexer(lang, code), _FORMATTER) if code else ""
    return (
        f'<pre style="margin:0; white-space:pre-wrap; color:{TEXT}; '
        f"font-family:{MONO_CSS}; font-size:{base_px}px; line-height:140%;\">"
        f"{body.rstrip()}</pre>"
    )


def plain_html(text: str) -> str:
    return f'<div style="white-space:pre-wrap;">{html.escape(text)}</div>'


# ----------------------------------------------------------------- saving
EXT_BY_LANG = {
    "python": "py", "py": "py", "javascript": "js", "js": "js", "typescript": "ts", "ts": "ts",
    "tsx": "tsx", "jsx": "jsx", "java": "java", "c": "c", "cpp": "cpp", "c++": "cpp",
    "csharp": "cs", "cs": "cs", "go": "go", "rust": "rs", "rs": "rs", "kotlin": "kt",
    "html": "html", "css": "css", "json": "json", "markdown": "md", "md": "md", "bash": "sh",
    "sh": "sh", "shell": "sh", "sql": "sql", "yaml": "yml", "yml": "yml", "xml": "xml",
    "php": "php", "ruby": "rb", "swift": "swift", "toml": "toml", "dockerfile": "Dockerfile",
}
_FILE_IN_TEXT = re.compile(r"\b([\w\-]+\.(?:md|py|js|ts|tsx|jsx|java|c|cpp|cs|go|rs|html|css|json|sh|sql|yml|yaml|txt|toml))\b")


def suggest_filename(lang: str, user_text: str = "") -> str:
    """Prefer a file name the user mentioned (e.g. design.md), else guess from the language."""
    ext = EXT_BY_LANG.get((lang or "").lower(), "txt")
    names = _FILE_IN_TEXT.findall(user_text or "")
    for n in names:
        if n.lower().endswith("." + ext.lower()):
            return n
    if ext == "Dockerfile":
        return "Dockerfile"
    if ext == "md":
        return "notes.md"
    return f"snippet.{ext}"
