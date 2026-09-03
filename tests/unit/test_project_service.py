import pytest

from frc_arch_modeler.domain.model import ComparisonState, SourceAnchor
from frc_arch_modeler.services.project_service import ProjectService


def test_create_save_and_open_project(tmp_path) -> None:
    service = ProjectService()
    created = service.create("Competition Robot")

    saved_path = service.save(tmp_path, created)
    reopened = service.open(tmp_path)

    assert saved_path.exists()
    assert reopened.to_dict() == created.to_dict()


def test_create_seeds_the_standard_robot_mode_behavior_diagram() -> None:
    project = ProjectService().create("Competition Robot")

    assert len(project.behavior_diagrams) == 1
    diagram = project.behavior_diagrams[0]
    assert diagram.name == "Robot Modes"
    assert {state.name.effective for state in diagram.states} == {
        "Start",
        "Disabled",
        "Autonomous",
        "Teleop",
        "Test",
    }
    assert len(diagram.transitions) == 6


def test_add_behavior_state_defaults_to_plain_state_kind() -> None:
    service = ProjectService()
    project = service.create("Competition Robot")
    diagram = project.behavior_diagrams[0]

    state = service.add_behavior_state(diagram, "Climb")

    assert state.kind == "state"
    assert state in diagram.states


def test_add_behavior_state_accepts_a_pseudostate_kind() -> None:
    service = ProjectService()
    project = service.create("Competition Robot")
    diagram = project.behavior_diagrams[0]

    decision = service.add_behavior_state(diagram, "Ball Detected?", kind="decision")

    assert decision.kind == "decision"
    assert decision in diagram.states


def test_add_behavior_diagram_accepts_owner_command_id() -> None:
    service = ProjectService()
    project = service.create("Competition Robot")
    command = service.add_command(project, "Score Coral")

    diagram = service.add_behavior_diagram(project, "Scoring Sequence", command.id)

    assert diagram.owner_command_id == command.id
    assert diagram in project.behavior_diagrams


def test_add_behavior_diagram_defaults_to_root_level() -> None:
    service = ProjectService()
    project = service.create("Competition Robot")

    diagram = service.add_behavior_diagram(project, "Extra Diagram")

    assert diagram.owner_command_id is None


def test_rename_behavior_diagram_updates_name() -> None:
    service = ProjectService()
    project = service.create("Competition Robot")
    diagram = project.behavior_diagrams[0]

    service.rename_behavior_diagram(diagram, "Match Modes")

    assert diagram.name == "Match Modes"


def test_add_design_elements() -> None:
    service = ProjectService()
    project = service.create("Competition Robot")

    command = service.add_command(project, "Score Coral")
    subsystem = service.add_subsystem(project, "Elevator")

    assert project.commands == [command]
    assert command.name.effective == "Score Coral"
    assert project.subsystems == [subsystem]
    assert subsystem.name.effective == "Elevator"


def test_add_design_device_and_trigger() -> None:
    service = ProjectService()
    project = service.create("Competition Robot")
    subsystem = service.add_subsystem(project, "Elevator")
    command = service.add_command(project, "Score Coral")

    device = service.add_device(project, subsystem.id, "Lift motor", "TalonFX", "REAL")
    trigger = service.add_trigger(project, command.id, "Operator A", "onTrue")

    assert device.owner_subsystem_id == subsystem.id
    assert device.mode.effective == "REAL"
    assert trigger.command_id == command.id
    assert trigger.expression.effective == "Operator A"


def test_add_explicit_design_relationship() -> None:
    service = ProjectService()
    project = service.create("Competition Robot")
    source = service.add_command(project, "Score")
    target = service.add_subsystem(project, "Elevator")

    relationship = service.add_relationship(project, "calls", source.id, target.id)

    assert project.relationships == [relationship]
    assert relationship.relationship_type == "calls"


def test_open_reports_corrupt_model_with_its_location(tmp_path) -> None:
    destination = tmp_path / ".frc-architecture" / "model.json"
    destination.parent.mkdir()
    destination.write_text("{not JSON", encoding="utf-8")

    with pytest.raises(ValueError, match="Could not load model") as error:
        ProjectService().open(tmp_path)

    assert str(destination) in str(error.value)


def test_save_writes_and_open_applies_binding_sidecar(tmp_path) -> None:
    service = ProjectService()
    project = service.create("Competition Robot")
    command = service.add_command(project, "Score")
    command.code_binding = SourceAnchor("src/Score.java", "robot.Score", 4, 4)

    service.save(tmp_path, project)
    bindings_path = tmp_path / ".frc-architecture" / "bindings.json"
    payload = bindings_path.read_text(encoding="utf-8")
    command.code_binding = None
    reopened = service.open(tmp_path)

    assert bindings_path.is_file()
    assert '"schemaVersion": 1' in payload
    assert reopened.commands[0].code_binding is not None
    assert reopened.commands[0].code_binding.qualified_symbol == "robot.Score"


def test_add_device_stores_the_wiring_and_budget_fields_as_design_values(tmp_path) -> None:
    service = ProjectService()
    project = service.create("Competition Robot")
    drive = service.add_subsystem(project, "Drive")

    device = service.add_device(
        project,
        drive.id,
        "Left front drive",
        "SparkMax",
        "REAL",
        bus="canivore",
        address="5",
        breaker_amps="40",
        mass_kg="0.94",
        notes="Shares a breaker with the rear motor.",
    )

    assert device.bus.design == "canivore"
    assert device.address.design == "5"
    assert device.breaker_amps.design == "40"
    assert device.mass_kg.design == "0.94"
    assert device.notes.design == "Shares a breaker with the rear motor."
    assert all(
        value.scanned is None
        for value in (device.bus, device.address, device.breaker_amps, device.mass_kg)
    )


def test_add_device_leaves_omitted_wiring_fields_unresolved(tmp_path) -> None:
    service = ProjectService()
    project = service.create("Competition Robot")
    drive = service.add_subsystem(project, "Drive")

    device = service.add_device(project, drive.id, "Left front drive", "SparkMax")

    assert device.bus.comparison_state is ComparisonState.UNRESOLVED
    assert device.address.design is None
    assert device.breaker_amps.design is None
    assert device.mass_kg.design is None
    assert device.notes.design is None
