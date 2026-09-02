"""The details panel: what the selected block says, and the edits made from it."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QDockWidget, QVBoxLayout

from frc_arch_modeler.domain.model import SourceAnchor
from frc_arch_modeler.ui.details_panel import (
    DetailsPanel,
    EditDescriptionCommand,
    EditNameCommand,
    EditRequirementsCommand,
)
from frc_arch_modeler.ui.source_viewer import SourceViewerDialog

if TYPE_CHECKING:
    from frc_arch_modeler.ui.main_window import MainWindow

DETAILS_DOCK_BREAKPOINT = 1280

INLINE_COMMAND_FLOWS = {
    "runOnce": ["Start", "action", "Finish"],
    "run": ["Start", "execute", "Until interrupted", "end(interrupted)"],
    "runEnd": ["Start", "execute", "end(interrupted)"],
    "startEnd": ["Start", "execute", "end(interrupted)"],
}


class DetailsController:
    """Fill the details dock and compact sheet, and route their edits through undo."""

    def __init__(self, window: MainWindow) -> None:
        self.window = window

    # -- construction -----------------------------------------------------

    def build_details_dock(self) -> None:
        window = self.window
        dock = QDockWidget("Details", window)
        dock.setObjectName("detailsDock")
        window.details_dock = dock
        window.details_panel = self._new_panel()
        dock.setWidget(window.details_panel)
        window.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
        window.compact_details_dialog: QDialog | None = None
        window.compact_details_panel: DetailsPanel | None = None

    def _new_panel(self) -> DetailsPanel:
        window = self.window
        return DetailsPanel(
            window.edit_selected_description,
            window.edit_selected_name,
            window.edit_selected_requirements,
            window._open_source_anchor,
            window.add_owned_object,
            window.edit_owned_object,
            window.remove_owned_object,
        )

    def update_details_presentation(self) -> None:
        """Use a dock on wide screens and reserve a sheet on laptop-width windows."""
        self.window.details_dock.setVisible(self.window.width() >= DETAILS_DOCK_BREAKPOINT)

    def open_compact_details(self) -> None:
        window = self.window
        if (
            window.width() >= DETAILS_DOCK_BREAKPOINT
            or len(window.scene.selected_blocks()) != 1
        ):
            return
        if window.compact_details_dialog is None:
            dialog = QDialog(window)
            dialog.setObjectName("compactDetailsDialog")
            dialog.setWindowTitle("Details")
            dialog.setModal(False)
            dialog.resize(440, 520)
            panel = self._new_panel()
            layout = QVBoxLayout(dialog)
            layout.addWidget(panel)
            window.compact_details_dialog = dialog
            window.compact_details_panel = panel
        self.update_compact_details()
        window.compact_details_dialog.show()
        window.compact_details_dialog.raise_()

    # -- selection -> panel contents --------------------------------------

    def update_selected_element(self) -> None:
        window = self.window
        selected = window.scene.selected_blocks()
        if len(selected) != 1:
            window.details_panel.set_element(None)
            self.update_compact_details()
            return
        imported_anchor = selected[0].source_anchor
        if isinstance(imported_anchor, SourceAnchor):
            conventional_command = (
                selected[0].kind == "command" and self._is_conventional_command(imported_anchor)
            )
            functional_command = self._functional_phase_expressions(imported_anchor)
            inline_flow = self._inline_command_flow(imported_anchor)
            window.details_panel.set_imported_fact(
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
            self.update_compact_details()
            return
        if window.project is None:
            window.details_panel.set_element(None)
            self.update_compact_details()
            return
        element_id = selected[0].element_id
        element = self._element_by_id(element_id)
        window.details_panel.set_element(
            element,
            *self._matched_code_details(element.id) if element is not None else (),
            subsystem_options=self.subsystem_options(),
            design_context=self._design_structure(element.id) if element is not None else None,
            owned_objects=self._owned_objects(element),
        )
        self.update_compact_details()

    def update_compact_details(self) -> None:
        """Mirror selection in a visible compact sheet without changing model state."""
        window = self.window
        if window.compact_details_panel is None:
            return
        selected = window.scene.selected_blocks()
        if len(selected) != 1:
            window.compact_details_panel.set_element(None)
            return
        block = selected[0]
        if isinstance(block.source_anchor, SourceAnchor):
            conventional_command = (
                block.kind == "command" and self._is_conventional_command(block.source_anchor)
            )
            window.compact_details_panel.set_imported_fact(
                block.title.toPlainText(),
                block.kind,
                block.source_anchor,
                self._imported_details(block),
                self._lifecycle_methods(block.source_anchor) if conventional_command else None,
                self._lifecycle_anchors(block.source_anchor) if conventional_command else None,
                conventional_command,
            )
            return
        if window.project is None:
            window.compact_details_panel.set_element(None)
            return
        element = self._element_by_id(block.element_id)
        window.compact_details_panel.set_element(
            element,
            *self._matched_code_details(element.id) if element is not None else (),
            subsystem_options=self.subsystem_options(),
            design_context=self._design_structure(element.id) if element is not None else None,
            owned_objects=self._owned_objects(element),
        )

    def _element_by_id(self, element_id):  # type: ignore[no-untyped-def]
        project = self.window.project
        if project is None:
            return None
        return next(
            (
                item
                for item in [*project.commands, *project.subsystems]
                if item.id == element_id
            ),
            None,
        )

    def subsystem_options(self) -> list[tuple]:  # type: ignore[type-arg]
        project = self.window.project
        if project is None:
            return []
        return [
            (subsystem.id, subsystem.name.effective or "Unnamed")
            for subsystem in project.subsystems
        ]

    # -- scanned code evidence --------------------------------------------

    def _matched_code_details(
        self, element_id
    ) -> tuple[str | None, str | None, SourceAnchor | None]:  # type: ignore[no-untyped-def]
        reconciliation = self.window.reconciliation
        if reconciliation is None:
            return (None, None, None)
        symbol = reconciliation.matches.get(element_id)
        if symbol is None:
            return (None, None, None)
        return (symbol.name, symbol.documentation, symbol.anchor)

    def _imported_details(self, block) -> str | None:  # type: ignore[no-untyped-def]
        """Augment imported facts with directly extracted architecture evidence."""
        last_scan = self.window.last_scan
        details = block.code_summary
        if not isinstance(block.source_anchor, SourceAnchor) or last_scan is None:
            return details
        lines: list[str] = [details] if details else []
        qualified_symbol = block.source_anchor.qualified_symbol
        if block.kind == "subsystem":
            devices = [
                f"- {device.device_type}{f' [{device.mode}]' if device.mode else ''}: "
                f"{device.resolved_arguments or device.constructor_arguments}"
                for device in last_scan.devices
                if self._logical_device_owner(device.owner_symbol) == qualified_symbol
            ]
            if devices:
                lines.extend(["Devices:", *devices])
        if block.kind == "command":
            normalized_block_name = self._normalized(block.title.toPlainText())
            triggers = [
                f"- {trigger.controller_expression} · {trigger.activation} → "
                f"{trigger.command_expression}"
                for trigger in last_scan.triggers
                if normalized_block_name in self._normalized(trigger.command_expression)
            ]
            lifecycle = [
                symbol.name
                for symbol in last_scan.symbols_of_kind("lifecycle_method")
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
                for relationship in last_scan.relationships
                if relationship.kind in {"default_command", "autonomous_registration"}
                and normalized_block_name in self._normalized(relationship.target_expression)
            ]
            if registrations:
                lines.extend(["Scheduler registrations:", *registrations])
        children = [
            relationship.target_expression
            for relationship in last_scan.relationships
            if relationship.kind == "composition_child"
            and relationship.source_symbol == qualified_symbol
        ]
        if children:
            lines.extend(["Composition children:", *(f"- {child}" for child in children)])
        decorators = [
            relationship.target_expression
            for relationship in last_scan.relationships
            if relationship.kind == "command_decorator"
            and relationship.source_symbol == qualified_symbol
        ]
        if decorators:
            lines.extend(["Decorators:", *(f"- {decorator}" for decorator in decorators)])
        functional_phases = [
            relationship.target_expression
            for relationship in last_scan.relationships
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
        last_scan = self.window.last_scan
        if last_scan is None:
            return []
        return [
            symbol.name
            for symbol in last_scan.symbols_of_kind("lifecycle_method")
            if symbol.anchor.qualified_symbol.startswith(f"{command_anchor.qualified_symbol}#")
        ]

    def _is_conventional_command(self, command_anchor: SourceAnchor) -> bool:
        """Only command subclasses have the conventional initialize/execute lifecycle."""
        last_scan = self.window.last_scan
        return last_scan is not None and any(
            symbol.kind == "command"
            and symbol.anchor.qualified_symbol == command_anchor.qualified_symbol
            for symbol in last_scan.symbols
        )

    def _functional_phase_expressions(self, command_anchor: SourceAnchor) -> list[str]:
        """Identify a FunctionalCommand form without fabricating conventional source methods."""
        last_scan = self.window.last_scan
        if last_scan is None:
            return []
        return [
            relationship.target_expression
            for relationship in last_scan.relationships
            if relationship.kind == "functional_phase"
            and relationship.source_symbol == command_anchor.qualified_symbol
        ]

    def _inline_command_flow(self, command_anchor: SourceAnchor) -> list[str] | None:
        """Describe the fixed scheduler behavior of supported inline WPILib factories."""
        last_scan = self.window.last_scan
        if last_scan is None or not any(
            symbol.kind == "command_composition"
            and symbol.anchor.qualified_symbol == command_anchor.qualified_symbol
            for symbol in last_scan.symbols
        ):
            return None
        form = command_anchor.qualified_symbol.rsplit(".", 1)[-1].split("@", 1)[0]
        return INLINE_COMMAND_FLOWS.get(form)

    def _lifecycle_anchors(self, command_anchor: SourceAnchor) -> dict[str, SourceAnchor]:
        last_scan = self.window.last_scan
        if last_scan is None:
            return {}
        return {
            symbol.name: symbol.anchor
            for symbol in last_scan.symbols_of_kind("lifecycle_method")
            if symbol.anchor.qualified_symbol.startswith(f"{command_anchor.qualified_symbol}#")
        }

    @staticmethod
    def _normalized(value: str) -> str:
        return "".join(character for character in value.casefold() if character.isalnum())

    def _logical_device_owner(self, owner_symbol: str) -> str:
        """Use the same conservative IO-to-subsystem presentation mapping as the canvas."""
        last_scan = self.window.last_scan
        if last_scan is None:
            return owner_symbol
        owner_type = owner_symbol.rsplit(".", 1)[-1]
        normalized_owner = self._normalized(owner_type)
        matches = [
            symbol.anchor.qualified_symbol
            for symbol in last_scan.symbols_of_kind("subsystem")
            if normalized_owner.startswith(self._normalized(symbol.name))
            and "io" in normalized_owner[len(self._normalized(symbol.name)) :]
        ]
        return matches[0] if len(matches) == 1 else owner_symbol

    # -- authored design context ------------------------------------------

    def _design_structure(self, element_id) -> str | None:  # type: ignore[no-untyped-def]
        """Summarize authored devices, controls, and typed links for the details panel."""
        project = self.window.project
        if project is None:
            return None
        lines: list[str] = []
        devices = [
            device for device in project.devices if device.owner_subsystem_id == element_id
        ]
        if devices:
            lines.append(
                "Devices: "
                + ", ".join(
                    f"{device.name.effective} ({device.device_type.effective})"
                    for device in devices
                )
            )
        triggers = [trigger for trigger in project.triggers if trigger.command_id == element_id]
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
            for relationship in project.relationships
            if element_id in {relationship.source_id, relationship.target_id}
        ]
        if links:
            lines.append("Relationships: " + ", ".join(links))
        return "\n".join(lines) or None

    def _element_names(self) -> dict:  # type: ignore[type-arg]
        project = self.window.project
        if project is None:
            return {}
        return {
            item.id: item.name.effective or "Unnamed"
            for item in [*project.commands, *project.subsystems]
        }

    def _owned_objects(self, element) -> dict:  # type: ignore[no-untyped-def, type-arg]
        """List, per kind, what the given element owns so its details panel can manage it."""
        project = self.window.project
        if project is None or element is None:
            return {}
        element_id = element.id
        names = self._element_names()
        return {
            "device": [
                (device.id, f"{device.name.effective} ({device.device_type.effective})")
                for device in project.devices
                if device.owner_subsystem_id == element_id
            ],
            "trigger": [
                (trigger.id, f"{trigger.expression.effective} · {trigger.activation.effective}")
                for trigger in project.triggers
                if trigger.command_id == element_id
            ],
            "relationship": [
                (
                    relationship.id,
                    f"{names.get(relationship.source_id, 'Unknown')} — "
                    f"{relationship.relationship_type.replace('_', ' ')} → "
                    f"{names.get(relationship.target_id, 'Unknown')}",
                )
                for relationship in project.relationships
                if element_id in {relationship.source_id, relationship.target_id}
            ],
        }

    # -- edits ------------------------------------------------------------

    def edit_selected_description(self, description: str | None) -> None:
        """Apply a selected element's design description through the undo stack."""
        window = self.window
        selected = window.scene.selected_blocks()
        if window.project is None or len(selected) != 1:
            return
        element = self._element_by_id(selected[0].element_id)
        if element is None or element.description.design == description:
            return
        window.undo_stack.push(
            EditDescriptionCommand(element, description, self.description_changed)
        )

    def edit_selected_name(self, name: str | None) -> None:
        """Apply a selected element's proposed display name through the undo stack."""
        window = self.window
        selected = window.scene.selected_blocks()
        if window.project is None or len(selected) != 1 or (name is not None and not name.strip()):
            return
        element = self._element_by_id(selected[0].element_id)
        if element is None or element.name.design == name:
            return
        window.undo_stack.push(EditNameCommand(element, name, self.name_changed))

    def edit_selected_requirements(self, requirement_ids) -> None:  # type: ignore[no-untyped-def]
        """Apply selected command requirement IDs through the undo stack."""
        window = self.window
        selected = window.scene.selected_blocks()
        if window.project is None or len(selected) != 1:
            return
        element = next(
            (item for item in window.project.commands if item.id == selected[0].element_id), None
        )
        if element is None:
            return
        valid_ids = {subsystem.id for subsystem in window.project.subsystems}
        normalized = list(dict.fromkeys(requirement_ids))
        if any(requirement_id not in valid_ids for requirement_id in normalized):
            return
        if element.requirement_ids != normalized:
            window.undo_stack.push(
                EditRequirementsCommand(element, normalized, self.requirements_changed)
            )

    def name_changed(self) -> None:
        self.window._mark_dirty("Name updated")
        self.window._render_preserving_selection()

    def requirements_changed(self) -> None:
        self.window._mark_dirty("Requirements updated")
        self.window._render_with_current_scan()

    def description_changed(self) -> None:
        self.window._mark_dirty("Description updated")
        self.window._render_preserving_selection()

    def open_source_anchor(self, anchor: SourceAnchor) -> None:
        """Open portable source evidence when a robot project is currently connected."""
        window = self.window
        if window.robot_project_root is None:
            return
        dialog = SourceViewerDialog(window.robot_project_root, anchor, window)
        dialog.open()
