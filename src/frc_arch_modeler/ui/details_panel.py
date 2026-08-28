"""Editable layered design details for the selected architecture element."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtGui import QUndoCommand
from PySide6.QtWidgets import (
    QFormLayout,
    QLabel,
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


class DetailsPanel(QWidget):
    """Shows code evidence beside the editable user-authored description."""

    def __init__(
        self,
        on_description_edit: Callable[[str | None], None],
        on_open_source: Callable[[SourceAnchor], None] | None = None,
    ) -> None:
        super().__init__()
        self._on_description_edit = on_description_edit
        self._element: ArchitectureElement | None = None
        self._source_anchor: SourceAnchor | None = None
        self._on_open_source = on_open_source
        layout = QVBoxLayout(self)
        self.title = QLabel("Select a command or subsystem to inspect its details.", self)
        self.title.setObjectName("detailsTitle")
        self.code_description = QLabel("No code-derived description available.", self)
        self.code_description.setObjectName("codeDescription")
        self.code_description.setWordWrap(True)
        self.design_description = QTextEdit(self)
        self.design_description.setObjectName("designDescription")
        self.design_description.setPlaceholderText("Optional proposed description")
        self.save_button = QPushButton("Apply Description", self)
        self.revert_button = QPushButton("Revert Design Override", self)
        self.open_source_button = QPushButton("Open Source", self)
        form = QFormLayout()
        form.addRow("From code", self.code_description)
        form.addRow("Design / proposed", self.design_description)
        layout.addWidget(self.title)
        layout.addLayout(form)
        layout.addWidget(self.save_button)
        layout.addWidget(self.revert_button)
        layout.addWidget(self.open_source_button)
        layout.addStretch()
        self.save_button.clicked.connect(self._apply_description)
        self.revert_button.clicked.connect(self._revert_description)
        self.open_source_button.clicked.connect(self._open_source)
        self._set_editing_enabled(False)

    def set_element(self, element: ArchitectureElement | None) -> None:
        self._element = element
        self._source_anchor = None
        if element is None:
            self.title.setText("Select a command or subsystem to inspect its details.")
            self.code_description.setText("No code-derived description available.")
            self.design_description.clear()
            self._set_editing_enabled(False)
            self.open_source_button.setEnabled(False)
            return
        self.title.setText(f"{element.name.effective} ({type(element).__name__})")
        self.code_description.setText(
            element.description.scanned or "No code-derived description available."
        )
        self.design_description.setPlainText(element.description.design or "")
        self._set_editing_enabled(True)
        self.open_source_button.setEnabled(False)

    def set_imported_fact(
        self, label: str, kind: str, anchor: SourceAnchor, documentation: str | None = None
    ) -> None:
        """Present selected regenerated code evidence without enabling design edits."""
        self._element = None
        self._source_anchor = anchor
        self.title.setText(f"{label} (imported {kind})")
        summary = documentation or "No attached JavaDoc was extracted."
        self.code_description.setText(
            f"{summary}\n\nCode-derived {kind} at {anchor.relative_path}:{anchor.start_line}.\n"
            f"Symbol: {anchor.qualified_symbol}\nConfidence: exact"
        )
        self.design_description.clear()
        self._set_editing_enabled(False)
        self.open_source_button.setEnabled(self._on_open_source is not None)

    def refresh(self) -> None:
        self.set_element(self._element)

    def _set_editing_enabled(self, enabled: bool) -> None:
        self.design_description.setEnabled(enabled)
        self.save_button.setEnabled(enabled)
        self.revert_button.setEnabled(enabled)

    def _apply_description(self) -> None:
        if self._element is not None:
            description = self.design_description.toPlainText().strip() or None
            self._on_description_edit(description)

    def _revert_description(self) -> None:
        if self._element is not None:
            self._on_description_edit(None)

    def _open_source(self) -> None:
        if self._source_anchor is not None and self._on_open_source is not None:
            self._on_open_source(self._source_anchor)
