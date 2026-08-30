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
SUBSYSTEM_COMMAND_HELPER_PATTERN = re.compile(
    r"\b(?P<subsystem>[a-z][A-Za-z0-9_]*)\.(?P<factory>runOnce|run)\s*\("
)
COMMAND_DECORATOR_PATTERN = re.compile(
    r"\.(?P<decorator>andThen|alongWith|withTimeout|until|onlyIf|deadlineFor)\s*\("
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
DEFAULT_COMMAND_PATTERN = re.compile(
    r"(?P<subsystem>[\w.]+)\.setDefaultCommand\s*\((?P<command>[^;]+?)\)\s*;",
    re.MULTILINE | re.DOTALL,
)
AUTONOMOUS_REGISTRATION_PATTERN = re.compile(
    r"\b(?:NamedCommands\.registerCommand|[\w.]+\.(?:setDefaultOption|addOption))\s*\(\s*"
    r"\"(?P<name>[^\"]+)\"\s*,\s*(?P<command>[^;]+?)\)\s*;",
    re.MULTILINE | re.DOTALL,
)
DEVICE_PATTERN = re.compile(
    r"\bnew\s+(?P<type>SparkMax|SparkFlex|TalonFX|TalonSRX|VictorSPX|"
    r"CANSparkMax|CANSparkFlex|DigitalInput|AnalogInput|Encoder|DutyCycleEncoder|"
    r"ADIS16470_IMU|Pigeon2|AHRS|PhotonCamera|Compressor|Solenoid|DoubleSolenoid|"
    r"AddressableLED)\s*\((?P<arguments>[^)]*)\)",
    re.MULTILINE,
)
CONSTANT_PATTERN = re.compile(
    r"\b(?:public|protected|private)?\s*(?:static\s+final|final\s+static)\s+"
    r"(?:int|long|double|boolean|String)\s+(?P<name>[A-Za-z_]\w*)\s*=\s*"
    r"(?P<value>[^;]+);"
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
        self,
        root: Path,
        should_cancel: Callable[[], bool] | None = None,
        on_file_scanned: Callable[[int, int], None] | None = None,
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
        source_paths = [
            path
            for path in sorted(source_root.rglob("*.java"))
            if not any(part in EXCLUDED_DIRECTORY_NAMES for part in path.relative_to(root).parts)
        ]
        # Constants routinely live in a separate Constants.java file.  Build a
        # deliberately small project-level index before extraction so a device
        # can retain both the original expression and a useful resolved port.
        # Bare names are only indexed when unique; guessing a duplicated name is
        # worse than leaving the evidence unresolved.
        self._project_constants = self._project_constant_values(source_paths)
        for index, source_path in enumerate(source_paths, start=1):
            if should_cancel is not None and should_cancel():
                raise ScanCancelled()
            self._scan_file(source_path, root, result)
            if on_file_scanned is not None:
                on_file_scanned(index, len(source_paths))
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
        constants = self._constant_values(source)
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
                    {**self._project_constants, **constants},
                )
                self._scan_command_registrations(
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
        self._scan_subsystem_command_helpers(source, package, relative_path, source_hash, result)
        self._scan_command_decorators(source, package, relative_path, source_hash, result)

    def _scan_command_decorators(
        self,
        source: str,
        package: str,
        relative_path: str,
        source_hash: str,
        result: ScanResult,
    ) -> None:
        """Record chained command decorators as semantic forms with source evidence."""
        for match in COMMAND_DECORATOR_PATTERN.finditer(source):
            line = source.count("\n", 0, match.start()) + 1
            decorator = match.group("decorator")
            receiver = self._decorator_receiver(source, match.start())
            if not receiver:
                continue
            qualified_name = (
                f"{package}.{decorator}@{line}" if package else f"{decorator}@{line}"
            )
            anchor = self._anchor_at_offset(
                qualified_name, source, match.start(), relative_path, source_hash
            )
            result.symbols.append(
                ScannedSymbol(
                    kind="command_composition",
                    name=f"{receiver}.{decorator} (line {line})",
                    anchor=anchor,
                    confidence="exact",
                )
            )
            opening_parenthesis = source.find("(", match.start("decorator"))
            closing_parenthesis = self._matching_parenthesis(source, opening_parenthesis)
            if closing_parenthesis is None:
                result.diagnostics.append(
                    ScanDiagnostic(
                        "warning",
                        f"Unclosed command decorator {decorator} near line {line}.",
                        relative_path,
                    )
                )
                continue
            arguments = " ".join(source[match.end() : closing_parenthesis].split())
            result.relationships.append(
                ScannedRelationship(
                    kind="command_decorator",
                    source_symbol=qualified_name,
                    target_expression=f"{receiver}.{decorator}({arguments})",
                    anchor=anchor,
                )
            )

    @staticmethod
    def _decorator_receiver(source: str, decorator_offset: int) -> str:
        """Return the immediately preceding simple chained expression for a decorator."""
        start = decorator_offset - 1
        while start >= 0 and (source[start].isalnum() or source[start] in "_.$()"):
            start -= 1
        return source[start + 1 : decorator_offset].rstrip(".")

    def _scan_subsystem_command_helpers(
        self,
        source: str,
        package: str,
        relative_path: str,
        source_hash: str,
        result: ScanResult,
    ) -> None:
        """Treat ``subsystem.run*`` helpers as commands with an implicit requirement."""
        for match in SUBSYSTEM_COMMAND_HELPER_PATTERN.finditer(source):
            line = source.count("\n", 0, match.start()) + 1
            subsystem = match.group("subsystem")
            factory = match.group("factory")
            qualified_name = (
                f"{package}.{subsystem}.{factory}@{line}"
                if package
                else f"{subsystem}.{factory}@{line}"
            )
            anchor = self._anchor_at_offset(
                qualified_name, source, match.start(), relative_path, source_hash
            )
            result.symbols.append(
                ScannedSymbol(
                    kind="command_composition",
                    name=f"{subsystem}.{factory} (line {line})",
                    anchor=anchor,
                    confidence="exact",
                )
            )
            result.relationships.append(
                ScannedRelationship(
                    kind="requires",
                    source_symbol=qualified_name,
                    target_expression=subsystem,
                    anchor=anchor,
                    confidence="exact",
                )
            )

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
            anchor = self._anchor_at_offset(
                qualified_name, source, match.start(), relative_path, source_hash
            )
            result.symbols.append(
                ScannedSymbol(
                    kind="command_composition",
                    name=f"{form} (line {line})",
                    anchor=anchor,
                    confidence="exact",
                )
            )
            closing_parenthesis = self._matching_parenthesis(source, match.end() - 1)
            if closing_parenthesis is None:
                result.diagnostics.append(
                    ScanDiagnostic(
                        "warning",
                        f"Unclosed command composition {form} near line {line}.",
                        relative_path,
                    )
                )
                continue
            arguments = source[match.end() : closing_parenthesis]
            for child_expression in self._split_top_level_arguments(arguments):
                result.relationships.append(
                    ScannedRelationship(
                        kind="composition_child",
                        source_symbol=qualified_name,
                        target_expression=child_expression,
                        anchor=anchor,
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
        constants: dict[str, str],
    ) -> None:
        body = source[body_start:body_end]
        for match in DEVICE_PATTERN.finditer(body):
            arguments = " ".join(match.group("arguments").split())
            resolved = self._resolve_constants(arguments, constants)
            result.devices.append(
                ScannedDevice(
                    device_type=match.group("type"),
                    constructor_arguments=arguments,
                    owner_symbol=owner_symbol,
                    anchor=self._anchor_at_offset(
                        owner_symbol,
                        source,
                        body_start + match.start(),
                        relative_path,
                        source_hash,
                    ),
                    resolved_arguments=resolved if resolved != arguments else None,
                    mode=self._implementation_mode(owner_symbol),
                )
            )

    @staticmethod
    def _implementation_mode(owner_symbol: str) -> str | None:
        """Return a truthful IO implementation mode when its type declares one."""
        type_name = owner_symbol.rsplit(".", 1)[-1].upper()
        for mode in ("REPLAY", "SIM", "REAL"):
            if type_name.endswith(mode) or f"IO{mode}" in type_name:
                return mode
        return None

    @staticmethod
    def _project_constant_values(source_paths: list[Path]) -> dict[str, str]:
        """Index qualified constants declared in other Java files.

        This is intentionally not Java type resolution.  It only follows static
        final literal-like declarations, which is enough for the common
        ``Constants.Drive.LEFT_ID`` hardware pattern while remaining safe when a
        project is incomplete.
        """
        values: dict[str, str] = {}
        bare_values: dict[str, str | None] = {}
        for source_path in source_paths:
            try:
                source = source_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            package_match = PACKAGE_PATTERN.search(source)
            package = package_match.group(1) if package_match else ""
            type_match = TYPE_PATTERN.search(source)
            if type_match is None:
                continue
            type_name = type_match.group("name")
            for name, value in JavaProjectScanner._constant_values(source).items():
                values[f"{type_name}.{name}"] = value
                if package:
                    values[f"{package}.{type_name}.{name}"] = value
                if name not in bare_values:
                    bare_values[name] = value
                elif bare_values[name] != value:
                    bare_values[name] = None
        values.update({name: value for name, value in bare_values.items() if value is not None})
        # Follow simple aliases such as ``simDriveId = realDriveId`` without
        # attempting expression evaluation or general Java type resolution.
        for _ in range(2):
            resolved_values = {
                name: JavaProjectScanner._resolve_constants(value, values)
                for name, value in values.items()
            }
            if resolved_values == values:
                break
            values = resolved_values
        return values

    @staticmethod
    def _constant_values(source: str) -> dict[str, str]:
        """Collect literal-like static constants for one safe local resolution hop."""
        return {
            match.group("name"): " ".join(match.group("value").split())
            for match in CONSTANT_PATTERN.finditer(source)
        }

    @staticmethod
    def _resolve_constants(arguments: str, constants: dict[str, str]) -> str:
        """Resolve uppercase constant references while retaining unknown expressions."""
        return re.sub(
            r"\b(?:[A-Za-z_]\w*\.)*(?P<name>[A-Za-z_]\w*)\b",
            lambda match: constants.get(
                match.group(0), constants.get(match.group("name"), match.group(0))
            ),
            arguments,
        )

    def _scan_command_registrations(
        self,
        source: str,
        body_start: int,
        body_end: int,
        owner_symbol: str,
        relative_path: str,
        source_hash: str,
        result: ScanResult,
    ) -> None:
        """Extract default scheduler bindings and named autonomous registrations."""
        body = source[body_start:body_end]
        for match in DEFAULT_COMMAND_PATTERN.finditer(body):
            command = " ".join(match.group("command").split())
            anchor = self._anchor_at_offset(
                owner_symbol, source, body_start + match.start(), relative_path, source_hash
            )
            result.symbols.append(
                ScannedSymbol(
                    kind="command_registration",
                    name=f"Default: {match.group('subsystem')} → {command}",
                    anchor=anchor,
                )
            )
            result.relationships.append(
                ScannedRelationship(
                    kind="default_command",
                    source_symbol=owner_symbol,
                    target_expression=command,
                    anchor=anchor,
                )
            )
        for match in AUTONOMOUS_REGISTRATION_PATTERN.finditer(body):
            command = " ".join(match.group("command").split())
            anchor = self._anchor_at_offset(
                owner_symbol, source, body_start + match.start(), relative_path, source_hash
            )
            result.symbols.append(
                ScannedSymbol(
                    kind="command_registration",
                    name=f"Auto: {match.group('name')}",
                    anchor=anchor,
                )
            )
            result.relationships.append(
                ScannedRelationship(
                    kind="autonomous_registration",
                    source_symbol=owner_symbol,
                    target_expression=command,
                    anchor=anchor,
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
                    documentation=self._attached_javadoc(source, body_offset + match.start()),
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
    def _matching_parenthesis(source: str, opening_parenthesis: int) -> int | None:
        depth = 0
        for index in range(opening_parenthesis, len(source)):
            if source[index] == "(":
                depth += 1
            elif source[index] == ")":
                depth -= 1
                if depth == 0:
                    return index
        return None

    @staticmethod
    def _split_top_level_arguments(arguments: str) -> list[str]:
        """Split composition arguments while preserving nested calls and lambdas."""
        values: list[str] = []
        start = 0
        parentheses = brackets = braces = 0
        quote: str | None = None
        escaped = False
        for index, character in enumerate(arguments):
            if quote is not None:
                if escaped:
                    escaped = False
                elif character == "\\":
                    escaped = True
                elif character == quote:
                    quote = None
                continue
            if character in {"'", '"'}:
                quote = character
            elif character == "(":
                parentheses += 1
            elif character == ")":
                parentheses -= 1
            elif character == "[":
                brackets += 1
            elif character == "]":
                brackets -= 1
            elif character == "{":
                braces += 1
            elif character == "}":
                braces -= 1
            elif character == "," and not (parentheses or brackets or braces):
                value = " ".join(arguments[start:index].split())
                if value:
                    values.append(value)
                start = index + 1
        value = " ".join(arguments[start:].split())
        if value:
            values.append(value)
        return values

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
            documentation=JavaProjectScanner._attached_javadoc(source, offset),
        )

    @staticmethod
    def _attached_javadoc(source: str, declaration_offset: int) -> str | None:
        """Return only JavaDoc immediately associated with a declaration."""
        matches = list(
            re.finditer(r"/\*\*(?P<content>.*?)\*/", source[:declaration_offset], re.DOTALL)
        )
        if not matches:
            return None
        match = matches[-1]
        if source[match.end() : declaration_offset].strip():
            return None
        lines = []
        for line in match.group("content").splitlines():
            cleaned = re.sub(r"^\s*\*?\s?", "", line).strip()
            if cleaned:
                lines.append(cleaned)
        return " ".join(lines) or None

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
