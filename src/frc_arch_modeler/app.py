"""Application entry point."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from frc_arch_modeler.ui.main_window import MainWindow
from frc_arch_modeler.ui.theme import apply_voltage_theme

_ASSETS_DIR = Path(__file__).resolve().parent.parent.parent / "assets"
_ICON_PATH = _ASSETS_DIR / "ArchitectureModelLogo.ico"


def _app_icon() -> QIcon:
    """Load the application icon, bundled at the given path in a frozen build."""
    if getattr(sys, "frozen", False):
        base = Path(sys._MEIPASS)  # type: ignore[attr-defined]
        icon_path = base / "assets" / "ArchitectureModelLogo.ico"
    else:
        icon_path = _ICON_PATH
    return QIcon(str(icon_path))


def create_application(argv: list[str] | None = None) -> QApplication:
    """Create the Qt application with its shared visual theme."""
    if sys.platform == "win32":
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "FRCArchitectureModeler.App"
        )
    app = QApplication.instance()
    if app is None:
        app = QApplication(argv if argv is not None else sys.argv)
    assert isinstance(app, QApplication)
    app.setApplicationName("FRC Architecture Modeler")
    app.setOrganizationName("FRC Architecture Modeler")
    app.setWindowIcon(_app_icon())
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
