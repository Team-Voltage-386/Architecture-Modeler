from pathlib import Path

from PySide6.QtGui import QCloseEvent, QPalette
from PySide6.QtWidgets import QDockWidget, QMessageBox

from frc_arch_modeler.app import create_application
from frc_arch_modeler.ui.architecture_scene import ArchitectureBlock
from frc_arch_modeler.ui.main_window import MainWindow
from frc_arch_modeler.ui.theme import MUTED_TEXT, OFF_WHITE


def test_main_window_has_planned_regions(qtbot) -> None:
    app = create_application([])
    window = MainWindow()
    qtbot.addWidget(window)

    assert window.windowTitle() == "FRC Architecture Modeler"
    assert window.findChild(QDockWidget, "detailsDock") is not None
    assert window.statusBar().currentMessage() == "No robot project connected"
    assert f"QToolBar QToolButton {{\n            color: {OFF_WHITE};" in app.styleSheet()
    input_selector = "QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QComboBox {"
    assert input_selector in app.styleSheet()
    assert app.palette().color(QPalette.ColorRole.PlaceholderText).name() == MUTED_TEXT.lower()


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


def test_compare_marks_exact_import_match_on_canvas(qtbot) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)
    window.new_project("Competition Robot")
    window.add_subsystem("Drive")
    fixture_root = Path(__file__).parents[1] / "fixtures" / "java_basic"
    window.connect_robot_project(fixture_root)

    comparison = window.compare_changes()

    assert comparison is not None
    assert len(comparison.matches) == 1
    assert window.accept_matches_action.isEnabled()
    matched_block = next(
        item
        for item in window.scene.items()
        if isinstance(item, ArchitectureBlock) and not item.imported and item.kind == "subsystem"
    )
    assert matched_block.caption.toPlainText() == "Matched SUBSYSTEM"

    assert window.accept_matches() == 1
    assert window.project.subsystems[0].code_binding is not None


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
