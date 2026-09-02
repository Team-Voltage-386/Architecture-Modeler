from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog

from frc_arch_modeler.app import create_application
from frc_arch_modeler.ui.architecture_scene import DeviceBlock
from frc_arch_modeler.ui.controllers.hardware_controller import (
    COL_BREAKER,
    COL_MASS,
    COL_MODE,
    COL_NAME,
    COL_NOTES,
    COL_SUBSYSTEM,
)
from frc_arch_modeler.ui.entity_dialogs import DeviceDialog
from frc_arch_modeler.ui.main_window import MainWindow
from frc_arch_modeler.ui.theme import MUTED_TEXT


def _new_robot_with_two_devices(qtbot):  # type: ignore[no-untyped-def]
    """A saved-shaped model with two subsystems, each owning one fully wired device."""
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)
    window.new_project("Competition Robot")
    window.add_subsystem("Shooter")
    window.add_subsystem("Drive")
    assert window.project is not None
    shooter, drive = window.project.subsystems
    window.add_device(shooter.id, "Flywheel motor", "Falcon500", "REAL", "rio", "5", "40", "2.1")
    window.add_device(drive.id, "Left motor", "SparkMax", "REAL", "canivore", "3")
    return window


def _row_for_device(window, device_id):  # type: ignore[no-untyped-def]
    table = window.hardware_table
    for row in range(table.rowCount()):
        item = table.item(row, COL_NAME)
        if item is not None and item.data(Qt.ItemDataRole.UserRole) == device_id:
            return row
    return None


def test_the_hardware_tab_lists_one_row_per_device_grouped_by_subsystem_by_default(
    qtbot,
) -> None:
    window = _new_robot_with_two_devices(qtbot)

    assert window.diagram_tabs.tabText(2) == "Hardware"
    table = window.hardware_table
    assert table.rowCount() == 2
    # "Drive" sorts before "Shooter", so its device leads despite being added second.
    assert table.cellWidget(0, COL_SUBSYSTEM).currentText() == "Drive"
    assert table.item(0, COL_NAME).text() == "Left motor"
    assert table.cellWidget(1, COL_SUBSYSTEM).currentText() == "Shooter"
    assert table.item(1, COL_NAME).text() == "Flywheel motor"


def test_editing_the_name_cell_pushes_one_undoable_edit(qtbot) -> None:
    window = _new_robot_with_two_devices(qtbot)
    assert window.project is not None
    device = next(d for d in window.project.devices if d.name.effective == "Left motor")
    row = _row_for_device(window, device.id)

    window.hardware_table.item(row, COL_NAME).setText("Left drive motor")

    assert device.name.effective == "Left drive motor"
    window.undo_stack.undo()
    assert device.name.effective == "Left motor"


def test_editing_the_breaker_cell_validates_updates_and_undoes(qtbot) -> None:
    window = _new_robot_with_two_devices(qtbot)
    assert window.project is not None
    device = next(d for d in window.project.devices if d.name.effective == "Flywheel motor")
    row = _row_for_device(window, device.id)

    window.hardware_table.item(row, COL_BREAKER).setText("30")

    assert device.breaker_amps.effective == "30"
    window.undo_stack.undo()
    assert device.breaker_amps.effective == "40"


def test_an_invalid_breaker_value_is_rejected_and_the_cell_reverts_without_an_undo_entry(
    qtbot,
) -> None:
    window = _new_robot_with_two_devices(qtbot)
    assert window.project is not None
    device = next(d for d in window.project.devices if d.name.effective == "Flywheel motor")
    row = _row_for_device(window, device.id)
    stack_count_before = window.undo_stack.count()

    window.hardware_table.item(row, COL_BREAKER).setText("not-a-number")

    assert device.breaker_amps.effective == "40"
    assert window.undo_stack.count() == stack_count_before
    row = _row_for_device(window, device.id)
    assert window.hardware_table.item(row, COL_BREAKER).text() == "40"


def test_changing_the_subsystem_combo_reassigns_the_device_and_undoes(qtbot) -> None:
    window = _new_robot_with_two_devices(qtbot)
    assert window.project is not None
    device = next(d for d in window.project.devices if d.name.effective == "Left motor")
    shooter = next(s for s in window.project.subsystems if s.name.effective == "Shooter")
    row = _row_for_device(window, device.id)
    combo = window.hardware_table.cellWidget(row, COL_SUBSYSTEM)

    combo.setCurrentIndex(combo.findData(shooter.id))

    assert device.owner_subsystem_id == shooter.id
    window.undo_stack.undo()
    assert device.owner_subsystem_id != shooter.id


def test_changing_the_mode_combo_updates_the_device_and_undoes(qtbot) -> None:
    window = _new_robot_with_two_devices(qtbot)
    assert window.project is not None
    device = next(d for d in window.project.devices if d.name.effective == "Left motor")
    row = _row_for_device(window, device.id)
    combo = window.hardware_table.cellWidget(row, COL_MODE)

    combo.setCurrentText("SIM")

    assert device.mode.effective == "SIM"
    window.undo_stack.undo()
    assert device.mode.effective == "REAL"


def test_selecting_a_table_row_selects_the_matching_device_block_and_reveals_a_hidden_subsystem(
    qtbot,
) -> None:
    window = _new_robot_with_two_devices(qtbot)
    assert window.scene.device_view_state == "grouped"
    assert window.scene.expanded_device_subsystems == set()
    device = next(d for d in window.project.devices if d.name.effective == "Left motor")
    row = _row_for_device(window, device.id)

    window.hardware_table.selectRow(row)

    blocks = [item for item in window.scene.items() if isinstance(item, DeviceBlock)]
    matching = [block for block in blocks if block.element_id == device.id]
    assert len(matching) == 1
    assert matching[0].isSelected()
    assert device.owner_subsystem_id in window.scene.expanded_device_subsystems


def test_selecting_a_device_block_on_canvas_selects_its_table_row(qtbot) -> None:
    window = _new_robot_with_two_devices(qtbot)
    window.device_view_action.trigger()  # cycle grouped -> expanded
    assert window.scene.device_view_state == "expanded"
    device = next(d for d in window.project.devices if d.name.effective == "Flywheel motor")
    block = next(
        item
        for item in window.scene.items()
        if isinstance(item, DeviceBlock) and item.element_id == device.id
    )

    block.setSelected(True)

    row = _row_for_device(window, device.id)
    selected_rows = {index.row() for index in window.hardware_table.selectedIndexes()}
    assert selected_rows == {row}


def test_add_device_button_on_the_hardware_toolbar_opens_the_device_dialog(
    qtbot, monkeypatch
) -> None:
    window = _new_robot_with_two_devices(qtbot)

    def fake_exec(self):  # type: ignore[no-untyped-def]
        self.name_edit.setText("New encoder")
        self.type_combo.setCurrentText("CANcoder")
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(DeviceDialog, "exec", fake_exec)
    window.hardware_toolbar.actions()[0].trigger()

    assert any(d.name.effective == "New encoder" for d in window.project.devices)
    assert window.hardware_table.rowCount() == 3


def test_delete_selected_on_the_hardware_toolbar_removes_the_device_and_undo_restores_it(
    qtbot,
) -> None:
    window = _new_robot_with_two_devices(qtbot)
    assert window.project is not None
    device = next(d for d in window.project.devices if d.name.effective == "Left motor")
    row = _row_for_device(window, device.id)
    window.hardware_table.selectRow(row)
    assert window.remove_selected_device_action.isEnabled()

    window.remove_selected_device_action.trigger()

    assert device not in window.project.devices
    assert window.hardware_table.rowCount() == 1
    window.undo_stack.undo()
    assert device in window.project.devices
    assert window.hardware_table.rowCount() == 2


def test_the_filter_field_hides_non_matching_rows(qtbot) -> None:
    window = _new_robot_with_two_devices(qtbot)

    window.hardware_filter_field.setText("flywheel")

    table = window.hardware_table
    hidden = [table.isRowHidden(row) for row in range(table.rowCount())]
    visible_names = [
        table.item(row, COL_NAME).text()
        for row in range(table.rowCount())
        if not table.isRowHidden(row)
    ]
    assert visible_names == ["Flywheel motor"]
    assert any(hidden)

    window.hardware_filter_field.setText("")
    assert not any(window.hardware_table.isRowHidden(row) for row in range(table.rowCount()))


def test_empty_optional_fields_render_as_a_muted_dash(qtbot) -> None:
    window = _new_robot_with_two_devices(qtbot)
    device = next(d for d in window.project.devices if d.name.effective == "Left motor")
    row = _row_for_device(window, device.id)
    table = window.hardware_table

    breaker_item = table.item(row, COL_BREAKER)
    mass_item = table.item(row, COL_MASS)
    notes_item = table.item(row, COL_NOTES)

    assert breaker_item.text() == "—"
    assert breaker_item.foreground().color().name().upper() == MUTED_TEXT
    assert mass_item.text() == "—"
    assert notes_item.text() == "—"


def test_clicking_a_column_header_resorts_the_table(qtbot) -> None:
    window = _new_robot_with_two_devices(qtbot)
    table = window.hardware_table

    table.horizontalHeader().sectionClicked.emit(COL_NAME)

    names = [table.item(row, COL_NAME).text() for row in range(table.rowCount())]
    assert names == ["Flywheel motor", "Left motor"]

    table.horizontalHeader().sectionClicked.emit(COL_NAME)

    names = [table.item(row, COL_NAME).text() for row in range(table.rowCount())]
    assert names == ["Left motor", "Flywheel motor"]
