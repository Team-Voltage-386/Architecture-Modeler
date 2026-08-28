"""Tolerant first-pass Java/WPILib project inventory scanner."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from frc_arch_modeler.domain.model import SourceAnchor
from frc_arch_modeler.importers.base import ScanDiagnostic, ScannedSymbol, ScanResult

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
EXCLUDED_DIRECTORY_NAMES = {".gradle", "build", "bin", "vendordeps"}


class JavaProjectScanner:
    """Locate Java source and extract a stable initial WPILib symbol inventory.

    This intentionally accepts incomplete Java. It reports file read failures and
    only records relationships directly visible in declarations; a Tree-sitter
    parser can replace the implementation behind this interface later.
    """

    def scan(self, root: Path) -> ScanResult:
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
            relative_path = source_path.relative_to(root)
            if any(part in EXCLUDED_DIRECTORY_NAMES for part in relative_path.parts):
                continue
            self._scan_file(source_path, root, result)
        return result

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
        package_match = PACKAGE_PATTERN.search(source)
        package = package_match.group(1) if package_match else ""
        source_hash = hashlib.sha256(source.encode("utf-8")).hexdigest()
        for match in TYPE_PATTERN.finditer(source):
            declaration = match.group("declaration")
            kind = self._type_kind(declaration)
            if kind:
                result.symbols.append(
                    self._symbol(
                        kind,
                        match.group("name"),
                        package,
                        source,
                        match.start(),
                        relative_path,
                        source_hash,
                    )
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
        line = source.count("\n", 0, offset) + 1
        qualified_name = f"{package}.{name}" if package else name
        return ScannedSymbol(
            kind=kind,
            name=name,
            anchor=SourceAnchor(
                relative_path=relative_path,
                qualified_symbol=qualified_name,
                start_line=line,
                end_line=line,
                source_hash=source_hash,
            ),
        )
