"""The Behavior tab: diagram selection, state and transition editing, model browser."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import QInputDialog, QMessageBox

from frc_arch_modeler.domain.model import BehaviorDiagram
from frc_arch_modeler.ui.details_panel import EditNameCommand
from frc_arch_modeler.ui.undo_commands import (
    AddDesignEntityCommand,
    EditTransitionEndpointsCommand,
    MoveBlocksCommand,
    RemoveDesignEntityCommand,
    RenameBehaviorDiagramCommand,
)

if TYPE_CHECKING:
    from frc_arch_modeler.ui.main_window import MainWindow

PSEUDOSTATE_LABELS = {
    "start": "Start",
    "end": "End",
    "decision": "Decision",
    "synchronization": "Sync",
    "join": "Join",
}


class BehaviorController:
    """Own which behavior diagram is active and every edit made to it."""

    def __init__(self, window: MainWindow) -> None:
        self.window = window
        self.selected_diagram_id: object = None

    # -- diagram selection ------------------------------------------------

    def active_diagram(self) -> BehaviorDiagram | None:
        """Return the behavior diagram currently selected in the model browser, if any."""
        window = self.window
        if window.project is None:
            return None
        return next(
            (
                diagram
                for diagram in window.project.behavior_diagrams
                if diagram.id == self.selected_diagram_id
            ),
            None,
        )

    def select_diagram(self, diagram_id: object) -> None:
        """Switch which diagram is rendered/edited, driven by the model browser's selection."""
        self.selected_diagram_id = diagram_id
        self.window.behavior_scene.render_diagram(self.active_diagram())
        self.window._update_delete_selected_action()

    def add_root_diagram(self) -> None:
        self._create_diagram(owner_command_id=None)

    def add_command_diagram(self, command_id: object) -> None:
        self._create_diagram(owner_command_id=command_id)

    def _create_diagram(self, owner_command_id: object) -> None:
        window = self.window
        if window.project is None:
            return
        diagram = window.project_service.add_behavior_diagram(
            window.project, "Untitled Diagram", owner_command_id
        )
        window.project.behavior_diagrams.remove(diagram)
        window.undo_stack.push(
            AddDesignEntityCommand(
                window.project.behavior_diagrams,
                diagram,
                "behavior diagram",
                self.refresh_after_edit,
            )
        )
        self.selected_diagram_id = diagram.id
        self.refresh_after_edit()

    def rename_diagram(self, diagram_id: object) -> None:
        diagram = self._diagram_by_id(diagram_id)
        if diagram is None:
            return
        name, accepted = QInputDialog.getText(
            self.window, "Rename diagram", "Diagram name:", text=diagram.name
        )
        if accepted and name.strip() and name.strip() != diagram.name:
            self.window.undo_stack.push(
                RenameBehaviorDiagramCommand(diagram, name.strip(), self.refresh_after_edit)
            )

    def delete_diagram(self, diagram_id: object) -> None:
        window = self.window
        diagram = self._diagram_by_id(diagram_id)
        if diagram is None:
            return
        if self.selected_diagram_id == diagram_id:
            self.selected_diagram_id = None
        window.undo_stack.push(
            RemoveDesignEntityCommand(
                window.project.behavior_diagrams,
                diagram,
                "behavior diagram",
                self.refresh_after_edit,
            )
        )

    def _diagram_by_id(self, diagram_id: object) -> BehaviorDiagram | None:
        project = self.window.project
        return next(
            (
                item
                for item in (project.behavior_diagrams if project else [])
                if item.id == diagram_id
            ),
            None,
        )

    # -- states and transitions -------------------------------------------

    def add_state(self, name: str, kind: str = "state") -> None:
        """Add a state (or pseudostate) to the active diagram, creating one first if needed."""
        window = self.window
        if window.project is None:
            return
        diagram = self.active_diagram()
        if diagram is None:
            diagram = window.project_service.add_behavior_diagram(
                window.project, "Untitled Diagram"
            )
            window.project.behavior_diagrams.remove(diagram)
            window.undo_stack.push(
                AddDesignEntityCommand(
                    window.project.behavior_diagrams,
                    diagram,
                    "behavior diagram",
                    self.refresh_after_edit,
                )
            )
            self.selected_diagram_id = diagram.id
        state = window.project_service.add_behavior_state(diagram, name, kind=kind)
        diagram.states.remove(state)
        window.undo_stack.push(
            AddDesignEntityCommand(diagram.states, state, "state", self.refresh_after_edit)
        )

    def add_pseudostate(self, kind: str) -> None:
        """Drop a SysML start/end/decision/synchronization/join node onto the behavior diagram."""
        self.add_state(PSEUDOSTATE_LABELS[kind], kind=kind)

    def add_transition(  # type: ignore[no-untyped-def]
        self, source_state_id, target_state_id, trigger_label: str
    ) -> None:
        """Add a transition to the active behavior diagram through the normal undo path."""
        window = self.window
        diagram = self.active_diagram()
        if diagram is None:
            return
        transition = window.project_service.add_behavior_transition(
            diagram, source_state_id, target_state_id, trigger_label
        )
        diagram.transitions.remove(transition)
        window.undo_stack.push(
            AddDesignEntityCommand(
                diagram.transitions, transition, "transition", self.refresh_after_edit
            )
        )

    def delete_selected(self) -> bool:
        """Delete one selected transition, or one state with no transition depending on it."""
        window = self.window
        diagram = self.active_diagram()
        if diagram is None:
            return False
        blocks = window.behavior_scene.selected_blocks()
        transition_ids = window.behavior_scene.selected_transition_ids()
        if len(transition_ids) == 1 and not blocks:
            self.delete_transition(transition_ids[0])
            return True
        if len(blocks) != 1:
            return False
        state_id = blocks[0].state_id
        state = next((item for item in diagram.states if item.id == state_id), None)
        if state is None:
            return False
        dependent = [
            transition
            for transition in diagram.transitions
            if state_id in {transition.source_state_id, transition.target_state_id}
        ]
        if dependent:
            QMessageBox.warning(
                window,
                "Cannot delete selected state",
                "Remove dependent transition(s) first.",
            )
            return False
        window.undo_stack.push(
            RemoveDesignEntityCommand(diagram.states, state, "state", self.refresh_after_edit)
        )
        return True

    def delete_transition(self, transition_id: object) -> None:
        """Delete one transition, e.g. from its right-click context menu."""
        diagram = self.active_diagram()
        if diagram is None:
            return
        transition = next(
            (item for item in diagram.transitions if item.id == transition_id), None
        )
        if transition is None:
            return
        self.window.undo_stack.push(
            RemoveDesignEntityCommand(
                diagram.transitions, transition, "transition", self.refresh_after_edit
            )
        )

    def reattach_transition(
        self, transition_id: object, end: str, new_state_id: object
    ) -> None:
        """Rewire a transition's dragged endpoint to a different state through undo."""
        diagram = self.active_diagram()
        if diagram is None:
            return
        transition = next(
            (item for item in diagram.transitions if item.id == transition_id), None
        )
        if transition is None:
            return
        new_source_id = new_state_id if end == "source" else transition.source_state_id
        new_target_id = new_state_id if end == "target" else transition.target_state_id
        self.window.undo_stack.push(
            EditTransitionEndpointsCommand(
                transition, new_source_id, new_target_id, self.refresh_after_edit
            )
        )

    # -- canvas interaction -----------------------------------------------

    def handle_connection_requested(self, source_block, target_block, drop_pos) -> None:  # type: ignore[no-untyped-def]
        """Prompt for the triggering event, then add the dragged state transition."""
        if self.active_diagram() is None:
            return
        trigger_label, accepted = QInputDialog.getText(
            self.window, "New transition", "Trigger / event:"
        )
        if accepted:
            self.add_transition(
                source_block.state_id, target_block.state_id, trigger_label.strip()
            )

    def prompt_rename_state(self, block) -> None:  # type: ignore[no-untyped-def]
        """Rename a behavior state via a lightweight prompt (no dedicated details panel yet)."""
        diagram = self.active_diagram()
        if diagram is None:
            return
        state = next((item for item in diagram.states if item.id == block.state_id), None)
        if state is None:
            return
        name, accepted = QInputDialog.getText(
            self.window, "Rename state", "State name:", text=state.name.effective or ""
        )
        if accepted and name.strip() and name.strip() != state.name.effective:
            self.window.undo_stack.push(
                EditNameCommand(state, name.strip(), self.refresh_after_edit)
            )

    def prompt_new_state(self) -> None:
        if self.window.project is None:
            return
        name, accepted = QInputDialog.getText(self.window, "New state", "State name:")
        if accepted and name.strip():
            self.add_state(name.strip())

    def record_layout_move(self, before, after) -> None:  # type: ignore[no-untyped-def]
        self.window.undo_stack.push(
            MoveBlocksCommand(
                self.window.behavior_scene, before, after, self.window._layout_changed
            )
        )

    def layout_changed(self) -> None:
        """A transition's connection point moved without changing the entity it connects to."""
        self.window._mark_dirty("Canvas layout updated")

    def refresh_after_edit(self) -> None:
        window = self.window
        assert window.project is not None
        window.behavior_scene.render_diagram(
            self.active_diagram(), window.behavior_scene.layout_state()
        )
        window.behavior_model_browser.rebuild(window.project, self.selected_diagram_id)
        window._mark_dirty(f"Unsaved design model: {window.project.name}")
