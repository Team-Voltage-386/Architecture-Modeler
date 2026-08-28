"""Main application shell for the Phase 0 spike."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import (
    QDockWidget,
    QGraphicsView,
    QLabel,
    QMainWindow,
    QToolBar,
)

from frc_arch_modeler.domain.model import ArchitectureProject
from frc_arch_modeler.ui.architecture_scene import ArchitectureScene


class MainWindow(QMainWindow):
    """Initial shell that reserves the plan's primary UI regions."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("FRC Architecture Modeler")
        self.resize(1280, 800)
        self.scene = ArchitectureScene(self)
        self._build_toolbar()
        self._build_canvas()
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

    def _build_canvas(self) -> None:
        canvas = QGraphicsView(self.scene, self)
        canvas.setRenderHint(QPainter.RenderHint.Antialiasing)
        canvas.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        canvas.setBackgroundBrush(Qt.GlobalColor.black)
        self.setCentralWidget(canvas)

    def set_project(self, project: ArchitectureProject | None) -> None:
        """Display a project with the deterministic initial canvas layout."""
        self.scene.render_project(project)
        if project is None:
            self.statusBar().showMessage("No robot project connected")
        else:
            self.statusBar().showMessage(f"Design model: {project.name}")

    def _build_details_dock(self) -> None:
        dock = QDockWidget("Details", self)
        dock.setObjectName("detailsDock")
        dock.setWidget(QLabel("Select a command or subsystem to inspect its details.", dock))
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
