"""Editable layered design details for the selected architecture element."""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

from PySide6.QtCore import Qt
from PySide6.QtGui import QUndoCommand
from PySide6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from frc_arch_modeler.domain.model import Command, FieldValue, SourceAnchor, Subsystem
from frc_arch_modeler.ui.command_flow_widget import CommandFlowWidget

ArchitectureElement = Command | Subsystem

#: Owned-object sections offered beside "Required subsystems", in display order. Each is
#: shown only for the element kinds that can own that sort of object.
OWNED_KINDS = ("device", "trigger", "relationship")
OWNED_LABELS = {
    "device": "Devices",
    "trigger": "Triggers",
    "relationship": "Relationships",
}


class EditDescriptionCommand(QUndoCommand):
    """Undoable replacement of one user-authored description override."""

    def __init__(
        self, element: ArchitectureElement, description: str | None, on_change: Callable[[], None]
    ) -> None:
        super().__init__("Edit description")
        self.element = element
        self.previous = element.description.design
        self.description = description
        self.on_change = on_change

    def redo(self) -> None:
        self.element.description.design = self.description
        self.on_change()

    def undo(self) -> None:
        self.element.description.design = self.previous
        self.on_change()


class EditNameCommand(QUndoCommand):
    """Undoable replacement of the user-authored display-name override."""

    def __init__(
        self, element: ArchitectureElement, name: str | None, on_change: Callable[[], None]
    ) -> None:
        super().__init__("Edit name")
        self.element = element
        self.previous = element.name.design
        self.name = name
        self.on_change = on_change

    def redo(self) -> None:
        self.element.name.design = self.name
        self.on_change()

    def undo(self) -> None:
        self.element.name.design = self.previous
        self.on_change()


class EditRequirementsCommand(QUndoCommand):
    """Undoable replacement of a command's designed subsystem requirements."""

    def __init__(
        self, element: Command, requirement_ids: list[UUID], on_change: Callable[[], None]
    ) -> None:
        super().__init__("Edit requirements")
        self.element = element
        self.previous = list(element.requirement_ids)
        self.requirement_ids = list(requirement_ids)
        self.on_change = on_change

    def redo(self) -> None:
        self.element.requirement_ids = list(self.requirement_ids)
        self.on_change()

    def undo(self) -> None:
        self.element.requirement_ids = list(self.previous)
        self.on_change()


class EditEntityFieldsCommand(QUndoCommand):
    """Undoable in-place edit of one owned entity's fields.

    ``fields`` maps an attribute name to its new value. A ``FieldValue`` attribute keeps
    its scanned fact and evidence untouched: only the design override is snapshotted and
    replaced, so an in-place edit never overwrites code-derived facts.
    """

    def __init__(
        self,
        entity: object,
        fields: dict[str, object],
        label: str,
        on_change: Callable[[], None],
    ) -> None:
        super().__init__(f"Edit {label}")
        self.entity = entity
        self.fields = dict(fields)
        self.previous = {name: self._read(entity, name) for name in self.fields}
        self.on_change = on_change

    @staticmethod
    def _read(entity: object, name: str) -> object:
        current = getattr(entity, name)
        return current.design if isinstance(current, FieldValue) else current

    @staticmethod
    def _write(entity: object, name: str, value: object) -> None:
        current = getattr(entity, name)
        if isinstance(current, FieldValue):
            current.design = value  # type: ignore[assignment]
        else:
            setattr(entity, name, value)

    def _apply(self, values: dict[str, object]) -> None:
        for name, value in values.items():
            self._write(self.entity, name, value)
        self.on_change()

    def redo(self) -> None:
        self._apply(self.fields)

    def undo(self) -> None:
        self._apply(self.previous)


class DetailsPanel(QWidget):
    """Shows code evidence beside the editable user-authored description."""

    def __init__(
        self,
        on_description_edit: Callable[[str | None], None],
        on_name_edit: Callable[[str | None], None],
        on_requirements_edit: Callable[[list[UUID]], None],
        on_open_source: Callable[[SourceAnchor], None] | None = None,
        on_owned_add: Callable[[str], None] | None = None,
        on_owned_edit: Callable[[str, UUID], None] | None = None,
        on_owned_remove: Callable[[str, UUID], None] | None = None,
    ) -> None:
        super().__init__()
        self._on_description_edit = on_description_edit
        self._on_name_edit = on_name_edit
        self._on_requirements_edit = on_requirements_edit
        self._on_owned_add = on_owned_add
        self._on_owned_edit = on_owned_edit
        self._on_owned_remove = on_owned_remove
        self._owned_lists: dict[str, QListWidget] = {}
        self._owned_rows: dict[str, QWidget] = {}
        self._owned_labels: dict[str, QLabel] = {}
        self._owned_buttons: dict[str, dict[str, QPushButton]] = {}
        self._owned_objects: dict[str, list[tuple[UUID, str]]] = {}
        self._element: ArchitectureElement | None = None
        self._source_anchor: SourceAnchor | None = None
        self._code_name: str | None = None
        self._code_description: str | None = None
        self._lifecycle_anchors: dict[str, SourceAnchor] = {}
        self._on_open_source = on_open_source
        layout = QVBoxLayout(self)
        self.title = QLabel("Select a command or subsystem to inspect its details.", self)
        self.title.setObjectName("detailsTitle")
        self.code_description = QLabel("No code-derived description available.", self)
        self.code_description.setObjectName("codeDescription")
        self.code_description.setWordWrap(True)
        self.code_name = QLabel("No code-derived name available.", self)
        self.code_name.setObjectName("codeName")
        self.code_name.setWordWrap(True)
        self.lifecycle_flow = QLabel(self)
        self.lifecycle_flow.setObjectName("lifecycleFlow")
        self.lifecycle_flow.setWordWrap(True)
        self.lifecycle_diagram = CommandFlowWidget(self)
        self.lifecycle_diagram.phase_activated.connect(self._open_lifecycle_source)
        self.design_context = QLabel(self)
        self.design_context.setObjectName("designContext")
        self.design_context.setWordWrap(True)
        self.design_name = QLineEdit(self)
        self.design_name.setObjectName("designName")
        self.design_name.setAccessibleName("Proposed architecture name")
        self.design_name.setPlaceholderText("Proposed display name")
        self.design_description = QTextEdit(self)
        self.design_description.setObjectName("designDescription")
        self.design_description.setAccessibleName("Proposed architecture description")
        self.design_description.setPlaceholderText("Optional proposed description")
        self.requirements = QListWidget(self)
        self.requirements.setObjectName("designRequirements")
        self.requirements.setAccessibleName("Proposed command subsystem requirements")
        self.save_button = QPushButton("Apply Proposed Fields", self)
        self.revert_button = QPushButton("Revert Proposed Description", self)
        self.adopt_description_button = QPushButton("Adopt Code Description", self)
        self.adopt_name_button = QPushButton("Adopt Code Name", self)
        self.revert_name_button = QPushButton("Revert Proposed Name", self)
        self.open_source_button = QPushButton("Open Source", self)
        form = QFormLayout()
        form.addRow("Name from code", self.code_name)
        form.addRow("Design / proposed name", self.design_name)
        form.addRow("From code", self.code_description)
        form.addRow("Lifecycle / flow", self.lifecycle_flow)
        form.addRow("", self.lifecycle_diagram)
        form.addRow("Design structure", self.design_context)
        form.addRow("Design / proposed", self.design_description)
        form.addRow("Required subsystems", self.requirements)
        for kind in OWNED_KINDS:
            label = QLabel(OWNED_LABELS[kind], self)
            self._owned_labels[kind] = label
            form.addRow(label, self._build_owned_section(kind))
        layout.addWidget(self.title)
        layout.addLayout(form)
        layout.addWidget(self.save_button)
        layout.addWidget(self.revert_button)
        layout.addWidget(self.adopt_description_button)
        layout.addWidget(self.adopt_name_button)
        layout.addWidget(self.revert_name_button)
        layout.addWidget(self.open_source_button)
        layout.addStretch()
        self.save_button.clicked.connect(self._apply_description)
        self.revert_button.clicked.connect(self._revert_description)
        self.adopt_description_button.clicked.connect(self._adopt_code_description)
        self.adopt_name_button.clicked.connect(self._adopt_code_name)
        self.revert_name_button.clicked.connect(self._revert_name)
        self.open_source_button.clicked.connect(self._open_source)
        self._set_editing_enabled(False)
        self._set_owned_objects(None, {})

    def _build_owned_section(self, kind: str) -> QWidget:
        """Build one owned-object list with the Add / Edit / Remove management buttons."""
        container = QWidget(self)
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        list_widget = QListWidget(container)
        list_widget.setObjectName(f"owned{kind.capitalize()}s")
        list_widget.setAccessibleName(f"Owned {kind}s of the selected element")
        container_layout.addWidget(list_widget)
        button_row = QHBoxLayout()
        buttons: dict[str, QPushButton] = {}
        for action, handler in (
            ("add", self._add_owned),
            ("edit", self._edit_owned),
            ("remove", self._remove_owned),
        ):
            button = QPushButton(action.capitalize(), container)
            button.setObjectName(f"{action}{kind.capitalize()}Button")
            button.clicked.connect(lambda _checked=False, k=kind, h=handler: h(k))
            button_row.addWidget(button)
            buttons[action] = button
        container_layout.addLayout(button_row)
        list_widget.itemSelectionChanged.connect(
            lambda k=kind: self._update_owned_buttons(k)
        )
        self._owned_lists[kind] = list_widget
        self._owned_rows[kind] = container
        self._owned_buttons[kind] = buttons
        return container

    def set_element(
        self,
        element: ArchitectureElement | None,
        code_name: str | None = None,
        code_description: str | None = None,
        code_anchor: SourceAnchor | None = None,
        subsystem_options: list[tuple[UUID, str]] | None = None,
        design_context: str | None = None,
        owned_objects: dict[str, list[tuple[UUID, str]]] | None = None,
    ) -> None:
        self._element = element
        self._owned_objects = dict(owned_objects or {})
        self._source_anchor = code_anchor
        self._code_name = code_name
        self._code_description = code_description
        if element is None:
            self.title.setText("Select a command or subsystem to inspect its details.")
            self.code_description.setText("No code-derived description available.")
            self.code_name.setText("No code-derived name available.")
            self._code_description = None
            self.design_name.clear()
            self.design_description.clear()
            self.requirements.clear()
            self.requirements.setVisible(False)
            self.lifecycle_flow.clear()
            self.lifecycle_flow.setVisible(False)
            self.lifecycle_diagram.set_phases([])
            self.design_context.clear()
            self.design_context.setVisible(False)
            self._set_owned_objects(None, {})
            self._set_editing_enabled(False)
            self.open_source_button.setEnabled(False)
            self.adopt_name_button.setEnabled(False)
            self.adopt_description_button.setEnabled(False)
            self.revert_name_button.setEnabled(False)
            return
        self.title.setText(f"{element.name.effective} ({type(element).__name__})")
        effective_code_name = code_name or element.name.scanned
        self.code_name.setText(effective_code_name or "No code-derived name available.")
        self.design_name.setText(element.name.design or element.name.effective or "")
        self._code_description = code_description or element.description.scanned
        self.code_description.setText(
            self._code_description or "No code-derived description available."
        )
        self.design_description.setPlainText(element.description.design or "")
        self.lifecycle_flow.clear()
        self.lifecycle_flow.setVisible(False)
        self.lifecycle_diagram.set_phases([])
        self.design_context.setText(design_context or "")
        self.design_context.setVisible(bool(design_context))
        self._set_requirement_options(element, subsystem_options or [])
        self._set_owned_objects(element, self._owned_objects)
        self._set_editing_enabled(True)
        self.open_source_button.setEnabled(
            code_anchor is not None and self._on_open_source is not None
        )
        self.adopt_name_button.setEnabled(effective_code_name is not None)
        self.revert_name_button.setEnabled(element.name.design is not None)
        self.adopt_description_button.setEnabled(self._code_description is not None)

    def set_imported_fact(
        self,
        label: str,
        kind: str,
        anchor: SourceAnchor,
        documentation: str | None = None,
        lifecycle_methods: list[str] | None = None,
        lifecycle_anchors: dict[str, SourceAnchor] | None = None,
        show_lifecycle: bool = False,
        custom_flow_phases: list[str] | None = None,
    ) -> None:
        """Present selected regenerated code evidence without enabling design edits."""
        self._element = None
        self._source_anchor = anchor
        self._code_name = label
        self._code_description = documentation
        self._lifecycle_anchors = lifecycle_anchors or {}
        self.title.setText(f"{label} (imported {kind})")
        self.code_name.setText(label)
        self.design_name.clear()
        summary = documentation or "No attached JavaDoc was extracted."
        self.code_description.setText(
            f"{summary}\n\nCode-derived {kind} at {anchor.relative_path}:{anchor.start_line}.\n"
            f"Symbol: {anchor.qualified_symbol}\nConfidence: exact"
        )
        if kind == "command" and custom_flow_phases:
            self.lifecycle_flow.setText(" → ".join(custom_flow_phases))
            self.lifecycle_flow.setVisible(True)
            self.lifecycle_diagram.set_phases(custom_flow_phases)
        elif kind == "command" and show_lifecycle:
            overridden = set(lifecycle_methods or [])
            phases = [
                "Start",
                *[
                    f"{display}{'' if method in overridden else ' (inherited)'}"
                    for display, method in (
                        ("initialize", "initialize"),
                        ("execute", "execute"),
                        ("isFinished", "isFinished"),
                        ("end(interrupted)", "end"),
                    )
                ],
            ]
            self.lifecycle_flow.setText(" → ".join(phases))
            self.lifecycle_flow.setVisible(True)
            self.lifecycle_diagram.set_phases(phases)
        else:
            self.lifecycle_flow.clear()
            self.lifecycle_flow.setVisible(False)
            self.lifecycle_diagram.set_phases([])
        self.design_description.clear()
        self.design_context.clear()
        self.design_context.setVisible(False)
        self.requirements.clear()
        self.requirements.setVisible(False)
        self._owned_objects = {}
        self._set_owned_objects(None, {})
        self._set_editing_enabled(False)
        self.open_source_button.setEnabled(self._on_open_source is not None)
        self.adopt_name_button.setEnabled(False)
        self.adopt_description_button.setEnabled(False)
        self.revert_name_button.setEnabled(False)

    def _open_lifecycle_source(self, display_phase: str) -> None:
        """Open only an explicit override; inherited phases deliberately have no source link."""
        phase = "end" if display_phase.startswith("end(") else display_phase.split(" ", 1)[0]
        anchor = self._lifecycle_anchors.get(phase)
        if anchor is not None and self._on_open_source is not None:
            self._on_open_source(anchor)

    def refresh(self) -> None:
        self.set_element(self._element, owned_objects=self._owned_objects)

    def _set_editing_enabled(self, enabled: bool) -> None:
        self.design_name.setEnabled(enabled)
        self.design_description.setEnabled(enabled)
        self.save_button.setEnabled(enabled)
        self.revert_button.setEnabled(enabled)

    def _set_requirement_options(
        self, element: ArchitectureElement, subsystem_options: list[tuple[UUID, str]]
    ) -> None:
        self.requirements.clear()
        is_command = isinstance(element, Command)
        self.requirements.setVisible(is_command)
        if not is_command:
            return
        selected = set(element.requirement_ids)
        for subsystem_id, name in subsystem_options:
            item = QListWidgetItem(name, self.requirements)
            item.setData(Qt.ItemDataRole.UserRole, str(subsystem_id))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked if subsystem_id in selected else Qt.CheckState.Unchecked
            )

    def _set_owned_objects(
        self,
        element: ArchitectureElement | None,
        owned_objects: dict[str, list[tuple[UUID, str]]],
    ) -> None:
        """List what the selected element owns, hiding sections it cannot own."""
        manageable = self._on_owned_add is not None
        owns = {
            "device": isinstance(element, Subsystem),
            "trigger": isinstance(element, Command),
            "relationship": element is not None,
        }
        for kind in OWNED_KINDS:
            list_widget = self._owned_lists[kind]
            list_widget.clear()
            for entity_id, label in owned_objects.get(kind, []):
                item = QListWidgetItem(label, list_widget)
                item.setData(Qt.ItemDataRole.UserRole, str(entity_id))
            visible = manageable and owns[kind]
            self._owned_labels[kind].setVisible(visible)
            self._owned_rows[kind].setVisible(visible)
            self._update_owned_buttons(kind)

    def _update_owned_buttons(self, kind: str) -> None:
        buttons = self._owned_buttons[kind]
        has_selection = self._owned_lists[kind].currentItem() is not None
        buttons["add"].setEnabled(self._element is not None)
        buttons["edit"].setEnabled(has_selection)
        buttons["remove"].setEnabled(has_selection)

    def _selected_owned_id(self, kind: str) -> UUID | None:
        item = self._owned_lists[kind].currentItem()
        return None if item is None else UUID(item.data(Qt.ItemDataRole.UserRole))

    def _add_owned(self, kind: str) -> None:
        if self._element is not None and self._on_owned_add is not None:
            self._on_owned_add(kind)

    def _edit_owned(self, kind: str) -> None:
        entity_id = self._selected_owned_id(kind)
        if entity_id is not None and self._on_owned_edit is not None:
            self._on_owned_edit(kind, entity_id)

    def _remove_owned(self, kind: str) -> None:
        entity_id = self._selected_owned_id(kind)
        if entity_id is not None and self._on_owned_remove is not None:
            self._on_owned_remove(kind, entity_id)

    def _apply_description(self) -> None:
        if self._element is not None:
            name = self.design_name.text().strip()
            if name:
                self._on_name_edit(name)
            description = self.design_description.toPlainText().strip() or None
            self._on_description_edit(description)
            if isinstance(self._element, Command):
                requirement_ids = [
                    UUID(item.data(Qt.ItemDataRole.UserRole))
                    for index in range(self.requirements.count())
                    if (item := self.requirements.item(index)).checkState()
                    == Qt.CheckState.Checked
                ]
                self._on_requirements_edit(requirement_ids)

    def _revert_description(self) -> None:
        if self._element is not None:
            self._on_description_edit(None)

    def _adopt_code_description(self) -> None:
        if self._element is not None and self._code_description is not None:
            self._on_description_edit(self._code_description)

    def _adopt_code_name(self) -> None:
        if self._element is not None and self._code_name is not None:
            self._on_name_edit(self._code_name)

    def _revert_name(self) -> None:
        if self._element is not None:
            self._on_name_edit(None)

    def _open_source(self) -> None:
        if self._source_anchor is not None and self._on_open_source is not None:
            self._on_open_source(self._source_anchor)
