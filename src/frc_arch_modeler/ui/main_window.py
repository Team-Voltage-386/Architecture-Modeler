"""Main application shell for the Phase 0 spike."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import (
    QDockWidget,
    QGraphicsView,
    QInputDialog,
    QLabel,
    QMainWindow,
    QToolBar,
)

from frc_arch_modeler.domain.model import ArchitectureProject
from frc_arch_modeler.services.project_service import ProjectService
from frc_arch_modeler.ui.architecture_scene import ArchitectureScene


class MainWindow(QMainWindow):
    """Initial shell that reserves the plan's primary UI regions."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("FRC Architecture Modeler")
        self.resize(1280, 800)
        self.project: ArchitectureProject | None = None
        self.is_dirty = False
        self.project_service = ProjectService()
        self.scene = ArchitectureScene(self)
        self._build_toolbar()
        self._build_canvas()
        self._build_details_dock()
        self.statusBar().showMessage("No robot project connected")

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Architecture actions", self)
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        self.new_model_action = toolbar.addAction("New Model", self._prompt_new_project)
        self.open_model_action = toolbar.addAction("Open Model")
        self.open_model_action.setEnabled(False)
        for label in (
            "Connect Robot Project",
            "Refresh Code",
            "Compare Changes",
            "Export Architecture",
            "Export AI Change Request",
        ):
            action = toolbar.addAction(label)
            action.setEnabled(False)
        self.new_command_action = toolbar.addAction("New Command", self._prompt_new_command)
        self.new_command_action.setEnabled(False)
        self.new_subsystem_action = toolbar.addAction("New Subsystem", self._prompt_new_subsystem)
        self.new_subsystem_action.setEnabled(False)

    def _build_canvas(self) -> None:
        canvas = QGraphicsView(self.scene, self)
        canvas.setRenderHint(QPainter.RenderHint.Antialiasing)
        canvas.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        canvas.setBackgroundBrush(Qt.GlobalColor.black)
        self.setCentralWidget(canvas)

    def set_project(self, project: ArchitectureProject | None) -> None:
        """Display a project with the deterministic initial canvas layout."""
        self.project = project
        self.scene.render_project(project)
        self.new_command_action.setEnabled(project is not None)
        self.new_subsystem_action.setEnabled(project is not None)
        if project is None:
            self.is_dirty = False
            self.statusBar().showMessage("No robot project connected")
        else:
            self.is_dirty = False
            self.statusBar().showMessage(f"Design model: {project.name}")

    def new_project(self, name: str) -> ArchitectureProject:
        """Create and display an unsaved design-only project."""
        project = self.project_service.create(name)
        self.set_project(project)
        self.is_dirty = True
        self.statusBar().showMessage(f"Unsaved design model: {project.name}")
        return project

    def add_command(self, name: str) -> None:
        """Add a command and refresh its deterministic initial canvas position."""
        if self.project is None:
            raise RuntimeError("Create or open a model before adding a command.")
        self.project_service.add_command(self.project, name)
        self._refresh_after_edit()

    def add_subsystem(self, name: str) -> None:
        """Add a subsystem and refresh its deterministic initial canvas position."""
        if self.project is None:
            raise RuntimeError("Create or open a model before adding a subsystem.")
        self.project_service.add_subsystem(self.project, name)
        self._refresh_after_edit()

    def _refresh_after_edit(self) -> None:
        assert self.project is not None
        self.scene.render_project(self.project)
        self.is_dirty = True
        self.statusBar().showMessage(f"Unsaved design model: {self.project.name}")

    def _prompt_new_project(self) -> None:
        name, accepted = QInputDialog.getText(self, "New model", "Model name:")
        if accepted and name.strip():
            self.new_project(name.strip())

    def _prompt_new_command(self) -> None:
        self._prompt_element("New command", self.add_command)

    def _prompt_new_subsystem(self) -> None:
        self._prompt_element("New subsystem", self.add_subsystem)

    def _prompt_element(self, title: str, create_element: Callable[[str], None]) -> None:
        name, accepted = QInputDialog.getText(self, title, "Name:")
        if accepted and name.strip():
            create_element(name.strip())

    def _build_details_dock(self) -> None:
        dock = QDockWidget("Details", self)
        dock.setObjectName("detailsDock")
        dock.setWidget(QLabel("Select a command or subsystem to inspect its details.", dock))
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
