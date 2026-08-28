from pathlib import Path

import pytest

from frc_arch_modeler.importers.java.scanner import JavaProjectScanner


def test_scanner_inventories_wpilib_symbols_with_source_evidence() -> None:
    root = Path(__file__).parents[1] / "fixtures" / "java_basic"

    result = JavaProjectScanner().scan(root)

    assert result.files_scanned == 3
    assert [(symbol.kind, symbol.name) for symbol in result.symbols] == [
        ("command_factory", "stopDrive"),
        ("subsystem", "Drive"),
        ("command", "DriveCommand"),
    ]
    drive = result.symbols_of_kind("subsystem")[0]
    assert drive.anchor.relative_path == "src/main/java/frc/robot/Drive.java"
    assert drive.anchor.qualified_symbol == "frc.robot.Drive"
    assert drive.anchor.source_hash


def test_scanner_requires_a_gradle_project(tmp_path) -> None:
    with pytest.raises(ValueError, match="No Gradle build file"):
        JavaProjectScanner().scan(tmp_path)
