import pytest

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


def test_open_reports_corrupt_model_with_its_location(tmp_path) -> None:
    destination = tmp_path / ".frc-architecture" / "model.json"
    destination.parent.mkdir()
    destination.write_text("{not JSON", encoding="utf-8")

    with pytest.raises(ValueError, match="Could not load model") as error:
        ProjectService().open(tmp_path)

    assert str(destination) in str(error.value)
