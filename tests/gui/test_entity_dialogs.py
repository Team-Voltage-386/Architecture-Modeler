from frc_arch_modeler.app import create_application
from frc_arch_modeler.ui.entity_dialogs import DeviceDialog, RelationshipDialog, TriggerDialog
from frc_arch_modeler.ui.main_window import MainWindow


def test_device_dialog_ok_disabled_until_name_and_type_are_entered(qtbot) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)
    window.new_project("Competition Robot")
    window.add_subsystem("Drive")
    assert window.project is not None

    dialog = DeviceDialog(window.project)
    qtbot.addWidget(dialog)

    assert not dialog._ok_button.isEnabled()
    assert "device name" in dialog._validation_label.text()

    dialog.name_edit.setText("Left motor")
    assert not dialog._ok_button.isEnabled()
    assert "device type" in dialog._validation_label.text()

    dialog.type_combo.setCurrentText("SparkMax")
    assert dialog._ok_button.isEnabled()
    assert dialog._validation_label.text() == ""


def test_device_dialog_prefills_fields_and_hides_add_another_in_edit_mode(qtbot) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)
    window.new_project("Competition Robot")
    window.add_subsystem("Drive")
    window.add_device(window.project.subsystems[0].id, "Left motor", "SparkMax", "REAL")
    device = window.project.devices[0]

    dialog = DeviceDialog(window.project, device=device)
    qtbot.addWidget(dialog)

    assert dialog.owner_combo.currentData() == device.owner_subsystem_id
    assert dialog.name_edit.text() == "Left motor"
    assert dialog.type_combo.currentText() == "SparkMax"
    assert dialog.mode_combo.currentText() == "REAL"
    assert dialog._add_another_button is None
    assert dialog._ok_button.isEnabled()


def test_trigger_dialog_ok_disabled_until_expression_is_entered(qtbot) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)
    window.new_project("Competition Robot")
    window.add_command("Teleop Drive")
    assert window.project is not None

    dialog = TriggerDialog(window.project)
    qtbot.addWidget(dialog)

    assert not dialog._ok_button.isEnabled()
    dialog.expression_edit.setText("Driver A")
    assert dialog._ok_button.isEnabled()


def test_trigger_dialog_prefills_fields_and_hides_add_another_in_edit_mode(qtbot) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)
    window.new_project("Competition Robot")
    window.add_command("Teleop Drive")
    window.add_trigger(window.project.commands[0].id, "Driver A", "whileTrue")
    trigger = window.project.triggers[0]

    dialog = TriggerDialog(window.project, trigger=trigger)
    qtbot.addWidget(dialog)

    assert dialog.command_combo.currentData() == trigger.command_id
    assert dialog.expression_edit.text() == "Driver A"
    assert dialog.activation_combo.currentText() == "whileTrue"
    assert dialog._add_another_button is None


def test_relationship_dialog_excludes_source_from_target_choices(qtbot) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)
    window.new_project("Competition Robot")
    window.add_subsystem("Drive")
    window.add_command("Teleop Drive")
    assert window.project is not None

    dialog = RelationshipDialog(window.project)
    qtbot.addWidget(dialog)

    source_id = dialog.source_combo.currentData()
    target_ids = [
        dialog.target_combo.itemData(index) for index in range(dialog.target_combo.count())
    ]
    assert source_id not in target_ids
    assert dialog._ok_button.isEnabled()


def test_relationship_dialog_ok_disabled_with_only_one_element(qtbot) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)
    window.new_project("Competition Robot")
    window.add_subsystem("Drive")
    assert window.project is not None

    dialog = RelationshipDialog(window.project)
    qtbot.addWidget(dialog)

    assert not dialog._ok_button.isEnabled()
    assert "another" in dialog._validation_label.text()


def test_relationship_dialog_prefills_fields_and_hides_add_another_in_edit_mode(qtbot) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)
    window.new_project("Competition Robot")
    window.add_subsystem("Drive")
    window.add_command("Teleop Drive")
    window.add_relationship(
        "calls", window.project.commands[0].id, window.project.subsystems[0].id
    )
    relationship = window.project.relationships[0]

    dialog = RelationshipDialog(window.project, relationship=relationship)
    qtbot.addWidget(dialog)

    assert dialog.source_combo.currentData() == relationship.source_id
    assert dialog.target_combo.currentData() == relationship.target_id
    assert dialog.type_combo.currentText() == "calls"
    assert dialog._add_another_button is None
