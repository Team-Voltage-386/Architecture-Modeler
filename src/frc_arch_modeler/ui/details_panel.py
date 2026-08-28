"""Editable layered design details for the selected architecture element."""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

from PySide6.QtCore import Qt
from PySide6.QtGui import QUndoCommand
from PySide6.QtWidgets import (
    QFormLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from frc_arch_modeler.domain.model import Command, SourceAnchor, Subsystem

ArchitectureElement = Command | Subsystem


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
        self, element: ArchitectureElement, name: str, on_change: Callable[[], None]
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


class DetailsPanel(QWidget):
    """Shows code evidence beside the editable user-authored description."""

    def __init__(
        self,
        on_description_edit: Callable[[str | None], None],
        on_name_edit: Callable[[str], None],
        on_requirements_edit: Callable[[list[UUID]], None],
        on_open_source: Callable[[SourceAnchor], None] | None = None,
    ) -> None:
        super().__init__()
        self._on_description_edit = on_description_edit
        self._on_name_edit = on_name_edit
        self._on_requirements_edit = on_requirements_edit
        self._element: ArchitectureElement | None = None
        self._source_anchor: SourceAnchor | None = None
        self._code_name: str | None = None
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
        self.revert_button = QPushButton("Revert Design Override", self)
        self.adopt_name_button = QPushButton("Adopt Code Name", self)
        self.open_source_button = QPushButton("Open Source", self)
        form = QFormLayout()
        form.addRow("Name from code", self.code_name)
        form.addRow("Design / proposed name", self.design_name)
        form.addRow("From code", self.code_description)
        form.addRow("Lifecycle / flow", self.lifecycle_flow)
        form.addRow("Design / proposed", self.design_description)
        form.addRow("Required subsystems", self.requirements)
        layout.addWidget(self.title)
        layout.addLayout(form)
        layout.addWidget(self.save_button)
        layout.addWidget(self.revert_button)
        layout.addWidget(self.adopt_name_button)
        layout.addWidget(self.open_source_button)
        layout.addStretch()
        self.save_button.clicked.connect(self._apply_description)
        self.revert_button.clicked.connect(self._revert_description)
        self.adopt_name_button.clicked.connect(self._adopt_code_name)
        self.open_source_button.clicked.connect(self._open_source)
        self._set_editing_enabled(False)

    def set_element(
        self,
        element: ArchitectureElement | None,
        code_name: str | None = None,
        code_description: str | None = None,
        code_anchor: SourceAnchor | None = None,
        subsystem_options: list[tuple[UUID, str]] | None = None,
    ) -> None:
        self._element = element
        self._source_anchor = code_anchor
        self._code_name = code_name
        if element is None:
            self.title.setText("Select a command or subsystem to inspect its details.")
            self.code_description.setText("No code-derived description available.")
            self.code_name.setText("No code-derived name available.")
            self.design_name.clear()
            self.design_description.clear()
            self.requirements.clear()
            self.requirements.setVisible(False)
            self.lifecycle_flow.clear()
            self.lifecycle_flow.setVisible(False)
            self._set_editing_enabled(False)
            self.open_source_button.setEnabled(False)
            self.adopt_name_button.setEnabled(False)
            return
        self.title.setText(f"{element.name.effective} ({type(element).__name__})")
        effective_code_name = code_name or element.name.scanned
        self.code_name.setText(effective_code_name or "No code-derived name available.")
        self.design_name.setText(element.name.design or element.name.effective or "")
        self.code_description.setText(
            code_description
            or element.description.scanned
            or "No code-derived description available."
        )
        self.design_description.setPlainText(element.description.design or "")
        self.lifecycle_flow.clear()
        self.lifecycle_flow.setVisible(False)
        self._set_requirement_options(element, subsystem_options or [])
        self._set_editing_enabled(True)
        self.open_source_button.setEnabled(
            code_anchor is not None and self._on_open_source is not None
        )
        self.adopt_name_button.setEnabled(effective_code_name is not None)

    def set_imported_fact(
        self,
        label: str,
        kind: str,
        anchor: SourceAnchor,
        documentation: str | None = None,
        lifecycle_methods: list[str] | None = None,
    ) -> None:
        """Present selected regenerated code evidence without enabling design edits."""
        self._element = None
        self._source_anchor = anchor
        self._code_name = label
        self.title.setText(f"{label} (imported {kind})")
        self.code_name.setText(label)
        self.design_name.clear()
        summary = documentation or "No attached JavaDoc was extracted."
        self.code_description.setText(
            f"{summary}\n\nCode-derived {kind} at {anchor.relative_path}:{anchor.start_line}.\n"
            f"Symbol: {anchor.qualified_symbol}\nConfidence: exact"
        )
        if kind == "command":
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
        else:
            self.lifecycle_flow.clear()
            self.lifecycle_flow.setVisible(False)
        self.design_description.clear()
        self.requirements.clear()
        self.requirements.setVisible(False)
        self._set_editing_enabled(False)
        self.open_source_button.setEnabled(self._on_open_source is not None)
        self.adopt_name_button.setEnabled(False)

    def refresh(self) -> None:
        self.set_element(self._element)

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

    def _adopt_code_name(self) -> None:
        if self._element is not None and self._code_name is not None:
            self._on_name_edit(self._code_name)

    def _open_source(self) -> None:
        if self._source_anchor is not None and self._on_open_source is not None:
            self._on_open_source(self._source_anchor)
