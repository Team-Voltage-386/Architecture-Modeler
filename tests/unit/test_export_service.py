from frc_arch_modeler.domain.model import ArchitectureProject, Command, FieldValue, Subsystem
from frc_arch_modeler.services.export_service import ArchitectureExportService


def test_architecture_export_is_deterministic_and_excludes_layout(tmp_path) -> None:
    drive = Subsystem(name=FieldValue(design="Drive"))
    command = Command(
        name=FieldValue(design="Teleop Drive"),
        description=FieldValue(design="Drive using joysticks."),
        requirement_ids=[drive.id],
    )
    project = ArchitectureProject(name="Competition Robot", commands=[command], subsystems=[drive])
    service = ArchitectureExportService()

    exported = service.export(tmp_path, project)
    content = exported.read_text(encoding="utf-8")

    assert exported == tmp_path / ".frc-architecture" / "exports" / "architecture.md"
    assert content == service.render(project)
    assert "# Architecture: Competition Robot" in content
    assert "### Drive" in content
    assert "- Requirements: Drive" in content
