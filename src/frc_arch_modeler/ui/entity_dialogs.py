"""Single-form create/edit dialogs for devices, triggers, and relationships.

Each dialog collects every field in one visit instead of a chain of QInputDialogs, so
cancelling partway through does not discard already-entered values.
"""

from __future__ import annotations

from uuid import UUID

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from frc_arch_modeler.domain.model import ArchitectureProject, Device, Relationship, TriggerBinding
from frc_arch_modeler.importers.java.scanner import DEVICE_PATTERN

#: Device types recognized by the Java scanner, in the order they appear in
#: DEVICE_PATTERN, offered as suggestions for the (still-editable) device type field.
DEVICE_TYPES = DEVICE_PATTERN.pattern.split("(?P<type>", 1)[1].split(r")\s*\(", 1)[0].split("|")

TRIGGER_ACTIVATIONS = [
    "onTrue",
    "onFalse",
    "whileTrue",
    "whileFalse",
    "toggleOnTrue",
    "toggleOnFalse",
]
RELATIONSHIP_TYPES = ["calls", "contains", "triggers", "owns_device"]


class _EntityDialog(QDialog):
    """Shared scaffolding: a form, an inline validation label, and OK/Cancel/Add another."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.add_another_clicked = False
        self._ok_button: QPushButton | None = None
        self._add_another_button: QPushButton | None = None
        self._validation_label = QLabel(self)

    def _build_layout(self, form: QFormLayout, *, allow_add_another: bool) -> None:
        self._validation_label.setObjectName("dialogValidationLabel")
        self._validation_label.setWordWrap(True)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self._ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)

        if allow_add_another:
            add_another_button = buttons.addButton(
                "Add another", QDialogButtonBox.ButtonRole.ActionRole
            )
            add_another_button.clicked.connect(self._accept_and_add_another)
            self._add_another_button = add_another_button

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self._validation_label)
        layout.addWidget(buttons)

    def _accept_and_add_another(self) -> None:
        self.add_another_clicked = True
        self.accept()

    def _update_validity(self) -> None:
        error = self._validity_error()
        self._validation_label.setText(error or "")
        enabled = error is None
        if self._ok_button is not None:
            self._ok_button.setEnabled(enabled)
        if self._add_another_button is not None:
            self._add_another_button.setEnabled(enabled)

    def _validity_error(self) -> str | None:
        raise NotImplementedError


class DeviceDialog(_EntityDialog):
    """Create or edit a hardware device owned by a subsystem."""

    def __init__(
        self,
        project: ArchitectureProject,
        device: Device | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Edit device" if device is not None else "New device")

        self.owner_combo = QComboBox(self)
        for subsystem in project.subsystems:
            self.owner_combo.addItem(subsystem.name.effective or "Unnamed", subsystem.id)

        self.name_edit = QLineEdit(self)

        self.type_combo = QComboBox(self)
        self.type_combo.setEditable(True)
        self.type_combo.addItems(DEVICE_TYPES)
        self.type_combo.setCurrentText("")

        self.mode_combo = QComboBox(self)
        self.mode_combo.addItems(["Unspecified", "REAL", "SIM", "REPLAY"])

        if device is not None:
            owner_index = self.owner_combo.findData(device.owner_subsystem_id)
            if owner_index >= 0:
                self.owner_combo.setCurrentIndex(owner_index)
            self.name_edit.setText(device.name.effective or "")
            self.type_combo.setCurrentText(device.device_type.effective or "")
            self.mode_combo.setCurrentText(device.mode.effective or "Unspecified")

        form = QFormLayout()
        form.addRow("Subsystem:", self.owner_combo)
        form.addRow("Name:", self.name_edit)
        form.addRow("Device type:", self.type_combo)
        form.addRow("Mode:", self.mode_combo)
        self._build_layout(form, allow_add_another=device is None)

        self.owner_combo.currentIndexChanged.connect(self._update_validity)
        self.name_edit.textChanged.connect(self._update_validity)
        self.type_combo.editTextChanged.connect(self._update_validity)
        self._update_validity()
        self.name_edit.setFocus()

    def _validity_error(self) -> str | None:
        if self.owner_combo.count() == 0:
            return "Add a subsystem before creating a device."
        if not self.name_edit.text().strip():
            return "Enter a device name."
        if not self.type_combo.currentText().strip():
            return "Enter a device type."
        return None

    def values(self) -> tuple[UUID, str, str, str | None]:
        mode = self.mode_combo.currentText()
        return (
            self.owner_combo.currentData(),
            self.name_edit.text().strip(),
            self.type_combo.currentText().strip(),
            None if mode == "Unspecified" else mode,
        )

    def reset_for_another(self) -> None:
        """Keep the owner/type/mode selection but clear the name for the next device."""
        self.name_edit.clear()
        self.name_edit.setFocus()


class TriggerDialog(_EntityDialog):
    """Create or edit a controller/trigger binding for a command."""

    def __init__(
        self,
        project: ArchitectureProject,
        trigger: TriggerBinding | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Edit trigger" if trigger is not None else "New trigger")

        self.command_combo = QComboBox(self)
        for command in project.commands:
            self.command_combo.addItem(command.name.effective or "Unnamed", command.id)

        self.expression_edit = QLineEdit(self)

        self.activation_combo = QComboBox(self)
        self.activation_combo.addItems(TRIGGER_ACTIVATIONS)

        if trigger is not None:
            command_index = self.command_combo.findData(trigger.command_id)
            if command_index >= 0:
                self.command_combo.setCurrentIndex(command_index)
            self.expression_edit.setText(trigger.expression.effective or "")
            self.activation_combo.setCurrentText(trigger.activation.effective or "onTrue")

        form = QFormLayout()
        form.addRow("Command:", self.command_combo)
        form.addRow("Controller / trigger expression:", self.expression_edit)
        form.addRow("Activation:", self.activation_combo)
        self._build_layout(form, allow_add_another=trigger is None)

        self.command_combo.currentIndexChanged.connect(self._update_validity)
        self.expression_edit.textChanged.connect(self._update_validity)
        self._update_validity()
        self.expression_edit.setFocus()

    def _validity_error(self) -> str | None:
        if self.command_combo.count() == 0:
            return "Add a command before creating a trigger."
        if not self.expression_edit.text().strip():
            return "Enter a controller / trigger expression."
        return None

    def values(self) -> tuple[UUID, str, str]:
        return (
            self.command_combo.currentData(),
            self.expression_edit.text().strip(),
            self.activation_combo.currentText(),
        )

    def reset_for_another(self) -> None:
        """Keep the command/activation selection but clear the expression for the next trigger."""
        self.expression_edit.clear()
        self.expression_edit.setFocus()


class RelationshipDialog(_EntityDialog):
    """Create or edit a typed relationship between two commands/subsystems."""

    def __init__(
        self,
        project: ArchitectureProject,
        relationship: Relationship | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Edit relationship" if relationship is not None else "New relationship")

        self._elements = [*project.commands, *project.subsystems]

        self.source_combo = QComboBox(self)
        for element in self._elements:
            self.source_combo.addItem(self._label(element), element.id)

        self.target_combo = QComboBox(self)

        self.type_combo = QComboBox(self)
        self.type_combo.addItems(RELATIONSHIP_TYPES)

        form = QFormLayout()
        form.addRow("Source:", self.source_combo)
        form.addRow("Target:", self.target_combo)
        form.addRow("Type:", self.type_combo)
        self._build_layout(form, allow_add_another=relationship is None)

        self.source_combo.currentIndexChanged.connect(self._refresh_targets)
        self.target_combo.currentIndexChanged.connect(self._update_validity)

        if relationship is not None:
            source_index = self.source_combo.findData(relationship.source_id)
            if source_index >= 0:
                self.source_combo.setCurrentIndex(source_index)
        self._refresh_targets()
        if relationship is not None:
            target_index = self.target_combo.findData(relationship.target_id)
            if target_index >= 0:
                self.target_combo.setCurrentIndex(target_index)
            self.type_combo.setCurrentText(relationship.relationship_type)

        self._update_validity()

    @staticmethod
    def _label(element: object) -> str:
        return f"{type(element).__name__}: {element.name.effective}"  # type: ignore[attr-defined]

    def _refresh_targets(self) -> None:
        source_id = self.source_combo.currentData()
        self.target_combo.blockSignals(True)
        self.target_combo.clear()
        for element in self._elements:
            if element.id != source_id:
                self.target_combo.addItem(self._label(element), element.id)
        self.target_combo.blockSignals(False)
        self._update_validity()

    def _validity_error(self) -> str | None:
        if self.source_combo.count() < 2:
            return "Add another command or subsystem to create a relationship."
        if self.target_combo.count() == 0:
            return "Choose a target."
        return None

    def values(self) -> tuple[str, UUID, UUID]:
        return (
            self.type_combo.currentText(),
            self.source_combo.currentData(),
            self.target_combo.currentData(),
        )

    def reset_for_another(self) -> None:
        """Keep the source selection but refocus the target for the next relationship."""
        self.target_combo.setFocus()
