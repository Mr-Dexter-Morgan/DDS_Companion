from __future__ import annotations

BG = "#0b0d13"
SIDEBAR = "#0e1119"
PANEL = "#121620"
PANEL_ALT = "#151a26"
BORDER = "#222939"
TEXT = "#edf2ff"
MUTED = "#8f98aa"
DIM = "#60697a"
ACCENT = "#7b7cff"
ACCENT_2 = "#9d6cff"
SUCCESS = "#55d6a2"
WARNING = "#f0c36a"
DANGER = "#ff6b81"
INFO = "#62b5ff"

APP_STYLESHEET = f"""
* {{
    font-family: "Segoe UI", "Inter", sans-serif;
    font-size: 10pt;
}}
QMainWindow, QWidget#Root {{
    background: {BG};
    color: {TEXT};
}}
QToolTip {{
    color: {TEXT};
    background: {PANEL_ALT};
    border: 1px solid {BORDER};
    padding: 6px;
}}
QScrollArea {{
    border: none;
    background: transparent;
}}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QWidget#PageScrollContent {{ background: transparent; }}
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 4px 2px;
}}
QScrollBar::handle:vertical {{
    background: #2a3142;
    border-radius: 4px;
    min-height: 28px;
}}
QScrollBar::handle:vertical:hover {{ background: #384159; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 2px 4px;
}}
QScrollBar::handle:horizontal {{
    background: #2a3142;
    border-radius: 4px;
    min-width: 28px;
}}
QFrame#Sidebar {{
    background: {SIDEBAR};
    border-right: 1px solid {BORDER};
}}
QFrame#Topbar {{
    background: {BG};
    border-bottom: 1px solid {BORDER};
}}
QFrame[card="true"] {{
    background: {PANEL};
    border: 1px solid {BORDER};
    border-radius: 14px;
}}
QFrame[card="true"]:hover {{ border-color: #30394d; }}
QLabel#BrandMark {{
    color: white;
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 {ACCENT}, stop:1 {ACCENT_2});
    border-radius: 10px;
    font-size: 11pt;
    font-weight: 800;
    padding: 4px;
}}
QLabel#BrandTitle {{ font-size: 13pt; font-weight: 700; color: {TEXT}; }}
QLabel#BrandSub {{ font-size: 9pt; color: {MUTED}; }}
QPushButton[nav="true"] {{
    text-align: left;
    padding: 10px 12px;
    border-radius: 9px;
    border: 1px solid #161c28;
    color: #9aa4b8;
    background: #10151f;
    font-weight: 600;
}}
QPushButton[nav="true"]:hover {{
    color: {TEXT};
    background: #1a2230;
    border-color: #2a3548;
}}
QPushButton[nav="true"]:checked,
QPushButton[nav="true"]:checked:hover {{
    color: white;
    background: #27263d;
    border-color: #6668f1;
    font-weight: 750;
}}
QPushButton[primary="true"] {{
    color: white;
    background: {ACCENT};
    border: none;
    border-radius: 9px;
    padding: 8px 13px;
    font-weight: 650;
}}
QPushButton[primary="true"]:hover {{ background: #8a8bff; }}
QPushButton[primary="true"]:pressed {{ background: #6d6eea; }}
QPushButton[secondary="true"] {{
    color: {TEXT};
    background: {PANEL_ALT};
    border: 1px solid {BORDER};
    border-radius: 9px;
    padding: 8px 12px;
    font-weight: 600;
}}
QPushButton[secondary="true"]:hover {{
    background: #1b2130;
    border-color: #333c52;
}}
QPushButton[secondary="true"][compact="true"] {{
    padding: 6px 10px;
    min-width: 0px;
}}
QPushButton[ghost="true"] {{
    color: {MUTED};
    background: transparent;
    border: 1px solid transparent;
    border-radius: 8px;
    padding: 6px 9px;
}}
QPushButton[ghost="true"]:hover {{ color: {TEXT}; background: #151a25; }}
QPushButton:disabled {{ color: #555e6e; background: #141821; border-color: #1c2230; }}
QTabWidget#SettingsTabs::pane {{
    border: none;
    background: transparent;
    top: -1px;
}}
QTabWidget#SettingsTabs QTabBar::tab {{
    color: {MUTED};
    background: #10151f;
    border: 1px solid #1b2230;
    border-bottom-color: {BORDER};
    padding: 8px 14px;
    margin-right: 6px;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    font-weight: 650;
}}
QTabWidget#SettingsTabs QTabBar::tab:hover {{
    color: {TEXT};
    background: #171e2a;
    border-color: #2b3548;
}}
QTabWidget#SettingsTabs QTabBar::tab:selected {{
    color: white;
    background: #27263d;
    border-color: #6668f1;
}}
QWidget#SettingsPathsContent {{ background: transparent; }}
QLabel#PageTitle {{ font-size: 19pt; font-weight: 750; color: {TEXT}; }}
QLabel#PageSubtitle {{ font-size: 9.5pt; color: {MUTED}; }}
QLabel#CardEyebrow {{ font-size: 8.5pt; font-weight: 650; color: {MUTED}; }}
QLabel#MetricValue {{ font-size: 22pt; font-weight: 760; color: {TEXT}; }}
QLabel#MetricHint {{ font-size: 9pt; color: {MUTED}; }}
QLabel#SectionTitle {{ font-size: 11pt; font-weight: 700; color: {TEXT}; }}
QLabel#SectionHint {{ font-size: 9pt; color: {MUTED}; }}
QLabel[state="RUNNING"] {{ color: {SUCCESS}; }}
QLabel[state="STARTING"] {{ color: {INFO}; }}
QLabel[state="LIMITED"] {{ color: {WARNING}; }}
QLabel[state="DEGRADED"] {{ color: {WARNING}; }}
QLabel[state="STALE"] {{ color: {WARNING}; }}
QLabel[state="WAITING"] {{ color: {MUTED}; }}
QLabel[state="ERROR"] {{ color: {DANGER}; }}
QLabel[state="STOPPED"] {{ color: {MUTED}; }}
QLabel#StatusPill {{
    padding: 6px 11px;
    border-radius: 10px;
    font-size: 9pt;
    font-weight: 800;
}}
QLabel#StatusPill[state="RUNNING"] {{ color: {SUCCESS}; background: #10251f; border: 1px solid #1e4f40; }}
QLabel#StatusPill[state="STARTING"] {{ color: {INFO}; background: #102131; border: 1px solid #214a6d; }}
QLabel#StatusPill[state="LIMITED"] {{ color: {WARNING}; background: #2a2314; border: 1px solid #5c4c25; }}
QLabel#StatusPill[state="DEGRADED"] {{ color: {WARNING}; background: #2a2314; border: 1px solid #5c4c25; }}
QLabel#StatusPill[state="STALE"] {{ color: {WARNING}; background: #2a2314; border: 1px solid #5c4c25; }}
QLabel#StatusPill[state="WAITING"] {{ color: {MUTED}; background: #171a21; border: 1px solid #2a303d; }}
QLabel#StatusPill[state="ERROR"] {{ color: {DANGER}; background: #2b151b; border: 1px solid #642d3a; }}
QLabel#StatusPill[state="STOPPED"] {{ color: {MUTED}; background: #171a21; border: 1px solid #2a303d; }}
QProgressBar {{
    border: none;
    background: #202635;
    border-radius: 4px;
    height: 8px;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{
    border-radius: 4px;
    background: {ACCENT};
}}
QLineEdit {{
    color: {TEXT};
    background: #0f131c;
    border: 1px solid {BORDER};
    border-radius: 9px;
    padding: 8px 10px;
    selection-background-color: {ACCENT};
}}
QLineEdit:focus {{ border-color: #525bb0; }}
QTreeWidget, QTableWidget {{
    color: {TEXT};
    background: transparent;
    alternate-background-color: #10141d;
    border: none;
    gridline-color: {BORDER};
    selection-background-color: #252d44;
    selection-color: white;
    outline: none;
}}
QTreeWidget::item {{ padding: 7px 5px; border-radius: 6px; }}
QTreeWidget::item:hover {{ background: #171c27; }}
QTreeWidget::item:selected {{ background: #242b40; }}
QHeaderView::section {{
    color: {MUTED};
    background: #10141d;
    border: none;
    border-bottom: 1px solid {BORDER};
    padding: 8px 7px;
    font-size: 8.5pt;
    font-weight: 700;
}}
QTableWidget::item {{ padding: 7px; border-bottom: 1px solid #171d28; }}
QSplitter::handle {{ background: transparent; width: 5px; height: 5px; }}
QStatusBar {{
    color: {MUTED};
    background: {SIDEBAR};
    border-top: 1px solid {BORDER};
}}
"""
