"""Composition root for the main application window.

MainWindow owns the widgets, the undo stack and the shared model state, and hands
every behavior to a controller in `controllers/`. The delegating methods below are
the single call path between those controllers, so a controller reaches a sibling
through the window rather than holding a reference to it.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QThread
from PySide6.QtGui import (
    QCloseEvent,
    QKeySequence,
    QUndoStack,
)
from PySide6.QtWidgets import (
    QDockWidget,
    QMainWindow,
    QStackedWidget,
    QToolBar,
    QTreeWidget,
    QTreeWidgetItem,
)

from frc_arch_modeler.domain.model import (
    ArchitectureProject,
    BehaviorDiagram,
    SourceAnchor,
)
from frc_arch_modeler.importers.base import ScanResult
from frc_arch_modeler.persistence.recent_model_store import RecentModelStore
from frc_arch_modeler.services.project_service import ProjectService
from frc_arch_modeler.services.reconcile_service import ReconciliationResult
from frc_arch_modeler.ui import toolbars
from frc_arch_modeler.ui.architecture_scene import ArchitectureScene
from frc_arch_modeler.ui.behavior_model_browser import BehaviorModelBrowser
from frc_arch_modeler.ui.behavior_scene import BehaviorScene
from frc_arch_modeler.ui.controllers.behavior_controller import BehaviorController
from frc_arch_modeler.ui.controllers.canvas_controller import CanvasController
from frc_arch_modeler.ui.controllers.details_controller import DetailsController
from frc_arch_modeler.ui.controllers.element_controller import ElementController
from frc_arch_modeler.ui.controllers.export_controller import ExportController
from frc_arch_modeler.ui.controllers.hardware_controller import HardwareController
from frc_arch_modeler.ui.controllers.project_controller import ProjectController
from frc_arch_modeler.ui.controllers.scan_controller import ScanController
from frc_arch_modeler.ui.help_panel import HelpPanel


class MainWindow(QMainWindow):
    """The plan's primary UI regions, wired to the controllers that drive them."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("FRC Architecture Modeler")
        self.resize(1280, 800)
        self.project: ArchitectureProject | None = None
        self.model_root: Path | None = None
        self.robot_project_root: Path | None = None
        self.last_scan: ScanResult | None = None
        self.reconciliation: ReconciliationResult | None = None
        self._last_scan_time: str | None = None
        self._git_revision_text: str | None = None
        self.is_dirty = False
        self.project_service = ProjectService()
        self.recent_model_store = RecentModelStore()
        self.behavior_controller = BehaviorController(self)
        self.canvas_controller = CanvasController(self)
        self.details_controller = DetailsController(self)
        self.element_controller = ElementController(self)
        self.export_controller = ExportController(self)
        self.hardware_controller = HardwareController(self)
        self.project_controller = ProjectController(self)
        self.scan_controller = ScanController(self)
        self.undo_stack = QUndoStack(self)
        self.scene = ArchitectureScene(self)
        self.behavior_scene = BehaviorScene(self)
        self.canvas_controller.connect_scenes()
        self._build_help_dock()
        self._build_toolbar()
        self.canvas_controller.build_canvas()
        self.hardware_controller.build_hardware_tab()
        self.details_controller.build_details_dock()
        self._build_inventory_dock()
        self.project_controller.build_status_bar()
        self.statusBar().showMessage("No robot project connected")

    def resizeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().resizeEvent(event)
        self._update_details_presentation()

    def _build_toolbar(self) -> None:
        toolbars.build_toolbar(self)

    @staticmethod
    def _set_action_help(action, text: str) -> None:  # type: ignore[no-untyped-def]
        toolbars.set_action_help(action, text)

    def _organize_toolbar(self, toolbar: QToolBar) -> None:
        toolbars.organize_toolbar(self, toolbar)

    def _build_behavior_toolbar(self) -> None:
        toolbars.build_behavior_toolbar(self)

    def closeEvent(self, event: QCloseEvent) -> None:
        self.project_controller.handle_close_event(event)

    def new_project(self, name: str) -> ArchitectureProject:
        return self.project_controller.new_project(name)

    def open_project(self, root: Path) -> ArchitectureProject:
        return self.project_controller.open_project(root)

    def save_project(self, root: Path | None = None) -> Path:
        return self.project_controller.save_project(root)

    def _mark_dirty(self, message: str) -> None:
        self.project_controller.mark_dirty(message)

    def _update_status_indicators(self) -> None:
        self.project_controller.update_status_indicators()

    def _prompt_new_project(self) -> None:
        self.project_controller.prompt_new_project()

    def _prompt_open_project(self) -> None:
        self.project_controller.prompt_open_project()

    def _prompt_save_project(self) -> None:
        self.project_controller.prompt_save_project()

    def _open_recent_model(self) -> None:
        self.project_controller.open_recent_model()

    def _refresh_recent_model_action(self) -> None:
        self.project_controller.refresh_recent_model_action()

    @property
    def _scan_thread(self) -> QThread | None:
        """The live scanner thread, exposed for tests that wait for a scan to finish."""
        return self.scan_controller.scan_thread

    def connect_robot_project(self, root: Path) -> ScanResult:
        return self.scan_controller.connect_robot_project(root)

    def refresh_robot_project(self) -> ScanResult | None:
        return self.scan_controller.refresh_robot_project()

    def _refresh_robot_project_async(self) -> None:
        self.scan_controller.refresh_robot_project_async()

    def _start_scan(self, root: Path, action: str) -> None:
        self.scan_controller.start_scan(root, action)

    def cancel_scan(self) -> None:
        self.scan_controller.cancel_scan()

    def _stop_background_scan_for_close(self) -> bool:
        return self.scan_controller.stop_background_scan_for_close()

    def _scan_progress(self, completed: int, total: int) -> None:
        self.scan_controller.scan_progress(completed, total)

    def _scan_completed(self, scan: ScanResult) -> None:
        self.scan_controller.scan_completed(scan)

    def _scan_failed(self, message: str) -> None:
        self.scan_controller.scan_failed(message)

    def _scan_cancelled(self) -> None:
        self.scan_controller.scan_cancelled()

    def _prompt_connect_robot_project(self) -> None:
        self.scan_controller.prompt_connect_robot_project()

    def _open_inventory_source(self, item: QTreeWidgetItem, column: int) -> None:
        self.scan_controller.open_inventory_source(item, column)

    def compare_changes(self) -> ReconciliationResult | None:
        return self.scan_controller.compare_changes()

    def accept_matches(self) -> int:
        return self.scan_controller.accept_matches()

    def bind_selected(self) -> bool:
        return self.scan_controller.bind_selected()

    def _comparison_statuses(self) -> dict:
        return self.scan_controller.comparison_statuses()

    def _allocation_findings(self) -> dict:
        return self.canvas_controller.allocation_findings()

    def _code_only_symbols(self) -> set[str]:
        return self.scan_controller.code_only_symbols()

    @property
    def _selected_behavior_diagram_id(self) -> object:
        return self.behavior_controller.selected_diagram_id

    @_selected_behavior_diagram_id.setter
    def _selected_behavior_diagram_id(self, diagram_id: object) -> None:
        self.behavior_controller.selected_diagram_id = diagram_id

    def _active_behavior_diagram(self) -> BehaviorDiagram | None:
        return self.behavior_controller.active_diagram()

    def _select_behavior_diagram(self, diagram_id: object) -> None:
        self.behavior_controller.select_diagram(diagram_id)

    def _add_root_behavior_diagram(self) -> None:
        self.behavior_controller.add_root_diagram()

    def _add_command_behavior_diagram(self, command_id: object) -> None:
        self.behavior_controller.add_command_diagram(command_id)

    def _rename_behavior_diagram(self, diagram_id: object) -> None:
        self.behavior_controller.rename_diagram(diagram_id)

    def _delete_behavior_diagram(self, diagram_id: object) -> None:
        self.behavior_controller.delete_diagram(diagram_id)

    def add_behavior_state(self, name: str, kind: str = "state") -> None:
        self.behavior_controller.add_state(name, kind)

    def _add_behavior_pseudostate(self, kind: str) -> None:
        self.behavior_controller.add_pseudostate(kind)

    def add_behavior_transition(  # type: ignore[no-untyped-def]
        self, source_state_id, target_state_id, trigger_label: str
    ) -> None:
        self.behavior_controller.add_transition(source_state_id, target_state_id, trigger_label)

    def delete_behavior_selected(self) -> bool:
        return self.behavior_controller.delete_selected()

    def _delete_behavior_transition(self, transition_id: object) -> None:
        self.behavior_controller.delete_transition(transition_id)

    def _reattach_behavior_transition(
        self, transition_id: object, end: str, new_state_id: object
    ) -> None:
        self.behavior_controller.reattach_transition(transition_id, end, new_state_id)

    def _handle_behavior_connection_requested(self, source_block, target_block, drop_pos) -> None:  # type: ignore[no-untyped-def]
        self.behavior_controller.handle_connection_requested(source_block, target_block, drop_pos)

    def _prompt_rename_behavior_state(self, block) -> None:  # type: ignore[no-untyped-def]
        self.behavior_controller.prompt_rename_state(block)

    def _prompt_new_behavior_state(self) -> None:
        self.behavior_controller.prompt_new_state()

    def _record_behavior_layout_move(self, before, after) -> None:  # type: ignore[no-untyped-def]
        self.behavior_controller.record_layout_move(before, after)

    def _behavior_layout_changed(self) -> None:
        self.behavior_controller.layout_changed()

    def _refresh_behavior_after_edit(self) -> None:
        self.behavior_controller.refresh_after_edit()

    def _render_with_current_scan(self) -> None:
        self.canvas_controller.render_with_current_scan()

    def _render_preserving_selection(self) -> None:
        self.canvas_controller.render_preserving_selection()

    def _toggle_command_forms(self, visible: bool) -> None:
        self.canvas_controller.toggle_command_forms(visible)

    def _cycle_device_view(self) -> None:
        self.canvas_controller.cycle_device_view()

    def _device_view_changed(self) -> None:
        self.canvas_controller.device_view_changed()

    def _apply_status_filters(self) -> None:
        self.canvas_controller.apply_status_filters()

    def _update_bind_selected_action(self) -> None:
        self.canvas_controller.update_bind_selected_action()

    def _update_delete_selected_action(self) -> None:
        self.canvas_controller.update_delete_selected_action()

    def _update_link_selected_action(self) -> None:
        self.canvas_controller.update_link_selected_action()

    def auto_layout(self) -> None:
        self.canvas_controller.auto_layout()

    def zoom_to_fit(self) -> None:
        self.canvas_controller.zoom_to_fit()

    def behavior_zoom_to_fit(self) -> None:
        self.canvas_controller.behavior_zoom_to_fit()

    def minimize_selected(self) -> None:
        self.canvas_controller.minimize_selected()

    def restore_selected(self) -> None:
        self.canvas_controller.restore_selected()

    def _layout_changed(self) -> None:
        self.canvas_controller.layout_changed()

    def _record_layout_move(self, before, after) -> None:  # type: ignore[no-untyped-def]
        self.canvas_controller.record_layout_move(before, after)

    def _sync_left_dock_to_active_tab(self, index: int) -> None:
        self.canvas_controller.sync_left_dock_to_active_tab(index)

    def add_command(self, name: str) -> None:
        self.element_controller.add_command(name)

    def add_subsystem(self, name: str) -> None:
        self.element_controller.add_subsystem(name)

    def add_device(  # type: ignore[no-untyped-def]
        self,
        owner_subsystem_id,
        name: str,
        device_type: str,
        mode: str | None = None,
        bus: str | None = None,
        address: str | None = None,
        breaker_amps: str | None = None,
        mass_kg: str | None = None,
        notes: str | None = None,
    ) -> None:
        self.element_controller.add_device(
            owner_subsystem_id,
            name,
            device_type,
            mode,
            bus,
            address,
            breaker_amps,
            mass_kg,
            notes,
        )

    def add_trigger(
        self, command_id, expression: str, activation: str
    ) -> None:  # type: ignore[no-untyped-def]
        self.element_controller.add_trigger(command_id, expression, activation)

    def add_relationship(
        self, relationship_type: str, source_id, target_id
    ) -> None:  # type: ignore[no-untyped-def]
        self.element_controller.add_relationship(relationship_type, source_id, target_id)

    def link_selected_requirement(self) -> bool:
        return self.element_controller.link_selected_requirement()

    def _handle_connection_requested(self, source_block, target_block, drop_pos) -> None:  # type: ignore[no-untyped-def]
        self.element_controller.handle_connection_requested(source_block, target_block, drop_pos)

    def _apply_requested_connection(  # type: ignore[no-untyped-def]
        self, source_block, target_block, relationship_type: str
    ) -> None:
        self.element_controller.apply_requested_connection(
            source_block, target_block, relationship_type
        )

    def _confirm_delete_selected(self) -> None:
        self.element_controller.confirm_delete_selected()

    def delete_selected(self) -> bool:
        return self.element_controller.delete_selected()

    def _refresh_after_edit(self) -> None:
        self.element_controller.refresh_after_edit()

    def add_owned_object(self, kind: str) -> None:
        self.element_controller.add_owned_object(kind)

    def edit_owned_object(self, kind: str, entity_id) -> None:  # type: ignore[no-untyped-def]
        self.element_controller.edit_owned_object(kind, entity_id)

    def remove_owned_object(self, kind: str, entity_id) -> None:  # type: ignore[no-untyped-def]
        self.element_controller.remove_owned_object(kind, entity_id)

    def _prompt_new_command(self) -> None:
        self.element_controller.prompt_new_command()

    def _prompt_new_subsystem(self) -> None:
        self.element_controller.prompt_new_subsystem()

    def _prompt_new_device(self) -> None:
        self.element_controller.prompt_new_device()

    def _prompt_new_trigger(self) -> None:
        self.element_controller.prompt_new_trigger()

    def _prompt_new_relationship(self) -> None:
        self.element_controller.prompt_new_relationship()

    def _refresh_after_hardware_edit(self) -> None:
        """Re-render the canvas and the Hardware table after a table-driven edit."""
        self.element_controller.refresh_after_edit()
        self.hardware_controller.refresh_table()

    def _hardware_column_header_clicked(self, column: int) -> None:
        self.hardware_controller.column_header_clicked(column)

    def _hardware_cell_changed(self, item) -> None:  # type: ignore[no-untyped-def]
        self.hardware_controller.cell_changed(item)

    def _hardware_alert_cell_clicked(self, row: int, column: int) -> None:
        self.hardware_controller.alert_cell_clicked(row, column)

    def _hardware_subsystem_cell_changed(self, device_id, combo) -> None:  # type: ignore[no-untyped-def]
        self.hardware_controller.subsystem_cell_changed(device_id, combo)

    def _hardware_mode_cell_changed(self, device_id, combo) -> None:  # type: ignore[no-untyped-def]
        self.hardware_controller.mode_cell_changed(device_id, combo)

    def _remove_selected_hardware_device(self) -> None:
        self.hardware_controller.remove_selected_device()

    def _filter_hardware_table(self, text: str) -> None:
        self.hardware_controller.apply_filter(text)

    def _sync_hardware_table_selection(self) -> None:
        self.hardware_controller.sync_table_to_canvas_selection()

    def _sync_canvas_to_hardware_selection(self) -> None:
        self.hardware_controller.sync_canvas_to_table_selection()

    def _update_details_presentation(self) -> None:
        self.details_controller.update_details_presentation()

    def _open_compact_details(self) -> None:
        self.details_controller.open_compact_details()

    def _update_compact_details(self) -> None:
        self.details_controller.update_compact_details()

    def _update_selected_element(self) -> None:
        self.details_controller.update_selected_element()

    def edit_selected_description(self, description: str | None) -> None:
        self.details_controller.edit_selected_description(description)

    def edit_selected_name(self, name: str | None) -> None:
        self.details_controller.edit_selected_name(name)

    def edit_selected_requirements(self, requirement_ids) -> None:  # type: ignore[no-untyped-def]
        self.details_controller.edit_selected_requirements(requirement_ids)

    def _requirements_changed(self) -> None:
        self.details_controller.requirements_changed()

    def _open_source_anchor(self, anchor: SourceAnchor) -> None:
        self.details_controller.open_source_anchor(anchor)

    def set_project(self, project: ArchitectureProject | None) -> None:
        """Display a project with the deterministic initial canvas layout."""
        self.project = project
        self.scene.render_project(
            project,
            scan=self.last_scan,
            statuses=self._comparison_statuses(),
            allocation_findings=self._allocation_findings(),
        )
        self._selected_behavior_diagram_id = (
            project.behavior_diagrams[0].id if project and project.behavior_diagrams else None
        )
        self.behavior_model_browser.rebuild(project, self._selected_behavior_diagram_id)
        self.behavior_scene.render_diagram(self._active_behavior_diagram())
        self.details_panel.set_element(None)
        self._update_compact_details()
        self.new_command_action.setEnabled(project is not None)
        self.new_subsystem_action.setEnabled(project is not None)
        self.new_device_action.setEnabled(project is not None and bool(project.subsystems))
        self.new_trigger_action.setEnabled(project is not None and bool(project.commands))
        self.new_relationship_action.setEnabled(
            project is not None and len(project.commands) + len(project.subsystems) > 1
        )
        for action in self._behavior_creation_actions:
            action.setEnabled(project is not None)
        self.behavior_zoom_to_fit_action.setEnabled(project is not None)
        self.save_model_action.setEnabled(project is not None)
        self.auto_layout_action.setEnabled(project is not None)
        self.zoom_to_fit_action.setEnabled(project is not None)
        self.minimize_action.setEnabled(project is not None)
        self.restore_action.setEnabled(project is not None)
        self.device_view_action.setEnabled(project is not None)
        self.canvas_controller.update_device_view_action()
        self.hardware_controller.refresh_table()
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
        self._update_status_indicators()

    def export_architecture(self, root: Path | None = None) -> Path:
        return self.export_controller.export_architecture(root)

    def export_change_request(self, root: Path | None = None) -> Path:
        return self.export_controller.export_change_request(root)

    def _prompt_export_architecture(self) -> None:
        self.export_controller.prompt_export_architecture()

    def _prompt_export_change_request(self) -> None:
        self.export_controller.prompt_export_change_request()

    def _build_inventory_dock(self) -> None:
        dock = QDockWidget("Code Inventory", self)
        dock.setObjectName("codeInventoryDock")
        self.inventory_tree = QTreeWidget(dock)
        self.inventory_tree.setObjectName("codeInventoryTree")
        self.inventory_tree.setHeaderLabels(["Symbol", "Source"])
        self.inventory_tree.itemDoubleClicked.connect(self._open_inventory_source)
        self.behavior_model_browser = BehaviorModelBrowser(dock)
        self.behavior_model_browser.diagram_selected.connect(self._select_behavior_diagram)
        self.behavior_model_browser.new_root_diagram_requested.connect(
            self._add_root_behavior_diagram
        )
        self.behavior_model_browser.new_command_diagram_requested.connect(
            self._add_command_behavior_diagram
        )
        self.behavior_model_browser.rename_requested.connect(self._rename_behavior_diagram)
        self.behavior_model_browser.delete_requested.connect(self._delete_behavior_diagram)
        self._left_dock_stack = QStackedWidget(dock)
        self._left_dock_stack.addWidget(self.inventory_tree)
        self._left_dock_stack.addWidget(self.behavior_model_browser)
        self._left_dock = dock
        dock.setWidget(self._left_dock_stack)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)
        self.diagram_tabs.currentChanged.connect(self._sync_left_dock_to_active_tab)
        self._sync_left_dock_to_active_tab(self.diagram_tabs.currentIndex())

    def _build_help_dock(self) -> None:
        """A notation help panel, hidden by default so it costs the canvas no width.

        Toggled by F1 or the "?" toolbar button via the dock's own built-in toggle
        action, so visibility state and action checked-state can never drift apart.
        """
        dock = QDockWidget("Notation Help", self)
        dock.setObjectName("helpDock")
        self.help_panel = HelpPanel(dock)
        dock.setWidget(self.help_panel)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)
        dock.setVisible(False)
        self.help_dock = dock
        self.toggle_help_action = dock.toggleViewAction()
        self.toggle_help_action.setText("?")
        self.toggle_help_action.setShortcut(QKeySequence(Qt.Key.Key_F1))
        self._set_action_help(
            self.toggle_help_action,
            "Show or hide the notation help panel. Use this when you forget what a "
            "block accent, border style, line, or palette shape means.",
        )

