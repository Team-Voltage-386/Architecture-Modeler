"""Tolerant first-pass Java/WPILib project inventory scanner."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from pathlib import Path

from frc_arch_modeler.domain.model import SourceAnchor
from frc_arch_modeler.importers.base import (
    ScanDiagnostic,
    ScannedDevice,
    ScannedRelationship,
    ScannedSymbol,
    ScannedTrigger,
    ScanResult,
)
from frc_arch_modeler.importers.java.parser import JavaSyntaxParser

PACKAGE_PATTERN = re.compile(r"^\s*package\s+([\w.]+)\s*;", re.MULTILINE)
TYPE_PATTERN = re.compile(
    r"^\s*(?:public\s+|protected\s+|private\s+|abstract\s+|final\s+)*class\s+"
    r"(?P<name>\w+)(?P<declaration>[^\{]*)\{",
    re.MULTILINE,
)
COMMAND_METHOD_PATTERN = re.compile(
    r"^\s*(?:public\s+|protected\s+|private\s+|static\s+|final\s+)*Command\s+"
    r"(?P<name>\w+)\s*\(",
    re.MULTILINE,
)
COMMAND_COMPOSITION_PATTERN = re.compile(
    r"\b(?:(?:Commands\.)?(?P<factory>runOnce|run|runEnd|startEnd|sequence|parallel|"
    r"race|deadline)|new\s+(?P<group>SequentialCommandGroup|ParallelCommandGroup|"
    r"ParallelRaceGroup|ParallelDeadlineGroup))\s*\("
)
REQUIREMENT_PATTERN = re.compile(r"\baddRequirements\s*\((?P<arguments>[^)]*)\)")
LIFECYCLE_PATTERN = re.compile(
    r"@Override\s+(?:public|protected)\s+(?:void|boolean)\s+"
    r"(?P<name>initialize|execute|isFinished|end)\s*\(",
    re.MULTILINE,
)
TRIGGER_PATTERN = re.compile(
    r"(?P<controller>[\w.]+\([^)]*\))\.(?P<activation>onTrue|onFalse|whileTrue|whileFalse|"
    r"toggleOnTrue|toggleOnFalse)\s*\((?P<command>[^;]+?)\)\s*;",
    re.MULTILINE | re.DOTALL,
)
DEVICE_PATTERN = re.compile(
    r"\bnew\s+(?P<type>SparkMax|SparkFlex|TalonFX|TalonSRX|VictorSPX|"
    r"CANSparkMax|CANSparkFlex|DigitalInput|AnalogInput|Encoder|DutyCycleEncoder|"
    r"ADIS16470_IMU|Pigeon2|AHRS|PhotonCamera|Compressor|Solenoid|DoubleSolenoid|"
    r"AddressableLED)\s*\((?P<arguments>[^)]*)\)",
    re.MULTILINE,
)
EXCLUDED_DIRECTORY_NAMES = {".gradle", "build", "bin", "vendordeps"}


class ScanCancelled(Exception):
    """Raised internally when an interactive scan has been cancelled."""


class JavaProjectScanner:
    """Locate Java source and extract a stable initial WPILib symbol inventory.

    This intentionally accepts incomplete Java. It reports file read failures and
    only records relationships directly visible in declarations; a Tree-sitter
    parser can replace the implementation behind this interface later.
    """

    def scan(
        self, root: Path, should_cancel: Callable[[], bool] | None = None
    ) -> ScanResult:
        root = Path(root).resolve()
        if not self.is_gradle_project(root):
            raise ValueError(f"No Gradle build file found in robot project: {root}")
        result = ScanResult(project_root=root)
        source_root = root / "src" / "main" / "java"
        if not source_root.exists():
            result.diagnostics.append(
                ScanDiagnostic("warning", "No src/main/java source root was found.")
            )
            return result
        for source_path in sorted(source_root.rglob("*.java")):
            if should_cancel is not None and should_cancel():
                raise ScanCancelled()
            relative_path = source_path.relative_to(root)
            if any(part in EXCLUDED_DIRECTORY_NAMES for part in relative_path.parts):
                continue
            self._scan_file(source_path, root, result)
        return result

    def __init__(self) -> None:
        self._syntax_parser = JavaSyntaxParser()

    @staticmethod
    def is_gradle_project(root: Path) -> bool:
        return (root / "build.gradle").is_file() or (root / "build.gradle.kts").is_file()

    def _scan_file(self, source_path: Path, root: Path, result: ScanResult) -> None:
        relative_path = source_path.relative_to(root).as_posix()
        try:
            source = source_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            result.diagnostics.append(
                ScanDiagnostic("warning", f"Could not read Java source: {error}", relative_path)
            )
            return
        result.files_scanned += 1
        for line in self._syntax_parser.error_lines(source):
            result.diagnostics.append(
                ScanDiagnostic("warning", f"Java syntax issue near line {line}.", relative_path)
            )
        package_match = PACKAGE_PATTERN.search(source)
        package = package_match.group(1) if package_match else ""
        source_hash = hashlib.sha256(source.encode("utf-8")).hexdigest()
        for match in TYPE_PATTERN.finditer(source):
            declaration = match.group("declaration")
            kind = self._type_kind(declaration)
            type_name = match.group("name")
            qualified_type = f"{package}.{type_name}" if package else type_name
            body_end = self._matching_brace(source, match.end() - 1)
            if body_end is not None:
                self._scan_trigger_bindings(
                    source,
                    match.end(),
                    body_end,
                    qualified_type,
                    relative_path,
                    source_hash,
                    result,
                )
                self._scan_devices(
                    source,
                    match.end(),
                    body_end,
                    qualified_type,
                    relative_path,
                    source_hash,
                    result,
                )
            if kind:
                symbol = self._symbol(
                    kind,
                    type_name,
                    package,
                    source,
                    match.start(),
                    relative_path,
                    source_hash,
                )
                result.symbols.append(symbol)
                if kind == "command":
                    self._scan_command_body(
                        source,
                        match.end() - 1,
                        symbol,
                        relative_path,
                        source_hash,
                        result,
                    )
        for match in COMMAND_METHOD_PATTERN.finditer(source):
            result.symbols.append(
                self._symbol(
                    "command_factory",
                    match.group("name"),
                    package,
                    source,
                    match.start(),
                    relative_path,
                    source_hash,
                )
            )
        self._scan_command_compositions(source, package, relative_path, source_hash, result)

    def _scan_command_compositions(
        self,
        source: str,
        package: str,
        relative_path: str,
        source_hash: str,
        result: ScanResult,
    ) -> None:
        """Record inline WPILib command forms without pretending to resolve their lambdas.

        A composition is deliberately kept separate from a named command class or
        factory: callers can present one unified command inventory while retaining
        the truth that this source is an inline factory/group expression.
        """
        for match in COMMAND_COMPOSITION_PATTERN.finditer(source):
            form = match.group("factory") or match.group("group")
            assert form is not None
            line = source.count("\n", 0, match.start()) + 1
            qualified_name = f"{package}.{form}@{line}" if package else f"{form}@{line}"
            result.symbols.append(
                ScannedSymbol(
                    kind="command_composition",
                    name=f"{form} (line {line})",
                    anchor=self._anchor_at_offset(
                        qualified_name, source, match.start(), relative_path, source_hash
                    ),
                    confidence="exact",
                )
            )

    def _scan_trigger_bindings(
        self,
        source: str,
        body_start: int,
        body_end: int,
        source_symbol: str,
        relative_path: str,
        source_hash: str,
        result: ScanResult,
    ) -> None:
        body = source[body_start:body_end]
        for match in TRIGGER_PATTERN.finditer(body):
            result.triggers.append(
                ScannedTrigger(
                    controller_expression=match.group("controller"),
                    activation=match.group("activation"),
                    command_expression=" ".join(match.group("command").split()),
                    anchor=self._anchor_at_offset(
                        source_symbol,
                        source,
                        body_start + match.start(),
                        relative_path,
                        source_hash,
                    ),
                )
            )

    def _scan_devices(
        self,
        source: str,
        body_start: int,
        body_end: int,
        owner_symbol: str,
        relative_path: str,
        source_hash: str,
        result: ScanResult,
    ) -> None:
        body = source[body_start:body_end]
        for match in DEVICE_PATTERN.finditer(body):
            result.devices.append(
                ScannedDevice(
                    device_type=match.group("type"),
                    constructor_arguments=" ".join(match.group("arguments").split()),
                    owner_symbol=owner_symbol,
                    anchor=self._anchor_at_offset(
                        owner_symbol,
                        source,
                        body_start + match.start(),
                        relative_path,
                        source_hash,
                    ),
                )
            )

    def _scan_command_body(
        self,
        source: str,
        opening_brace: int,
        command: ScannedSymbol,
        relative_path: str,
        source_hash: str,
        result: ScanResult,
    ) -> None:
        body_end = self._matching_brace(source, opening_brace)
        if body_end is None:
            result.diagnostics.append(
                ScanDiagnostic(
                    "warning",
                    f"Unclosed class body for command {command.name}.",
                    relative_path,
                )
            )
            return
        body = source[opening_brace + 1 : body_end]
        body_offset = opening_brace + 1
        for match in REQUIREMENT_PATTERN.finditer(body):
            for argument in (item.strip() for item in match.group("arguments").split(",")):
                if argument:
                    result.relationships.append(
                        ScannedRelationship(
                            kind="requires",
                            source_symbol=command.anchor.qualified_symbol,
                            target_expression=argument,
                            anchor=self._anchor_at_offset(
                                command.anchor.qualified_symbol,
                                source,
                                body_offset + match.start(),
                                relative_path,
                                source_hash,
                            ),
                        )
                    )
        for match in LIFECYCLE_PATTERN.finditer(body):
            lifecycle_name = match.group("name")
            result.symbols.append(
                ScannedSymbol(
                    kind="lifecycle_method",
                    name=lifecycle_name,
                    anchor=self._anchor_at_offset(
                        f"{command.anchor.qualified_symbol}#{lifecycle_name}",
                        source,
                        body_offset + match.start(),
                        relative_path,
                        source_hash,
                    ),
                )
            )

    @staticmethod
    def _matching_brace(source: str, opening_brace: int) -> int | None:
        depth = 0
        for index in range(opening_brace, len(source)):
            if source[index] == "{":
                depth += 1
            elif source[index] == "}":
                depth -= 1
                if depth == 0:
                    return index
        return None

    @staticmethod
    def _type_kind(declaration: str) -> str | None:
        normalized = " ".join(declaration.split())
        if re.search(r"\bextends\s+(?:[\w.]+\.)?SubsystemBase\b", normalized) or re.search(
            r"\bimplements\s+(?:[\w.]+\.)?Subsystem\b", normalized
        ):
            return "subsystem"
        if re.search(r"\bextends\s+(?:[\w.]+\.)?(?:CommandBase|Command)\b", normalized):
            return "command"
        return None

    @staticmethod
    def _symbol(
        kind: str,
        name: str,
        package: str,
        source: str,
        offset: int,
        relative_path: str,
        source_hash: str,
    ) -> ScannedSymbol:
        qualified_name = f"{package}.{name}" if package else name
        return ScannedSymbol(
            kind=kind,
            name=name,
            anchor=JavaProjectScanner._anchor_at_offset(
                qualified_name, source, offset, relative_path, source_hash
            ),
        )

    @staticmethod
    def _anchor_at_offset(
        qualified_symbol: str,
        source: str,
        offset: int,
        relative_path: str,
        source_hash: str,
    ) -> SourceAnchor:
        line = source.count("\n", 0, offset) + 1
        return SourceAnchor(
            relative_path=relative_path,
            qualified_symbol=qualified_symbol,
            start_line=line,
            end_line=line,
            source_hash=source_hash,
        )
