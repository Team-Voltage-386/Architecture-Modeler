from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent, QKeySequence, QPalette
from PySide6.QtWidgets import QDockWidget, QMessageBox

from frc_arch_modeler.app import create_application
from frc_arch_modeler.domain.model import ComparisonState
from frc_arch_modeler.ui.architecture_scene import ArchitectureBlock
from frc_arch_modeler.ui.main_window import MainWindow
from frc_arch_modeler.ui.theme import MUTED_TEXT, OFF_WHITE


def test_main_window_has_planned_regions(qtbot) -> None:
    app = create_application([])
    window = MainWindow()
    qtbot.addWidget(window)

    assert window.windowTitle() == "FRC Architecture Modeler"
    assert window.findChild(QDockWidget, "detailsDock") is not None
    assert window.findChild(QDockWidget, "legendDock") is not None
    assert window.statusBar().currentMessage() == "No robot project connected"
    assert f"QToolBar QToolButton {{\n            color: {OFF_WHITE};" in app.styleSheet()
    input_selector = "QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QComboBox {"
    assert input_selector in app.styleSheet()
    assert app.palette().color(QPalette.ColorRole.PlaceholderText).name() == MUTED_TEXT.lower()
    assert window.search_field.accessibleName() == "Search architecture evidence"
    assert window.canvas.accessibleName() == "Architecture canvas"
    assert window.find_shortcut.key() == QKeySequence.StandardKey.Find
    assert window.save_model_action.shortcut() == QKeySequence.StandardKey.Save


def test_new_model_and_design_elements_update_the_canvas(qtbot) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)

    window.new_project("Competition Robot")
    window.add_subsystem("Drive")
    window.add_command("Teleop Drive")

    assert window.is_dirty
    assert window.new_command_action.isEnabled()
    assert window.project is not None
    assert len(window.project.commands) == 1
    assert len(window.project.subsystems) == 1
    assert len([item for item in window.scene.items() if isinstance(item, ArchitectureBlock)]) == 2


def test_design_devices_and_triggers_appear_on_their_canvas_blocks(qtbot) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)
    window.new_project("Competition Robot")
    window.add_subsystem("Drive")
    window.add_command("Teleop Drive")
    assert window.project is not None

    window.add_device(window.project.subsystems[0].id, "Left motor", "SparkMax", "REAL")
    window.add_trigger(window.project.commands[0].id, "Driver A", "onTrue")

    blocks = [item for item in window.scene.items() if isinstance(item, ArchitectureBlock)]
    drive = next(block for block in blocks if block.title.toPlainText() == "Drive")
    command = next(block for block in blocks if block.title.toPlainText() == "Teleop Drive")
    assert "SparkMax: Left motor" in drive.summary.toPlainText()
    assert "Driver A · onTrue" in command.summary.toPlainText()
    assert window.new_device_action.isEnabled()
    assert window.new_trigger_action.isEnabled()


def test_imported_command_details_show_lifecycle_with_inherited_phases(qtbot) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)
    fixture_root = Path(__file__).parents[1] / "fixtures" / "java_basic"

    window.connect_robot_project(fixture_root)
    command = next(
        block
        for block in window.scene.items()
        if isinstance(block, ArchitectureBlock)
        and block.imported
        and block.title.toPlainText() == "DriveCommand"
    )
    command.setSelected(True)

    assert "Start → initialize → execute → isFinished → end(interrupted)" in (
        window.details_panel.lifecycle_flow.text()
    )


def test_save_and_open_model_round_trip_from_window(qtbot, tmp_path) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)
    window.new_project("Competition Robot")
    window.add_subsystem("Drive")
    window.add_command("Teleop Drive")

    saved_path = window.save_project(tmp_path)

    reopened_window = MainWindow()
    qtbot.addWidget(reopened_window)
    reopened = reopened_window.open_project(tmp_path)

    assert saved_path == tmp_path / ".frc-architecture" / "model.json"
    assert not window.is_dirty
    assert reopened.name == "Competition Robot"
    assert len(reopened.commands) == 1
    assert len(reopened.subsystems) == 1
    reopened_blocks = [
        item for item in reopened_window.scene.items() if isinstance(item, ArchitectureBlock)
    ]
    assert len(reopened_blocks) == 2


def test_open_model_offers_to_restore_a_differing_draft(qtbot, tmp_path, monkeypatch) -> None:
    create_application([])
    writer = MainWindow()
    qtbot.addWidget(writer)
    writer.new_project("Competition Robot")
    writer.save_project(tmp_path)
    writer.add_command("Recovered Command")

    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args: QMessageBox.StandardButton.Yes,
    )
    reopened = MainWindow()
    qtbot.addWidget(reopened)
    project = reopened.open_project(tmp_path)

    assert [command.name.effective for command in project.commands] == ["Recovered Command"]
    assert reopened.is_dirty
    assert "Recovered unsaved draft" in reopened.statusBar().currentMessage()


def test_opening_corrupt_model_does_not_replace_current_project(qtbot, tmp_path) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)
    window.new_project("Current Model")
    destination = tmp_path / ".frc-architecture" / "model.json"
    destination.parent.mkdir()
    destination.write_text("not JSON", encoding="utf-8")

    with pytest.raises(ValueError, match="Could not load model"):
        window.open_project(tmp_path)

    assert window.project is not None
    assert window.project.name == "Current Model"


def test_description_edit_undo_and_redo(qtbot) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)
    window.new_project("Competition Robot")
    window.add_command("Teleop Drive")
    block = next(item for item in window.scene.items() if isinstance(item, ArchitectureBlock))
    block.setSelected(True)

    window.edit_selected_description("Drive with joysticks")

    assert window.project.commands[0].description.design == "Drive with joysticks"
    window.undo_stack.undo()
    assert window.project.commands[0].description.design is None
    window.undo_stack.redo()
    assert window.project.commands[0].description.design == "Drive with joysticks"


def test_name_edit_undo_and_redo(qtbot) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)
    window.new_project("Competition Robot")
    window.add_command("Teleop Drive")
    block = next(item for item in window.scene.items() if isinstance(item, ArchitectureBlock))
    block.setSelected(True)

    window.edit_selected_name("Driver Control")

    assert window.project.commands[0].name.design == "Driver Control"
    window.undo_stack.undo()
    assert window.project.commands[0].name.design == "Teleop Drive"
    window.undo_stack.redo()
    assert window.project.commands[0].name.design == "Driver Control"


def test_command_requirement_edit_undo_and_redo(qtbot) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)
    window.new_project("Competition Robot")
    window.add_subsystem("Drive")
    window.add_command("Teleop Drive")
    command_block = next(
        item
        for item in window.scene.items()
        if isinstance(item, ArchitectureBlock) and item.kind == "command"
    )
    command_block.setSelected(True)

    window.edit_selected_requirements([window.project.subsystems[0].id])

    assert window.project.commands[0].requirement_ids == [window.project.subsystems[0].id]
    window.undo_stack.undo()
    assert window.project.commands[0].requirement_ids == []
    window.undo_stack.redo()
    assert window.project.commands[0].requirement_ids == [window.project.subsystems[0].id]


def test_command_details_apply_checked_subsystem_requirement(qtbot) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)
    window.new_project("Competition Robot")
    window.add_subsystem("Drive")
    window.add_command("Teleop Drive")
    command_block = next(
        item
        for item in window.scene.items()
        if isinstance(item, ArchitectureBlock) and item.kind == "command"
    )
    command_block.setSelected(True)

    assert window.details_panel.requirements.count() == 1
    window.details_panel.requirements.item(0).setCheckState(Qt.CheckState.Checked)
    window.details_panel.save_button.click()

    assert window.project.commands[0].requirement_ids == [window.project.subsystems[0].id]


def test_design_edit_creates_recoverable_draft_after_model_is_saved(qtbot, tmp_path) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)
    window.new_project("Competition Robot")
    window.save_project(tmp_path)
    window.add_command("Teleop Drive")

    assert (tmp_path / ".frc-architecture" / "draft.json").is_file()

    window.save_project()

    assert not (tmp_path / ".frc-architecture" / "draft.json").exists()


def test_connect_robot_project_scans_code_without_changing_design(qtbot) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)
    fixture_root = Path(__file__).parents[1] / "fixtures" / "java_basic"

    scan = window.connect_robot_project(fixture_root)

    assert window.project is None
    assert window.refresh_code_action.isEnabled()
    assert len(scan.symbols_of_kind("subsystem")) == 1
    assert "1 subsystems" in window.statusBar().currentMessage()
    assert "1 triggers" in window.statusBar().currentMessage()
    assert "1 devices" in window.statusBar().currentMessage()
    assert window.inventory_tree.topLevelItemCount() == 6
    assert window.inventory_tree.topLevelItem(0).text(0) == "Subsystems"
    group_names = [
        window.inventory_tree.topLevelItem(index).text(0)
        for index in range(window.inventory_tree.topLevelItemCount())
    ]
    assert "Trigger bindings" in group_names
    assert "Devices" in group_names
    imported_blocks = [
        item
        for item in window.scene.items()
        if isinstance(item, ArchitectureBlock) and item.imported
    ]
    assert len(imported_blocks) == 3


def test_background_scan_updates_the_window_without_blocking(qtbot) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)
    fixture_root = Path(__file__).parents[1] / "fixtures" / "java_basic"

    window._start_scan(fixture_root, "Connected")

    qtbot.waitUntil(lambda: window._scan_thread is None, timeout=5000)
    assert window.last_scan is not None
    assert window.last_scan.files_scanned == 4
    assert window.robot_project_root == fixture_root
    assert window.connect_robot_action.isEnabled()


def test_imported_canvas_block_shows_read_only_evidence(qtbot) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)
    fixture_root = Path(__file__).parents[1] / "fixtures" / "java_basic"
    window.connect_robot_project(fixture_root)
    block = next(
        item
        for item in window.scene.items()
        if isinstance(item, ArchitectureBlock)
        and item.imported
        and item.title.toPlainText() == "Drive"
    )

    block.setSelected(True)

    assert "imported subsystem" in window.details_panel.title.text()
    assert "Drive.java" in window.details_panel.code_description.text()
    assert "Devices:" in window.details_panel.code_description.text()
    assert "SparkMax: 4, MotorType.kBrushless" in window.details_panel.code_description.text()
    assert not window.details_panel.design_description.isEnabled()
    assert window.details_panel.open_source_button.isEnabled()


def test_imported_composition_details_show_direct_children(qtbot, tmp_path) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)
    (tmp_path / "build.gradle").write_text("plugins {}", encoding="utf-8")
    source_root = tmp_path / "src" / "main" / "java"
    source_root.mkdir(parents=True)
    (source_root / "Autos.java").write_text(
        """class Autos {
  Command auto() { return Commands.sequence(one(), two()); }
}
""",
        encoding="utf-8",
    )
    window.connect_robot_project(tmp_path)
    composition = next(
        item
        for item in window.scene.items()
        if isinstance(item, ArchitectureBlock) and item.title.toPlainText().startswith("sequence")
    )

    composition.setSelected(True)

    assert "Composition children:" in window.details_panel.code_description.text()
    assert "- one()" in window.details_panel.code_description.text()
    assert "- two()" in window.details_panel.code_description.text()


def test_details_dock_switches_to_compact_sheet_on_laptop_width(qtbot) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)
    window.new_project("Competition Robot")
    window.add_command("Teleop Drive")
    block = next(item for item in window.scene.items() if isinstance(item, ArchitectureBlock))
    block.setSelected(True)

    window.resize(1000, 800)
    window._open_compact_details()

    assert not window.details_dock.isVisible()
    assert window.compact_details_dialog is not None
    assert window.compact_details_dialog.isVisible()
    assert window.compact_details_panel is not None
    assert window.compact_details_panel.title.text() == "Teleop Drive (Command)"


def test_compare_marks_exact_import_match_on_canvas(qtbot) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)
    window.new_project("Competition Robot")
    window.add_subsystem("Drive")
    fixture_root = Path(__file__).parents[1] / "fixtures" / "java_basic"
    window.connect_robot_project(fixture_root)

    assert window.compare_action.isEnabled()
    assert window.export_change_request_action.isEnabled()
    comparison = window.compare_changes()

    assert comparison is not None
    assert len(comparison.matches) == 1
    assert window.accept_matches_action.isEnabled()
    matched_block = next(
        item
        for item in window.scene.items()
        if isinstance(item, ArchitectureBlock) and not item.imported and item.kind == "subsystem"
    )
    assert matched_block.caption.toPlainText() == "✓ MATCHED"

    assert window.accept_matches() == 1
    assert window.project.subsystems[0].code_binding is not None


def test_matched_design_details_can_show_and_adopt_code_name(qtbot) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)
    window.new_project("Competition Robot")
    window.add_subsystem("Drive Design")
    fixture_root = Path(__file__).parents[1] / "fixtures" / "java_basic"
    window.connect_robot_project(fixture_root)
    design_block = next(
        item
        for item in window.scene.items()
        if isinstance(item, ArchitectureBlock) and not item.imported
    )
    code_block = next(
        item
        for item in window.scene.items()
        if isinstance(item, ArchitectureBlock) and item.imported and item.kind == "subsystem"
    )
    design_block.setSelected(True)
    code_block.setSelected(True)
    assert window.bind_selected()
    design_block = next(
        item
        for item in window.scene.items()
        if isinstance(item, ArchitectureBlock) and not item.imported
    )
    design_block.setSelected(True)

    assert window.details_panel.code_name.text() == "Drive"
    assert window.details_panel.open_source_button.isEnabled()
    window.details_panel.adopt_name_button.click()

    assert window.project.subsystems[0].name.design == "Drive"
    assert window.details_panel.code_name.text() == "Drive"
    assert window.details_panel.open_source_button.isEnabled()


def test_bind_selected_explicitly_links_renamed_design_to_code(qtbot) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)
    window.new_project("Competition Robot")
    window.add_subsystem("Drive Design")
    fixture_root = Path(__file__).parents[1] / "fixtures" / "java_basic"
    window.connect_robot_project(fixture_root)
    design_block = next(
        item
        for item in window.scene.items()
        if isinstance(item, ArchitectureBlock) and not item.imported
    )
    code_block = next(
        item
        for item in window.scene.items()
        if isinstance(item, ArchitectureBlock) and item.imported and item.kind == "subsystem"
    )
    design_block.setSelected(True)
    code_block.setSelected(True)

    assert window.bind_selected_action.isEnabled()
    assert window.bind_selected()
    assert window.project.subsystems[0].code_binding == code_block.source_anchor
    assert window.reconciliation is not None
    assert (
        window.reconciliation.statuses[window.project.subsystems[0].id]
        == ComparisonState.MODIFIED
    )


def test_export_change_request_from_window(qtbot, tmp_path) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)
    window.new_project("Competition Robot")
    window.add_command("Score Coral")
    fixture_root = Path(__file__).parents[1] / "fixtures" / "java_basic"
    window.connect_robot_project(fixture_root)

    destination = window.export_change_request(tmp_path)

    assert destination.exists()
    assert "### Command: Score Coral" in destination.read_text(encoding="utf-8")


def test_close_ignores_dirty_model_when_user_cancels(qtbot, monkeypatch) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    window.new_project("Competition Robot")
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *args: QMessageBox.StandardButton.Cancel,
    )
    event = QCloseEvent()

    window.closeEvent(event)

    assert not event.isAccepted()
    window.is_dirty = False


def test_close_without_a_worker_accepts_immediately(qtbot) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)
    event = QCloseEvent()

    window.closeEvent(event)

    assert event.isAccepted()
