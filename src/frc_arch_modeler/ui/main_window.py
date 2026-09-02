"""Main application shell for the Phase 0 spike."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QThread
from PySide6.QtGui import (
    QCloseEvent,
    QKeySequence,
    QUndoStack,
)
from PySide6.QtWidgets import (
    QDialog,
    QDockWidget,
    QMainWindow,
    QStackedWidget,
    QToolBar,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
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
from frc_arch_modeler.ui.controllers.element_controller import ElementController
from frc_arch_modeler.ui.controllers.export_controller import ExportController
from frc_arch_modeler.ui.controllers.project_controller import ProjectController
from frc_arch_modeler.ui.controllers.scan_controller import ScanController
from frc_arch_modeler.ui.details_panel import (
    DetailsPanel,
    EditDescriptionCommand,
    EditNameCommand,
    EditRequirementsCommand,
)
from frc_arch_modeler.ui.help_panel import HelpPanel
from frc_arch_modeler.ui.source_viewer import SourceViewerDialog

DETAILS_DOCK_BREAKPOINT = 1280


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
        self._last_scan_time: str | None = None
        self._git_revision_text: str | None = None
        self.is_dirty = False
        self.project_service = ProjectService()
        self.recent_model_store = RecentModelStore()
        self.behavior_controller = BehaviorController(self)
        self.canvas_controller = CanvasController(self)
        self.element_controller = ElementController(self)
        self.export_controller = ExportController(self)
        self.project_controller = ProjectController(self)
        self.scan_controller = ScanController(self)
        self.undo_stack = QUndoStack(self)
        self.scene = ArchitectureScene(self)
        self.behavior_scene = BehaviorScene(self)
        self.canvas_controller.connect_scenes()
        self._build_help_dock()
        self._build_toolbar()
        self.canvas_controller.build_canvas()
        self._build_details_dock()
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

    def add_device(
        self, owner_subsystem_id, name: str, device_type: str, mode: str | None = None
    ) -> None:  # type: ignore[no-untyped-def]
        self.element_controller.add_device(owner_subsystem_id, name, device_type, mode)

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

    def set_project(self, project: ArchitectureProject | None) -> None:
        """Display a project with the deterministic initial canvas layout."""
        self.project = project
        self.scene.render_project(
            project, scan=self.last_scan, statuses=self._comparison_statuses()
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
            owned_objects=self._owned_objects(element),
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

    def _element_names(self) -> dict:  # type: ignore[type-arg]
        if self.project is None:
            return {}
        return {
            item.id: item.name.effective or "Unnamed"
            for item in [*self.project.commands, *self.project.subsystems]
        }

    def _owned_objects(self, element) -> dict:  # type: ignore[no-untyped-def, type-arg]
        """List, per kind, what the given element owns so its details panel can manage it."""
        if self.project is None or element is None:
            return {}
        element_id = element.id
        names = self._element_names()
        return {
            "device": [
                (device.id, f"{device.name.effective} ({device.device_type.effective})")
                for device in self.project.devices
                if device.owner_subsystem_id == element_id
            ],
            "trigger": [
                (trigger.id, f"{trigger.expression.effective} · {trigger.activation.effective}")
                for trigger in self.project.triggers
                if trigger.command_id == element_id
            ],
            "relationship": [
                (
                    relationship.id,
                    f"{names.get(relationship.source_id, 'Unknown')} — "
                    f"{relationship.relationship_type.replace('_', ' ')} → "
                    f"{names.get(relationship.target_id, 'Unknown')}",
                )
                for relationship in self.project.relationships
                if element_id in {relationship.source_id, relationship.target_id}
            ],
        }

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
        self._render_preserving_selection()

    def _requirements_changed(self) -> None:
        self._mark_dirty("Requirements updated")
        self._render_with_current_scan()

    def _description_changed(self) -> None:
        self._mark_dirty("Description updated")
        self._render_preserving_selection()

    def _build_details_dock(self) -> None:
        dock = QDockWidget("Details", self)
        dock.setObjectName("detailsDock")
        self.details_dock = dock
        self.details_panel = DetailsPanel(
            self.edit_selected_description,
            self.edit_selected_name,
            self.edit_selected_requirements,
            self._open_source_anchor,
            self.add_owned_object,
            self.edit_owned_object,
            self.remove_owned_object,
        )
        dock.setWidget(self.details_panel)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
        self.compact_details_dialog: QDialog | None = None
        self.compact_details_panel: DetailsPanel | None = None

    def _update_details_presentation(self) -> None:
        """Use a dock on wide screens and reserve a sheet on laptop-width windows."""
        self.details_dock.setVisible(self.width() >= DETAILS_DOCK_BREAKPOINT)

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
                self.add_owned_object,
                self.edit_owned_object,
                self.remove_owned_object,
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
            owned_objects=self._owned_objects(element),
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

    def _open_source_anchor(self, anchor: SourceAnchor) -> None:
        """Open portable source evidence when a robot project is currently connected."""
        if self.robot_project_root is None:
            return
        dialog = SourceViewerDialog(self.robot_project_root, anchor, self)
        dialog.open()
