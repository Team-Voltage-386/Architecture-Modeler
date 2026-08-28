from frc_arch_modeler.domain.model import (
    ArchitectureProject,
    Command,
    ComparisonState,
    Device,
    FieldValue,
    Relationship,
    SourceAnchor,
    Subsystem,
    TriggerBinding,
)
from frc_arch_modeler.importers.base import (
    ScanDiagnostic,
    ScannedDevice,
    ScannedSymbol,
    ScannedTrigger,
    ScanResult,
)
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


def test_architecture_export_includes_design_hardware_controls_and_relationships(tmp_path) -> None:
    drive = Subsystem(name=FieldValue(design="Drive"))
    command = Command(name=FieldValue(design="Teleop"))
    motor = Device(
        name=FieldValue(design="Left motor"),
        device_type=FieldValue(design="SparkMax"),
        owner_subsystem_id=drive.id,
        mode=FieldValue(design="REAL"),
    )
    trigger = TriggerBinding(
        expression=FieldValue(design="Driver A"),
        activation=FieldValue(design="onTrue"),
        command_id=command.id,
    )
    project = ArchitectureProject(
        name="Robot",
        commands=[command],
        subsystems=[drive],
        devices=[motor],
        triggers=[trigger],
        relationships=[Relationship("owns_device", drive.id, motor.id)],
    )

    content = ArchitectureExportService().render(project)

    assert "  - Left motor: SparkMax (REAL)" in content
    assert "  - Driver A â€” onTrue" in content
    assert "## Design Relationships" in content
    assert "| owns_device | Drive | Left motor |" in content


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
        devices=[
            ScannedDevice(
                "SparkMax",
                "DRIVE_ID, MotorType.kBrushless",
                "robot.DriveIOReal",
                SourceAnchor("src/DriveIOReal.java", "robot.DriveIOReal", 8, 8),
                resolved_arguments="4, MotorType.kBrushless",
                mode="REAL",
            )
        ],
        triggers=[
            ScannedTrigger(
                "driver.a()",
                "onTrue",
                "new DriveCommand(drive)",
                SourceAnchor("src/RobotContainer.java", "robot.RobotContainer", 22, 22),
            )
        ],
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
    assert "## Imported Hardware" in content
    assert "| robot.DriveIOReal | SparkMax (REAL) | `4, MotorType.kBrushless` |" in content
    assert "## Imported Trigger Bindings" in content
    assert "| driver.a() | onTrue | `new DriveCommand(drive)` |" in content
    assert "Example warning (src/Broken.java)" in content
