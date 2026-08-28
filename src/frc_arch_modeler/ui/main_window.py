"""Main application shell for the Phase 0 spike."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDockWidget,
    QLabel,
    QMainWindow,
    QToolBar,
    QVBoxLayout,
    QWidget,
)


class MainWindow(QMainWindow):
    """Initial shell that reserves the plan's primary UI regions."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("FRC Architecture Modeler")
        self.resize(1280, 800)
        self._build_toolbar()
        self._build_central_placeholder()
        self._build_details_dock()
        self.statusBar().showMessage("No robot project connected")

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Architecture actions", self)
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        for label in (
            "Open Model",
            "Connect Robot Project",
            "Refresh Code",
            "New Command",
            "New Subsystem",
            "Compare Changes",
            "Export Architecture",
            "Export AI Change Request",
        ):
            action = toolbar.addAction(label)
            action.setEnabled(False)

    def _build_central_placeholder(self) -> None:
        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title = QLabel("Architecture canvas", central)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 24px; font-weight: 600;")
        subtitle = QLabel(
            "Create or open a model to begin designing your robot architecture.", central
        )
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        self.setCentralWidget(central)

    def _build_details_dock(self) -> None:
        dock = QDockWidget("Details", self)
        dock.setObjectName("detailsDock")
        dock.setWidget(QLabel("Select a command or subsystem to inspect its details.", dock))
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
