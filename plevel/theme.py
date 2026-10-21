"""Dark theme stylesheet."""

BG = "#14161b"
PANEL = "#1b1d23"
PANEL_ALT = "#22252d"
BORDER = "#2b2f38"
TEXT = "#e6e6e6"
MUTED = "#8b93a1"
ACCENT = "#6ea8fe"
ACCENT_HOVER = "#8dbcff"
DANGER = "#ef6b6b"

STYLESHEET = f"""
QWidget {{
    background-color: {BG};
    color: {TEXT};
    font-size: 13px;
}}
QMainWindow, QDialog {{ background-color: {BG}; }}
QMenuBar {{ background-color: {PANEL}; }}
QMenuBar::item:selected, QMenu::item:selected {{ background-color: {PANEL_ALT}; }}
QMenu {{ background-color: {PANEL}; border: 1px solid {BORDER}; }}
QStatusBar {{ background-color: {PANEL}; color: {MUTED}; }}

QFrame#sidebar, QFrame#settings {{
    background-color: {PANEL};
    border: none;
}}
QFrame#sidebar {{ border-right: 1px solid {BORDER}; }}
QFrame#settings {{ border-left: 1px solid {BORDER}; }}

QLabel#heading {{ font-weight: bold; font-size: 14px; background: transparent; }}
QLabel#muted {{ color: {MUTED}; background: transparent; }}
QLabel {{ background: transparent; }}

QLineEdit, QPlainTextEdit, QComboBox, QTextBrowser {{
    background-color: {PANEL_ALT};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 6px;
    selection-background-color: {ACCENT};
    selection-color: #0b0d12;
}}
QTextBrowser#chat {{ border: none; border-radius: 0; background-color: {BG}; padding: 8px 16px; }}
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus {{ border: 1px solid {ACCENT}; }}
QComboBox QAbstractItemView {{ background-color: {PANEL}; selection-background-color: {PANEL_ALT}; }}

QPushButton {{
    background-color: {PANEL_ALT};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 6px 12px;
}}
QPushButton:hover {{ border-color: {ACCENT}; }}
QPushButton:disabled {{ color: {MUTED}; }}
QPushButton#primary {{
    background-color: {ACCENT};
    color: #0b0d12;
    border: none;
    font-weight: bold;
}}
QPushButton#primary:hover {{ background-color: {ACCENT_HOVER}; }}
QPushButton#danger {{ background-color: {DANGER}; color: #0b0d12; border: none; font-weight: bold; }}

QListWidget {{
    background-color: {PANEL};
    border: none;
    outline: none;
}}
QListWidget::item {{ padding: 8px; border-radius: 6px; margin: 1px 4px; }}
QListWidget::item:selected {{ background-color: {PANEL_ALT}; color: {TEXT}; }}
QListWidget::item:hover {{ background-color: {PANEL_ALT}; }}

QSlider::groove:horizontal {{ height: 4px; background: {BORDER}; border-radius: 2px; }}
QSlider::handle:horizontal {{
    background: {ACCENT}; width: 14px; height: 14px; margin: -6px 0; border-radius: 7px;
}}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 2px; }}

QProgressBar {{ background-color: {BORDER}; border: none; border-radius: 4px; }}
QProgressBar::chunk {{ background-color: {ACCENT}; border-radius: 4px; }}
QPushButton::menu-indicator {{ subcontrol-position: right center; right: 6px; }}

QScrollBar:vertical {{ background: {BG}; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 5px; min-height: 30px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QToolTip {{ background-color: {PANEL_ALT}; color: {TEXT}; border: 1px solid {BORDER}; }}
"""
