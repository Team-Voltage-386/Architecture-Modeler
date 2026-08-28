from frc_arch_modeler.domain.model import (
    ArchitectureProject,
    Command,
    ComparisonState,
    FieldValue,
    SourceAnchor,
    Subsystem,
)
from frc_arch_modeler.importers.base import ScanDiagnostic, ScannedSymbol, ScanResult
from frc_arch_modeler.services.export_service import ArchitectureExportService
from frc_arch_modeler.services.reconcile_service import ReconciliationResult


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


def test_architecture_export_includes_optional_code_scan_discrepancies(tmp_path) -> None:
    drive = Subsystem(name=FieldValue(design="Drive"))
    imported = ScannedSymbol(
        kind="subsystem",
        name="Drive",
        anchor=SourceAnchor("src/Drive.java", "robot.Drive", 4, 4),
    )
    scan = ScanResult(
        project_root=tmp_path,
        symbols=[imported],
        files_scanned=1,
        diagnostics=[ScanDiagnostic("warning", "Example warning", "src/Broken.java")],
    )
    comparison = ReconciliationResult(
        matches={drive.id: imported}, statuses={drive.id: ComparisonState.MATCHED}
    )

    content = ArchitectureExportService().render(
        ArchitectureProject(name="Robot", subsystems=[drive]), scan, comparison
    )

    assert "## Imported Code Summary" in content
    assert "## Design / Code Discrepancies" in content
    assert "| Drive | Subsystem | matched | `src/Drive.java:4` |" in content
    assert "Example warning (src/Broken.java)" in content
