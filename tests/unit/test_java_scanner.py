from pathlib import Path

import pytest

from frc_arch_modeler.importers.java.scanner import JavaProjectScanner, ScanCancelled


def test_scanner_inventories_wpilib_symbols_with_source_evidence() -> None:
    root = Path(__file__).parents[1] / "fixtures" / "java_basic"

    result = JavaProjectScanner().scan(root)

    assert result.files_scanned == 4
    architecture_symbols = [
        (symbol.kind, symbol.name)
        for symbol in result.symbols
        if symbol.kind != "lifecycle_method"
    ]
    assert architecture_symbols == [
        ("command_factory", "stopDrive"),
        ("subsystem", "Drive"),
        ("command", "DriveCommand"),
    ]
    drive = result.symbols_of_kind("subsystem")[0]
    assert drive.anchor.relative_path == "src/main/java/frc/robot/Drive.java"
    assert drive.anchor.qualified_symbol == "frc.robot.Drive"
    assert drive.anchor.source_hash
    relationships = [(item.kind, item.target_expression) for item in result.relationships]
    assert relationships == [("requires", "drive")]
    lifecycle = [symbol.name for symbol in result.symbols_of_kind("lifecycle_method")]
    assert lifecycle == ["initialize", "execute", "isFinished", "end"]
    assert [(trigger.controller_expression, trigger.activation) for trigger in result.triggers] == [
        ("driver.a()", "onTrue")
    ]
    assert result.triggers[0].command_expression == "new DriveCommand(drive)"
    assert [(device.device_type, device.constructor_arguments) for device in result.devices] == [
        ("SparkMax", "4, MotorType.kBrushless")
    ]
    assert result.devices[0].owner_symbol == "frc.robot.Drive"


def test_scanner_requires_a_gradle_project(tmp_path) -> None:
    with pytest.raises(ValueError, match="No Gradle build file"):
        JavaProjectScanner().scan(tmp_path)


def test_scanner_stops_between_files_when_cancelled() -> None:
    root = Path(__file__).parents[1] / "fixtures" / "java_basic"

    with pytest.raises(ScanCancelled):
        JavaProjectScanner().scan(root, should_cancel=lambda: True)


def test_scanner_reports_syntax_issues_without_aborting_other_files(tmp_path) -> None:
    (tmp_path / "build.gradle").write_text("plugins {}", encoding="utf-8")
    source_root = tmp_path / "src" / "main" / "java"
    source_root.mkdir(parents=True)
    (source_root / "Broken.java").write_text("class Broken { void run( {", encoding="utf-8")
    (source_root / "Drive.java").write_text(
        "class Drive extends SubsystemBase {}", encoding="utf-8"
    )

    result = JavaProjectScanner().scan(tmp_path)

    assert result.files_scanned == 2
    assert len(result.diagnostics) == 1
    assert result.diagnostics[0].relative_path == "src/main/java/Broken.java"
    assert [symbol.name for symbol in result.symbols_of_kind("subsystem")] == ["Drive"]


def test_scanner_inventories_inline_command_forms_and_groups(tmp_path) -> None:
    (tmp_path / "build.gradle").write_text("plugins {}", encoding="utf-8")
    source_root = tmp_path / "src" / "main" / "java"
    source_root.mkdir(parents=True)
    (source_root / "Autos.java").write_text(
        """package frc.robot;
class Autos {
  Command auto() {
    return Commands.sequence(Commands.runOnce(() -> {}),
        new ParallelCommandGroup(Commands.run(() -> {})));
  }
}
""",
        encoding="utf-8",
    )

    result = JavaProjectScanner().scan(tmp_path)

    assert [item.name for item in result.symbols_of_kind("command_composition")] == [
        "sequence (line 4)",
        "runOnce (line 4)",
        "ParallelCommandGroup (line 5)",
        "run (line 5)",
    ]
