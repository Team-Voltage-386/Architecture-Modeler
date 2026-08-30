from pathlib import Path

import pytest

from frc_arch_modeler.importers.java.scanner import JavaProjectScanner, ScanCancelled


def test_scanner_inventories_wpilib_symbols_with_source_evidence() -> None:
    root = Path(__file__).parents[1] / "fixtures" / "java_basic"
    progress: list[tuple[int, int]] = []

    result = JavaProjectScanner().scan(
        root, on_file_scanned=lambda completed, total: progress.append((completed, total))
    )

    assert result.files_scanned == 4
    assert progress == [(1, 4), (2, 4), (3, 4), (4, 4)]
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


def test_scanner_preserves_composed_trigger_expression(tmp_path) -> None:
    (tmp_path / "build.gradle").write_text("plugins {}", encoding="utf-8")
    source_root = tmp_path / "src" / "main" / "java"
    source_root.mkdir(parents=True)
    (source_root / "RobotContainer.java").write_text(
        """class RobotContainer {
  void configure() { driver.a().debounce(0.15).whileTrue(new IntakeCommand()); }
}
""",
        encoding="utf-8",
    )

    result = JavaProjectScanner().scan(tmp_path)

    assert [(trigger.controller_expression, trigger.activation) for trigger in result.triggers] == [
        ("driver.a().debounce(0.15)", "whileTrue")
    ]


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
    assert [diagnostic.relative_path for diagnostic in result.diagnostics] == [
        "src/main/java/Broken.java",
        "src/main/java/Broken.java",
    ]
    assert result.diagnostics[0].message.startswith("Java syntax issue")
    assert result.diagnostics[1].message.startswith("Unclosed command composition")
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
    assert [
        (relationship.source_symbol, relationship.target_expression)
        for relationship in result.relationships
        if relationship.kind == "composition_child"
    ] == [
        (
            "frc.robot.sequence@4",
            "Commands.runOnce(() -> {})",
        ),
        (
            "frc.robot.sequence@4",
            "new ParallelCommandGroup(Commands.run(() -> {}))",
        ),
        ("frc.robot.runOnce@4", "() -> {}"),
        ("frc.robot.ParallelCommandGroup@5", "Commands.run(() -> {})"),
        ("frc.robot.run@5", "() -> {}"),
    ]


def test_scanner_records_implicit_requirement_of_subsystem_command_helpers(tmp_path) -> None:
    (tmp_path / "build.gradle").write_text("plugins {}", encoding="utf-8")
    source_root = tmp_path / "src" / "main" / "java"
    source_root.mkdir(parents=True)
    (source_root / "Drive.java").write_text(
        """package frc.robot;
class Drive extends SubsystemBase {
  Command stop() { return drive.runOnce(() -> stopMotor()); }
}
""",
        encoding="utf-8",
    )

    result = JavaProjectScanner().scan(tmp_path)

    helper = next(
        symbol
        for symbol in result.symbols_of_kind("command_composition")
        if symbol.name == "drive.runOnce (line 3)"
    )
    assert (helper.anchor.qualified_symbol, helper.anchor.start_line) == (
        "frc.robot.drive.runOnce@3",
        3,
    )
    assert ("requires", "drive") in [
        (relationship.kind, relationship.target_expression) for relationship in result.relationships
    ]


def test_scanner_records_chained_command_decorators(tmp_path) -> None:
    (tmp_path / "build.gradle").write_text("plugins {}", encoding="utf-8")
    source_root = tmp_path / "src" / "main" / "java"
    source_root.mkdir(parents=True)
    (source_root / "Autos.java").write_text(
        """package frc.robot;
class Autos {
  Command auto() { return score().withTimeout(2.0).andThen(stow()); }
}
""",
        encoding="utf-8",
    )

    result = JavaProjectScanner().scan(tmp_path)

    assert [symbol.name for symbol in result.symbols_of_kind("command_composition")] == [
        "score().withTimeout (line 3)",
        "score().withTimeout(2.0).andThen (line 3)",
    ]
    assert [
        (relationship.kind, relationship.target_expression)
        for relationship in result.relationships
        if relationship.kind == "command_decorator"
    ] == [
        ("command_decorator", "score().withTimeout(2.0)"),
        ("command_decorator", "score().withTimeout(2.0).andThen(stow())"),
    ]


def test_scanner_extracts_attached_javadoc_for_types_and_lifecycle(tmp_path) -> None:
    (tmp_path / "build.gradle").write_text("plugins {}", encoding="utf-8")
    source_root = tmp_path / "src" / "main" / "java"
    source_root.mkdir(parents=True)
    (source_root / "Documented.java").write_text(
        """package frc.robot;
/** Runs the intake safely. */
class Documented extends CommandBase {
  /** Stops motors when ending. */
  @Override public void end(boolean interrupted) {}
}
""",
        encoding="utf-8",
    )

    result = JavaProjectScanner().scan(tmp_path)

    assert result.symbols_of_kind("command")[0].documentation == "Runs the intake safely."
    assert (
        result.symbols_of_kind("lifecycle_method")[0].documentation
        == "Stops motors when ending."
    )


def test_scanner_extracts_default_and_autonomous_command_registrations(tmp_path) -> None:
    (tmp_path / "build.gradle").write_text("plugins {}", encoding="utf-8")
    source_root = tmp_path / "src" / "main" / "java"
    source_root.mkdir(parents=True)
    (source_root / "RobotContainer.java").write_text(
        """package frc.robot;
class RobotContainer {
  void configure(Drive drive) {
    drive.setDefaultCommand(new DriveCommand(drive));
    NamedCommands.registerCommand("Score", new ScoreCommand());
  }
}
""",
        encoding="utf-8",
    )

    result = JavaProjectScanner().scan(tmp_path)

    assert [item.name for item in result.symbols_of_kind("command_registration")] == [
        "Default: drive → new DriveCommand(drive)",
        "Auto: Score",
    ]
    assert [(item.kind, item.target_expression) for item in result.relationships] == [
        ("default_command", "new DriveCommand(drive)"),
        ("autonomous_registration", "new ScoreCommand()"),
    ]


def test_scanner_resolves_local_static_hardware_constants(tmp_path) -> None:
    (tmp_path / "build.gradle").write_text("plugins {}", encoding="utf-8")
    source_root = tmp_path / "src" / "main" / "java"
    source_root.mkdir(parents=True)
    (source_root / "Drive.java").write_text(
        """class Drive extends SubsystemBase {
  private static final int LEFT_MOTOR_ID = 4;
  private final SparkMax motor = new SparkMax(LEFT_MOTOR_ID, MotorType.kBrushless);
}
""",
        encoding="utf-8",
    )

    result = JavaProjectScanner().scan(tmp_path)

    assert result.devices[0].constructor_arguments == "LEFT_MOTOR_ID, MotorType.kBrushless"
    assert result.devices[0].resolved_arguments == "4, MotorType.kBrushless"


def test_scanner_inventories_broader_wpilib_hardware_catalog(tmp_path) -> None:
    (tmp_path / "build.gradle").write_text("plugins {}", encoding="utf-8")
    source_root = tmp_path / "src" / "main" / "java"
    source_root.mkdir(parents=True)
    (source_root / "Hardware.java").write_text(
        """class Hardware extends SubsystemBase {
  CANcoder encoder = new CANcoder(3);
  PneumaticHub hub = new PneumaticHub(1);
  PowerDistribution pdh = new PowerDistribution();
  Servo indicator = new Servo(0);
}
""",
        encoding="utf-8",
    )

    result = JavaProjectScanner().scan(tmp_path)

    assert [device.device_type for device in result.devices] == [
        "CANcoder",
        "PneumaticHub",
        "PowerDistribution",
        "Servo",
    ]


def test_scanner_resolves_cross_file_constants_and_marks_io_mode(tmp_path) -> None:
    (tmp_path / "build.gradle").write_text("plugins {}", encoding="utf-8")
    source_root = tmp_path / "src" / "main" / "java"
    source_root.mkdir(parents=True)
    (source_root / "Constants.java").write_text(
        """package frc.robot;
class Constants { static final int LEFT_MOTOR_ID = 9; }
""",
        encoding="utf-8",
    )
    (source_root / "DriveIOSim.java").write_text(
        """package frc.robot;
class DriveIOSim {
  private final SparkMax motor = new SparkMax(Constants.LEFT_MOTOR_ID, MotorType.kBrushless);
}
""",
        encoding="utf-8",
    )

    result = JavaProjectScanner().scan(tmp_path)

    assert result.devices[0].resolved_arguments == "9, MotorType.kBrushless"
    assert result.devices[0].mode == "SIM"


def test_scanner_resolves_camel_case_cross_file_constant_aliases(tmp_path) -> None:
    (tmp_path / "build.gradle").write_text("plugins {}", encoding="utf-8")
    source_root = tmp_path / "src" / "main" / "java"
    source_root.mkdir(parents=True)
    (source_root / "DriveConstants.java").write_text(
        """package frc.robot.constants;
class DriveConstants {
  static final int physicalCanId = 7;
  static final int driveCanId = physicalCanId;
}
""",
        encoding="utf-8",
    )
    (source_root / "Drive.java").write_text(
        """package frc.robot;
class Drive extends SubsystemBase {
  private final SparkMax motor = new SparkMax(DriveConstants.driveCanId, MotorType.kBrushless);
}
""",
        encoding="utf-8",
    )

    result = JavaProjectScanner().scan(tmp_path)

    assert result.devices[0].resolved_arguments == "7, MotorType.kBrushless"


def test_scanner_leaves_ambiguous_cross_package_constant_unresolved(tmp_path) -> None:
    (tmp_path / "build.gradle").write_text("plugins {}", encoding="utf-8")
    source_root = tmp_path / "src" / "main" / "java"
    for package, value in (("a", "3"), ("b", "9")):
        package_root = source_root / package
        package_root.mkdir(parents=True, exist_ok=True)
        (package_root / "Constants.java").write_text(
            f"package {package}; class Constants {{ static final int motorId = {value}; }}",
            encoding="utf-8",
        )
    (source_root / "Drive.java").write_text(
        """class Drive extends SubsystemBase {
  private final SparkMax motor = new SparkMax(Constants.motorId, MotorType.kBrushless);
}
""",
        encoding="utf-8",
    )

    result = JavaProjectScanner().scan(tmp_path)

    assert result.devices[0].resolved_arguments is None
