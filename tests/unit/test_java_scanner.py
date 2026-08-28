from pathlib import Path

import pytest

from frc_arch_modeler.importers.java.scanner import JavaProjectScanner


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


def test_scanner_requires_a_gradle_project(tmp_path) -> None:
    with pytest.raises(ValueError, match="No Gradle build file"):
        JavaProjectScanner().scan(tmp_path)
