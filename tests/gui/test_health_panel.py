"""The Model Health dock: live counts, reveal-on-click, and inline undoable fixes."""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDockWidget

from frc_arch_modeler.app import create_application
from frc_arch_modeler.services.health_service import (
    FIX_ASSIGN_NEXT_FREE_ADDRESS,
    HealthService,
)
from frc_arch_modeler.ui.architecture_scene import ArchitectureBlock, DeviceBlock
from frc_arch_modeler.ui.behavior_scene import StateBlock
from frc_arch_modeler.ui.health_panel import HEALTHY_MESSAGE, NO_MODEL_MESSAGE
from frc_arch_modeler.ui.main_window import MainWindow

SAMPLE_MODEL_ROOT = Path(__file__).parents[2] / "resources" / "sample_model"


def _window(qtbot) -> MainWindow:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)
    return window


def _findings_of_kind(window: MainWindow, kind: str) -> list:
    return [finding for finding in window.health_controller.findings if finding.kind == kind]


def test_the_model_health_dock_exists_hidden_behind_a_toggle_with_no_model_loaded(
    qtbot,
) -> None:
    window = _window(qtbot)

    dock = window.findChild(QDockWidget, "healthDock")
    assert dock is not None
    assert not dock.isVisible()
    assert window.toggle_health_action.text() == "Model Health"
    assert window.health_panel.summary_label.text() == NO_MODEL_MESSAGE
    assert window.status_health_label.text() == ""


def test_the_status_bar_reports_a_live_finding_count_that_follows_the_model(qtbot) -> None:
    window = _window(qtbot)
    window.new_project("Competition Robot")

    assert window.status_health_label.text() == "Health: OK"

    window.add_subsystem("Drive")
    qtbot.waitUntil(lambda: not window._health_timer.isActive())

    assert window.status_health_label.text() == "Health: 1 (1 warning)"
    assert _findings_of_kind(window, "subsystem_not_required")


def test_recomputation_is_debounced_rather_than_run_on_every_edit(qtbot) -> None:
    window = _window(qtbot)
    window.new_project("Competition Robot")

    window.add_subsystem("Drive")
    window.add_subsystem("Intake")
    # The edits queue a single pass; nothing has been recomputed yet.
    assert window._health_timer.isActive()
    assert window.health_controller.findings == []

    qtbot.waitUntil(lambda: not window._health_timer.isActive())

    assert len(_findings_of_kind(window, "subsystem_not_required")) == 2


def test_the_shipped_sample_robot_reports_a_healthy_model(qtbot) -> None:
    window = _window(qtbot)
    window.open_project(SAMPLE_MODEL_ROOT)

    assert window.health_controller.findings == []
    assert window.health_panel.summary_label.text() == HEALTHY_MESSAGE
    assert window.status_health_label.text() == "Health: OK"


def test_the_panel_groups_findings_by_severity_without_knowing_any_rule(qtbot) -> None:
    window = _window(qtbot)
    window.new_project("Competition Robot")
    window.add_subsystem("Drive")
    window.add_device(window.project.subsystems[0].id, "Left Motor", "SparkMax", "REAL")
    qtbot.waitUntil(lambda: not window._health_timer.isActive())

    headings = [
        window.health_panel.tree.topLevelItem(index).text(0)
        for index in range(window.health_panel.tree.topLevelItemCount())
    ]

    assert headings == ["Warnings (1)", "Incomplete (1)"]
    assert window.health_panel.summary_label.text() == "1 warning, 1 incomplete item"


def test_clicking_a_finding_selects_the_structural_element_it_is_about(qtbot) -> None:
    window = _window(qtbot)
    window.new_project("Competition Robot")
    window.add_subsystem("Drive")
    qtbot.waitUntil(lambda: not window._health_timer.isActive())
    finding = _findings_of_kind(window, "subsystem_not_required")[0]

    assert window._reveal_health_finding(finding)

    assert window.diagram_tabs.currentIndex() == 0
    selected = [
        item for item in window.scene.selectedItems() if isinstance(item, ArchitectureBlock)
    ]
    assert [block.element_id for block in selected] == [window.project.subsystems[0].id]


def test_clicking_a_device_finding_expands_the_group_hiding_it_and_selects_it(qtbot) -> None:
    window = _window(qtbot)
    window.new_project("Competition Robot")
    window.add_subsystem("Drive")
    window.add_device(window.project.subsystems[0].id, "Left Motor", "SparkMax", "REAL")
    qtbot.waitUntil(lambda: not window._health_timer.isActive())
    finding = _findings_of_kind(window, "incomplete_address")[0]

    assert window._reveal_health_finding(finding)

    selected = [item for item in window.scene.selectedItems() if isinstance(item, DeviceBlock)]
    assert [block.element_id for block in selected] == [window.project.devices[0].id]


def test_clicking_a_behavior_finding_switches_to_the_diagram_that_owns_it(qtbot) -> None:
    window = _window(qtbot)
    window.new_project("Competition Robot")
    diagram = window.project.behavior_diagrams[0]
    window.project_service.add_behavior_state(diagram, "Climbing")
    window._select_behavior_diagram(None)
    window._refresh_model_health()
    finding = _findings_of_kind(window, "unreachable_behavior_state")[0]

    assert window._reveal_health_finding(finding)

    assert window.diagram_tabs.currentIndex() == 1
    assert window._selected_behavior_diagram_id == diagram.id
    selected = [
        item for item in window.behavior_scene.selectedItems() if isinstance(item, StateBlock)
    ]
    assert [block.state_id for block in selected] == [finding.entity_ids[0]]


def test_an_unambiguous_fix_is_offered_but_never_applied_on_its_own(qtbot) -> None:
    window = _window(qtbot)
    window.new_project("Competition Robot")
    window.add_subsystem("Drive")
    window.add_device(
        window.project.subsystems[0].id, "Left Motor", "SparkMax", "REAL", bus="rio"
    )
    qtbot.waitUntil(lambda: not window._health_timer.isActive())
    finding = _findings_of_kind(window, "incomplete_address")[0]

    assert finding.fix_action == FIX_ASSIGN_NEXT_FREE_ADDRESS
    assert finding.fix_label == "Assign address 1 on rio"
    # Selecting the finding reveals it and changes nothing about the model.
    window._reveal_health_finding(finding)
    assert window.project.devices[0].address.effective is None


def test_applying_a_fix_assigns_the_next_free_address_and_is_undoable(qtbot) -> None:
    window = _window(qtbot)
    window.new_project("Competition Robot")
    window.add_subsystem("Drive")
    window.add_device(
        window.project.subsystems[0].id,
        "Left Motor",
        "SparkMax",
        "REAL",
        bus="rio",
        address="1",
    )
    window.add_device(
        window.project.subsystems[0].id, "Right Motor", "SparkMax", "REAL", bus="rio"
    )
    qtbot.waitUntil(lambda: not window._health_timer.isActive())
    finding = _findings_of_kind(window, "incomplete_address")[0]

    assert window._apply_health_fix(finding)

    assert window.project.devices[1].address.effective == "2"
    window.undo_stack.undo()
    assert window.project.devices[1].address.effective is None


def test_applying_a_fix_removes_a_relationship_left_pointing_at_a_deleted_element(
    qtbot,
) -> None:
    window = _window(qtbot)
    window.new_project("Competition Robot")
    window.add_subsystem("Drive")
    window.add_command("Teleop Drive")
    window.add_relationship(
        "calls", window.project.commands[0].id, window.project.subsystems[0].id
    )
    window.project.subsystems.clear()
    window._refresh_model_health()
    finding = _findings_of_kind(window, "orphaned_relationship")[0]

    assert window._apply_health_fix(finding)

    assert window.project.relationships == []
    window.undo_stack.undo()
    assert len(window.project.relationships) == 1


def test_the_panel_renders_exactly_the_findings_the_service_computes(qtbot) -> None:
    """The panel holds no rule logic: what it lists is what the service returned."""
    window = _window(qtbot)
    window.new_project("Competition Robot")
    window.add_subsystem("Drive")
    window.add_command("Score")
    qtbot.waitUntil(lambda: not window._health_timer.isActive())

    tree = window.health_panel.tree
    listed = []
    for group in range(tree.topLevelItemCount()):
        header = tree.topLevelItem(group)
        for child in range(header.childCount()):
            listed.append(header.child(child).data(0, Qt.ItemDataRole.UserRole))

    assert listed == list(range(len(window.health_controller.findings)))
    assert window.health_controller.findings == HealthService().check(window.project)
