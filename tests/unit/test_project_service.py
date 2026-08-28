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
