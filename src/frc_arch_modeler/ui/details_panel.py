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

from frc_arch_modeler.domain.model import Command, Subsystem

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

    def __init__(self, on_description_edit: Callable[[str | None], None]) -> None:
        super().__init__()
        self._on_description_edit = on_description_edit
        self._element: ArchitectureElement | None = None
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
        form = QFormLayout()
        form.addRow("From code", self.code_description)
        form.addRow("Design / proposed", self.design_description)
        layout.addWidget(self.title)
        layout.addLayout(form)
        layout.addWidget(self.save_button)
        layout.addWidget(self.revert_button)
        layout.addStretch()
        self.save_button.clicked.connect(self._apply_description)
        self.revert_button.clicked.connect(self._revert_description)
        self._set_editing_enabled(False)

    def set_element(self, element: ArchitectureElement | None) -> None:
        self._element = element
        if element is None:
            self.title.setText("Select a command or subsystem to inspect its details.")
            self.code_description.setText("No code-derived description available.")
            self.design_description.clear()
            self._set_editing_enabled(False)
            return
        self.title.setText(f"{element.name.effective} ({type(element).__name__})")
        self.code_description.setText(
            element.description.scanned or "No code-derived description available."
        )
        self.design_description.setPlainText(element.description.design or "")
        self._set_editing_enabled(True)

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
