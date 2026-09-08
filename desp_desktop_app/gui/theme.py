from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QFontDatabase
from PyQt5.QtWidgets import QApplication

from core.app_paths import resource_dir


COLORS = {
    "navy": "#00205B",
    "blue": "#005199",
    "cyan": "#008BAC",
    "teal": "#3CBFAE",
    "magenta": "#8F489A",
    "amber": "#F5A114",
    "red": "#CA252C",
    "ink": "#323E48",
    "gray": "#76777B",
    "line": "#DAD9D7",
    "canvas": "#F4F5F3",
    "surface": "#FFFFFF",
    "soft_blue": "#EAF4F7",
}


def configure_high_dpi() -> None:
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)


def configure_application(app: QApplication) -> None:
    font_dir = resource_dir() / "assets" / "fonts"
    for path in font_dir.glob("*.ttf"):
        QFontDatabase.addApplicationFont(str(path))
    app.setApplicationName("DESP Studio")
    app.setOrganizationName("DESP")
    app.setStyle("Fusion")
    app.setFont(QFont("Noto Sans", 10))
    app.setStyleSheet(STYLESHEET)
    configure_matplotlib()


def configure_matplotlib() -> None:
    from cycler import cycler
    from matplotlib import rcParams

    rcParams.update(
        {
            "axes.unicode_minus": False,
            "font.family": "Noto Sans",
            "font.size": 9,
            "figure.facecolor": COLORS["surface"],
            "axes.facecolor": COLORS["surface"],
            "axes.edgecolor": COLORS["line"],
            "axes.labelcolor": COLORS["ink"],
            "axes.titlecolor": COLORS["navy"],
            "axes.titleweight": 600,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": True,
            "grid.color": COLORS["line"],
            "grid.alpha": 0.7,
            "lines.linewidth": 1.2,
            "legend.frameon": False,
            "axes.prop_cycle": cycler(color=[COLORS["blue"], COLORS["cyan"], COLORS["teal"], COLORS["magenta"], COLORS["amber"], COLORS["red"]]),
        }
    )


STYLESHEET = f"""
QMainWindow, QWidget#AppRoot {{ background: {COLORS['canvas']}; color: {COLORS['ink']}; }}
QWidget {{ color: {COLORS['ink']}; font-family: "Noto Sans"; font-size: 13px; }}
QFrame#Header {{ background: {COLORS['navy']}; border: none; }}
QLabel#Product {{ color: white; font-size: 22px; font-weight: 700; }}
QLabel#HeaderContext {{ color: #D9EEF8; font-size: 12px; }}
QLabel#PageTitle {{ color: {COLORS['navy']}; font-size: 22px; font-weight: 700; }}
QLabel#PageLead {{ color: {COLORS['gray']}; font-size: 12px; }}
QLabel#MethodTitle {{ color: {COLORS['navy']}; font-size: 19px; font-weight: 700; }}
QLabel#MethodCode {{ color: white; background: {COLORS['cyan']}; min-width: 48px; min-height: 48px; max-width: 48px; max-height: 48px; font-size: 16px; font-weight: 700; qproperty-alignment: AlignCenter; }}
QLabel#Badge {{ color: {COLORS['blue']}; background: {COLORS['soft_blue']}; border: 1px solid #B7DCE8; padding: 4px 8px; }}
QLabel#KpiValue {{ color: {COLORS['navy']}; font-size: 18px; font-weight: 700; }}
QLabel#KpiLabel {{ color: {COLORS['gray']}; font-size: 11px; }}
QLabel#QualityWarning {{ color: #6B4300; background: #FFF4DC; border-left: 4px solid {COLORS['amber']}; padding: 9px 12px; }}
QTabBar#StageBar {{ background: white; border-bottom: 1px solid {COLORS['line']}; }}
QTabBar#StageBar::tab {{ min-width: 150px; min-height: 42px; padding: 0 18px; color: {COLORS['gray']}; background: white; border: none; border-bottom: 3px solid transparent; font-weight: 600; }}
QTabBar#StageBar::tab:selected {{ color: {COLORS['navy']}; border-bottom: 3px solid {COLORS['cyan']}; }}
QTabBar#MethodBar::tab {{ min-width: 92px; min-height: 36px; padding: 0 12px; color: {COLORS['gray']}; background: #EEF0EF; border: 1px solid {COLORS['line']}; border-right: none; }}
QTabBar#MethodBar::tab:last {{ border-right: 1px solid {COLORS['line']}; }}
QTabBar#MethodBar::tab:selected {{ color: white; background: {COLORS['navy']}; border-color: {COLORS['navy']}; }}
QFrame#ToolPanel, QFrame#SourceStrip, QFrame#KpiStrip {{ background: white; border: 1px solid {COLORS['line']}; }}
QFrame#ToolPanel {{ border-top: 4px solid {COLORS['cyan']}; }}
QPushButton {{ min-height: 34px; padding: 0 14px; border: 1px solid #AAB1B5; background: white; color: {COLORS['ink']}; }}
QPushButton:hover {{ border-color: {COLORS['cyan']}; color: {COLORS['navy']}; }}
QPushButton[variant="primary"] {{ background: {COLORS['blue']}; color: white; border-color: {COLORS['blue']}; font-weight: 600; }}
QPushButton[variant="primary"]:hover {{ background: {COLORS['navy']}; }}
QPushButton[variant="accent"] {{ background: {COLORS['cyan']}; color: white; border-color: {COLORS['cyan']}; font-weight: 600; }}
QToolButton {{ min-width: 30px; min-height: 30px; border: 1px solid {COLORS['line']}; background: white; }}
QPushButton:checked {{ background: {COLORS['soft_blue']}; color: {COLORS['navy']}; border: 2px solid {COLORS['cyan']}; }}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{ min-height: 32px; padding: 0 8px; background: white; border: 1px solid #B9BEC1; selection-background-color: {COLORS['cyan']}; }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{ border: 2px solid {COLORS['cyan']}; }}
QTableWidget {{ background: white; alternate-background-color: #F7F8F7; border: 1px solid {COLORS['line']}; gridline-color: {COLORS['line']}; }}
QHeaderView::section {{ background: #EEF0EF; color: {COLORS['navy']}; border: none; border-right: 1px solid {COLORS['line']}; border-bottom: 1px solid {COLORS['line']}; padding: 8px; font-weight: 600; }}
QTabWidget::pane {{ border: 1px solid {COLORS['line']}; background: white; }}
QTabBar::tab {{ padding: 8px 13px; }}
QScrollArea {{ border: none; background: transparent; }}
QProgressBar {{ min-height: 8px; max-height: 8px; border: none; background: #E3E5E4; }}
QProgressBar::chunk {{ background: {COLORS['teal']}; }}
QStatusBar {{ background: white; border-top: 1px solid {COLORS['line']}; color: {COLORS['gray']}; }}
QToolTip {{ color: white; background: {COLORS['ink']}; border: none; padding: 5px; }}
"""
