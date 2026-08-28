"""Application entry point."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from frc_arch_modeler.ui.main_window import MainWindow
from frc_arch_modeler.ui.theme import apply_voltage_theme


def create_application(argv: list[str] | None = None) -> QApplication:
    """Create the Qt application with its shared visual theme."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(argv if argv is not None else sys.argv)
    assert isinstance(app, QApplication)
    app.setApplicationName("FRC Architecture Modeler")
    app.setOrganizationName("FRC Architecture Modeler")
    apply_voltage_theme(app)
    return app


def main(argv: list[str] | None = None) -> int:
    """Start the desktop application."""
    app = create_application(argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
