"""Authoring of design entities: commands, subsystems, devices, triggers, relationships."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QDialog, QInputDialog, QMenu, QMessageBox

from frc_arch_modeler.ui.architecture_scene import CanvasBlock
from frc_arch_modeler.ui.details_panel import EditEntityFieldsCommand, EditRequirementsCommand
from frc_arch_modeler.ui.entity_dialogs import DeviceDialog, RelationshipDialog, TriggerDialog
from frc_arch_modeler.ui.undo_commands import AddDesignEntityCommand, RemoveDesignEntityCommand

if TYPE_CHECKING:
    from frc_arch_modeler.ui.main_window import MainWindow


class ElementController:
    """Create, edit and delete the user-authored entities on the structure canvas."""

    def __init__(self, window: MainWindow) -> None:
        self.window = window

    # -- creation ---------------------------------------------------------

    def add_command(self, name: str) -> None:
        """Add a command and refresh its deterministic initial canvas position."""
        window = self.window
        if window.project is None:
            raise RuntimeError("Create or open a model before adding a command.")
        command = window.project_service.add_command(window.project, name)
        window.project.commands.remove(command)
        window.undo_stack.push(
            AddDesignEntityCommand(
                window.project.commands, command, "command", self.refresh_after_edit
            )
        )

    def add_subsystem(self, name: str) -> None:
        """Add a subsystem and refresh its deterministic initial canvas position."""
        window = self.window
        if window.project is None:
            raise RuntimeError("Create or open a model before adding a subsystem.")
        subsystem = window.project_service.add_subsystem(window.project, name)
        window.project.subsystems.remove(subsystem)
        window.undo_stack.push(
            AddDesignEntityCommand(
                window.project.subsystems, subsystem, "subsystem", self.refresh_after_edit
            )
        )

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
        """Add a proposed hardware device and surface it on its subsystem block."""
        window = self.window
        if window.project is None:
            raise RuntimeError("Create or open a model before adding a device.")
        device = window.project_service.add_device(
            window.project,
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
        window.project.devices.remove(device)
        window.undo_stack.push(
            AddDesignEntityCommand(
                window.project.devices, device, "device", self.refresh_after_edit
            )
        )

    def add_trigger(
        self, command_id, expression: str, activation: str
    ) -> None:  # type: ignore[no-untyped-def]
        """Add a proposed trigger binding and surface it on its command block."""
        window = self.window
        if window.project is None:
            raise RuntimeError("Create or open a model before adding a trigger.")
        trigger = window.project_service.add_trigger(
            window.project, command_id, expression, activation
        )
        window.project.triggers.remove(trigger)
        window.undo_stack.push(
            AddDesignEntityCommand(
                window.project.triggers, trigger, "trigger", self.refresh_after_edit
            )
        )

    def add_relationship(
        self, relationship_type: str, source_id, target_id
    ) -> None:  # type: ignore[no-untyped-def]
        """Add an authored relationship between visible command/subsystem blocks."""
        window = self.window
        if window.project is None:
            raise RuntimeError("Create or open a model before adding a relationship.")
        relationship = window.project_service.add_relationship(
            window.project, relationship_type, source_id, target_id
        )
        window.project.relationships.remove(relationship)
        window.undo_stack.push(
            AddDesignEntityCommand(
                window.project.relationships,
                relationship,
                "relationship",
                self.refresh_after_edit,
            )
        )

    # -- canvas-driven authoring ------------------------------------------

    def link_selected_requirement(self) -> bool:
        """Create the visible command-to-subsystem requirement selected on the canvas."""
        window = self.window
        if window.project is None:
            return False
        blocks = window.scene.selected_blocks()
        if (
            len(blocks) != 2
            or any(block.imported for block in blocks)
            or {block.kind for block in blocks} != {"command", "subsystem"}
        ):
            return False
        command_block = next(block for block in blocks if block.kind == "command")
        subsystem_block = next(block for block in blocks if block.kind == "subsystem")
        command = next(
            (item for item in window.project.commands if item.id == command_block.element_id),
            None,
        )
        if command is None or subsystem_block.element_id in command.requirement_ids:
            return False
        window.undo_stack.push(
            EditRequirementsCommand(
                command,
                [*command.requirement_ids, subsystem_block.element_id],
                window._requirements_changed,
            )
        )
        return True

    def handle_connection_requested(self, source_block, target_block, drop_pos) -> None:  # type: ignore[no-untyped-def]
        """Offer relationship types at the drop point, Visio connector-tool style."""
        if self.window.project is None:
            return
        menu = QMenu(self.window)
        actions: dict[object, str] = {}
        if source_block.kind == "command" and target_block.kind == "subsystem":
            action = menu.addAction("Requires (scheduler requirement)")
            actions[action] = "requires"
            menu.addSeparator()
        for label, value in (
            ("Calls", "calls"),
            ("Contains", "contains"),
            ("Triggers", "triggers"),
            ("Owns Device", "owns_device"),
        ):
            action = menu.addAction(label)
            actions[action] = value
        chosen = menu.exec(QCursor.pos())
        relationship_type = actions.get(chosen)
        if relationship_type is not None:
            self.apply_requested_connection(source_block, target_block, relationship_type)

    def apply_requested_connection(  # type: ignore[no-untyped-def]
        self, source_block, target_block, relationship_type: str
    ) -> None:
        """Create the connector-drag's chosen relationship through the normal undo paths."""
        window = self.window
        if window.project is None:
            return
        if relationship_type == "requires":
            command = next(
                (
                    item
                    for item in window.project.commands
                    if item.id == source_block.element_id
                ),
                None,
            )
            if command is None or target_block.element_id in command.requirement_ids:
                return
            window.undo_stack.push(
                EditRequirementsCommand(
                    command,
                    [*command.requirement_ids, target_block.element_id],
                    window._requirements_changed,
                )
            )
            return
        window.add_relationship(
            relationship_type, source_block.element_id, target_block.element_id
        )

    # -- deletion ---------------------------------------------------------

    def confirm_delete_selected(self) -> None:
        window = self.window
        if window.diagram_tabs.currentWidget() is window._behavior_tab:
            window.delete_behavior_selected()
            return
        if not self.delete_selected():
            return

    def delete_selected(self) -> bool:
        """Delete one authored block, cascading its owned dependents as one undo entry."""
        window = self.window
        if window.project is None:
            return False
        blocks = window.scene.selected_blocks()
        if len(blocks) != 1 or blocks[0].imported:
            return False
        element_id = blocks[0].element_id
        element = next(
            (
                item
                for item in [*window.project.commands, *window.project.subsystems]
                if item.id == element_id
            ),
            None,
        )
        if element is None:
            return False
        # A command still requiring this subsystem is a real modelling error rather than an
        # ownership relation, so it stays a refusal — but one that names the commands.
        requiring = sorted(
            command.name.effective or "Unnamed"
            for command in window.project.commands
            if element_id in command.requirement_ids
        )
        if requiring:
            QMessageBox.warning(
                window,
                "Cannot delete selected element",
                f"{element.name.effective} is still required by "
                + ", ".join(requiring)
                + ". Clear that requirement first.",
            )
            return False
        devices = [
            device for device in window.project.devices if device.owner_subsystem_id == element_id
        ]
        triggers = [
            trigger for trigger in window.project.triggers if trigger.command_id == element_id
        ]
        relationships = [
            relationship
            for relationship in window.project.relationships
            if element_id in {relationship.source_id, relationship.target_id}
        ]
        summary = self._dependent_summary(
            [
                (len(devices), "device"),
                (len(triggers), "trigger"),
                (len(relationships), "relationship"),
            ]
        )
        if summary is not None:
            choice = QMessageBox.question(
                window,
                "Delete element and its dependents",
                f"Delete {element.name.effective} and its {summary}?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if choice != QMessageBox.StandardButton.Yes:
                return False
        collection = (
            window.project.commands
            if element in window.project.commands
            else window.project.subsystems
        )
        label = type(element).__name__.lower()
        window.undo_stack.beginMacro(f"Delete {label}")
        for kind, dependents in (
            ("device", devices),
            ("trigger", triggers),
            ("relationship", relationships),
        ):
            for dependent in dependents:
                window.undo_stack.push(
                    RemoveDesignEntityCommand(
                        self.owned_collection(kind), dependent, kind, self.refresh_after_edit
                    )
                )
        window.undo_stack.push(
            RemoveDesignEntityCommand(collection, element, label, self.refresh_after_edit)
        )
        window.undo_stack.endMacro()
        return True

    @staticmethod
    def _dependent_summary(counts: list[tuple[int, str]]) -> str | None:
        """Phrase the cascade as "2 devices, 1 trigger and 1 relationship"."""
        parts = [
            f"{count} {label if count == 1 else f'{label}s'}" for count, label in counts if count
        ]
        if not parts:
            return None
        if len(parts) == 1:
            return parts[0]
        return ", ".join(parts[:-1]) + f" and {parts[-1]}"

    def refresh_after_edit(self) -> None:
        window = self.window
        assert window.project is not None
        window.scene.render_project(
            window.project,
            scan=window.last_scan,
            allocation_findings=window._allocation_findings(),
        )
        window.new_device_action.setEnabled(bool(window.project.subsystems))
        window.new_trigger_action.setEnabled(bool(window.project.commands))
        window.new_relationship_action.setEnabled(
            len(window.project.commands) + len(window.project.subsystems) > 1
        )
        # Commands can gain/lose their model-browser node here too (e.g. add/delete command).
        window.behavior_model_browser.rebuild(
            window.project, window._selected_behavior_diagram_id
        )
        window.hardware_controller.refresh_table()
        window._update_structure_empty_state()
        window._sync_left_dock_to_active_tab(window.diagram_tabs.currentIndex())
        window._update_selected_element()
        window._mark_dirty(f"Unsaved design model: {window.project.name}")

    # -- owned objects on the details panel -------------------------------

    def selected_design_element(self):  # type: ignore[no-untyped-def]
        """Return the single authored element currently selected on the structure canvas."""
        window = self.window
        selected = window.scene.selected_blocks()
        if window.project is None or len(selected) != 1 or selected[0].imported:
            return None
        return next(
            (
                item
                for item in [*window.project.commands, *window.project.subsystems]
                if item.id == selected[0].element_id
            ),
            None,
        )

    def selected_device_id(self):  # type: ignore[no-untyped-def]
        """Return the id of the single device block selected on the canvas, if any."""
        blocks = self.window.scene.selected_device_blocks()
        return blocks[0].element_id if len(blocks) == 1 else None

    def reselect_element(self, element_id) -> None:  # type: ignore[no-untyped-def]
        """Keep the details panel on its element after an edit rebuilt the canvas."""
        window = self.window
        for item in window.scene.items():
            if isinstance(item, CanvasBlock) and item.element_id == element_id:
                item.setSelected(True)
        window._update_selected_element()

    def owned_collection(self, kind: str) -> list:  # type: ignore[type-arg]
        assert self.window.project is not None
        return {
            "device": self.window.project.devices,
            "trigger": self.window.project.triggers,
            "relationship": self.window.project.relationships,
        }[kind]

    def _owned_entity(self, kind: str, entity_id):  # type: ignore[no-untyped-def]
        return next(
            (item for item in self.owned_collection(kind) if item.id == entity_id), None
        )

    def add_owned_object(self, kind: str) -> None:
        """Create a device, trigger, or relationship owned by the selected element."""
        window = self.window
        element = self.selected_design_element()
        if window.project is None or element is None:
            return
        if kind == "device":
            dialog = DeviceDialog(window.project, parent=window)
            self._preselect(dialog.owner_combo, element.id)
            self.run_entity_dialog(dialog, window.add_device)
        elif kind == "trigger":
            dialog = TriggerDialog(window.project, parent=window)
            self._preselect(dialog.command_combo, element.id)
            self.run_entity_dialog(dialog, window.add_trigger)
        else:
            dialog = RelationshipDialog(window.project, parent=window)
            self._preselect(dialog.source_combo, element.id)
            self.run_entity_dialog(dialog, window.add_relationship)
        self.reselect_element(element.id)

    def edit_owned_object(self, kind: str, entity_id) -> None:  # type: ignore[no-untyped-def]
        """Edit an owned entity in place through the undo stack."""
        window = self.window
        element = self.selected_design_element()
        # A device edited from its own canvas block has no owning element selected, so
        # remember the block itself to reselect after the edit re-renders the scene.
        reselect_id = element.id if element is not None else self.selected_device_id()
        entity = self._owned_entity(kind, entity_id) if window.project is not None else None
        if window.project is None or entity is None:
            return
        if kind == "device":
            dialog = DeviceDialog(window.project, entity, parent=window)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            (
                owner_id,
                name,
                device_type,
                mode,
                bus,
                address,
                breaker_amps,
                mass_kg,
                notes,
            ) = dialog.values()
            fields = {
                "owner_subsystem_id": owner_id,
                "name": name,
                "device_type": device_type,
                "mode": mode,
                "bus": bus,
                "address": address,
                "breaker_amps": breaker_amps,
                "mass_kg": mass_kg,
                "notes": notes,
            }
        elif kind == "trigger":
            dialog = TriggerDialog(window.project, entity, parent=window)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            command_id, expression, activation = dialog.values()
            fields = {
                "command_id": command_id,
                "expression": expression,
                "activation": activation,
            }
        else:
            dialog = RelationshipDialog(window.project, entity, parent=window)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            relationship_type, source_id, target_id = dialog.values()
            fields = {
                "relationship_type": relationship_type,
                "source_id": source_id,
                "target_id": target_id,
            }
        window.undo_stack.push(
            EditEntityFieldsCommand(entity, fields, kind, self.refresh_after_edit)
        )
        if reselect_id is not None:
            self.reselect_element(reselect_id)

    def remove_owned_object(self, kind: str, entity_id) -> None:  # type: ignore[no-untyped-def]
        """Delete an owned entity from its owning element's details panel."""
        window = self.window
        element = self.selected_design_element()
        entity = self._owned_entity(kind, entity_id) if window.project is not None else None
        if entity is None:
            return
        window.undo_stack.push(
            RemoveDesignEntityCommand(
                self.owned_collection(kind), entity, kind, self.refresh_after_edit
            )
        )
        if element is not None:
            self.reselect_element(element.id)

    # -- dialogs ----------------------------------------------------------

    @staticmethod
    def _preselect(combo, value) -> None:  # type: ignore[no-untyped-def]
        """Point a dialog's owner/source picker at the element the panel is managing."""
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    def run_entity_dialog(self, dialog, create_entity) -> None:  # type: ignore[no-untyped-def]
        """Run one create dialog, honouring its "Add another" button without reopening it."""
        while True:
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            create_entity(*dialog.values())
            if not dialog.add_another_clicked:
                return
            dialog.add_another_clicked = False
            dialog.reset_for_another()

    def prompt_new_command(self) -> None:
        self._prompt_element("New command", self.window.add_command)

    def prompt_new_subsystem(self) -> None:
        self._prompt_element("New subsystem", self.window.add_subsystem)

    def prompt_new_device(self) -> None:
        window = self.window
        if window.project is None or not window.project.subsystems:
            return
        self.run_entity_dialog(
            DeviceDialog(window.project, parent=window), window.add_device
        )

    def prompt_new_trigger(self) -> None:
        window = self.window
        if window.project is None or not window.project.commands:
            return
        self.run_entity_dialog(
            TriggerDialog(window.project, parent=window), window.add_trigger
        )

    def prompt_new_relationship(self) -> None:
        window = self.window
        if window.project is None or len(window.project.commands) + len(
            window.project.subsystems
        ) < 2:
            return
        self.run_entity_dialog(
            RelationshipDialog(window.project, parent=window), window.add_relationship
        )

    def _prompt_element(self, title: str, create_element: Callable[[str], None]) -> None:
        name, accepted = QInputDialog.getText(self.window, title, "Name:")
        if accepted and name.strip():
            create_element(name.strip())
