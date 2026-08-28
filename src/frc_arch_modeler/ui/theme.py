"""Shared Voltage dark theme for Qt widgets."""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

VOLTAGE_YELLOW = "#FFE800"
VOLTAGE_BLUE = "#0429D2"
NEAR_BLACK = "#111318"
PANEL_BLACK = "#1A1E26"
OFF_WHITE = "#F4F6FA"
MUTED_TEXT = "#AAB5C7"


def apply_voltage_theme(app: QApplication) -> None:
    """Apply a readable dark palette without relying on status color alone."""
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(NEAR_BLACK))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(OFF_WHITE))
    palette.setColor(QPalette.ColorRole.Base, QColor(PANEL_BLACK))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(NEAR_BLACK))
    palette.setColor(QPalette.ColorRole.Text, QColor(OFF_WHITE))
    palette.setColor(QPalette.ColorRole.Button, QColor(PANEL_BLACK))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(OFF_WHITE))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(VOLTAGE_BLUE))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(OFF_WHITE))
    app.setPalette(palette)
    app.setStyleSheet(
        f"""
        QToolBar {{ background: {PANEL_BLACK}; border-bottom: 1px solid #303846; }}
        QToolBar QToolButton {{
            color: {OFF_WHITE};
            background: transparent;
            padding: 5px 8px;
        }}
        QToolBar QToolButton:hover {{ background: #303846; color: {VOLTAGE_YELLOW}; }}
        QToolBar QToolButton:disabled {{ color: {MUTED_TEXT}; }}
        QMenuBar, QMenu {{ background: {PANEL_BLACK}; color: {OFF_WHITE}; }}
        QMenuBar::item:selected, QMenu::item:selected {{
            background: #303846;
            color: {VOLTAGE_YELLOW};
        }}
        QStatusBar {{ color: {MUTED_TEXT}; background: {PANEL_BLACK}; }}
        QDialog {{ background: {NEAR_BLACK}; color: {OFF_WHITE}; }}
        QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QComboBox {{
            background: {PANEL_BLACK};
            color: {OFF_WHITE};
            border: 1px solid #4A5568;
            border-radius: 4px;
            padding: 5px;
            selection-background-color: {VOLTAGE_BLUE};
            selection-color: {OFF_WHITE};
        }}
        QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QComboBox:focus {{
            border-color: {VOLTAGE_YELLOW};
        }}
        QComboBox QAbstractItemView {{ background: {PANEL_BLACK}; color: {OFF_WHITE}; }}
        QPushButton {{ border: 1px solid #4A5568; border-radius: 4px; padding: 6px 10px; }}
        QPushButton:hover {{ border-color: {VOLTAGE_YELLOW}; }}
        """
    )
