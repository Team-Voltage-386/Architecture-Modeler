"""The Model Health dock: a live, clickable list of what is wrong with the model.

This widget is presentation only. Every rule lives in `services.health_service`; the
panel renders whatever findings it is handed, in the order it is handed them, and
reports what the user clicked. It deliberately knows nothing about what makes a finding
appear, so a rule can never drift between the service and the screen.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import QLabel, QMenu, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from frc_arch_modeler.services.allocation_service import (
    SEVERITY_ERROR,
    SEVERITY_INCOMPLETE,
    SEVERITY_WARNING,
)
from frc_arch_modeler.services.health_service import HealthFinding
from frc_arch_modeler.ui.theme import ALERT_RED, MUTED_TEXT, VOLTAGE_YELLOW

#: Group headings in the order the service already sorts findings into, so the tree
#: reads top-down in the order a student should work through it. Each entry carries the
#: heading, the singular noun used in a count, and the accent colour.
SEVERITY_GROUPS: tuple[tuple[str, str, str, str], ...] = (
    (SEVERITY_ERROR, "Errors", "error", ALERT_RED),
    (SEVERITY_WARNING, "Warnings", "warning", VOLTAGE_YELLOW),
    (SEVERITY_INCOMPLETE, "Incomplete", "incomplete item", MUTED_TEXT),
)

HEALTHY_MESSAGE = "No problems found. Every rule the tool checks currently passes."
NO_MODEL_MESSAGE = "Create or open a model to see what needs attention."


class HealthPanel(QWidget):
    """Findings grouped by severity, clickable, with an inline fix where one is safe."""

    finding_activated = Signal(object)  # HealthFinding
    fix_requested = Signal(object)  # HealthFinding

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("healthPanel")
        self._findings: list[HealthFinding] = []
        self._context_menu: QMenu | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        self.summary_label = QLabel(NO_MODEL_MESSAGE, self)
        self.summary_label.setObjectName("healthSummary")
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

        self.tree = QTreeWidget(self)
        self.tree.setObjectName("healthTree")
        self.tree.setAccessibleName("Model health findings")
        self.tree.setHeaderLabels(["Finding"])
        self.tree.setColumnCount(1)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._show_context_menu)
        self.tree.itemSelectionChanged.connect(self._handle_selection_changed)
        self.tree.itemDoubleClicked.connect(self._handle_double_click)
        layout.addWidget(self.tree)

        self.setMinimumWidth(300)

    def set_findings(
        self, findings: list[HealthFinding], has_project: bool = True
    ) -> None:
        """Redraw the whole list; the caller decides when, and debounces it."""
        self._findings = list(findings)
        self.tree.blockSignals(True)
        self.tree.clear()
        for severity, title, _, color in SEVERITY_GROUPS:
            matching = [
                (index, finding)
                for index, finding in enumerate(self._findings)
                if finding.severity == severity
            ]
            if not matching:
                continue
            header = QTreeWidgetItem(self.tree, [f"{title} ({len(matching)})"])
            header.setFlags(header.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            header.setForeground(0, QBrush(QColor(color)))
            header.setExpanded(True)
            for index, finding in matching:
                item = QTreeWidgetItem(header, [self._label_for(finding)])
                item.setToolTip(0, finding.message)
                item.setData(0, Qt.ItemDataRole.UserRole, index)
        self.tree.blockSignals(False)
        if not has_project:
            self.summary_label.setText(NO_MODEL_MESSAGE)
        elif not self._findings:
            self.summary_label.setText(HEALTHY_MESSAGE)
        else:
            self.summary_label.setText(summary_text(self._findings))

    @staticmethod
    def _label_for(finding: HealthFinding) -> str:
        if finding.fix_label is None:
            return finding.message
        return f"{finding.message}  ({finding.fix_label})"

    def selected_finding(self) -> HealthFinding | None:
        items = self.tree.selectedItems()
        return self._finding_for(items[0]) if items else None

    def _finding_for(self, item: QTreeWidgetItem | None) -> HealthFinding | None:
        index = item.data(0, Qt.ItemDataRole.UserRole) if item is not None else None
        if not isinstance(index, int) or not 0 <= index < len(self._findings):
            return None
        return self._findings[index]

    def _handle_selection_changed(self) -> None:
        finding = self.selected_finding()
        if finding is not None:
            self.finding_activated.emit(finding)

    def _handle_double_click(self, item: QTreeWidgetItem, column: int) -> None:
        finding = self._finding_for(item)
        if finding is not None:
            self.finding_activated.emit(finding)

    def _show_context_menu(self, pos) -> None:  # type: ignore[no-untyped-def]
        """Offer the fix explicitly; a fix is never applied just by clicking a finding."""
        finding = self._finding_for(self.tree.itemAt(pos))
        if finding is None or finding.fix_action is None:
            return
        menu = QMenu(self)
        fix_action = menu.addAction(finding.fix_label or "Apply fix")
        fix_action.triggered.connect(lambda: self.fix_requested.emit(finding))
        # popup(), never exec(): a nested modal loop opened from inside a right-click
        # has corrupted this application's event dispatch on Windows before.
        self._context_menu = menu
        menu.popup(self.tree.viewport().mapToGlobal(pos))


def summary_text(findings: list[HealthFinding]) -> str:
    """A one-line count per severity, used by the panel header and the status bar."""
    present = []
    for severity, _, noun, _color in SEVERITY_GROUPS:
        count = sum(1 for finding in findings if finding.severity == severity)
        if count:
            present.append(f"{count} {noun}" if count == 1 else f"{count} {noun}s")
    return ", ".join(present) if present else "0 findings"
