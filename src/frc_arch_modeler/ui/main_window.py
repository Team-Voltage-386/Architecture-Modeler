"""Main application shell for the Phase 0 spike."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt, QThread
from PySide6.QtGui import (
    QCloseEvent,
    QIcon,
    QKeySequence,
    QPainter,
    QShortcut,
    QUndoCommand,
    QUndoStack,
)
from PySide6.QtWidgets import (
    QDialog,
    QDockWidget,
    QFileDialog,
    QGraphicsView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QToolBar,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from frc_arch_modeler.domain.model import ArchitectureProject, ComparisonState, SourceAnchor
from frc_arch_modeler.importers.base import ScanResult
from frc_arch_modeler.importers.java.scanner import JavaProjectScanner
from frc_arch_modeler.persistence.draft_store import DraftStore
from frc_arch_modeler.persistence.layout_store import LayoutStore
from frc_arch_modeler.services.change_request_export import ChangeRequestExportService
from frc_arch_modeler.services.export_service import ArchitectureExportService
from frc_arch_modeler.services.project_service import ProjectService
from frc_arch_modeler.services.reconcile_service import ReconciliationResult, ReconciliationService
from frc_arch_modeler.ui.architecture_scene import ArchitectureScene
from frc_arch_modeler.ui.details_panel import (
    DetailsPanel,
    EditDescriptionCommand,
    EditNameCommand,
    EditRequirementsCommand,
)
from frc_arch_modeler.ui.scan_worker import JavaScanWorker
from frc_arch_modeler.ui.source_viewer import SourceViewerDialog

DETAILS_DOCK_BREAKPOINT = 1280


class AddDesignEntityCommand(QUndoCommand):
    """Undoable insertion of one user-authored architecture entity."""

    def __init__(
        self, collection: list, entity: object, label: str, on_change: Callable[[], None]
    ) -> None:
        super().__init__(f"Add {label}")
        self.collection = collection
        self.entity = entity
        self.on_change = on_change

    def redo(self) -> None:
        if self.entity not in self.collection:
            self.collection.append(self.entity)
        self.on_change()

    def undo(self) -> None:
        if self.entity in self.collection:
            self.collection.remove(self.entity)
        self.on_change()


class MoveBlocksCommand(QUndoCommand):
    """Undoable canvas movement that leaves semantic design intent untouched."""

    def __init__(self, scene: ArchitectureScene, before, after, on_change) -> None:  # type: ignore[no-untyped-def]
        super().__init__("Move architecture blocks")
        self.scene = scene
        self.before = before
        self.after = after
        self.on_change = on_change

    def redo(self) -> None:
        self.scene.apply_block_positions(self.after)
        self.on_change()

    def undo(self) -> None:
        self.scene.apply_block_positions(self.before)
        self.on_change()


class RemoveDesignEntityCommand(QUndoCommand):
    """Undoable removal of an authored entity once its references are clear."""

    def __init__(
        self, collection: list, entity: object, label: str, on_change: Callable[[], None]
    ) -> None:
        super().__init__(f"Delete {label}")
        self.collection = collection
        self.entity = entity
        self.index = collection.index(entity)
        self.on_change = on_change

    def redo(self) -> None:
        if self.entity in self.collection:
            self.collection.remove(self.entity)
        self.on_change()

    def undo(self) -> None:
        if self.entity not in self.collection:
            self.collection.insert(self.index, self.entity)
        self.on_change()


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
        self.reconciliation: ReconciliationResult | None = None
        self._scan_thread: QThread | None = None
        self._scan_worker: JavaScanWorker | None = None
        self._pending_scan_root: Path | None = None
        self._pending_scan_action = "Connected"
        self._inventory_symbols: dict[str, object] = {}
        self.is_dirty = False
        self.project_service = ProjectService()
        self.export_service = ArchitectureExportService()
        self.change_request_export_service = ChangeRequestExportService()
        self.undo_stack = QUndoStack(self)
        self.scene = ArchitectureScene(self)
        self.scene.layout_changed.connect(self._layout_changed)
        self.scene.layout_move_completed.connect(self._record_layout_move)
        self.scene.block_double_clicked.connect(self._open_compact_details)
        self._build_toolbar()
        self._build_canvas()
        self._build_details_dock()
        self._build_inventory_dock()
        self._build_legend_dock()
        self.statusBar().showMessage("No robot project connected")

    def resizeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().resizeEvent(event)
        self._update_details_presentation()

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Architecture actions", self)
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        self.new_model_action = self.addAction("New Model", self._prompt_new_project)
        self.new_model_action.setShortcut(QKeySequence.StandardKey.New)
        self.open_model_action = self.addAction("Open Model", self._prompt_open_project)
        self.open_model_action.setShortcut(QKeySequence.StandardKey.Open)
        self.save_model_action = self.addAction("Save Model", self._prompt_save_project)
        self.save_model_action.setShortcut(QKeySequence.StandardKey.Save)
        self.save_model_action.setEnabled(False)
        self.connect_robot_action = self.addAction(
            "Connect Robot Project", self._prompt_connect_robot_project
        )
        self.refresh_code_action = self.addAction(
            "Refresh Code", self._refresh_robot_project_async
        )
        self.refresh_code_action.setShortcut(QKeySequence(Qt.Key.Key_F5))
        self.refresh_code_action.setEnabled(False)
        self.cancel_scan_action = self.addAction("Cancel Scan", self.cancel_scan)
        self.cancel_scan_action.setEnabled(False)
        self.compare_action = self.addAction("Compare Changes", self.compare_changes)
        self.compare_action.setEnabled(False)
        self.accept_matches_action = self.addAction("Accept Matches", self.accept_matches)
        self.accept_matches_action.setEnabled(False)
        self.bind_selected_action = self.addAction("Bind Selected", self.bind_selected)
        self.bind_selected_action.setEnabled(False)
        self.export_change_request_action = self.addAction(
            "Export AI Change Request", self._prompt_export_change_request
        )
        self.export_change_request_action.setEnabled(False)
        self.export_architecture_action = self.addAction(
            "Export Architecture", self._prompt_export_architecture
        )
        self.export_architecture_action.setShortcut(QKeySequence("Ctrl+E"))
        self.export_architecture_action.setEnabled(False)
        self.new_command_action = self.addAction("New Command", self._prompt_new_command)
        self.new_command_action.setEnabled(False)
        self.new_subsystem_action = self.addAction("New Subsystem", self._prompt_new_subsystem)
        self.new_subsystem_action.setEnabled(False)
        self.new_device_action = self.addAction("New Device", self._prompt_new_device)
        self.new_device_action.setEnabled(False)
        self.new_trigger_action = self.addAction("New Trigger", self._prompt_new_trigger)
        self.new_trigger_action.setEnabled(False)
        self.new_relationship_action = self.addAction(
            "New Relationship", self._prompt_new_relationship
        )
        self.new_relationship_action.setEnabled(False)
        self.show_command_forms_action = self.addAction("Show Command Forms")
        self.show_command_forms_action.setCheckable(True)
        self.show_command_forms_action.toggled.connect(self._toggle_command_forms)
        self.link_selected_action = self.addAction(
            "Link Selected (Requires)", self.link_selected_requirement
        )
        self.link_selected_action.setShortcut(QKeySequence("Ctrl+L"))
        self.link_selected_action.setEnabled(False)
        self.delete_selected_action = self.addAction(
            "Delete Selected", self._confirm_delete_selected
        )
        self.delete_selected_action.setShortcut(QKeySequence(Qt.Key.Key_Delete))
        self.delete_selected_action.setEnabled(False)
        self.search_field = QLineEdit(self)
        self.search_field.setObjectName("architectureSearch")
        self.search_field.setAccessibleName("Search architecture evidence")
        self.search_field.setPlaceholderText("Search architecture")
        self.search_field.setClearButtonEnabled(True)
        self.search_field.textChanged.connect(self.scene.filter_blocks)
        self.find_shortcut = QShortcut(QKeySequence.StandardKey.Find, self)
        self.find_shortcut.activated.connect(self.search_field.setFocus)
        self._status_filter_actions = {}
        for state, label in (
            (ComparisonState.MATCHED, "Matched"),
            (ComparisonState.MODIFIED, "Modified"),
            (ComparisonState.DESIGN_ONLY, "Design Only"),
            (ComparisonState.CODE_ONLY, "Code Only"),
            (ComparisonState.UNRESOLVED, "Unresolved"),
            (ComparisonState.AMBIGUOUS, "Ambiguous"),
            (ComparisonState.SCAN_ERROR, "Scan Error"),
        ):
            action = self.addAction(label)
            action.setCheckable(True)
            action.setChecked(True)
            action.toggled.connect(self._apply_status_filters)
            self._status_filter_actions[state] = action
        toolbar.addSeparator()
        self.undo_action = self.undo_stack.createUndoAction(self, "Undo")
        self.redo_action = self.undo_stack.createRedoAction(self, "Redo")
        self.auto_layout_action = self.addAction("Auto Layout", self.auto_layout)
        self.zoom_to_fit_action = self.addAction("Zoom to Fit", self.zoom_to_fit)
        self.minimize_action = self.addAction("Minimize Selected", self.minimize_selected)
        self.restore_action = self.addAction("Restore Selected", self.restore_selected)
        for action in (
            self.auto_layout_action,
            self.zoom_to_fit_action,
            self.minimize_action,
            self.restore_action,
        ):
            action.setEnabled(False)
        self._organize_toolbar(toolbar)

    def _organize_toolbar(self, toolbar: QToolBar) -> None:
        """Replace a wrapping action strip with compact, named action groups."""
        toolbar.clear()

        def add_group(label: str, actions: list) -> None:  # type: ignore[no-untyped-def]
            button = QToolButton(toolbar)
            button.setText(label)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            menu = QMenu(button)
            menu.addActions(actions)
            button.setMenu(menu)
            toolbar.addWidget(button)

        add_group("Model", [self.new_model_action, self.open_model_action, self.save_model_action])
        add_group(
            "Code",
            [
                self.connect_robot_action,
                self.refresh_code_action,
                self.cancel_scan_action,
                self.compare_action,
                self.accept_matches_action,
                self.bind_selected_action,
                self.show_command_forms_action,
                self.export_architecture_action,
                self.export_change_request_action,
            ],
        )
        add_group(
            "New",
            [
                self.new_command_action,
                self.new_subsystem_action,
                self.new_device_action,
                self.new_trigger_action,
                self.new_relationship_action,
                self.link_selected_action,
                self.delete_selected_action,
            ],
        )
        add_group("Filters", list(self._status_filter_actions.values()))
        add_group(
            "View",
            [
                self.auto_layout_action,
                self.zoom_to_fit_action,
                self.minimize_action,
                self.restore_action,
            ],
        )
        toolbar.addSeparator()
        icon_root = Path(__file__).resolve().parents[1] / "resources" / "icons"
        self.undo_action.setIcon(QIcon(str(icon_root / "undo.svg")))
        self.redo_action.setIcon(QIcon(str(icon_root / "redo.svg")))
        toolbar.addAction(self.undo_action)
        toolbar.addAction(self.redo_action)
        toolbar.addSeparator()
        toolbar.addWidget(self.search_field)

    def closeEvent(self, event: QCloseEvent) -> None:
        """Protect unsaved design and canvas edits when the main window closes."""
        if not self.is_dirty or not self.isVisible():
            if self._stop_background_scan_for_close():
                event.accept()
            else:
                event.ignore()
            return
        choice = QMessageBox.warning(
            self,
            "Unsaved architecture model",
            "Save changes before closing?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if choice == QMessageBox.StandardButton.Discard:
            if self._stop_background_scan_for_close():
                event.accept()
            else:
                event.ignore()
            return
        if choice == QMessageBox.StandardButton.Save:
            try:
                self._prompt_save_project()
            except OSError as error:
                QMessageBox.critical(self, "Could not save model", str(error))
            if not self.is_dirty:
                if self._stop_background_scan_for_close():
                    event.accept()
                else:
                    event.ignore()
                return
        event.ignore()

    def _stop_background_scan_for_close(self) -> bool:
        """Cancel a live worker before destroying its Qt owner during window shutdown."""
        if self._scan_thread is None:
            return True
        self.cancel_scan()
        if not self._scan_thread.wait(1500):
            self.statusBar().showMessage("Waiting for the code scan to cancel before closing.")
            return False
        self._scan_thread = None
        self._scan_worker = None
        self._pending_scan_root = None
        return True

    def _build_canvas(self) -> None:
        self.canvas = QGraphicsView(self.scene, self)
        self.canvas.setAccessibleName("Architecture canvas")
        self.canvas.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.canvas.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.canvas.setBackgroundBrush(Qt.GlobalColor.black)
        self.setCentralWidget(self.canvas)
        self.scene.selectionChanged.connect(self._update_selected_element)
        self.scene.selectionChanged.connect(self._update_bind_selected_action)
        self.scene.selectionChanged.connect(self._update_delete_selected_action)
        self.scene.selectionChanged.connect(self._update_link_selected_action)

    def set_project(self, project: ArchitectureProject | None) -> None:
        """Display a project with the deterministic initial canvas layout."""
        self.project = project
        self.scene.render_project(
            project, scan=self.last_scan, statuses=self._comparison_statuses()
        )
        self.details_panel.set_element(None)
        self._update_compact_details()
        self.new_command_action.setEnabled(project is not None)
        self.new_subsystem_action.setEnabled(project is not None)
        self.new_device_action.setEnabled(project is not None and bool(project.subsystems))
        self.new_trigger_action.setEnabled(project is not None and bool(project.commands))
        self.new_relationship_action.setEnabled(
            project is not None and len(project.commands) + len(project.subsystems) > 1
        )
        self.save_model_action.setEnabled(project is not None)
        self.auto_layout_action.setEnabled(project is not None)
        self.zoom_to_fit_action.setEnabled(project is not None)
        self.minimize_action.setEnabled(project is not None)
        self.restore_action.setEnabled(project is not None)
        self.export_architecture_action.setEnabled(project is not None)
        self.compare_action.setEnabled(project is not None and self.last_scan is not None)
        self.export_change_request_action.setEnabled(
            project is not None and self.last_scan is not None
        )
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
        draft = DraftStore(self.model_root).load()
        recovered = False
        if draft is not None and draft.to_dict() != project.to_dict():
            choice = QMessageBox.question(
                self,
                "Recover unsaved draft",
                "An autosaved draft differs from the saved model. Restore it?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if choice == QMessageBox.StandardButton.Yes:
                project = draft
                recovered = True
        self.set_project(project)
        layout_store = LayoutStore(self.model_root)
        self.scene.render_project(project, layout_store.load(), self.last_scan)
        self._restore_ui_preferences(layout_store.load_ui())
        if recovered:
            self.is_dirty = True
            self.statusBar().showMessage(f"Recovered unsaved draft: {project.name}")
        else:
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
        LayoutStore(self.model_root).save(self.scene.layout_state(), self._ui_preferences())
        DraftStore(self.model_root).discard()
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
        destination = self.export_service.export(
            export_root, self.project, self.last_scan, self.reconciliation
        )
        self.statusBar().showMessage(f"Exported architecture: {destination}")
        return destination

    def export_change_request(self, root: Path | None = None) -> Path:
        """Export the current design/code delta as an implementation-ready Markdown brief."""
        if self.project is None or self.last_scan is None:
            raise RuntimeError(
                "Create a model and connect a robot project before exporting changes."
            )
        export_root = Path(root) if root is not None else self.model_root
        if export_root is None:
            raise RuntimeError("Choose a folder for the change-request export.")
        comparison = self.reconciliation or ReconciliationService().reconcile(
            self.project, self.last_scan
        )
        destination = self.change_request_export_service.export(
            export_root, self.project, self.last_scan, comparison
        )
        self.statusBar().showMessage(f"Exported AI change request: {destination}")
        return destination

    def connect_robot_project(self, root: Path) -> ScanResult:
        """Scan a Java/WPILib project without altering the user-authored design."""
        root = Path(root)
        scan = JavaProjectScanner().scan(root)
        self._apply_scan(root, scan, "Connected")
        return scan

    def _apply_scan(self, root: Path, scan: ScanResult, action: str) -> None:
        """Apply a completed scan atomically to the visible, regenerable code layer."""
        self.robot_project_root = root
        self.last_scan = scan
        self.reconciliation = None
        self.refresh_code_action.setEnabled(True)
        self.compare_action.setEnabled(self.project is not None)
        self.export_change_request_action.setEnabled(self.project is not None)
        self._render_with_current_scan()
        self._show_scan_inventory()
        self._show_scan_status(action)

    def refresh_robot_project(self) -> ScanResult | None:
        """Refresh the current code-derived inventory while retaining design edits."""
        if self.robot_project_root is None:
            return None
        scan = JavaProjectScanner().scan(self.robot_project_root)
        self._apply_scan(self.robot_project_root, scan, "Refreshed")
        return scan

    def _refresh_robot_project_async(self) -> None:
        if self.robot_project_root is not None:
            self._start_scan(self.robot_project_root, "Refreshed")

    def _start_scan(self, root: Path, action: str) -> None:
        """Run a toolbar-initiated scan off the UI thread, preserving the old view on failure."""
        if self._scan_thread is not None:
            return
        self._pending_scan_root = Path(root)
        self._pending_scan_action = action
        thread = QThread(self)
        worker = JavaScanWorker(self._pending_scan_root)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.completed.connect(self._scan_completed)
        worker.failed.connect(self._scan_failed)
        worker.cancelled.connect(self._scan_cancelled)
        worker.progress.connect(self._scan_progress)
        self._scan_thread = thread
        self._scan_worker = worker
        self.connect_robot_action.setEnabled(False)
        self.refresh_code_action.setEnabled(False)
        self.cancel_scan_action.setEnabled(True)
        self.statusBar().showMessage(f"{action} Java project in background…")
        thread.start()

    def cancel_scan(self) -> None:
        if self._scan_worker is not None:
            self._scan_worker.request_cancel()
            self.statusBar().showMessage("Cancelling Java project scan…")

    def _scan_progress(self, completed: int, total: int) -> None:
        self.statusBar().showMessage(
            f"{self._pending_scan_action} Java project in background… {completed}/{total} files"
        )

    def _scan_completed(self, scan: ScanResult) -> None:
        assert self._pending_scan_root is not None
        self._apply_scan(self._pending_scan_root, scan, self._pending_scan_action)
        self._finish_background_scan()

    def _scan_failed(self, message: str) -> None:
        self.statusBar().showMessage(f"Code scan failed: {message}")
        self._finish_background_scan()

    def _scan_cancelled(self) -> None:
        self.statusBar().showMessage("Code scan cancelled; prior code view was retained.")
        self._finish_background_scan()

    def _finish_background_scan(self) -> None:
        if self._scan_thread is not None:
            self._scan_thread.quit()
            self._scan_thread.wait()
            self._scan_thread.deleteLater()
        if self._scan_worker is not None:
            self._scan_worker.deleteLater()
        self._scan_thread = None
        self._scan_worker = None
        self._pending_scan_root = None
        self.connect_robot_action.setEnabled(True)
        self.refresh_code_action.setEnabled(self.robot_project_root is not None)
        self.cancel_scan_action.setEnabled(False)

    def _show_scan_status(self, action: str) -> None:
        assert self.robot_project_root is not None
        assert self.last_scan is not None
        subsystem_count = len(self.last_scan.symbols_of_kind("subsystem"))
        command_count = len(self.last_scan.symbols_of_kind("command"))
        factory_count = len(self.last_scan.symbols_of_kind("command_factory"))
        form_count = len(self.last_scan.symbols_of_kind("command_composition"))
        trigger_count = len(self.last_scan.triggers)
        device_count = len(self.last_scan.devices)
        diagnostic_count = len(self.last_scan.diagnostics)
        self.statusBar().showMessage(
            f"{action} {self.robot_project_root.name}: {subsystem_count} subsystems, "
            f"{command_count} commands, {factory_count} factories, {form_count} forms, "
            f"{trigger_count} triggers, {device_count} devices, {diagnostic_count} warnings"
        )

    def _show_scan_inventory(self) -> None:
        assert self.last_scan is not None
        self.inventory_tree.clear()
        self._inventory_symbols = {}
        labels = {
            "subsystem": "Subsystems",
            "command": "Commands",
            "command_factory": "Command factories",
            "command_composition": "Command forms and groups",
            "command_registration": "Default and autonomous commands",
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
        if self.last_scan.triggers:
            trigger_group = QTreeWidgetItem(["Trigger bindings", ""])
            self.inventory_tree.addTopLevelItem(trigger_group)
            for index, trigger in enumerate(self.last_scan.triggers):
                key = f"trigger:{index}"
                item = QTreeWidgetItem(
                    [
                        f"{trigger.controller_expression} · {trigger.activation}",
                        f"{trigger.anchor.relative_path}:{trigger.anchor.start_line}",
                    ]
                )
                item.setData(0, Qt.ItemDataRole.UserRole, key)
                self._inventory_symbols[key] = trigger
                trigger_group.addChild(item)
        if self.last_scan.devices:
            device_group = QTreeWidgetItem(["Devices", ""])
            self.inventory_tree.addTopLevelItem(device_group)
            for index, device in enumerate(self.last_scan.devices):
                key = f"device:{index}"
                item = QTreeWidgetItem(
                    [
                        self._device_inventory_label(device),
                        f"{device.anchor.relative_path}:{device.anchor.start_line}",
                    ]
                )
                item.setData(0, Qt.ItemDataRole.UserRole, key)
                self._inventory_symbols[key] = device
                device_group.addChild(item)
        if self.last_scan.diagnostics:
            diagnostic_group = QTreeWidgetItem(["Scan diagnostics", ""])
            self.inventory_tree.addTopLevelItem(diagnostic_group)
            for diagnostic in self.last_scan.diagnostics:
                diagnostic_group.addChild(
                    QTreeWidgetItem([diagnostic.message, diagnostic.relative_path or ""])
                )
        self.inventory_tree.expandAll()

    @staticmethod
    def _device_inventory_label(device) -> str:  # type: ignore[no-untyped-def]
        resolved = (
            f" → {device.resolved_arguments}" if device.resolved_arguments is not None else ""
        )
        return f"{device.device_type} ({device.constructor_arguments}{resolved})"

    def _render_with_current_scan(self) -> None:
        self.scene.render_project(
            self.project,
            layout=self.scene.layout_state(),
            scan=self.last_scan,
            statuses=self._comparison_statuses(),
            code_only_symbols=self._code_only_symbols(),
        )

    def _toggle_command_forms(self, visible: bool) -> None:
        """Keep inline forms in the inventory unless the user explicitly expands the canvas."""
        self.scene.show_command_forms = visible
        self._render_with_current_scan()

    def compare_changes(self) -> ReconciliationResult | None:
        """Display a non-destructive design/code comparison on the canvas."""
        if self.project is None or self.last_scan is None:
            return None
        reconciliation_service = ReconciliationService()
        self.reconciliation = reconciliation_service.reconcile(self.project, self.last_scan)
        reconciliation_service.populate_scanned_fields(self.project, self.reconciliation)
        self._render_with_current_scan()
        self.accept_matches_action.setEnabled(bool(self.reconciliation.matches))
        matched = len(self.reconciliation.matches)
        design_only = sum(
            state.value == "design_only" for state in self.reconciliation.statuses.values()
        )
        self.statusBar().showMessage(f"Comparison: {matched} matched, {design_only} design-only")
        return self.reconciliation

    def accept_matches(self) -> int:
        """Persist the currently suggested unambiguous bindings after user confirmation."""
        if self.project is None or self.reconciliation is None:
            return 0
        accepted = ReconciliationService.accept_matches(self.project, self.reconciliation)
        if accepted:
            self._mark_dirty(f"Accepted {accepted} code binding(s)")
        self.accept_matches_action.setEnabled(False)
        return accepted

    def bind_selected(self) -> bool:
        """Persist an explicit design-to-code binding selected by the user."""
        if self.project is None or self.last_scan is None:
            return False
        blocks = self.scene.selected_blocks()
        if len(blocks) != 2:
            return False
        design_block = next((block for block in blocks if not block.imported), None)
        code_block = next((block for block in blocks if block.imported), None)
        if design_block is None or code_block is None or design_block.kind != code_block.kind:
            return False
        if not isinstance(code_block.source_anchor, SourceAnchor):
            return False
        element = next(
            (
                item
                for item in [*self.project.commands, *self.project.subsystems]
                if item.id == design_block.element_id
            ),
            None,
        )
        if element is None:
            return False
        element.code_binding = code_block.source_anchor
        code_name = code_block.title.toPlainText()
        reconciliation_service = ReconciliationService()
        self.reconciliation = reconciliation_service.reconcile(self.project, self.last_scan)
        reconciliation_service.populate_scanned_fields(self.project, self.reconciliation)
        self._render_with_current_scan()
        self._mark_dirty(f"Bound {element.name.effective} to {code_name}")
        return True

    def _comparison_statuses(self) -> dict:
        return self.reconciliation.statuses if self.reconciliation is not None else {}

    def _code_only_symbols(self) -> set[str]:
        if self.reconciliation is None:
            return set()
        return {symbol.anchor.qualified_symbol for symbol in self.reconciliation.code_only}

    def _apply_status_filters(self) -> None:
        self.scene.set_status_filter(
            {state for state, action in self._status_filter_actions.items() if action.isChecked()}
        )

    def _update_bind_selected_action(self) -> None:
        blocks = self.scene.selected_blocks()
        self.bind_selected_action.setEnabled(
            len(blocks) == 2
            and {block.imported for block in blocks} == {False, True}
            and blocks[0].kind == blocks[1].kind
            and self.project is not None
            and self.last_scan is not None
        )

    def _update_delete_selected_action(self) -> None:
        blocks = self.scene.selected_blocks()
        self.delete_selected_action.setEnabled(
            self.project is not None and len(blocks) == 1 and not blocks[0].imported
        )

    def _update_link_selected_action(self) -> None:
        """Enable the direct drafting shortcut for a command/subsystem pair."""
        blocks = self.scene.selected_blocks()
        self.link_selected_action.setEnabled(
            self.project is not None
            and len(blocks) == 2
            and not any(block.imported for block in blocks)
            and {block.kind for block in blocks} == {"command", "subsystem"}
        )

    def add_command(self, name: str) -> None:
        """Add a command and refresh its deterministic initial canvas position."""
        if self.project is None:
            raise RuntimeError("Create or open a model before adding a command.")
        command = self.project_service.add_command(self.project, name)
        self.project.commands.remove(command)
        self.undo_stack.push(
            AddDesignEntityCommand(
                self.project.commands, command, "command", self._refresh_after_edit
            )
        )

    def add_subsystem(self, name: str) -> None:
        """Add a subsystem and refresh its deterministic initial canvas position."""
        if self.project is None:
            raise RuntimeError("Create or open a model before adding a subsystem.")
        subsystem = self.project_service.add_subsystem(self.project, name)
        self.project.subsystems.remove(subsystem)
        self.undo_stack.push(
            AddDesignEntityCommand(
                self.project.subsystems, subsystem, "subsystem", self._refresh_after_edit
            )
        )

    def add_device(
        self, owner_subsystem_id, name: str, device_type: str, mode: str | None = None
    ) -> None:  # type: ignore[no-untyped-def]
        """Add a proposed hardware device and surface it on its subsystem block."""
        if self.project is None:
            raise RuntimeError("Create or open a model before adding a device.")
        device = self.project_service.add_device(
            self.project, owner_subsystem_id, name, device_type, mode
        )
        self.project.devices.remove(device)
        self.undo_stack.push(
            AddDesignEntityCommand(self.project.devices, device, "device", self._refresh_after_edit)
        )

    def add_trigger(
        self, command_id, expression: str, activation: str
    ) -> None:  # type: ignore[no-untyped-def]
        """Add a proposed trigger binding and surface it on its command block."""
        if self.project is None:
            raise RuntimeError("Create or open a model before adding a trigger.")
        trigger = self.project_service.add_trigger(self.project, command_id, expression, activation)
        self.project.triggers.remove(trigger)
        self.undo_stack.push(
            AddDesignEntityCommand(
                self.project.triggers, trigger, "trigger", self._refresh_after_edit
            )
        )

    def add_relationship(
        self, relationship_type: str, source_id, target_id
    ) -> None:  # type: ignore[no-untyped-def]
        """Add an authored relationship between visible command/subsystem blocks."""
        if self.project is None:
            raise RuntimeError("Create or open a model before adding a relationship.")
        relationship = self.project_service.add_relationship(
            self.project, relationship_type, source_id, target_id
        )
        self.project.relationships.remove(relationship)
        self.undo_stack.push(
            AddDesignEntityCommand(
                self.project.relationships, relationship, "relationship", self._refresh_after_edit
            )
        )

    def link_selected_requirement(self) -> bool:
        """Create the visible command-to-subsystem requirement selected on the canvas."""
        if self.project is None:
            return False
        blocks = self.scene.selected_blocks()
        if (
            len(blocks) != 2
            or any(block.imported for block in blocks)
            or {block.kind for block in blocks} != {"command", "subsystem"}
        ):
            return False
        command_block = next(block for block in blocks if block.kind == "command")
        subsystem_block = next(block for block in blocks if block.kind == "subsystem")
        command = next(
            (item for item in self.project.commands if item.id == command_block.element_id), None
        )
        if command is None or subsystem_block.element_id in command.requirement_ids:
            return False
        self.undo_stack.push(
            EditRequirementsCommand(
                command,
                [*command.requirement_ids, subsystem_block.element_id],
                self._requirements_changed,
            )
        )
        return True

    def _confirm_delete_selected(self) -> None:
        if not self.delete_selected():
            return

    def delete_selected(self) -> bool:
        """Delete one authored block only when no other design fact depends on it."""
        if self.project is None:
            return False
        blocks = self.scene.selected_blocks()
        if len(blocks) != 1 or blocks[0].imported:
            return False
        element_id = blocks[0].element_id
        element = next(
            (
                item
                for item in [*self.project.commands, *self.project.subsystems]
                if item.id == element_id
            ),
            None,
        )
        if element is None:
            return False
        dependencies = [
            *[
                "command requirement"
                for command in self.project.commands
                if element_id in command.requirement_ids
            ],
            *[
                "device"
                for device in self.project.devices
                if device.owner_subsystem_id == element_id
            ],
            *["trigger" for trigger in self.project.triggers if trigger.command_id == element_id],
            *[
                "relationship"
                for relationship in self.project.relationships
                if element_id in {relationship.source_id, relationship.target_id}
            ],
        ]
        if dependencies:
            QMessageBox.warning(
                self,
                "Cannot delete selected element",
                "Remove dependent " + ", ".join(sorted(set(dependencies))) + " entries first.",
            )
            return False
        collection = (
            self.project.commands if element in self.project.commands else self.project.subsystems
        )
        self.undo_stack.push(
            RemoveDesignEntityCommand(
                collection, element, type(element).__name__.lower(), self._refresh_after_edit
            )
        )
        return True

    def _refresh_after_edit(self) -> None:
        assert self.project is not None
        self.scene.render_project(self.project, scan=self.last_scan)
        self.new_device_action.setEnabled(bool(self.project.subsystems))
        self.new_trigger_action.setEnabled(bool(self.project.commands))
        self.new_relationship_action.setEnabled(
            len(self.project.commands) + len(self.project.subsystems) > 1
        )
        self._mark_dirty(f"Unsaved design model: {self.project.name}")

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
        if self.project is not None and self.model_root is not None:
            DraftStore(self.model_root).save(self.project)
        self.statusBar().showMessage(message)

    def _layout_changed(self) -> None:
        self._mark_dirty("Canvas layout updated")

    def _record_layout_move(self, before, after) -> None:  # type: ignore[no-untyped-def]
        """Place completed drags on the normal undo stack after Qt releases the mouse."""
        self.undo_stack.push(MoveBlocksCommand(self.scene, before, after, self._layout_changed))

    def _update_selected_element(self) -> None:
        selected = self.scene.selected_blocks()
        if len(selected) != 1:
            self.details_panel.set_element(None)
            self._update_compact_details()
            return
        imported_anchor = selected[0].source_anchor
        if isinstance(imported_anchor, SourceAnchor):
            conventional_command = (
                selected[0].kind == "command" and self._is_conventional_command(imported_anchor)
            )
            functional_command = self._functional_phase_expressions(imported_anchor)
            inline_flow = self._inline_command_flow(imported_anchor)
            self.details_panel.set_imported_fact(
                selected[0].title.toPlainText(),
                selected[0].kind,
                imported_anchor,
                self._imported_details(selected[0]),
                self._lifecycle_methods(imported_anchor)
                if conventional_command
                else ["initialize", "execute", "isFinished", "end"]
                if functional_command
                else None,
                self._lifecycle_anchors(imported_anchor) if conventional_command else None,
                conventional_command or bool(functional_command) or bool(inline_flow),
                inline_flow,
            )
            self._update_compact_details()
            return
        if self.project is None:
            self.details_panel.set_element(None)
            self._update_compact_details()
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
        self.details_panel.set_element(
            element,
            *self._matched_code_details(element.id) if element is not None else (),
            subsystem_options=self._subsystem_options(),
            design_context=self._design_structure(element.id) if element is not None else None,
        )
        self._update_compact_details()

    def _matched_code_details(
        self, element_id
    ) -> tuple[str | None, str | None, SourceAnchor | None]:  # type: ignore[no-untyped-def]
        if self.reconciliation is None:
            return (None, None, None)
        symbol = self.reconciliation.matches.get(element_id)
        if symbol is None:
            return (None, None, None)
        return (symbol.name, symbol.documentation, symbol.anchor)

    def _imported_details(self, block) -> str | None:  # type: ignore[no-untyped-def]
        """Augment imported facts with directly extracted architecture evidence."""
        details = block.code_summary
        if not isinstance(block.source_anchor, SourceAnchor) or self.last_scan is None:
            return details
        lines: list[str] = [details] if details else []
        qualified_symbol = block.source_anchor.qualified_symbol
        if block.kind == "subsystem":
            devices = [
                f"- {device.device_type}{f' [{device.mode}]' if device.mode else ''}: "
                f"{device.resolved_arguments or device.constructor_arguments}"
                for device in self.last_scan.devices
                if self._logical_device_owner(device.owner_symbol) == qualified_symbol
            ]
            if devices:
                lines.extend(["Devices:", *devices])
        if block.kind == "command":
            normalized_block_name = self._normalized(block.title.toPlainText())
            triggers = [
                f"- {trigger.controller_expression} · {trigger.activation} → "
                f"{trigger.command_expression}"
                for trigger in self.last_scan.triggers
                if normalized_block_name in self._normalized(trigger.command_expression)
            ]
            lifecycle = [
                symbol.name
                for symbol in self.last_scan.symbols_of_kind("lifecycle_method")
                if symbol.anchor.qualified_symbol.startswith(f"{qualified_symbol}#")
            ]
            if triggers:
                lines.extend(["Triggers:", *triggers])
            if lifecycle:
                lines.append(f"Lifecycle overrides: {', '.join(lifecycle)}")
            registrations = [
                "- "
                + (
                    "Default command"
                    if relationship.kind == "default_command"
                    else "Autonomous registration"
                )
                + f": {relationship.target_expression}"
                for relationship in self.last_scan.relationships
                if relationship.kind in {"default_command", "autonomous_registration"}
                and normalized_block_name in self._normalized(relationship.target_expression)
            ]
            if registrations:
                lines.extend(["Scheduler registrations:", *registrations])
        children = [
            relationship.target_expression
            for relationship in self.last_scan.relationships
            if relationship.kind == "composition_child"
            and relationship.source_symbol == qualified_symbol
        ]
        if children:
            lines.extend(["Composition children:", *(f"- {child}" for child in children)])
        decorators = [
            relationship.target_expression
            for relationship in self.last_scan.relationships
            if relationship.kind == "command_decorator"
            and relationship.source_symbol == qualified_symbol
        ]
        if decorators:
            lines.extend(["Decorators:", *(f"- {decorator}" for decorator in decorators)])
        functional_phases = [
            relationship.target_expression
            for relationship in self.last_scan.relationships
            if relationship.kind == "functional_phase"
            and relationship.source_symbol == qualified_symbol
        ]
        if functional_phases:
            lines.extend(
                ["Functional command phases:", *(f"- {phase}" for phase in functional_phases)]
            )
        return "\n\n".join(lines) or None

    def _lifecycle_methods(self, command_anchor: SourceAnchor) -> list[str]:
        """Return overrides for an imported command without inventing absent phases."""
        if self.last_scan is None:
            return []
        return [
            symbol.name
            for symbol in self.last_scan.symbols_of_kind("lifecycle_method")
            if symbol.anchor.qualified_symbol.startswith(f"{command_anchor.qualified_symbol}#")
        ]

    def _is_conventional_command(self, command_anchor: SourceAnchor) -> bool:
        """Only command subclasses have the conventional initialize/execute lifecycle."""
        return self.last_scan is not None and any(
            symbol.kind == "command"
            and symbol.anchor.qualified_symbol == command_anchor.qualified_symbol
            for symbol in self.last_scan.symbols
        )

    def _functional_phase_expressions(self, command_anchor: SourceAnchor) -> list[str]:
        """Identify a FunctionalCommand form without fabricating conventional source methods."""
        if self.last_scan is None:
            return []
        return [
            relationship.target_expression
            for relationship in self.last_scan.relationships
            if relationship.kind == "functional_phase"
            and relationship.source_symbol == command_anchor.qualified_symbol
        ]

    def _inline_command_flow(self, command_anchor: SourceAnchor) -> list[str] | None:
        """Describe the fixed scheduler behavior of supported inline WPILib factories."""
        if self.last_scan is None or not any(
            symbol.kind == "command_composition"
            and symbol.anchor.qualified_symbol == command_anchor.qualified_symbol
            for symbol in self.last_scan.symbols
        ):
            return None
        form = command_anchor.qualified_symbol.rsplit(".", 1)[-1].split("@", 1)[0]
        flows = {
            "runOnce": ["Start", "action", "Finish"],
            "run": ["Start", "execute", "Until interrupted", "end(interrupted)"],
            "runEnd": ["Start", "execute", "end(interrupted)"],
            "startEnd": ["Start", "execute", "end(interrupted)"],
        }
        return flows.get(form)

    def _lifecycle_anchors(self, command_anchor: SourceAnchor) -> dict[str, SourceAnchor]:
        if self.last_scan is None:
            return {}
        return {
            symbol.name: symbol.anchor
            for symbol in self.last_scan.symbols_of_kind("lifecycle_method")
            if symbol.anchor.qualified_symbol.startswith(f"{command_anchor.qualified_symbol}#")
        }

    def _design_structure(self, element_id) -> str | None:  # type: ignore[no-untyped-def]
        """Summarize authored devices, controls, and typed links for the details panel."""
        if self.project is None:
            return None
        lines: list[str] = []
        devices = [
            device for device in self.project.devices if device.owner_subsystem_id == element_id
        ]
        if devices:
            lines.append(
                "Devices: "
                + ", ".join(
                    f"{device.name.effective} ({device.device_type.effective})"
                    for device in devices
                )
            )
        triggers = [
            trigger for trigger in self.project.triggers if trigger.command_id == element_id
        ]
        if triggers:
            lines.append(
                "Triggers: "
                + ", ".join(
                    f"{trigger.expression.effective} · {trigger.activation.effective}"
                    for trigger in triggers
                )
            )
        links = [
            relationship.relationship_type.replace("_", " ")
            for relationship in self.project.relationships
            if element_id in {relationship.source_id, relationship.target_id}
        ]
        if links:
            lines.append("Relationships: " + ", ".join(links))
        return "\n".join(lines) or None

    @staticmethod
    def _normalized(value: str) -> str:
        return "".join(character for character in value.casefold() if character.isalnum())

    def _logical_device_owner(self, owner_symbol: str) -> str:
        """Use the same conservative IO-to-subsystem presentation mapping as the canvas."""
        if self.last_scan is None:
            return owner_symbol
        owner_type = owner_symbol.rsplit(".", 1)[-1]
        normalized_owner = self._normalized(owner_type)
        matches = [
            symbol.anchor.qualified_symbol
            for symbol in self.last_scan.symbols_of_kind("subsystem")
            if normalized_owner.startswith(self._normalized(symbol.name))
            and "io" in normalized_owner[len(self._normalized(symbol.name)) :]
        ]
        return matches[0] if len(matches) == 1 else owner_symbol

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

    def edit_selected_name(self, name: str | None) -> None:
        """Apply a selected element's proposed display name through the undo stack."""
        selected = self.scene.selected_blocks()
        if self.project is None or len(selected) != 1 or (name is not None and not name.strip()):
            return
        element = next(
            (
                item
                for item in [*self.project.commands, *self.project.subsystems]
                if item.id == selected[0].element_id
            ),
            None,
        )
        if element is None or element.name.design == name:
            return
        self.undo_stack.push(EditNameCommand(element, name, self._name_changed))

    def edit_selected_requirements(self, requirement_ids) -> None:  # type: ignore[no-untyped-def]
        """Apply selected command requirement IDs through the undo stack."""
        selected = self.scene.selected_blocks()
        if self.project is None or len(selected) != 1:
            return
        element = next(
            (item for item in self.project.commands if item.id == selected[0].element_id), None
        )
        if element is None:
            return
        valid_ids = {subsystem.id for subsystem in self.project.subsystems}
        normalized = list(dict.fromkeys(requirement_ids))
        if any(requirement_id not in valid_ids for requirement_id in normalized):
            return
        if element.requirement_ids != normalized:
            self.undo_stack.push(
                EditRequirementsCommand(element, normalized, self._requirements_changed)
            )

    def _name_changed(self) -> None:
        self._mark_dirty("Name updated")
        self._update_selected_element()

    def _requirements_changed(self) -> None:
        self._mark_dirty("Requirements updated")
        self._render_with_current_scan()

    def _description_changed(self) -> None:
        self._mark_dirty("Description updated")
        self._update_selected_element()

    def _prompt_new_project(self) -> None:
        name, accepted = QInputDialog.getText(self, "New model", "Model name:")
        if accepted and name.strip():
            self.new_project(name.strip())

    def _prompt_open_project(self) -> None:
        root = QFileDialog.getExistingDirectory(self, "Open architecture model")
        if root:
            try:
                self.open_project(Path(root))
            except ValueError as error:
                QMessageBox.critical(self, "Could not open model", str(error))

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

    def _prompt_export_change_request(self) -> None:
        root = self.model_root
        if root is None:
            selected_root = QFileDialog.getExistingDirectory(self, "Export AI change request")
            if not selected_root:
                return
            root = Path(selected_root)
        self.export_change_request(root)

    def _prompt_connect_robot_project(self) -> None:
        root = QFileDialog.getExistingDirectory(self, "Connect Java/WPILib robot project")
        if root:
            self._start_scan(Path(root), "Connected")

    def _prompt_new_command(self) -> None:
        self._prompt_element("New command", self.add_command)

    def _prompt_new_subsystem(self) -> None:
        self._prompt_element("New subsystem", self.add_subsystem)

    def _prompt_new_device(self) -> None:
        if self.project is None or not self.project.subsystems:
            return
        names = [subsystem.name.effective or "Unnamed" for subsystem in self.project.subsystems]
        owner_name, accepted = QInputDialog.getItem(
            self, "New device", "Subsystem:", names, 0, False
        )
        if not accepted:
            return
        owner = next(
            subsystem
            for subsystem in self.project.subsystems
            if subsystem.name.effective == owner_name
        )
        name, accepted = QInputDialog.getText(self, "New device", "Device name:")
        if not accepted or not name.strip():
            return
        device_type, accepted = QInputDialog.getText(self, "New device", "Device type:")
        if not accepted or not device_type.strip():
            return
        mode, accepted = QInputDialog.getItem(
            self, "New device", "Mode:", ["Unspecified", "REAL", "SIM", "REPLAY"], 0, False
        )
        if accepted:
            self.add_device(
                owner.id,
                name.strip(),
                device_type.strip(),
                None if mode == "Unspecified" else mode,
            )

    def _prompt_new_trigger(self) -> None:
        if self.project is None or not self.project.commands:
            return
        names = [command.name.effective or "Unnamed" for command in self.project.commands]
        command_name, accepted = QInputDialog.getItem(
            self, "New trigger", "Command:", names, 0, False
        )
        if not accepted:
            return
        command = next(
            command
            for command in self.project.commands
            if command.name.effective == command_name
        )
        expression, accepted = QInputDialog.getText(
            self, "New trigger", "Controller / trigger expression:"
        )
        if not accepted or not expression.strip():
            return
        activation, accepted = QInputDialog.getItem(
            self,
            "New trigger",
            "Activation:",
            ["onTrue", "onFalse", "whileTrue", "whileFalse", "toggleOnTrue", "toggleOnFalse"],
            0,
            False,
        )
        if accepted:
            self.add_trigger(command.id, expression.strip(), activation)

    def _prompt_new_relationship(self) -> None:
        if self.project is None:
            return
        elements = [*self.project.commands, *self.project.subsystems]
        if len(elements) < 2:
            return
        labels = [f"{type(element).__name__}: {element.name.effective}" for element in elements]
        source_label, accepted = QInputDialog.getItem(
            self, "New relationship", "Source:", labels, 0, False
        )
        if not accepted:
            return
        source = elements[labels.index(source_label)]
        target_options = [label for label in labels if label != source_label]
        target_label, accepted = QInputDialog.getItem(
            self, "New relationship", "Target:", target_options, 0, False
        )
        if not accepted:
            return
        target = elements[labels.index(target_label)]
        relationship_type, accepted = QInputDialog.getItem(
            self,
            "New relationship",
            "Type:",
            ["calls", "contains", "triggers", "owns_device"],
            0,
            False,
        )
        if accepted:
            self.add_relationship(relationship_type, source.id, target.id)

    def _prompt_element(self, title: str, create_element: Callable[[str], None]) -> None:
        name, accepted = QInputDialog.getText(self, title, "Name:")
        if accepted and name.strip():
            create_element(name.strip())

    def _build_details_dock(self) -> None:
        dock = QDockWidget("Details", self)
        dock.setObjectName("detailsDock")
        self.details_dock = dock
        self.details_panel = DetailsPanel(
            self.edit_selected_description,
            self.edit_selected_name,
            self.edit_selected_requirements,
            self._open_source_anchor,
        )
        dock.setWidget(self.details_panel)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
        self.compact_details_dialog: QDialog | None = None
        self.compact_details_panel: DetailsPanel | None = None

    def _update_details_presentation(self) -> None:
        """Use a dock on wide screens and reserve a sheet on laptop-width windows."""
        self.details_dock.setVisible(self.width() >= DETAILS_DOCK_BREAKPOINT)

    def _ui_preferences(self) -> dict[str, int]:
        """Persist bounded presentation values separately from semantic design data."""
        return {
            "windowWidth": self.width(),
            "windowHeight": self.height(),
            "detailsWidth": self.details_dock.width(),
        }

    def _restore_ui_preferences(self, preferences: dict[str, object]) -> None:
        """Restore only reasonable dimensions so changed monitor setups remain usable."""
        width = preferences.get("windowWidth")
        height = preferences.get("windowHeight")
        if isinstance(width, int) and isinstance(height, int):
            self.resize(min(max(width, 800), 2560), min(max(height, 600), 1600))
        details_width = preferences.get("detailsWidth")
        if isinstance(details_width, int) and 180 <= details_width <= 900:
            self.resizeDocks(
                [self.details_dock], [details_width], Qt.Orientation.Horizontal
            )
        self._update_details_presentation()

    def _open_compact_details(self) -> None:
        if self.width() >= DETAILS_DOCK_BREAKPOINT or len(self.scene.selected_blocks()) != 1:
            return
        if self.compact_details_dialog is None:
            dialog = QDialog(self)
            dialog.setObjectName("compactDetailsDialog")
            dialog.setWindowTitle("Details")
            dialog.setModal(False)
            dialog.resize(440, 520)
            panel = DetailsPanel(
                self.edit_selected_description,
                self.edit_selected_name,
                self.edit_selected_requirements,
                self._open_source_anchor,
            )
            layout = QVBoxLayout(dialog)
            layout.addWidget(panel)
            self.compact_details_dialog = dialog
            self.compact_details_panel = panel
        self._update_compact_details()
        self.compact_details_dialog.show()
        self.compact_details_dialog.raise_()

    def _update_compact_details(self) -> None:
        """Mirror selection in a visible compact sheet without changing model state."""
        if self.compact_details_panel is None:
            return
        selected = self.scene.selected_blocks()
        if len(selected) != 1:
            self.compact_details_panel.set_element(None)
            return
        block = selected[0]
        if isinstance(block.source_anchor, SourceAnchor):
            conventional_command = (
                block.kind == "command" and self._is_conventional_command(block.source_anchor)
            )
            self.compact_details_panel.set_imported_fact(
                block.title.toPlainText(),
                block.kind,
                block.source_anchor,
                self._imported_details(block),
                self._lifecycle_methods(block.source_anchor) if conventional_command else None,
                self._lifecycle_anchors(block.source_anchor) if conventional_command else None,
                conventional_command,
            )
            return
        if self.project is None:
            self.compact_details_panel.set_element(None)
            return
        element = next(
            (
                item
                for item in [*self.project.commands, *self.project.subsystems]
                if item.id == block.element_id
            ),
            None,
        )
        self.compact_details_panel.set_element(
            element,
            *self._matched_code_details(element.id) if element is not None else (),
            subsystem_options=self._subsystem_options(),
            design_context=self._design_structure(element.id) if element is not None else None,
        )

    def _subsystem_options(self) -> list[tuple]:  # type: ignore[type-arg]
        if self.project is None:
            return []
        return [
            (subsystem.id, subsystem.name.effective or "Unnamed")
            for subsystem in self.project.subsystems
        ]

    def _build_inventory_dock(self) -> None:
        dock = QDockWidget("Code Inventory", self)
        dock.setObjectName("codeInventoryDock")
        self.inventory_tree = QTreeWidget(dock)
        self.inventory_tree.setObjectName("codeInventoryTree")
        self.inventory_tree.setHeaderLabels(["Symbol", "Source"])
        self.inventory_tree.itemDoubleClicked.connect(self._open_inventory_source)
        dock.setWidget(self.inventory_tree)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)

    def _build_legend_dock(self) -> None:
        dock = QDockWidget("Legend", self)
        dock.setObjectName("legendDock")
        legend = QLabel(
            "Command: yellow\nSubsystem: blue\n"
            "Solid: design intent\nDotted: imported code\nGreen: matched design/code",
            dock,
        )
        legend.setWordWrap(True)
        dock.setWidget(legend)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)

    def _open_inventory_source(self, item: QTreeWidgetItem, column: int) -> None:
        symbol_name = item.data(0, Qt.ItemDataRole.UserRole)
        symbol = self._inventory_symbols.get(symbol_name)
        if symbol is None or self.robot_project_root is None:
            return
        self._open_source_anchor(symbol.anchor)

    def _open_source_anchor(self, anchor: SourceAnchor) -> None:
        """Open portable source evidence when a robot project is currently connected."""
        if self.robot_project_root is None:
            return
        dialog = SourceViewerDialog(self.robot_project_root, anchor, self)
        dialog.open()
