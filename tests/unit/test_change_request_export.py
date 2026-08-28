from frc_arch_modeler.domain.model import (
    ArchitectureProject,
    Command,
    ComparisonState,
    FieldValue,
    SourceAnchor,
)
from frc_arch_modeler.importers.base import ScannedSymbol, ScanResult
from frc_arch_modeler.services.change_request_export import ChangeRequestExportService
from frc_arch_modeler.services.reconcile_service import ReconciliationResult


def test_change_request_export_contains_only_design_deltas_and_source_anchors(tmp_path) -> None:
    command = Command(
        name=FieldValue(design="Score Coral"), description=FieldValue(design="Score at the reef.")
    )
    project = ArchitectureProject(name="Competition Robot", commands=[command])
    code_only = ScannedSymbol(
        kind="command", name="OldCommand", anchor=SourceAnchor("src/Old.java", "robot.Old", 8, 8)
    )
    scan = ScanResult(project_root=tmp_path / "robot")
    comparison = ReconciliationResult(
        statuses={command.id: ComparisonState.DESIGN_ONLY}, code_only=[code_only]
    )

    destination = ChangeRequestExportService().export(tmp_path, project, scan, comparison)
    content = destination.read_text(encoding="utf-8")

    assert destination == tmp_path / ".frc-architecture" / "exports" / "change-request.md"
    assert "### Command: Score Coral" in content
    assert "Score at the reef." in content
    assert "`src/Old.java:8`" in content
    assert ".\\gradlew.bat build" in content
