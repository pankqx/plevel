"""Design tokens, bundled fonts and the Qt stylesheet.

Look: deep blue-black canvas, one violet-to-cyan accent gradient, generous
spacing, rounded corners, Inter for text and JetBrains Mono for code.
"""

from __future__ import annotations

from pathlib import Path

ASSETS = Path(__file__).resolve().parent / "assets"

# ---- palette -------------------------------------------------------------
BG = "#0b0d12"
SURFACE = "#10131a"
SURFACE2 = "#161a23"
SURFACE3 = "#1d2230"
BORDER = "#232a3b"
TEXT = "#e8ebf2"
MUTED = "#7b8499"
SUBTLE = "#4b5368"
ACCENT = "#7c6cff"
ACCENT2 = "#22d3ee"
DANGER = "#ff6b81"
GREEN = "#4ade80"
AMBER = "#fbbf24"
CODE_BG = "#0d1017"
INLINE_CODE_BG = "#1a2030"
INLINE_CODE_FG = "#9ee7ff"

GRADIENT = f"qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {ACCENT}, stop:1 {ACCENT2})"
GRADIENT_HOVER = "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #9084ff, stop:1 #5ce1f2)"

UI_FALLBACK = '"Inter Variable", "Inter", "Ubuntu", "Cantarell", "Noto Sans", sans-serif'
MONO_FALLBACK = '"JetBrains Mono", "Fira Code", "Ubuntu Mono", "DejaVu Sans Mono", monospace'
MONO_CSS = "'JetBrains Mono', 'Fira Code', 'Ubuntu Mono', 'DejaVu Sans Mono', monospace"
UI_CSS = "'Inter Variable', 'Inter', 'Ubuntu', 'Cantarell', 'Noto Sans', sans-serif"


def load_fonts() -> None:
    """Register the bundled fonts with Qt (safe to call once per process)."""
    from PySide6.QtGui import QFontDatabase
    for f in sorted((ASSETS / "fonts").glob("*.ttf")):
        QFontDatabase.addApplicationFont(str(f))


def chevron_path() -> str:
    return str(ASSETS / "chevron-down.svg")


def document_css(base_px: int = 14) -> str:
    """Default stylesheet for the rich-text widgets that show chat prose."""
    return f"""
        body, p, li, td, th {{ color: {TEXT}; font-family: {UI_CSS}; font-size: {base_px}px; }}
        p {{ margin-top: 0px; margin-bottom: 11px; line-height: 155%; }}
        h1 {{ font-size: {base_px + 8}px; font-weight: 700; margin-top: 20px; margin-bottom: 9px; }}
        h2 {{ font-size: {base_px + 4}px; font-weight: 700; margin-top: 18px; margin-bottom: 8px; }}
        h3 {{ font-size: {base_px + 2}px; font-weight: 700; margin-top: 14px; margin-bottom: 6px; }}
        h4, h5, h6 {{ font-size: {base_px}px; font-weight: 700; margin-top: 12px; margin-bottom: 4px; }}
        ul, ol {{ margin-top: 0px; margin-bottom: 11px; }}
        li {{ margin-bottom: 5px; line-height: 155%; }}
        a {{ color: {ACCENT2}; text-decoration: none; }}
        code {{ font-family: {MONO_CSS}; font-size: {base_px - 1}px; color: {INLINE_CODE_FG};
               background-color: {INLINE_CODE_BG}; }}
        blockquote {{ color: {MUTED}; margin-left: 14px; }}
        th {{ background-color: {SURFACE3}; font-weight: 700; }}
        hr {{ color: {BORDER}; }}
    """


def stylesheet() -> str:
    chev = chevron_path().replace("\\", "/")
    return f"""
* {{ font-family: {UI_FALLBACK}; font-size: 14px; outline: none; }}
QWidget {{ color: {TEXT}; }}
QMainWindow, QDialog {{ background-color: {BG}; }}
QLabel {{ background: transparent; }}
QLabel#muted {{ color: {MUTED}; font-size: 12px; }}
QLabel#tiny {{ color: {MUTED}; font-size: 11px; }}
QLabel#heading {{ font-weight: 700; font-size: 13px; color: {TEXT}; }}
QLabel#title {{ font-weight: 700; font-size: 15px; }}
QLabel#section {{ color: {SUBTLE}; font-size: 11px; font-weight: 700; letter-spacing: 1px; }}

QMenuBar {{ background-color: {BG}; color: {MUTED}; padding: 2px 6px; }}
QMenuBar::item {{ padding: 5px 10px; border-radius: 6px; background: transparent; }}
QMenuBar::item:selected {{ background-color: {SURFACE2}; color: {TEXT}; }}
QMenu {{ background-color: {SURFACE2}; border: 1px solid {BORDER}; padding: 6px; }}
QMenu::item {{ padding: 7px 22px 7px 14px; border-radius: 6px; }}
QMenu::item:selected {{ background-color: {SURFACE3}; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 5px 8px; }}
QToolTip {{ background-color: {SURFACE3}; color: {TEXT}; border: 1px solid {BORDER};
           padding: 6px 8px; border-radius: 6px; }}
QStatusBar {{ background: transparent; }}

/* ---- panels -------------------------------------------------------- */
QFrame#sidebar {{ background-color: {SURFACE}; border: none; border-right: 1px solid {BORDER}; }}
QFrame#sidebar QWidget {{ background-color: transparent; }}
QFrame#drawer {{ background-color: {SURFACE}; border: none; border-left: 1px solid {BORDER}; }}
QFrame#drawer QWidget {{ background-color: transparent; }}
QWidget#header {{ background-color: transparent; }}
QWidget#canvas {{ background-color: {BG}; }}
QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: none; }}

/* ---- inputs ------------------------------------------------------- */
QLineEdit {{ background-color: {SURFACE2}; border: 1px solid {BORDER}; border-radius: 10px;
            padding: 8px 12px; selection-background-color: {ACCENT}; }}
QLineEdit:focus {{ border: 1px solid {ACCENT}; }}
QPlainTextEdit#sysedit {{ background-color: {SURFACE2}; border: 1px solid {BORDER}; border-radius: 10px;
            padding: 8px 10px; selection-background-color: {ACCENT}; }}
QPlainTextEdit#sysedit:focus {{ border: 1px solid {ACCENT}; }}

QFrame#composer {{ background-color: {SURFACE}; border: 1px solid {BORDER}; border-radius: 18px; }}
QFrame#composer[focused="true"] {{ border: 1px solid {ACCENT}; }}
QPlainTextEdit#composerEdit {{ background: transparent; border: none; padding: 4px 4px;
            selection-background-color: {ACCENT}; font-size: 15px; }}

QComboBox {{ background-color: {SURFACE2}; border: 1px solid {BORDER}; border-radius: 12px;
            padding: 7px 34px 7px 14px; }}
QComboBox:hover {{ border: 1px solid {SUBTLE}; }}
QComboBox:focus {{ border: 1px solid {ACCENT}; }}
QComboBox::drop-down {{ border: none; width: 28px; subcontrol-position: center right; }}
QComboBox::down-arrow {{ image: url({chev}); width: 12px; height: 12px; }}
QComboBox QAbstractItemView {{ background-color: {SURFACE2}; border: 1px solid {BORDER};
            selection-background-color: {SURFACE3}; padding: 4px; outline: none; }}

/* ---- buttons ------------------------------------------------------ */
QPushButton {{ background-color: {SURFACE2}; border: 1px solid {BORDER}; border-radius: 12px;
              padding: 7px 14px; color: {TEXT}; }}
QPushButton:hover {{ border: 1px solid {SUBTLE}; background-color: {SURFACE3}; }}
QPushButton:pressed {{ background-color: {SURFACE}; }}
QPushButton:disabled {{ color: {SUBTLE}; background-color: {SURFACE}; }}
QPushButton::menu-indicator {{ image: url({chev}); width: 10px; height: 10px;
              subcontrol-position: right center; right: 10px; }}
QPushButton#primary {{ background: {GRADIENT}; border: none; color: #ffffff; font-weight: 700;
              padding: 10px 14px; border-radius: 12px; }}
QPushButton#primary:hover {{ background: {GRADIENT_HOVER}; }}
QPushButton#ghost {{ background: transparent; border: none; color: {MUTED}; padding: 5px 9px;
              border-radius: 8px; font-size: 12px; }}
QPushButton#ghost:hover {{ background-color: {SURFACE2}; color: {TEXT}; }}
QPushButton#icon {{ background: transparent; border: none; color: {MUTED}; padding: 6px 10px;
              border-radius: 10px; font-size: 16px; }}
QPushButton#icon:hover {{ background-color: {SURFACE2}; color: {TEXT}; }}
QPushButton#icon:checked {{ background-color: {SURFACE3}; color: {TEXT}; }}
QPushButton#pill {{ background-color: {SURFACE2}; border: 1px solid {BORDER}; border-radius: 12px;
              padding: 7px 28px 7px 14px; }}
QPushButton#send {{ background: {GRADIENT}; border: none; border-radius: 19px; color: white;
              font-size: 18px; font-weight: 700; padding: 0px; }}
QPushButton#send:hover {{ background: {GRADIENT_HOVER}; }}
QPushButton#send:disabled {{ background: {SURFACE3}; color: {SUBTLE}; }}
QPushButton#send[busy="true"] {{ background: {DANGER}; }}
QPushButton#attach {{ background: transparent; border: 1px solid {BORDER}; color: {MUTED};
              border-radius: 14px; padding: 5px 12px; font-size: 12px; }}
QPushButton#attach:hover {{ color: {TEXT}; border: 1px solid {SUBTLE}; }}
QPushButton#rate {{ border-radius: 12px; padding: 8px 16px; font-weight: 700; }}
QPushButton#rate[kind="pass"]:hover {{ border: 1px solid {GREEN}; color: {GREEN}; }}
QPushButton#rate[kind="partial"]:hover {{ border: 1px solid {AMBER}; color: {AMBER}; }}
QPushButton#rate[kind="fail"]:hover {{ border: 1px solid {DANGER}; color: {DANGER}; }}
QPushButton#rate[chosen="true"][kind="pass"] {{ background-color: rgba(74,222,128,40); border: 1px solid {GREEN}; color: {GREEN}; }}
QPushButton#rate[chosen="true"][kind="partial"] {{ background-color: rgba(251,191,36,40); border: 1px solid {AMBER}; color: {AMBER}; }}
QPushButton#rate[chosen="true"][kind="fail"] {{ background-color: rgba(255,107,129,40); border: 1px solid {DANGER}; color: {DANGER}; }}

/* ---- lists -------------------------------------------------------- */
QListWidget {{ background: transparent; border: none; outline: none; }}
QListWidget::item {{ padding: 9px 12px; border-radius: 10px; margin: 1px 0px; color: {MUTED}; }}
QListWidget::item:hover {{ background-color: {SURFACE2}; color: {TEXT}; }}
QListWidget::item:selected {{ background-color: {SURFACE3}; color: {TEXT}; }}
QListWidget::item:disabled {{ background: transparent; color: {SUBTLE}; font-size: 11px;
              font-weight: 700; padding: 12px 12px 4px 12px; }}

/* ---- slider / progress --------------------------------------------- */
QSlider::groove:horizontal {{ height: 4px; background: {BORDER}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {TEXT}; width: 14px; height: 14px; margin: -5px 0;
              border-radius: 7px; }}
QSlider::sub-page:horizontal {{ background: {GRADIENT}; border-radius: 2px; }}
QProgressBar {{ background-color: {SURFACE3}; border: none; border-radius: 2px; max-height: 4px; }}
QProgressBar::chunk {{ background-color: {GREEN}; border-radius: 2px; }}

/* ---- scrollbars --------------------------------------------------- */
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {SURFACE3}; border-radius: 3px; min-height: 36px; }}
QScrollBar::handle:vertical:hover {{ background: {SUBTLE}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {SURFACE3}; border-radius: 3px; min-width: 36px; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0px; }}

/* ---- chat pieces -------------------------------------------------- */
QFrame#userBubble {{ background: transparent; border: none; }}
QFrame#userBubble QWidget {{ background: transparent; }}
QFrame#userBubble QFrame#codecard {{ background-color: rgba(8,10,16,170); border: 1px solid rgba(255,255,255,26); }}
QFrame#codecard {{ background-color: {CODE_BG}; border: 1px solid {BORDER}; border-radius: 14px; }}
QFrame#codecard QWidget {{ background: transparent; }}
QFrame#doccard {{ background-color: {SURFACE}; border: 1px solid {BORDER}; border-radius: 14px; }}
QFrame#doccard QWidget {{ background: transparent; }}
QFrame#errorcard {{ background-color: rgba(255,107,129,28); border: 1px solid rgba(255,107,129,110);
              border-radius: 14px; }}
QFrame#errorcard QWidget {{ background: transparent; }}
QFrame#suggest {{ background-color: {SURFACE}; border: 1px solid {BORDER}; border-radius: 16px; }}
QFrame#suggest:hover {{ background-color: {SURFACE2}; border: 1px solid {ACCENT}; }}
QFrame#suggest QLabel {{ background: transparent; }}
QTextBrowser {{ background: transparent; border: none; selection-background-color: {ACCENT};
              selection-color: #ffffff; }}
QTextEdit {{ background: transparent; border: none; selection-background-color: {ACCENT}; }}
QTableWidget {{ background-color: {SURFACE}; color: {TEXT}; border: 1px solid {BORDER};
              border-radius: 12px; outline: none; }}
QTableWidget::item {{ padding: 6px 8px; border: none; }}
QHeaderView {{ background: transparent; }}
QHeaderView::section {{ background-color: {SURFACE}; color: {MUTED}; border: none;
              border-bottom: 1px solid {BORDER}; padding: 8px; font-weight: bold; }}
QTableCornerButton::section {{ background: {SURFACE}; border: none; }}
"""
