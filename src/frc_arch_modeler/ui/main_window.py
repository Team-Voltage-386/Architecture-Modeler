"""Main application shell for the Phase 0 spike."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QUndoStack
from PySide6.QtWidgets import (
    QDockWidget,
    QFileDialog,
    QGraphicsView,
    QInputDialog,
    QMainWindow,
    QToolBar,
    QTreeWidget,
    QTreeWidgetItem,
)

from frc_arch_modeler.domain.model import ArchitectureProject
from frc_arch_modeler.importers.base import ScanResult
from frc_arch_modeler.importers.java.scanner import JavaProjectScanner
from frc_arch_modeler.persistence.layout_store import LayoutStore
from frc_arch_modeler.services.export_service import ArchitectureExportService
from frc_arch_modeler.services.project_service import ProjectService
from frc_arch_modeler.ui.architecture_scene import ArchitectureScene
from frc_arch_modeler.ui.details_panel import DetailsPanel, EditDescriptionCommand
from frc_arch_modeler.ui.source_viewer import SourceViewerDialog


class MainWindow(QMainWindow):
    """Initial shell that reserves the plan's primary UI regions."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("FRC Architecture Modeler")
        self.resize(1280, 800)
        self.project: ArchitectureProject | None = None
        self.model_root: Path | None = None
        self.robot_project_root: Path | None = None
        self.last_scan: ScanResult | None = None
        self._inventory_symbols: dict[str, object] = {}
        self.is_dirty = False
        self.project_service = ProjectService()
        self.export_service = ArchitectureExportService()
        self.undo_stack = QUndoStack(self)
        self.scene = ArchitectureScene(self)
        self.scene.layout_changed.connect(self._layout_changed)
        self._build_toolbar()
        self._build_canvas()
        self._build_details_dock()
        self._build_inventory_dock()
        self.statusBar().showMessage("No robot project connected")

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Architecture actions", self)
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        self.new_model_action = toolbar.addAction("New Model", self._prompt_new_project)
        self.open_model_action = toolbar.addAction("Open Model", self._prompt_open_project)
        self.save_model_action = toolbar.addAction("Save Model", self._prompt_save_project)
        self.save_model_action.setEnabled(False)
        self.connect_robot_action = toolbar.addAction(
            "Connect Robot Project", self._prompt_connect_robot_project
        )
        self.refresh_code_action = toolbar.addAction("Refresh Code", self.refresh_robot_project)
        self.refresh_code_action.setEnabled(False)
        for label in ("Compare Changes", "Export AI Change Request"):
            action = toolbar.addAction(label)
            action.setEnabled(False)
        self.export_architecture_action = toolbar.addAction(
            "Export Architecture", self._prompt_export_architecture
        )
        self.export_architecture_action.setEnabled(False)
        self.new_command_action = toolbar.addAction("New Command", self._prompt_new_command)
        self.new_command_action.setEnabled(False)
        self.new_subsystem_action = toolbar.addAction("New Subsystem", self._prompt_new_subsystem)
        self.new_subsystem_action.setEnabled(False)
        toolbar.addSeparator()
        self.undo_action = self.undo_stack.createUndoAction(self, "Undo")
        self.redo_action = self.undo_stack.createRedoAction(self, "Redo")
        toolbar.addAction(self.undo_action)
        toolbar.addAction(self.redo_action)
        toolbar.addSeparator()
        self.auto_layout_action = toolbar.addAction("Auto Layout", self.auto_layout)
        self.zoom_to_fit_action = toolbar.addAction("Zoom to Fit", self.zoom_to_fit)
        self.minimize_action = toolbar.addAction("Minimize Selected", self.minimize_selected)
        self.restore_action = toolbar.addAction("Restore Selected", self.restore_selected)
        for action in (
            self.auto_layout_action,
            self.zoom_to_fit_action,
            self.minimize_action,
            self.restore_action,
        ):
            action.setEnabled(False)

    def _build_canvas(self) -> None:
        self.canvas = QGraphicsView(self.scene, self)
        self.canvas.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.canvas.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.canvas.setBackgroundBrush(Qt.GlobalColor.black)
        self.setCentralWidget(self.canvas)
        self.scene.selectionChanged.connect(self._update_selected_element)

    def set_project(self, project: ArchitectureProject | None) -> None:
        """Display a project with the deterministic initial canvas layout."""
        self.project = project
        self.scene.render_project(project, scan=self.last_scan)
        self.details_panel.set_element(None)
        self.new_command_action.setEnabled(project is not None)
        self.new_subsystem_action.setEnabled(project is not None)
        self.save_model_action.setEnabled(project is not None)
        self.auto_layout_action.setEnabled(project is not None)
        self.zoom_to_fit_action.setEnabled(project is not None)
        self.minimize_action.setEnabled(project is not None)
        self.restore_action.setEnabled(project is not None)
        self.export_architecture_action.setEnabled(project is not None)
        if project is None:
            self.is_dirty = False
            self.statusBar().showMessage("No robot project connected")
        else:
            self.is_dirty = False
            self.undo_stack.clear()
            self.statusBar().showMessage(f"Design model: {project.name}")

    def new_project(self, name: str) -> ArchitectureProject:
        """Create and display an unsaved design-only project."""
        project = self.project_service.create(name)
        self.model_root = None
        self.set_project(project)
        self.is_dirty = True
        self.statusBar().showMessage(f"Unsaved design model: {project.name}")
        return project

    def open_project(self, root: Path) -> ArchitectureProject:
        """Load a saved model sidecar directory into the canvas."""
        project = self.project_service.open(root)
        self.model_root = Path(root)
        self.set_project(project)
        self.scene.render_project(project, LayoutStore(self.model_root).load(), self.last_scan)
        self.statusBar().showMessage(f"Opened design model: {project.name}")
        return project

    def save_project(self, root: Path | None = None) -> Path:
        """Persist the current design model and clear its dirty state."""
        if self.project is None:
            raise RuntimeError("Create or open a model before saving.")
        if root is not None:
            self.model_root = Path(root)
        if self.model_root is None:
            raise RuntimeError("Choose a folder for the model before saving.")
        saved_path = self.project_service.save(self.model_root, self.project)
        LayoutStore(self.model_root).save(self.scene.layout_state())
        self.is_dirty = False
        self.undo_stack.setClean()
        self.statusBar().showMessage(f"Saved design model: {saved_path}")
        return saved_path

    def export_architecture(self, root: Path | None = None) -> Path:
        """Write a deterministic Architecture Markdown document for the current design."""
        if self.project is None:
            raise RuntimeError("Create or open a model before exporting.")
        export_root = Path(root) if root is not None else self.model_root
        if export_root is None:
            raise RuntimeError("Choose a folder for the architecture export.")
        destination = self.export_service.export(export_root, self.project)
        self.statusBar().showMessage(f"Exported architecture: {destination}")
        return destination

    def connect_robot_project(self, root: Path) -> ScanResult:
        """Scan a Java/WPILib project without altering the user-authored design."""
        self.robot_project_root = Path(root)
        self.last_scan = JavaProjectScanner().scan(self.robot_project_root)
        self.refresh_code_action.setEnabled(True)
        self._render_with_current_scan()
        self._show_scan_inventory()
        self._show_scan_status("Connected")
        return self.last_scan

    def refresh_robot_project(self) -> ScanResult | None:
        """Refresh the current code-derived inventory while retaining design edits."""
        if self.robot_project_root is None:
            return None
        self.last_scan = JavaProjectScanner().scan(self.robot_project_root)
        self._render_with_current_scan()
        self._show_scan_inventory()
        self._show_scan_status("Refreshed")
        return self.last_scan

    def _show_scan_status(self, action: str) -> None:
        assert self.robot_project_root is not None
        assert self.last_scan is not None
        subsystem_count = len(self.last_scan.symbols_of_kind("subsystem"))
        command_count = len(self.last_scan.symbols_of_kind("command"))
        factory_count = len(self.last_scan.symbols_of_kind("command_factory"))
        diagnostic_count = len(self.last_scan.diagnostics)
        self.statusBar().showMessage(
            f"{action} {self.robot_project_root.name}: {subsystem_count} subsystems, "
            f"{command_count} commands, {factory_count} factories, {diagnostic_count} warnings"
        )

    def _show_scan_inventory(self) -> None:
        assert self.last_scan is not None
        self.inventory_tree.clear()
        self._inventory_symbols = {}
        labels = {
            "subsystem": "Subsystems",
            "command": "Commands",
            "command_factory": "Command factories",
            "lifecycle_method": "Lifecycle methods",
        }
        groups: dict[str, QTreeWidgetItem] = {}
        for kind, label in labels.items():
            symbols = self.last_scan.symbols_of_kind(kind)
            if symbols:
                group = QTreeWidgetItem([label, ""])
                self.inventory_tree.addTopLevelItem(group)
                groups[kind] = group
        for symbol in self.last_scan.symbols:
            group = groups.get(symbol.kind)
            if group is not None:
                item = QTreeWidgetItem(
                    [symbol.name, f"{symbol.anchor.relative_path}:{symbol.anchor.start_line}"]
                )
                item.setData(0, Qt.ItemDataRole.UserRole, symbol.anchor.qualified_symbol)
                self._inventory_symbols[symbol.anchor.qualified_symbol] = symbol
                group.addChild(item)
        self.inventory_tree.expandAll()

    def _render_with_current_scan(self) -> None:
        self.scene.render_project(
            self.project, layout=self.scene.layout_state(), scan=self.last_scan
        )

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
        self.scene.render_project(self.project, scan=self.last_scan)
        self.is_dirty = True
        self.statusBar().showMessage(f"Unsaved design model: {self.project.name}")

    def auto_layout(self) -> None:
        """Restore the deterministic layout without changing design intent."""
        if self.project is None:
            return
        self.scene.render_project(self.project, scan=self.last_scan)
        self._mark_dirty("Auto-layout applied")

    def zoom_to_fit(self) -> None:
        """Fit the current design into the visible canvas without changing it."""
        if self.project is not None and not self.scene.sceneRect().isEmpty():
            self.canvas.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def minimize_selected(self) -> None:
        if self.scene.set_selected_minimized(True):
            self._mark_dirty("Selected items minimized")

    def restore_selected(self) -> None:
        if self.scene.set_selected_minimized(False):
            self._mark_dirty("Selected items restored")

    def _mark_dirty(self, message: str) -> None:
        self.is_dirty = True
        self.statusBar().showMessage(message)

    def _layout_changed(self) -> None:
        self._mark_dirty("Canvas layout updated")

    def _update_selected_element(self) -> None:
        if self.project is None:
            self.details_panel.set_element(None)
            return
        selected = self.scene.selected_blocks()
        if len(selected) != 1:
            self.details_panel.set_element(None)
            return
        element_id = selected[0].element_id
        element = next(
            (
                item
                for item in [*self.project.commands, *self.project.subsystems]
                if item.id == element_id
            ),
            None,
        )
        self.details_panel.set_element(element)

    def edit_selected_description(self, description: str | None) -> None:
        """Apply a selected element's design description through the undo stack."""
        selected = self.scene.selected_blocks()
        if self.project is None or len(selected) != 1:
            return
        element_id = selected[0].element_id
        element = next(
            (
                item
                for item in [*self.project.commands, *self.project.subsystems]
                if item.id == element_id
            ),
            None,
        )
        if element is None or element.description.design == description:
            return
        self.undo_stack.push(
            EditDescriptionCommand(element, description, self._description_changed)
        )

    def _description_changed(self) -> None:
        self._mark_dirty("Description updated")
        self.details_panel.refresh()

    def _prompt_new_project(self) -> None:
        name, accepted = QInputDialog.getText(self, "New model", "Model name:")
        if accepted and name.strip():
            self.new_project(name.strip())

    def _prompt_open_project(self) -> None:
        root = QFileDialog.getExistingDirectory(self, "Open architecture model")
        if root:
            self.open_project(Path(root))

    def _prompt_save_project(self) -> None:
        if self.model_root is None:
            root = QFileDialog.getExistingDirectory(self, "Save architecture model")
            if not root:
                return
            self.save_project(Path(root))
        else:
            self.save_project()

    def _prompt_export_architecture(self) -> None:
        root = self.model_root
        if root is None:
            selected_root = QFileDialog.getExistingDirectory(self, "Export architecture")
            if not selected_root:
                return
            root = Path(selected_root)
        self.export_architecture(root)

    def _prompt_connect_robot_project(self) -> None:
        root = QFileDialog.getExistingDirectory(self, "Connect Java/WPILib robot project")
        if root:
            self.connect_robot_project(Path(root))

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
        self.details_panel = DetailsPanel(self.edit_selected_description)
        dock.setWidget(self.details_panel)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)

    def _build_inventory_dock(self) -> None:
        dock = QDockWidget("Code Inventory", self)
        dock.setObjectName("codeInventoryDock")
        self.inventory_tree = QTreeWidget(dock)
        self.inventory_tree.setObjectName("codeInventoryTree")
        self.inventory_tree.setHeaderLabels(["Symbol", "Source"])
        self.inventory_tree.itemDoubleClicked.connect(self._open_inventory_source)
        dock.setWidget(self.inventory_tree)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)

    def _open_inventory_source(self, item: QTreeWidgetItem, column: int) -> None:
        symbol_name = item.data(0, Qt.ItemDataRole.UserRole)
        symbol = self._inventory_symbols.get(symbol_name)
        if symbol is None or self.robot_project_root is None:
            return
        dialog = SourceViewerDialog(self.robot_project_root, symbol.anchor, self)
        dialog.open()
