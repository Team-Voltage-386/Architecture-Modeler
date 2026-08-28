from frc_arch_modeler.domain.model import (
    ArchitectureProject,
    Command,
    ComparisonState,
    FieldValue,
    SourceAnchor,
    Subsystem,
)
from frc_arch_modeler.importers.base import ScannedSymbol, ScanResult
from frc_arch_modeler.services.reconcile_service import ReconciliationService


def test_reconciliation_matches_exact_normalized_names_without_mutating_design(tmp_path) -> None:
    drive = Subsystem(name=FieldValue(design="Drive"))
    command = Command(name=FieldValue(design="Teleop-Drive"))
    project = ArchitectureProject(name="Robot", commands=[command], subsystems=[drive])
    scan = ScanResult(
        project_root=tmp_path,
        symbols=[
            _symbol("subsystem", "Drive"),
            _symbol("command", "TeleopDrive"),
            _symbol("command", "UnmappedCommand"),
        ],
    )

    result = ReconciliationService().reconcile(project, scan)

    assert result.statuses == {
        drive.id: ComparisonState.MATCHED,
        command.id: ComparisonState.MATCHED,
    }
    assert result.matches[command.id].name == "TeleopDrive"
    assert [symbol.name for symbol in result.code_only] == ["UnmappedCommand"]
    assert command.code_binding is None

    accepted = ReconciliationService.accept_matches(project, result)

    assert accepted == 2
    assert command.code_binding == result.matches[command.id].anchor
    assert drive.code_binding == result.matches[drive.id].anchor


def test_reconciliation_marks_explicitly_bound_renamed_symbol_as_modified(tmp_path) -> None:
    command = Command(name=FieldValue(design="Drive With Joysticks"))
    bound = _symbol("command", "DriveCommand")
    command.code_binding = bound.anchor
    project = ArchitectureProject(name="Robot", commands=[command])

    result = ReconciliationService().reconcile(
        project, ScanResult(project_root=tmp_path, symbols=[bound])
    )

    assert result.matches == {command.id: bound}
    assert result.statuses[command.id] == ComparisonState.MODIFIED


def _symbol(kind: str, name: str) -> ScannedSymbol:
    return ScannedSymbol(
        kind=kind,
        name=name,
        anchor=SourceAnchor(f"src/{name}.java", f"frc.robot.{name}", 1, 1),
    )
