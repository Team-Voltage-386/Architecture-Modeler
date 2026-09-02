"""The Hardware tab: a device-per-row table kept in sync with the Structure canvas."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from frc_arch_modeler.ui import toolbars
from frc_arch_modeler.ui.architecture_scene import DeviceBlock
from frc_arch_modeler.ui.details_panel import EditEntityFieldsCommand
from frc_arch_modeler.ui.entity_dialogs import DeviceDialog
from frc_arch_modeler.ui.theme import MUTED_TEXT

if TYPE_CHECKING:
    from frc_arch_modeler.ui.main_window import MainWindow

COL_SUBSYSTEM = 0
COL_NAME = 1
COL_TYPE = 2
COL_BUS = 3
COL_ADDRESS = 4
COL_BREAKER = 5
COL_MASS = 6
COL_MODE = 7
COL_NOTES = 8

_HEADERS = [
    "Subsystem",
    "Name",
    "Type",
    "Bus",
    "Address",
    "Breaker (A)",
    "Mass (kg)",
    "Mode",
    "Notes",
]

# Columns backed by a plain editable QTableWidgetItem, mapped to their Device field.
_TEXT_FIELDS = {
    COL_NAME: "name",
    COL_TYPE: "device_type",
    COL_BUS: "bus",
    COL_ADDRESS: "address",
    COL_BREAKER: "breaker_amps",
    COL_MASS: "mass_kg",
    COL_NOTES: "notes",
}

_NUMERIC_LABELS = {COL_BREAKER: "Breaker rating", COL_MASS: "Mass"}

_MODES = ["Unspecified", "REAL", "SIM", "REPLAY"]


class HardwareController:
    """Build and drive the Hardware tab: table contents, edits, and canvas selection sync.

    Every sort or resort rebuilds the table from scratch rather than relying on
    QTableWidget's built-in ``setSortingEnabled`` reordering, because widgets set with
    ``setCellWidget`` (the Subsystem and Mode combo cells) do not reliably follow their
    row when Qt's own sort machinery reorders rows underneath them.
    """

    def __init__(self, window: MainWindow) -> None:
        self.window = window
        self._populating = False
        self._syncing = False
        self._filter_text = ""
        self._sort_column = COL_SUBSYSTEM
        self._sort_ascending = True

    # -- construction -------------------------------------------------------

    def build_hardware_tab(self) -> None:
        window = self.window

        table = QTableWidget(0, len(_HEADERS), window)
        table.setObjectName("hardwareTable")
        table.setAccessibleName("Hardware table")
        table.setHorizontalHeaderLabels(_HEADERS)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(32)
        table.setShowGrid(False)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.horizontalHeader().setStretchLastSection(True)
        table.horizontalHeader().setSectionsClickable(True)
        table.horizontalHeader().setSortIndicatorShown(True)
        table.horizontalHeader().setSortIndicator(COL_SUBSYSTEM, Qt.SortOrder.AscendingOrder)
        table.horizontalHeader().sectionClicked.connect(window._hardware_column_header_clicked)
        table.itemChanged.connect(window._hardware_cell_changed)
        table.itemSelectionChanged.connect(window._sync_canvas_to_hardware_selection)
        window.hardware_table = table

        toolbar = QToolBar("Hardware actions", window)
        toolbar.setMovable(False)
        toolbar.addAction(window.new_device_action)
        window.remove_selected_device_action = toolbar.addAction(
            "Delete Selected", window._remove_selected_hardware_device
        )
        window.remove_selected_device_action.setEnabled(False)
        toolbars.set_action_help(
            window.remove_selected_device_action,
            "Delete the device selected in the Hardware table. Use this to remove a "
            "device you no longer want — press Ctrl+Z to undo.",
        )
        filter_field = QLineEdit(window)
        filter_field.setObjectName("hardwareFilterField")
        filter_field.setAccessibleName("Filter hardware table")
        filter_field.setPlaceholderText("Filter hardware")
        filter_field.setClearButtonEnabled(True)
        filter_field.textChanged.connect(window._filter_hardware_table)
        toolbar.addSeparator()
        toolbar.addWidget(filter_field)
        window.hardware_filter_field = filter_field
        window.hardware_toolbar = toolbar

        window._hardware_tab = QWidget(window)
        layout = QVBoxLayout(window._hardware_tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(toolbar)
        layout.addWidget(table)

        window.diagram_tabs.addTab(window._hardware_tab, "Hardware")
        window.scene.selectionChanged.connect(window._sync_hardware_table_selection)

    # -- population -----------------------------------------------------------

    def refresh_table(self) -> None:
        """Rebuild every row from the model, preserving selection and the active filter."""
        window = self.window
        table = window.hardware_table
        previous_selection = self._selected_device_id()
        self._populating = True
        try:
            table.setRowCount(0)
            project = window.project
            if project is None:
                return
            devices = sorted(
                project.devices, key=self._sort_key, reverse=not self._sort_ascending
            )
            table.setRowCount(len(devices))
            for row, device in enumerate(devices):
                self._populate_row(row, device)
        finally:
            self._populating = False
        table.resizeRowsToContents()
        self._apply_filter_to_rows()
        if previous_selection is not None:
            self._select_row_for_device(previous_selection)
        self.update_delete_action()

    def _populate_row(self, row: int, device) -> None:  # type: ignore[no-untyped-def]
        window = self.window
        table = window.hardware_table
        project = window.project
        assert project is not None

        subsystem_combo = QComboBox(table)
        for subsystem in project.subsystems:
            subsystem_combo.addItem(subsystem.name.effective or "Unnamed", subsystem.id)
        owner_index = subsystem_combo.findData(device.owner_subsystem_id)
        if owner_index >= 0:
            subsystem_combo.setCurrentIndex(owner_index)
        subsystem_combo.currentIndexChanged.connect(
            lambda _index, device_id=device.id, combo=subsystem_combo: (
                window._hardware_subsystem_cell_changed(device_id, combo)
            )
        )
        table.setCellWidget(row, COL_SUBSYSTEM, subsystem_combo)

        self._set_text_item(row, COL_NAME, device.name.effective, device.id)
        self._set_text_item(row, COL_TYPE, device.device_type.effective)
        self._set_text_item(row, COL_BUS, device.bus.effective)
        self._set_text_item(row, COL_ADDRESS, device.address.effective)
        self._set_numeric_item(row, COL_BREAKER, device.breaker_amps.effective)
        self._set_numeric_item(row, COL_MASS, device.mass_kg.effective)

        mode_combo = QComboBox(table)
        mode_combo.addItems(_MODES)
        mode_combo.setCurrentText(device.mode.effective or "Unspecified")
        mode_combo.currentIndexChanged.connect(
            lambda _index, device_id=device.id, combo=mode_combo: (
                window._hardware_mode_cell_changed(device_id, combo)
            )
        )
        table.setCellWidget(row, COL_MODE, mode_combo)

        self._set_text_item(row, COL_NOTES, device.notes.effective)

    def _set_text_item(
        self, row: int, column: int, value: str | None, device_id: object | None = None
    ) -> None:
        item = QTableWidgetItem(value if value else "—")
        if not value:
            item.setForeground(QColor(MUTED_TEXT))
        if device_id is not None:
            item.setData(Qt.ItemDataRole.UserRole, device_id)
        self.window.hardware_table.setItem(row, column, item)

    def _set_numeric_item(self, row: int, column: int, value: str | None) -> None:
        item = QTableWidgetItem(value if value else "—")
        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        font = QFont("Consolas")
        font.setStyleHint(QFont.StyleHint.Monospace)
        item.setFont(font)
        if not value:
            item.setForeground(QColor(MUTED_TEXT))
        self.window.hardware_table.setItem(row, column, item)

    # -- sorting ----------------------------------------------------------

    def column_header_clicked(self, column: int) -> None:
        if column == self._sort_column:
            self._sort_ascending = not self._sort_ascending
        else:
            self._sort_column = column
            self._sort_ascending = True
        order = (
            Qt.SortOrder.AscendingOrder if self._sort_ascending else Qt.SortOrder.DescendingOrder
        )
        self.window.hardware_table.horizontalHeader().setSortIndicator(column, order)
        self.refresh_table()

    def _sort_key(self, device):  # type: ignore[no-untyped-def]
        column = self._sort_column
        if column == COL_NAME:
            return (device.name.effective or "").casefold()
        if column == COL_TYPE:
            return (device.device_type.effective or "").casefold()
        if column == COL_BUS:
            return (device.bus.effective or "").casefold()
        if column == COL_ADDRESS:
            return (device.address.effective or "").casefold()
        if column == COL_BREAKER:
            return self._numeric_key(device.breaker_amps.effective)
        if column == COL_MASS:
            return self._numeric_key(device.mass_kg.effective)
        if column == COL_MODE:
            return (device.mode.effective or "").casefold()
        if column == COL_NOTES:
            return (device.notes.effective or "").casefold()
        return (
            self._subsystem_name(device.owner_subsystem_id).casefold(),
            (device.name.effective or "").casefold(),
        )

    @staticmethod
    def _numeric_key(value: str | None) -> float:
        if not value:
            return float("inf")
        try:
            return float(value)
        except ValueError:
            return float("inf")

    # -- filtering ----------------------------------------------------------

    def apply_filter(self, text: str) -> None:
        self._filter_text = text.strip().casefold()
        self._apply_filter_to_rows()

    def _apply_filter_to_rows(self) -> None:
        table = self.window.hardware_table
        query = self._filter_text
        for row in range(table.rowCount()):
            table.setRowHidden(row, bool(query) and not self._row_matches(row, query))

    def _row_matches(self, row: int, query: str) -> bool:
        table = self.window.hardware_table
        parts: list[str] = []
        subsystem_combo = table.cellWidget(row, COL_SUBSYSTEM)
        if isinstance(subsystem_combo, QComboBox):
            parts.append(subsystem_combo.currentText())
        for column in (COL_NAME, COL_TYPE, COL_BUS, COL_ADDRESS, COL_NOTES):
            item = table.item(row, column)
            if item is not None:
                parts.append(item.text())
        return query in " ".join(parts).casefold()

    # -- cell edits -----------------------------------------------------------

    def cell_changed(self, item: QTableWidgetItem) -> None:
        if self._populating:
            return
        field = _TEXT_FIELDS.get(item.column())
        if field is None:
            return
        device = self._device_by_id(self._row_device_id(item.row()))
        if device is None:
            return
        raw = item.text().strip()
        new_value = None if raw in ("", "—") else raw
        label = _NUMERIC_LABELS.get(item.column())
        if label is not None:
            error = DeviceDialog._positive_number_error(raw, label)
            if error is not None:
                self.refresh_table()
                return
        if getattr(device, field).effective == new_value:
            return
        self._push_edit(device, {field: new_value})

    def subsystem_cell_changed(self, device_id: object, combo: QComboBox) -> None:
        if self._populating:
            return
        device = self._device_by_id(device_id)
        if device is None:
            return
        new_owner = combo.currentData()
        if new_owner == device.owner_subsystem_id:
            return
        self._push_edit(device, {"owner_subsystem_id": new_owner})

    def mode_cell_changed(self, device_id: object, combo: QComboBox) -> None:
        if self._populating:
            return
        device = self._device_by_id(device_id)
        if device is None:
            return
        text = combo.currentText()
        new_mode = None if text == "Unspecified" else text
        if device.mode.effective == new_mode:
            return
        self._push_edit(device, {"mode": new_mode})

    def _push_edit(self, device, fields: dict) -> None:  # type: ignore[no-untyped-def, type-arg]
        self.window.undo_stack.push(
            EditEntityFieldsCommand(
                device, fields, "device", self.window._refresh_after_hardware_edit
            )
        )

    # -- deletion -----------------------------------------------------------

    def remove_selected_device(self) -> None:
        device_id = self._selected_device_id()
        if device_id is None:
            return
        self.window.remove_owned_object("device", device_id)

    def update_delete_action(self) -> None:
        self.window.remove_selected_device_action.setEnabled(self._selected_device_id() is not None)

    # -- selection sync -------------------------------------------------------

    def sync_table_to_canvas_selection(self) -> None:
        """Reflect the canvas's device-block selection in the table (canvas -> table)."""
        if self._syncing:
            return
        window = self.window
        blocks = window.scene.selected_device_blocks()
        self._syncing = True
        try:
            if len(blocks) == 1:
                self._select_row_for_device(blocks[0].element_id)
            else:
                window.hardware_table.clearSelection()
        finally:
            self._syncing = False
        self.update_delete_action()

    def sync_canvas_to_table_selection(self) -> None:
        """Select the matching DeviceBlock for the active table row (table -> canvas).

        Expands the owning subsystem's device group first if it is not currently shown,
        since a block that was never rendered cannot be selected.
        """
        if self._syncing:
            return
        window = self.window
        self._syncing = True
        try:
            for block in window.scene.selected_device_blocks():
                block.setSelected(False)
            if window.project is None:
                return
            device_id = self._selected_device_id()
            if device_id is None:
                return
            device = self._device_by_id(device_id)
            if device is None:
                return
            scene = window.scene
            owner_id = device.owner_subsystem_id
            expanded = scene.device_view_state == "expanded" or (
                scene.device_view_state == "grouped"
                and owner_id in scene.expanded_device_subsystems
            )
            if not expanded:
                if scene.device_view_state == "hidden":
                    scene.device_view_state = "grouped"
                scene.expanded_device_subsystems.add(owner_id)
                window.canvas_controller.render_with_current_scan()
            block = next(
                (
                    item
                    for item in window.scene.items()
                    if isinstance(item, DeviceBlock) and item.element_id == device_id
                ),
                None,
            )
            if block is not None:
                block.setSelected(True)
        finally:
            self._syncing = False
        self.update_delete_action()

    # -- lookups --------------------------------------------------------------

    def _device_by_id(self, device_id: object | None):  # type: ignore[no-untyped-def]
        project = self.window.project
        if project is None or device_id is None:
            return None
        return next((device for device in project.devices if device.id == device_id), None)

    def _subsystem_name(self, subsystem_id: object) -> str:
        project = self.window.project
        if project is None:
            return "Unknown"
        subsystem = next(
            (item for item in project.subsystems if item.id == subsystem_id), None
        )
        return (subsystem.name.effective or "Unnamed") if subsystem is not None else "Unknown"

    def _row_device_id(self, row: int) -> object | None:
        item = self.window.hardware_table.item(row, COL_NAME)
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else None

    def _selected_device_id(self) -> object | None:
        table = self.window.hardware_table
        rows = {index.row() for index in table.selectedIndexes()}
        if len(rows) != 1:
            return None
        return self._row_device_id(next(iter(rows)))

    def _select_row_for_device(self, device_id: object) -> None:
        table = self.window.hardware_table
        table.clearSelection()
        for row in range(table.rowCount()):
            item = table.item(row, COL_NAME)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == device_id:
                table.selectRow(row)
                table.scrollToItem(item)
                return
