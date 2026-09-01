"""Tree of behavior diagrams shown in the left dock while the Behavior tab is active.

A project can have several named behavior (activity) diagrams: some standalone at the
root level, others scoped to a specific command. This widget lists both groups, lets the
user create/rename/delete diagrams, and reports which one should be rendered on the
behavior canvas.
"""

from __future__ import annotations

from uuid import UUID

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QMenu, QTreeWidget, QTreeWidgetItem, QTreeWidgetItemIterator

from frc_arch_modeler.domain.model import ArchitectureProject


class BehaviorModelBrowser(QTreeWidget):
    """Root-level and per-command behavior diagrams, grouped for browsing and creation."""

    diagram_selected = Signal(object)  # UUID | None
    new_root_diagram_requested = Signal()
    new_command_diagram_requested = Signal(object)  # command UUID
    rename_requested = Signal(object)  # diagram UUID
    delete_requested = Signal(object)  # diagram UUID

    def __init__(self, parent=None) -> None:  # type: ignore[no-untyped-def]
        super().__init__(parent)
        self.setHeaderLabels(["Behavior Diagrams"])
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self.itemSelectionChanged.connect(self._handle_selection_changed)
        self.itemDoubleClicked.connect(self._handle_double_click)
        self._context_menu: QMenu | None = None

    def rebuild(
        self, project: ArchitectureProject | None, selected_diagram_id: UUID | None
    ) -> None:
        """Repopulate the tree from the project and re-select the active diagram, if any."""
        self.blockSignals(True)
        self.clear()
        if project is not None:
            root_header = QTreeWidgetItem(self, ["Root Diagrams"])
            root_header.setFlags(root_header.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            root_header.setExpanded(True)
            for diagram in project.behavior_diagrams:
                if diagram.owner_command_id is None:
                    item = QTreeWidgetItem(root_header, [diagram.name])
                    item.setData(0, Qt.ItemDataRole.UserRole, ("diagram", diagram.id))

            commands_header = QTreeWidgetItem(self, ["Commands"])
            commands_header.setFlags(commands_header.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            commands_header.setExpanded(True)
            for command in project.commands:
                command_item = QTreeWidgetItem(
                    commands_header, [command.name.effective or "Unnamed Command"]
                )
                command_item.setFlags(command_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
                command_item.setData(0, Qt.ItemDataRole.UserRole, ("command", command.id))
                command_item.setExpanded(True)
                for diagram in project.behavior_diagrams:
                    if diagram.owner_command_id == command.id:
                        item = QTreeWidgetItem(command_item, [diagram.name])
                        item.setData(0, Qt.ItemDataRole.UserRole, ("diagram", diagram.id))

            selected_item = self._find_diagram_item(selected_diagram_id)
            if selected_item is not None:
                selected_item.setSelected(True)
                self.scrollToItem(selected_item)
        self.blockSignals(False)

    def _find_diagram_item(self, diagram_id: UUID | None) -> QTreeWidgetItem | None:
        if diagram_id is None:
            return None
        iterator = QTreeWidgetItemIterator(self)
        item = iterator.value()
        while item is not None:
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(data, tuple) and data[0] == "diagram" and data[1] == diagram_id:
                return item
            iterator += 1
            item = iterator.value()
        return None

    def _handle_selection_changed(self) -> None:
        items = self.selectedItems()
        data = items[0].data(0, Qt.ItemDataRole.UserRole) if items else None
        if isinstance(data, tuple) and data[0] == "diagram":
            self.diagram_selected.emit(data[1])
        else:
            self.diagram_selected.emit(None)

    def _handle_double_click(self, item: QTreeWidgetItem, column: int) -> None:
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(data, tuple) and data[0] == "diagram":
            self.rename_requested.emit(data[1])

    def _show_context_menu(self, pos) -> None:  # type: ignore[no-untyped-def]
        item = self.itemAt(pos)
        data = item.data(0, Qt.ItemDataRole.UserRole) if item is not None else None
        menu = QMenu(self)
        if isinstance(data, tuple) and data[0] == "diagram":
            diagram_id = data[1]
            rename_action = menu.addAction("Rename…")
            rename_action.triggered.connect(lambda: self.rename_requested.emit(diagram_id))
            delete_action = menu.addAction("Delete")
            delete_action.triggered.connect(lambda: self.delete_requested.emit(diagram_id))
        elif isinstance(data, tuple) and data[0] == "command":
            command_id = data[1]
            new_action = menu.addAction("New Behavior Diagram…")
            new_action.triggered.connect(
                lambda: self.new_command_diagram_requested.emit(command_id)
            )
        else:
            new_action = menu.addAction("New Behavior Diagram…")
            new_action.triggered.connect(self.new_root_diagram_requested.emit)
        self._context_menu = menu
        menu.popup(self.viewport().mapToGlobal(pos))
