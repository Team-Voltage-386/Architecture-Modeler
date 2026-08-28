import pytest

from frc_arch_modeler.domain.model import SourceAnchor
from frc_arch_modeler.services.project_service import ProjectService


def test_create_save_and_open_project(tmp_path) -> None:
    service = ProjectService()
    created = service.create("Competition Robot")

    saved_path = service.save(tmp_path, created)
    reopened = service.open(tmp_path)

    assert saved_path.exists()
    assert reopened.to_dict() == created.to_dict()


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
