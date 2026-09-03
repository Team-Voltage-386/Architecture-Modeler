from pathlib import Path

import pytest
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QCloseEvent, QKeySequence, QPalette
from PySide6.QtWidgets import (
    QDialog,
    QDockWidget,
    QGraphicsPathItem,
    QInputDialog,
    QMessageBox,
    QToolButton,
)

from frc_arch_modeler.app import create_application
from frc_arch_modeler.domain.model import ComparisonState
from frc_arch_modeler.ui.architecture_scene import (
    ArchitectureBlock,
    DeviceBlock,
    DeviceCountChip,
)
from frc_arch_modeler.ui.behavior_scene import StateBlock
from frc_arch_modeler.ui.entity_dialogs import (
    CommandTemplateDialog,
    DeviceDialog,
    SubsystemTemplateDialog,
)
from frc_arch_modeler.ui.main_window import MainWindow
from frc_arch_modeler.ui.theme import MUTED_TEXT, OFF_WHITE


def test_main_window_has_planned_regions(qtbot) -> None:
    app = create_application([])
    window = MainWindow()
    qtbot.addWidget(window)

    assert window.windowTitle() == "FRC Architecture Modeler"
    assert window.findChild(QDockWidget, "detailsDock") is not None
    help_dock = window.findChild(QDockWidget, "helpDock")
    assert help_dock is not None
    assert not help_dock.isVisible()
    assert not app.windowIcon().isNull()
    assert window.statusBar().currentMessage() == "No robot project connected"
    assert f"QToolBar QToolButton {{\n            color: {OFF_WHITE};" in app.styleSheet()
    input_selector = "QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QComboBox {"
    assert input_selector in app.styleSheet()
    assert "QTabBar::tab {" in app.styleSheet()
    assert "QTabBar::tab:selected {" in app.styleSheet()
    assert window.diagram_tabs.tabText(0) == "Structure"
    assert window.diagram_tabs.tabText(1) == "Behavior"
    assert app.palette().color(QPalette.ColorRole.PlaceholderText).name() == MUTED_TEXT.lower()
    assert window.search_field.accessibleName() == "Search architecture evidence"
    assert window.canvas.accessibleName() == "Architecture canvas"
    assert window.find_shortcut.key() == QKeySequence.StandardKey.Find
    assert window.save_model_action.shortcut() == QKeySequence.StandardKey.Save
    toolbar_labels = [button.text() for button in window.findChildren(QToolButton)]
    assert {"Model", "Code", "New", "Filters", "View"} <= set(toolbar_labels)
    assert not window.undo_action.icon().isNull()
    assert not window.redo_action.icon().isNull()


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


def test_creation_actions_are_undoable(qtbot) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)
    window.new_project("Competition Robot")
    window.add_subsystem("Drive")

    window.undo_stack.undo()
    assert window.project is not None
    assert not window.project.subsystems
    window.undo_stack.redo()
    assert [subsystem.name.effective for subsystem in window.project.subsystems] == ["Drive"]


def test_canvas_layout_moves_are_undoable(qtbot) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)
    window.new_project("Competition Robot")
    window.add_command("Score")
    block = next(item for item in window.scene.items() if isinstance(item, ArchitectureBlock))
    before = QPointF(block.pos())
    after = QPointF(160, 90)
    block.setPos(after)

    window._record_layout_move({block.element_id: before}, {block.element_id: after})
    window.undo_stack.undo()
    assert block.pos() == before
    window.undo_stack.redo()
    assert block.pos() == after


def test_zoom_to_fit_uses_item_bounds_not_the_padded_scene_rect(qtbot, monkeypatch) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)
    window.new_project("Competition Robot")
    window.add_subsystem("Drive")

    fitted_rects = []
    monkeypatch.setattr(
        window.canvas, "fitInView", lambda rect, *a, **k: fitted_rects.append(QRectF(rect))
    )
    window.zoom_to_fit()

    assert fitted_rects, "zoom_to_fit did not fit the view to a rect"
    items_bounds = window.scene.itemsBoundingRect()
    assert window.scene.sceneRect() != items_bounds
    margin = 20
    assert fitted_rects[0] == items_bounds.adjusted(-margin, -margin, margin, margin)


def test_behavior_zoom_to_fit_uses_item_bounds_not_the_padded_scene_rect(
    qtbot, monkeypatch
) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)
    window.new_project("Competition Robot")

    fitted_rects = []
    monkeypatch.setattr(
        window.behavior_canvas,
        "fitInView",
        lambda rect, *a, **k: fitted_rects.append(QRectF(rect)),
    )
    window.behavior_zoom_to_fit()

    assert fitted_rects, "behavior_zoom_to_fit did not fit the view to a rect"
    items_bounds = window.behavior_scene.itemsBoundingRect()
    assert window.behavior_scene.sceneRect() != items_bounds
    margin = 20
    assert fitted_rects[0] == items_bounds.adjusted(-margin, -margin, margin, margin)


def test_selected_design_block_can_be_deleted_and_undone(qtbot) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)
    window.new_project("Competition Robot")
    window.add_command("Score")
    block = next(item for item in window.scene.items() if isinstance(item, ArchitectureBlock))
    block.setSelected(True)

    assert window.delete_selected()
    assert window.project is not None
    assert not window.project.commands
    window.undo_stack.undo()
    assert [command.name.effective for command in window.project.commands] == ["Score"]


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
    # Hardware reaches the canvas as its own tier now, announced by a count chip.
    assert drive.device_chip is not None
    assert drive.device_chip.label.toPlainText().endswith("1 device")
    assert "SparkMax" not in drive.summary.toPlainText()
    assert "Driver A · onTrue" in command.summary.toPlainText()
    assert window.new_device_action.isEnabled()
    assert window.new_trigger_action.isEnabled()
    drive.setSelected(True)
    assert "Devices: Left motor (SparkMax)" in window.details_panel.design_context.text()
    drive.setSelected(False)
    command.setSelected(True)
    assert "Triggers: Driver A · onTrue" in window.details_panel.design_context.text()


def test_new_device_dialog_add_another_creates_three_devices_in_one_visit(
    qtbot, monkeypatch
) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)
    window.new_project("Competition Robot")
    window.add_subsystem("Drive")
    assert window.project is not None

    names = iter(["Left motor", "Right motor", "Back motor"])
    created_dialogs = []
    exec_calls = {"count": 0}

    original_init = DeviceDialog.__init__

    def tracking_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        created_dialogs.append(self)

    def fake_exec(self):
        exec_calls["count"] += 1
        self.type_combo.setCurrentText("SparkMax")
        self.name_edit.setText(next(names))
        self.add_another_clicked = exec_calls["count"] < 3
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(DeviceDialog, "__init__", tracking_init)
    monkeypatch.setattr(DeviceDialog, "exec", fake_exec)

    window._prompt_new_device()

    assert exec_calls["count"] == 3
    assert len(created_dialogs) == 1
    assert [device.name.effective for device in window.project.devices] == [
        "Left motor",
        "Right motor",
        "Back motor",
    ]
    assert all(device.device_type.effective == "SparkMax" for device in window.project.devices)


def test_new_subsystem_from_template_creates_a_swerve_drivetrain_undone_by_one_ctrl_z(
    qtbot, monkeypatch
) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)
    window.new_project("Competition Robot")
    assert window.project is not None
    assert window.new_subsystem_from_template_action.isEnabled()

    def fake_exec(self):
        index = self.template_combo.findText("Swerve Drivetrain")
        self.template_combo.setCurrentIndex(index)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(SubsystemTemplateDialog, "exec", fake_exec)

    window._prompt_new_subsystem_from_template()

    assert [subsystem.name.effective for subsystem in window.project.subsystems] == [
        "Swerve Drivetrain"
    ]
    devices = window.project.devices
    assert len(devices) == 13
    subsystem_id = window.project.subsystems[0].id
    assert all(device.owner_subsystem_id == subsystem_id for device in devices)
    addresses = [device.address.effective for device in devices if device.bus.effective]
    assert len(addresses) == len(set(addresses)), "template devices must not collide"

    window.undo_stack.undo()

    assert not window.project.subsystems
    assert not window.project.devices

    window.undo_stack.redo()

    assert len(window.project.subsystems) == 1
    assert len(window.project.devices) == 13


def test_new_subsystem_from_template_proposes_addresses_after_existing_devices(
    qtbot, monkeypatch
) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)
    window.new_project("Competition Robot")
    window.add_subsystem("Existing")
    assert window.project is not None
    window.add_device(
        window.project.subsystems[0].id, "Existing Motor", "TalonFX", bus="canivore", address="1"
    )

    def fake_exec(self):
        index = self.template_combo.findText("Vision")
        self.template_combo.setCurrentIndex(index)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(SubsystemTemplateDialog, "exec", fake_exec)

    window._prompt_new_subsystem_from_template()

    vision_devices = [
        device for device in window.project.devices if device.name.effective == "Camera"
    ]
    assert len(vision_devices) == 1


def test_new_command_from_template_creates_command_requirement_and_trigger_in_one_undo_entry(
    qtbot, monkeypatch
) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)
    window.new_project("Competition Robot")
    window.add_subsystem("Drive")
    assert window.project is not None
    assert window.new_command_from_template_action.isEnabled()

    def fake_exec(self):
        self.name_edit.setText("Teleop Drive")
        self.add_trigger_checkbox.setChecked(True)
        self.expression_edit.setText("Driver A")
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(CommandTemplateDialog, "exec", fake_exec)

    window._prompt_new_command_from_template()

    assert [command.name.effective for command in window.project.commands] == ["Teleop Drive"]
    command = window.project.commands[0]
    assert command.requirement_ids == [window.project.subsystems[0].id]
    assert len(window.project.triggers) == 1
    assert window.project.triggers[0].expression.effective == "Driver A"

    window.undo_stack.undo()

    assert not window.project.commands
    assert not window.project.triggers

    window.undo_stack.redo()

    assert len(window.project.commands) == 1
    assert len(window.project.triggers) == 1


def test_new_command_from_template_without_a_trigger_creates_no_trigger(qtbot, monkeypatch) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)
    window.new_project("Competition Robot")
    window.add_subsystem("Drive")
    assert window.project is not None

    def fake_exec(self):
        self.name_edit.setText("Teleop Drive")
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(CommandTemplateDialog, "exec", fake_exec)

    window._prompt_new_command_from_template()

    assert len(window.project.commands) == 1
    assert not window.project.triggers


def test_explicit_design_relationship_is_rendered_with_evidence_tooltip(qtbot) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)
    window.new_project("Competition Robot")
    window.add_subsystem("Drive")
    window.add_command("Teleop Drive")
    assert window.project is not None

    window.add_relationship(
        "calls", window.project.commands[0].id, window.project.subsystems[0].id
    )

    edges = [item for item in window.scene.items() if isinstance(item, QGraphicsPathItem)]
    assert any(item.toolTip() == "Designed calls relationship" for item in edges)
    assert window.new_relationship_action.isEnabled()


def test_selected_command_and_subsystem_can_be_linked_as_a_requirement(qtbot) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)
    window.new_project("Competition Robot")
    window.add_subsystem("Drive")
    window.add_command("Teleop Drive")
    assert window.project is not None

    blocks = [item for item in window.scene.items() if isinstance(item, ArchitectureBlock)]
    next(block for block in blocks if block.kind == "command").setSelected(True)
    next(block for block in blocks if block.kind == "subsystem").setSelected(True)

    assert window.link_selected_action.isEnabled()
    assert window.link_selected_requirement()
    assert window.project.subsystems[0].id in window.project.commands[0].requirement_ids
    edges = [item for item in window.scene.items() if isinstance(item, QGraphicsPathItem)]
    assert any(item.toolTip() == "Designed requirement" for item in edges)


def test_drag_connection_between_command_and_subsystem_offers_requires(qtbot) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)
    window.new_project("Competition Robot")
    window.add_subsystem("Drive")
    window.add_command("Teleop Drive")
    assert window.project is not None

    blocks = [item for item in window.scene.items() if isinstance(item, ArchitectureBlock)]
    command_block = next(block for block in blocks if block.kind == "command")
    subsystem_block = next(block for block in blocks if block.kind == "subsystem")

    window._apply_requested_connection(command_block, subsystem_block, "requires")

    assert window.project.subsystems[0].id in window.project.commands[0].requirement_ids


def test_drag_connection_creates_typed_relationship(qtbot) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)
    window.new_project("Competition Robot")
    window.add_subsystem("Drive")
    window.add_subsystem("Intake")
    assert window.project is not None

    blocks = [item for item in window.scene.items() if isinstance(item, ArchitectureBlock)]
    drive_block, intake_block = blocks[0], blocks[1]

    window._apply_requested_connection(drive_block, intake_block, "contains")

    assert len(window.project.relationships) == 1
    relationship = window.project.relationships[0]
    assert relationship.relationship_type == "contains"
    assert relationship.source_id == drive_block.element_id
    assert relationship.target_id == intake_block.element_id


def test_new_project_seeds_and_renders_the_robot_mode_behavior_diagram(qtbot) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)

    window.new_project("Competition Robot")

    assert len(window.project.behavior_diagrams) == 1
    blocks = [item for item in window.behavior_scene.items() if isinstance(item, StateBlock)]
    assert {block.title.toPlainText() for block in blocks} == {
        "Start",
        "Disabled",
        "Autonomous",
        "Teleop",
        "Test",
    }
    assert window.new_behavior_state_action.isEnabled()


def test_behavior_toolbar_sits_above_the_behavior_canvas_and_starts_disabled(qtbot) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)

    assert window.behavior_toolbar.parent() is window._behavior_tab
    assert window.diagram_tabs.widget(1) is window._behavior_tab
    for action in (
        window.new_behavior_state_action,
        window.new_behavior_start_action,
        window.new_behavior_end_action,
        window.new_behavior_decision_action,
        window.new_behavior_sync_action,
        window.new_behavior_join_action,
    ):
        assert not action.isEnabled()

    window.new_project("Competition Robot")

    for action in (
        window.new_behavior_state_action,
        window.new_behavior_start_action,
        window.new_behavior_end_action,
        window.new_behavior_decision_action,
        window.new_behavior_sync_action,
        window.new_behavior_join_action,
    ):
        assert action.isEnabled()


def test_every_toolbar_action_has_a_tooltip_and_status_tip(qtbot) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)

    toolbar_actions = [
        window.new_model_action,
        window.open_model_action,
        window.save_model_action,
        window.connect_robot_action,
        window.refresh_code_action,
        window.cancel_scan_action,
        window.compare_action,
        window.accept_matches_action,
        window.bind_selected_action,
        window.export_change_request_action,
        window.export_architecture_action,
        window.new_command_action,
        window.new_command_from_template_action,
        window.new_subsystem_action,
        window.new_subsystem_from_template_action,
        window.new_device_action,
        window.new_trigger_action,
        window.new_relationship_action,
        window.show_command_forms_action,
        window.link_selected_action,
        window.delete_selected_action,
        window.undo_action,
        window.redo_action,
        window.auto_layout_action,
        window.zoom_to_fit_action,
        window.minimize_action,
        window.restore_action,
        window.device_view_action,
        window.toggle_help_action,
        *window._status_filter_actions.values(),
        window.new_behavior_state_action,
        window.new_behavior_start_action,
        window.new_behavior_end_action,
        window.new_behavior_decision_action,
        window.new_behavior_sync_action,
        window.new_behavior_join_action,
        window.behavior_zoom_to_fit_action,
    ]
    for action in toolbar_actions:
        assert action.toolTip(), f"{action.text()!r} has no tooltip"
        assert action.statusTip(), f"{action.text()!r} has no status tip"


def test_behavior_palette_buttons_get_a_shape_icon_matching_the_canvas(qtbot) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)

    for action in (
        window.new_behavior_state_action,
        window.new_behavior_start_action,
        window.new_behavior_end_action,
        window.new_behavior_decision_action,
        window.new_behavior_sync_action,
        window.new_behavior_join_action,
    ):
        assert not action.icon().isNull()


def test_help_panel_is_hidden_on_startup_and_toggled_by_f1_and_the_toolbar_button(
    qtbot,
) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    qtbot.waitUntil(window.isVisible)

    assert not window.help_dock.isVisible()
    assert window.toggle_help_action.shortcut() == QKeySequence(Qt.Key.Key_F1)

    window.toggle_help_action.trigger()
    qtbot.waitUntil(window.help_dock.isVisible)

    window.toggle_help_action.trigger()
    qtbot.waitUntil(lambda: not window.help_dock.isVisible())


def test_help_panel_search_filters_sections_by_title_and_content(qtbot) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    qtbot.waitUntil(window.isVisible)
    window.toggle_help_action.trigger()
    qtbot.waitUntil(window.help_dock.isVisible)

    panel = window.help_panel
    visible_titles = lambda: {  # noqa: E731
        title for title, _, _, label in panel._sections if label.isVisible()
    }
    structure_titles = {
        title for title, _, context, _ in panel._sections if context == "structure"
    }
    assert visible_titles() == structure_titles

    panel.search_field.setText("diamond")
    assert visible_titles() == {"Relationship lines"}

    panel.search_field.setText("")
    assert visible_titles() == structure_titles


def test_help_panel_shows_only_the_active_diagram_tabs_sections(qtbot) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    qtbot.waitUntil(window.isVisible)
    window.toggle_help_action.trigger()
    qtbot.waitUntil(window.help_dock.isVisible)

    panel = window.help_panel
    visible_titles = lambda: {  # noqa: E731
        title for title, _, _, label in panel._sections if label.isVisible()
    }
    structure_titles = {
        title for title, _, context, _ in panel._sections if context == "structure"
    }
    behavior_titles = {
        title for title, _, context, _ in panel._sections if context == "behavior"
    }
    assert visible_titles() == structure_titles

    window.diagram_tabs.setCurrentWidget(window._behavior_tab)
    assert visible_titles() == behavior_titles

    window.diagram_tabs.setCurrentIndex(0)
    assert visible_titles() == structure_titles


@pytest.mark.parametrize(
    ("kind", "label"),
    [
        ("start", "Start"),
        ("end", "End"),
        ("decision", "Decision"),
        ("synchronization", "Sync"),
        ("join", "Join"),
    ],
)
def test_behavior_palette_buttons_add_the_matching_pseudostate(qtbot, kind, label) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)
    window.new_project("Competition Robot")

    window._add_behavior_pseudostate(kind)

    diagram = window.project.behavior_diagrams[0]
    added = next(state for state in diagram.states if state.kind == kind)
    assert added.name.effective == label
    block = next(
        item
        for item in window.behavior_scene.items()
        if isinstance(item, StateBlock) and item.state_id == added.id
    )
    assert block.kind == kind


def test_behavior_transition_from_start_pseudostate_allows_blank_trigger(
    qtbot, monkeypatch
) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)
    window.new_project("Competition Robot")
    window._add_behavior_pseudostate("start")
    diagram = window.project.behavior_diagrams[0]
    monkeypatch.setattr(QInputDialog, "getText", lambda *args, **kwargs: ("", True))

    blocks = {
        block.title.toPlainText(): block
        for block in window.behavior_scene.items()
        if isinstance(block, StateBlock)
    }
    window._handle_behavior_connection_requested(blocks["Start"], blocks["Disabled"], QPointF(0, 0))

    assert any(
        transition.trigger_label == ""
        and transition.source_state_id == blocks["Start"].state_id
        and transition.target_state_id == blocks["Disabled"].state_id
        for transition in diagram.transitions
    )


def test_behavior_transition_created_via_connector_drag_prompts_for_trigger(
    qtbot, monkeypatch
) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)
    window.new_project("Competition Robot")
    diagram = window.project.behavior_diagrams[0]
    monkeypatch.setattr(QInputDialog, "getText", lambda *args, **kwargs: ("Match starts", True))

    blocks = {
        block.title.toPlainText(): block
        for block in window.behavior_scene.items()
        if isinstance(block, StateBlock)
    }
    window._handle_behavior_connection_requested(
        blocks["Disabled"], blocks["Teleop"], QPointF(0, 0)
    )

    assert any(
        transition.trigger_label == "Match starts"
        and transition.source_state_id == blocks["Disabled"].state_id
        and transition.target_state_id == blocks["Teleop"].state_id
        for transition in diagram.transitions
    )


def test_behavior_state_rename_and_dependency_blocked_delete(qtbot, monkeypatch) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)
    window.new_project("Competition Robot")
    diagram = window.project.behavior_diagrams[0]
    disabled_state = next(state for state in diagram.states if state.name.effective == "Disabled")

    block = next(
        item
        for item in window.behavior_scene.items()
        if isinstance(item, StateBlock) and item.state_id == disabled_state.id
    )
    monkeypatch.setattr(
        QInputDialog, "getText", lambda *args, **kwargs: ("Robot Disabled", True)
    )
    window._prompt_rename_behavior_state(block)
    assert disabled_state.name.effective == "Robot Disabled"

    # Renaming re-renders the scene, so the state's block is a fresh instance now.
    block = next(
        item
        for item in window.behavior_scene.items()
        if isinstance(item, StateBlock) and item.state_id == disabled_state.id
    )
    warnings = []
    monkeypatch.setattr(
        QMessageBox, "warning", lambda *args, **kwargs: warnings.append(args) or None
    )
    block.setSelected(True)
    assert not window.delete_behavior_selected()
    assert warnings


def test_behavior_transition_line_deleted_via_right_click_style_signal(qtbot) -> None:
    """The scene's context menu emits transition_delete_requested; verify the window handles it."""
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)
    window.new_project("Competition Robot")
    diagram = window.project.behavior_diagrams[0]
    transition = diagram.transitions[0]

    window.behavior_scene.transition_delete_requested.emit(transition.id)

    assert transition not in diagram.transitions
    window.undo_stack.undo()
    assert transition in diagram.transitions


def test_selecting_a_transition_line_enables_delete_selected(qtbot) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)
    window.new_project("Competition Robot")
    window.diagram_tabs.setCurrentIndex(1)
    edge = window.behavior_scene._edges[0]

    assert not window.delete_selected_action.isEnabled()

    edge.setSelected(True)
    transition_id = edge.transition_id

    assert window.delete_selected_action.isEnabled()
    assert window.delete_behavior_selected()
    assert transition_id not in {t.id for t in window.project.behavior_diagrams[0].transitions}


def test_dragging_a_transition_endpoint_onto_a_new_state_reconnects_it(qtbot) -> None:
    """The scene's transition_reattach_requested signal is what an endpoint drag emits."""
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)
    window.new_project("Competition Robot")
    diagram = window.project.behavior_diagrams[0]
    transition = next(
        t for t in diagram.transitions if t.trigger_label == "Autonomous period starts"
    )
    original_target_id = transition.target_state_id
    climb_state = window.project_service.add_behavior_state(diagram, "Climb")
    window._refresh_behavior_after_edit()

    window.behavior_scene.transition_reattach_requested.emit(
        transition.id, "target", climb_state.id
    )

    assert transition.target_state_id == climb_state.id
    window.undo_stack.undo()
    assert transition.target_state_id == original_target_id


def test_behavior_diagram_survives_save_and_reopen(qtbot, tmp_path) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)
    window.new_project("Competition Robot")
    window.add_behavior_state("Climb")
    window.save_project(tmp_path)

    reopened_window = MainWindow()
    qtbot.addWidget(reopened_window)
    reopened_project = reopened_window.open_project(tmp_path)

    assert {state.name.effective for state in reopened_project.behavior_diagrams[0].states} == {
        "Start",
        "Disabled",
        "Autonomous",
        "Teleop",
        "Test",
        "Climb",
    }
    reopened_blocks = [
        item for item in reopened_window.behavior_scene.items() if isinstance(item, StateBlock)
    ]
    assert len(reopened_blocks) == 6


def test_recent_model_action_is_hidden_until_a_model_has_been_saved_or_opened(qtbot) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)

    assert window.open_recent_model_action.isVisible() is False


def test_saving_a_model_reveals_the_recent_model_action(qtbot, tmp_path) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)
    window.new_project("Competition Robot")

    window.save_project(tmp_path)

    assert window.open_recent_model_action.isVisible() is True
    assert tmp_path.name in window.open_recent_model_action.text()
    assert window.recent_model_store.load() == tmp_path


def test_recent_model_action_survives_a_fresh_main_window_and_reopens_the_model(
    qtbot, tmp_path
) -> None:
    """A relaunch of the app (a new MainWindow) should still see the last model saved
    by a previous run, since it's tracked on disk rather than in memory."""
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)
    window.new_project("Competition Robot")
    window.save_project(tmp_path)

    reopened_window = MainWindow()
    qtbot.addWidget(reopened_window)

    assert reopened_window.open_recent_model_action.isVisible() is True

    reopened_window._open_recent_model()

    assert reopened_window.project is not None
    assert reopened_window.project.name == "Competition Robot"
    assert reopened_window.model_root == tmp_path


def test_behavior_model_browser_replaces_inventory_dock_on_behavior_tab(qtbot) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)
    window.new_project("Competition Robot")
    fixture_root = Path(__file__).parents[1] / "fixtures" / "java_basic"
    window.connect_robot_project(fixture_root)

    assert window._left_dock_stack.currentWidget() is window.inventory_tree

    window.diagram_tabs.setCurrentIndex(1)
    assert window._left_dock_stack.currentWidget() is window.behavior_model_browser

    window.diagram_tabs.setCurrentIndex(0)
    assert window._left_dock_stack.currentWidget() is window.inventory_tree


def test_model_browser_shows_root_and_command_scoped_diagrams(qtbot) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)
    window.new_project("Competition Robot")
    window.add_command("Auto Routine")
    command = window.project.commands[0]
    window._add_command_behavior_diagram(command.id)

    root_header = window.behavior_model_browser.topLevelItem(0)
    commands_header = window.behavior_model_browser.topLevelItem(1)
    assert root_header.text(0) == "Root Diagrams"
    assert commands_header.text(0) == "Commands"
    assert root_header.child(0).text(0) == "Robot Modes"
    command_item = next(
        commands_header.child(i)
        for i in range(commands_header.childCount())
        if commands_header.child(i).data(0, Qt.ItemDataRole.UserRole) == ("command", command.id)
    )
    assert command_item.child(0).text(0) == "Untitled Diagram"


def test_selecting_a_diagram_in_the_tree_renders_it_on_the_behavior_canvas(qtbot) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)
    window.new_project("Competition Robot")
    window._add_root_behavior_diagram()
    second_diagram_id = window.project.behavior_diagrams[1].id
    first_diagram_id = window.project.behavior_diagrams[0].id

    window._select_behavior_diagram(second_diagram_id)
    assert window._active_behavior_diagram().id == second_diagram_id
    assert not any(
        isinstance(item, StateBlock) for item in window.behavior_scene.items()
    )

    window._select_behavior_diagram(first_diagram_id)
    assert window._active_behavior_diagram().id == first_diagram_id
    assert any(isinstance(item, StateBlock) for item in window.behavior_scene.items())


def test_new_root_diagram_action_creates_and_selects_a_diagram(qtbot) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)
    window.new_project("Competition Robot")

    window._add_root_behavior_diagram()

    assert len(window.project.behavior_diagrams) == 2
    new_diagram = window.project.behavior_diagrams[1]
    assert new_diagram.owner_command_id is None
    assert window._selected_behavior_diagram_id == new_diagram.id

    window.undo_stack.undo()
    assert len(window.project.behavior_diagrams) == 1


def test_new_command_diagram_action_ties_diagram_to_command(qtbot) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)
    window.new_project("Competition Robot")
    window.add_command("Auto Routine")
    command = window.project.commands[0]

    window._add_command_behavior_diagram(command.id)

    new_diagram = window.project.behavior_diagrams[1]
    assert new_diagram.owner_command_id == command.id


def test_rename_behavior_diagram_via_dialog_is_undoable(qtbot, monkeypatch) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)
    window.new_project("Competition Robot")
    diagram = window.project.behavior_diagrams[0]
    monkeypatch.setattr(QInputDialog, "getText", lambda *args, **kwargs: ("Match Modes", True))

    window._rename_behavior_diagram(diagram.id)

    assert diagram.name == "Match Modes"
    window.undo_stack.undo()
    assert diagram.name == "Robot Modes"


def test_delete_behavior_diagram_is_undoable_without_confirmation(qtbot, monkeypatch) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)
    window.new_project("Competition Robot")
    diagram = window.project.behavior_diagrams[0]

    def _fail_if_called(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("Delete must not prompt for confirmation")

    monkeypatch.setattr(QMessageBox, "question", _fail_if_called)

    window._delete_behavior_diagram(diagram.id)

    assert diagram not in window.project.behavior_diagrams
    assert window._selected_behavior_diagram_id is None
    window.undo_stack.undo()
    assert diagram in window.project.behavior_diagrams


def test_opening_legacy_project_selects_first_diagram_as_root_level(qtbot, tmp_path) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)
    window.new_project("Competition Robot")
    window.save_project(tmp_path)
    saved_payload = (tmp_path / ".frc-architecture" / "model.json").read_text(encoding="utf-8")
    assert "ownerCommandId" not in saved_payload or '"ownerCommandId": null' in saved_payload

    reopened_window = MainWindow()
    qtbot.addWidget(reopened_window)
    reopened_project = reopened_window.open_project(tmp_path)

    assert reopened_window._selected_behavior_diagram_id == reopened_project.behavior_diagrams[0].id
    root_header = reopened_window.behavior_model_browser.topLevelItem(0)
    assert root_header.child(0).text(0) == "Robot Modes"


def test_open_sample_model_copies_the_shipped_sample_into_a_chosen_folder_and_opens_it(
    qtbot, tmp_path
) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)
    destination = tmp_path / "my_robot"
    shipped_model = (
        Path(__file__).parents[2]
        / "resources"
        / "sample_model"
        / ".frc-architecture"
        / "model.json"
    )
    shipped_contents_before = shipped_model.read_text(encoding="utf-8")

    project = window.open_sample_model(destination)

    assert project.name == "Sample Swerve Robot"
    assert window.model_root == destination
    copied_model = destination / ".frc-architecture" / "model.json"
    assert copied_model.read_text(encoding="utf-8") == shipped_contents_before

    window.add_command("Student's New Command")
    window.save_project()

    assert shipped_model.read_text(encoding="utf-8") == shipped_contents_before


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
    assert not window.details_panel.lifecycle_diagram.isHidden()
    window.show()
    qtbot.waitUntil(window.details_panel.lifecycle_diagram.isVisible)
    assert not window.details_panel.lifecycle_diagram.grab().isNull()
    opened = []
    window.details_panel._on_open_source = opened.append
    window.details_panel.lifecycle_diagram.phase_activated.emit("initialize")
    assert opened[0].qualified_symbol.endswith("DriveCommand#initialize")
    window.details_panel.lifecycle_diagram.phase_activated.emit("inherited phase")
    assert len(opened) == 1


def test_imported_functional_command_shows_lifecycle_flow(qtbot, tmp_path) -> None:
    create_application([])
    source_root = tmp_path / "src" / "main" / "java"
    source_root.mkdir(parents=True)
    (tmp_path / "build.gradle").write_text("plugins {}", encoding="utf-8")
    (source_root / "Commands.java").write_text(
        """class Commands {
  Command hold() {
    return new FunctionalCommand(() -> start(), () -> run(),
        interrupted -> stop(), () -> false);
  }
}
""",
        encoding="utf-8",
    )
    window = MainWindow()
    qtbot.addWidget(window)

    window.connect_robot_project(tmp_path)
    window.show_command_forms_action.setChecked(True)
    functional = next(
        block
        for block in window.scene.items()
        if isinstance(block, ArchitectureBlock)
        and block.title.toPlainText() == "FunctionalCommand (line 3)"
    )
    functional.setSelected(True)

    assert "Start \u2192 initialize \u2192 execute \u2192 isFinished \u2192 end(interrupted)" in (
        window.details_panel.lifecycle_flow.text()
    )
    assert "Functional command phases:" in window.details_panel.code_description.text()


def test_imported_run_once_command_shows_its_instant_flow(qtbot, tmp_path) -> None:
    create_application([])
    source_root = tmp_path / "src" / "main" / "java"
    source_root.mkdir(parents=True)
    (tmp_path / "build.gradle").write_text("plugins {}", encoding="utf-8")
    (source_root / "Commands.java").write_text(
        """class Commands {
  Command stop() { return Commands.runOnce(() -> stopMotor()); }
}
""",
        encoding="utf-8",
    )
    window = MainWindow()
    qtbot.addWidget(window)

    window.connect_robot_project(tmp_path)
    window.show_command_forms_action.setChecked(True)
    run_once = next(
        block
        for block in window.scene.items()
        if isinstance(block, ArchitectureBlock) and block.title.toPlainText() == "runOnce (line 2)"
    )
    run_once.setSelected(True)

    assert window.details_panel.lifecycle_flow.text() == "Start \u2192 action \u2192 Finish"


def test_imported_command_details_show_scheduler_registration_evidence(qtbot, tmp_path) -> None:
    create_application([])
    source_root = tmp_path / "src" / "main" / "java"
    source_root.mkdir(parents=True)
    (tmp_path / "build.gradle").write_text("plugins {}", encoding="utf-8")
    (source_root / "DriveCommand.java").write_text(
        "class DriveCommand extends CommandBase {}", encoding="utf-8"
    )
    (source_root / "RobotContainer.java").write_text(
        """class RobotContainer {
  void configure(Drive drive) { drive.setDefaultCommand(new DriveCommand()); }
}
""",
        encoding="utf-8",
    )
    window = MainWindow()
    qtbot.addWidget(window)

    window.connect_robot_project(tmp_path)
    command = next(
        block
        for block in window.scene.items()
        if isinstance(block, ArchitectureBlock) and block.title.toPlainText() == "DriveCommand"
    )
    command.setSelected(True)

    assert "Scheduler registrations:" in window.details_panel.code_description.text()
    assert "Default command: new DriveCommand()" in window.details_panel.code_description.text()


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


def test_design_only_description_is_rendered_on_the_canvas_immediately(qtbot) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)
    window.new_project("Competition Robot")
    window.add_command("Teleop Drive")
    block = next(item for item in window.scene.items() if isinstance(item, ArchitectureBlock))
    block.setSelected(True)

    window.edit_selected_description("Drive using the joystick.")

    updated = next(item for item in window.scene.items() if isinstance(item, ArchitectureBlock))
    assert "Drive using the joystick." in updated.summary.toPlainText()


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


def test_details_can_revert_proposed_name_and_description_to_scanned_values(qtbot) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)
    window.new_project("Competition Robot")
    window.add_command("Proposed Drive")
    command = window.project.commands[0]
    command.name.scanned = "DriveCommand"
    command.description.scanned = "Drives the robot from joystick input."
    block = next(item for item in window.scene.items() if isinstance(item, ArchitectureBlock))
    block.setSelected(True)
    window.edit_selected_description("Custom proposed behavior.")

    window.details_panel.revert_name_button.click()
    window.details_panel.revert_button.click()

    assert command.name.design is None
    assert command.name.effective == "DriveCommand"
    assert command.description.design is None
    assert command.description.effective == "Drives the robot from joystick input."


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
    window.show_command_forms_action.setChecked(True)
    composition = next(
        item
        for item in window.scene.items()
        if isinstance(item, ArchitectureBlock) and item.title.toPlainText().startswith("sequence")
    )

    composition.setSelected(True)

    assert "Composition children:" in window.details_panel.code_description.text()
    assert window.details_panel.lifecycle_flow.isHidden()
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


def _select_block(window, title: str) -> ArchitectureBlock:
    block = next(
        item
        for item in window.scene.items()
        if isinstance(item, ArchitectureBlock) and item.title.toPlainText() == title
    )
    block.setSelected(True)
    return block


def test_selected_subsystem_lists_its_devices_and_a_command_lists_its_triggers(qtbot) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)
    window.new_project("Competition Robot")
    window.add_subsystem("Shooter")
    window.add_command("Score Coral")
    assert window.project is not None
    window.add_device(window.project.subsystems[0].id, "Left motor", "SparkMax")
    window.add_trigger(window.project.commands[0].id, "Driver A", "onTrue")
    window.add_relationship(
        "calls", window.project.commands[0].id, window.project.subsystems[0].id
    )
    panel = window.details_panel

    _select_block(window, "Shooter")

    assert [
        panel._owned_lists["device"].item(index).text()
        for index in range(panel._owned_lists["device"].count())
    ] == ["Left motor (SparkMax)"]
    assert panel._owned_rows["device"].isVisibleTo(panel)
    assert not panel._owned_rows["trigger"].isVisibleTo(panel)
    assert panel._owned_lists["relationship"].count() == 1

    window.scene.clearSelection()
    _select_block(window, "Score Coral")

    assert [
        panel._owned_lists["trigger"].item(index).text()
        for index in range(panel._owned_lists["trigger"].count())
    ] == ["Driver A · onTrue"]
    assert not panel._owned_rows["device"].isVisibleTo(panel)


def test_a_device_can_be_renamed_from_its_subsystem_details_panel(qtbot, monkeypatch) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)
    window.new_project("Competition Robot")
    window.add_subsystem("Shooter")
    assert window.project is not None
    window.add_device(window.project.subsystems[0].id, "Left motor", "SparkMax")
    device = window.project.devices[0]

    def fake_exec(self):
        self.name_edit.setText("Feeder motor")
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(DeviceDialog, "exec", fake_exec)
    _select_block(window, "Shooter")
    window.details_panel._owned_lists["device"].setCurrentRow(0)
    window.details_panel._owned_buttons["device"]["edit"].click()

    assert device.name.effective == "Feeder motor"
    window.undo_stack.undo()
    assert device.name.effective == "Left motor"


def test_editing_a_device_leaves_its_scanned_fact_untouched(qtbot, monkeypatch) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)
    window.new_project("Competition Robot")
    window.add_subsystem("Shooter")
    assert window.project is not None
    window.add_device(window.project.subsystems[0].id, "Left motor", "SparkMax")
    device = window.project.devices[0]
    device.name.scanned = "leftMotor"

    monkeypatch.setattr(
        DeviceDialog,
        "exec",
        lambda self: (self.name_edit.setText("Feeder motor"), QDialog.DialogCode.Accepted)[1],
    )
    _select_block(window, "Shooter")
    window.details_panel._owned_lists["device"].setCurrentRow(0)
    window.details_panel._owned_buttons["device"]["edit"].click()

    assert device.name.design == "Feeder motor"
    assert device.name.scanned == "leftMotor"


def test_a_device_can_be_deleted_from_its_subsystem_details_panel(qtbot) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)
    window.new_project("Competition Robot")
    window.add_subsystem("Shooter")
    assert window.project is not None
    window.add_device(window.project.subsystems[0].id, "Left motor", "SparkMax")

    _select_block(window, "Shooter")
    window.details_panel._owned_lists["device"].setCurrentRow(0)
    window.details_panel._owned_buttons["device"]["remove"].click()

    assert not window.project.devices
    window.undo_stack.undo()
    assert [device.name.effective for device in window.project.devices] == ["Left motor"]


def test_deleting_a_subsystem_removes_its_dependents_in_one_confirmed_step(
    qtbot, monkeypatch
) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)
    window.new_project("Competition Robot")
    window.add_subsystem("Shooter")
    window.add_command("Score Coral")
    assert window.project is not None
    subsystem = window.project.subsystems[0]
    window.add_device(subsystem.id, "Left motor", "SparkMax")
    window.add_device(subsystem.id, "Right motor", "SparkMax")
    window.add_trigger(window.project.commands[0].id, "Driver A", "onTrue")
    window.add_relationship("calls", window.project.commands[0].id, subsystem.id)
    prompts = []

    def fake_question(parent, title, text, *args):
        prompts.append(text)
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(QMessageBox, "question", fake_question)
    _select_block(window, "Shooter")

    assert window.delete_selected()
    assert prompts == ["Delete Shooter and its 2 devices and 1 relationship?"]
    assert not window.project.subsystems
    assert not window.project.devices
    assert not window.project.relationships
    assert len(window.project.triggers) == 1

    window.undo_stack.undo()

    assert [item.name.effective for item in window.project.subsystems] == ["Shooter"]
    assert [device.name.effective for device in window.project.devices] == [
        "Left motor",
        "Right motor",
    ]
    assert len(window.project.relationships) == 1


def test_declining_the_cascade_confirmation_deletes_nothing(qtbot, monkeypatch) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)
    window.new_project("Competition Robot")
    window.add_subsystem("Shooter")
    assert window.project is not None
    window.add_device(window.project.subsystems[0].id, "Left motor", "SparkMax")
    monkeypatch.setattr(
        QMessageBox, "question", lambda *args: QMessageBox.StandardButton.No
    )
    _select_block(window, "Shooter")

    assert not window.delete_selected()
    assert window.project.subsystems
    assert window.project.devices


def test_deleting_a_subsystem_a_command_requires_is_still_refused(qtbot, monkeypatch) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)
    window.new_project("Competition Robot")
    window.add_subsystem("Shooter")
    window.add_command("Score Coral")
    assert window.project is not None
    window.project.commands[0].requirement_ids = [window.project.subsystems[0].id]
    warnings = []

    def fake_warning(parent, title, text, *args):
        warnings.append(text)
        return QMessageBox.StandardButton.Ok

    monkeypatch.setattr(QMessageBox, "warning", fake_warning)
    _select_block(window, "Shooter")

    assert not window.delete_selected()
    assert warnings == ["Shooter is still required by Score Coral. Clear that requirement first."]
    assert window.project.subsystems


def _new_robot_with_a_device(qtbot, name: str = "Left motor"):  # type: ignore[no-untyped-def]
    """A saved-shaped model with one subsystem owning one fully wired device."""
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)
    window.new_project("Competition Robot")
    window.add_subsystem("Drive")
    assert window.project is not None
    window.add_device(
        window.project.subsystems[0].id, name, "SparkMax", "REAL", "canivore", "3"
    )
    return window


def test_device_view_action_cycles_grouped_expanded_and_hidden(qtbot) -> None:
    window = _new_robot_with_a_device(qtbot)
    device_blocks = lambda: [  # noqa: E731
        item for item in window.scene.items() if isinstance(item, DeviceBlock)
    ]
    chips = lambda: [  # noqa: E731
        item for item in window.scene.items() if isinstance(item, DeviceCountChip)
    ]

    assert window.device_view_action.isEnabled()
    assert window.device_view_action.text() == "Devices: Grouped"
    assert not device_blocks()
    assert len(chips()) == 1

    window.device_view_action.trigger()
    assert window.scene.device_view_state == "expanded"
    assert window.device_view_action.text() == "Devices: Expanded"
    assert [block.title.toPlainText() for block in device_blocks()] == ["Left motor"]
    assert not chips()

    window.device_view_action.trigger()
    assert window.device_view_action.text() == "Devices: Hidden"
    assert not device_blocks()
    assert not chips()

    window.device_view_action.trigger()
    assert window.device_view_action.text() == "Devices: Grouped"
    assert len(chips()) == 1


def test_device_view_state_survives_save_and_reopen(qtbot, tmp_path) -> None:
    window = _new_robot_with_a_device(qtbot)
    window.device_view_action.trigger()
    window.device_view_action.trigger()
    assert window.scene.device_view_state == "hidden"
    window.save_project(tmp_path)

    reopened = MainWindow()
    qtbot.addWidget(reopened)
    reopened.open_project(tmp_path)

    assert reopened.scene.device_view_state == "hidden"
    assert reopened.device_view_action.text() == "Devices: Hidden"
    assert not [item for item in reopened.scene.items() if isinstance(item, DeviceBlock)]


def test_per_subsystem_device_expansion_survives_save_and_reopen(qtbot, tmp_path) -> None:
    window = _new_robot_with_a_device(qtbot)
    window.add_subsystem("Arm")
    assert window.project is not None
    window.add_device(window.project.subsystems[1].id, "Elbow", "TalonFX")
    drive_id = window.project.subsystems[0].id

    window.scene.toggle_subsystem_devices(drive_id)
    assert [
        item.title.toPlainText()
        for item in window.scene.items()
        if isinstance(item, DeviceBlock)
    ] == ["Left motor"]
    window.save_project(tmp_path)

    reopened = MainWindow()
    qtbot.addWidget(reopened)
    reopened.open_project(tmp_path)

    assert reopened.scene.device_view_state == "grouped"
    assert reopened.scene.expanded_device_subsystems == {drive_id}
    assert [
        item.title.toPlainText()
        for item in reopened.scene.items()
        if isinstance(item, DeviceBlock)
    ] == ["Left motor"]


def test_selecting_a_device_block_shows_it_in_the_details_panel(qtbot, monkeypatch) -> None:
    window = _new_robot_with_a_device(qtbot)
    window.device_view_action.trigger()
    device = window.project.devices[0]
    block = next(
        item for item in window.scene.items() if isinstance(item, DeviceBlock)
    )

    block.setSelected(True)

    panel = window.details_panel
    assert panel.title.text() == "Left motor (Device)"
    context = panel.design_context.text()
    assert "Owner subsystem: Drive" in context
    assert "Type: SparkMax" in context
    assert "Bus: canivore" in context
    assert "Address: 3" in context
    assert panel.edit_device_button.isVisibleTo(panel)

    monkeypatch.setattr(
        DeviceDialog,
        "exec",
        lambda self: (self.name_edit.setText("Feeder motor"), QDialog.DialogCode.Accepted)[1],
    )
    panel.edit_device_button.click()

    assert device.name.effective == "Feeder motor"
    assert len(window.scene.selected_device_blocks()) == 1
    window.undo_stack.undo()
    assert device.name.effective == "Left motor"


def test_closing_the_left_panel_can_be_restored_from_the_toolbar(qtbot) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)
    window.new_project("Competition Robot")

    window._left_dock.close()

    assert not window._left_dock.isVisibleTo(window)
    assert not window.toggle_left_dock_action.isChecked()

    window.toggle_left_dock_action.trigger()

    assert window._left_dock.isVisibleTo(window)
    assert window.toggle_left_dock_action.isChecked()


def test_launching_with_no_project_shows_the_start_screen(qtbot) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)

    assert window._central_stack.currentWidget() is window.start_screen
    assert not window.start_screen.open_recent_button.isVisibleTo(window.start_screen)
    assert not window.start_screen.tour_button.isEnabled()


def test_creating_a_new_model_dismisses_the_start_screen(qtbot) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)

    window.new_project("Competition Robot")

    assert window._central_stack.currentWidget() is window.diagram_tabs


def test_opening_the_sample_model_dismisses_the_start_screen(qtbot, tmp_path) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)

    window.open_sample_model(tmp_path / "my_robot")

    assert window._central_stack.currentWidget() is window.diagram_tabs


def test_connecting_a_robot_project_without_a_model_dismisses_the_start_screen(qtbot) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)
    fixture_root = Path(__file__).parents[1] / "fixtures" / "java_basic"

    window.connect_robot_project(fixture_root)

    assert window.project is None
    assert window._central_stack.currentWidget() is window.diagram_tabs


def test_start_screen_shows_open_recent_only_once_a_model_has_been_saved(
    qtbot, tmp_path
) -> None:
    create_application([])
    first_window = MainWindow()
    qtbot.addWidget(first_window)
    first_window.new_project("Competition Robot")
    first_window.save_project(tmp_path)

    second_window = MainWindow()
    qtbot.addWidget(second_window)

    assert second_window.start_screen.open_recent_button.isVisibleTo(
        second_window.start_screen
    )
    assert tmp_path.name in second_window.start_screen.open_recent_button.text()


def test_structure_canvas_shows_a_purposeful_empty_state_until_something_exists(qtbot) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)

    window.new_project("Competition Robot")

    assert window._structure_stack.currentWidget() is window._structure_empty_state
    assert window._structure_empty_state.button is not None

    window.add_subsystem("Drive")

    assert window._structure_stack.currentWidget() is window.canvas


def test_code_inventory_shows_a_purposeful_empty_state_until_a_scan_exists(qtbot) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)

    assert window._left_dock_stack.currentWidget() is window._inventory_empty_state

    fixture_root = Path(__file__).parents[1] / "fixtures" / "java_basic"
    window.connect_robot_project(fixture_root)

    assert window._left_dock_stack.currentWidget() is window.inventory_tree


def test_behavior_diagram_list_shows_a_purposeful_empty_state_until_a_diagram_exists(
    qtbot,
) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)
    window.new_project("Competition Robot")
    # A new project ships with a seeded "Robot Modes" diagram; remove it to reach the
    # genuinely empty state a loaded project with none could also be in.
    window._delete_behavior_diagram(window.project.behavior_diagrams[0].id)

    window.diagram_tabs.setCurrentWidget(window._behavior_tab)

    assert window._left_dock_stack.currentWidget() is window._behavior_empty_state

    window._add_root_behavior_diagram()

    assert window._left_dock_stack.currentWidget() is window.behavior_model_browser


def test_hardware_table_shows_a_purposeful_empty_state_until_a_device_exists(qtbot) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)
    window.new_project("Competition Robot")
    window.add_subsystem("Drive")

    assert window._hardware_stack.currentWidget() is window._hardware_empty_state
    assert window._hardware_empty_state.button.isEnabled()

    window.add_device(window.project.subsystems[0].id, "Left motor", "SparkMax")

    assert window._hardware_stack.currentWidget() is window.hardware_table


def test_details_panel_offers_to_add_a_subsystem_when_nothing_exists_to_select(
    qtbot, monkeypatch
) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)
    window.new_project("Competition Robot")

    assert window.details_panel.empty_state_button.isVisibleTo(window.details_panel)

    monkeypatch.setattr(QInputDialog, "getText", lambda *args, **kwargs: ("Drive", True))
    window.details_panel.empty_state_button.click()

    assert window.project.subsystems[0].name.effective == "Drive"
    assert not window.details_panel.empty_state_button.isVisibleTo(window.details_panel)


def test_details_panel_hides_code_actions_until_a_scan_exists(qtbot) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)
    window.new_project("Competition Robot")
    window.add_command("Teleop Drive")
    block = next(item for item in window.scene.items() if isinstance(item, ArchitectureBlock))
    block.setSelected(True)

    panel = window.details_panel
    assert not panel.adopt_name_button.isVisibleTo(panel)
    assert not panel.adopt_description_button.isVisibleTo(panel)
    assert not panel.revert_name_button.isVisibleTo(panel)
    assert not panel.revert_button.isVisibleTo(panel)
    assert not panel.open_source_button.isVisibleTo(panel)
    assert panel.save_button.isVisibleTo(panel)

    fixture_root = Path(__file__).parents[1] / "fixtures" / "java_basic"
    window.connect_robot_project(fixture_root)
    block = next(
        item
        for item in window.scene.items()
        if isinstance(item, ArchitectureBlock)
        and not item.imported
        and item.title.toPlainText() == "Teleop Drive"
    )
    block.setSelected(True)

    assert panel.adopt_name_button.isVisibleTo(panel)
    assert panel.adopt_description_button.isVisibleTo(panel)
    assert panel.revert_name_button.isVisibleTo(panel)
    assert panel.revert_button.isVisibleTo(panel)
    assert panel.open_source_button.isVisibleTo(panel)
