"""Undoable design edits shared by the main window's controllers.

Every design edit reaches the model through one of these commands so a single
Ctrl+Z reverses it, and so a cascading delete can be grouped into one macro.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtGui import QUndoCommand

from frc_arch_modeler.domain.model import BehaviorDiagram
from frc_arch_modeler.ui.architecture_scene import ArchitectureScene


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


class EditTransitionEndpointsCommand(QUndoCommand):
    """Undoable rewire of a behavior transition's source or target state."""

    def __init__(
        self,
        transition: object,
        source_state_id: object,
        target_state_id: object,
        on_change: Callable[[], None],
    ) -> None:
        super().__init__("Reconnect transition")
        self.transition = transition
        self.previous = (transition.source_state_id, transition.target_state_id)
        self.next = (source_state_id, target_state_id)
        self.on_change = on_change

    def redo(self) -> None:
        self.transition.source_state_id, self.transition.target_state_id = self.next
        self.on_change()

    def undo(self) -> None:
        self.transition.source_state_id, self.transition.target_state_id = self.previous
        self.on_change()


class RenameBehaviorDiagramCommand(QUndoCommand):
    """Undoable rename of a behavior diagram (plain str name, unlike FieldValue-backed entities)."""

    def __init__(
        self, diagram: BehaviorDiagram, name: str, on_change: Callable[[], None]
    ) -> None:
        super().__init__("Rename behavior diagram")
        self.diagram = diagram
        self.previous = diagram.name
        self.name = name
        self.on_change = on_change

    def redo(self) -> None:
        self.diagram.name = self.name
        self.on_change()

    def undo(self) -> None:
        self.diagram.name = self.previous
        self.on_change()
