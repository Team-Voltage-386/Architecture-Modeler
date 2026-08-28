from frc_arch_modeler.domain.model import (
    ArchitectureProject,
    Command,
    ComparisonState,
    Device,
    FieldValue,
    SourceAnchor,
    Subsystem,
    TriggerBinding,
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


def test_change_request_export_includes_modified_bound_elements(tmp_path) -> None:
    command = Command(
        name=FieldValue(design="Driver Control"),
        description=FieldValue(design="Use revised controls."),
    )
    symbol = ScannedSymbol(
        kind="command",
        name="DriveCommand",
        anchor=SourceAnchor("src/DriveCommand.java", "robot.DriveCommand", 12, 12),
    )
    comparison = ReconciliationResult(
        matches={command.id: symbol}, statuses={command.id: ComparisonState.MODIFIED}
    )

    content = ChangeRequestExportService().render(
        ArchitectureProject(name="Robot", commands=[command]),
        ScanResult(project_root=tmp_path),
        comparison,
    )

    assert "## Required Modifications" in content
    assert "### Modify Command: Driver Control" in content
    assert "`src/DriveCommand.java:12`" in content


def test_change_request_export_includes_design_devices_and_triggers(tmp_path) -> None:
    drive = Subsystem(name=FieldValue(design="Drive"))
    command = Command(name=FieldValue(design="Teleop"), requirement_ids=[drive.id])
    project = ArchitectureProject(
        name="Robot",
        subsystems=[drive],
        commands=[command],
        devices=[
            Device(
                name=FieldValue(design="Left motor"),
                device_type=FieldValue(design="SparkMax"),
                owner_subsystem_id=drive.id,
                mode=FieldValue(design="REAL"),
            )
        ],
        triggers=[
            TriggerBinding(
                expression=FieldValue(design="Driver A"),
                activation=FieldValue(design="onTrue"),
                command_id=command.id,
            )
        ],
    )
    comparison = ReconciliationResult(
        statuses={drive.id: ComparisonState.DESIGN_ONLY, command.id: ComparisonState.DESIGN_ONLY}
    )

    content = ChangeRequestExportService().render(project, ScanResult(tmp_path), comparison)

    assert "  - Left motor: SparkMax (REAL)" in content
    assert "  - Driver A â€” onTrue" in content
