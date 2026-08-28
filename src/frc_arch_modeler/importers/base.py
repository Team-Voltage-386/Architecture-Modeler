"""Language-neutral scan result interfaces."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from frc_arch_modeler.domain.model import SourceAnchor


@dataclass(frozen=True, slots=True)
class ScannedSymbol:
    """One code-derived architecture symbol with traceable source evidence."""

    kind: str
    name: str
    anchor: SourceAnchor
    confidence: str = "exact"


@dataclass(frozen=True, slots=True)
class ScanDiagnostic:
    """A non-fatal issue encountered while scanning source files."""

    severity: str
    message: str
    relative_path: str | None = None


@dataclass(frozen=True, slots=True)
class ScannedRelationship:
    """A source-derived relationship with the original expression retained as evidence."""

    kind: str
    source_symbol: str
    target_expression: str
    anchor: SourceAnchor
    confidence: str = "exact"


@dataclass(frozen=True, slots=True)
class ScannedTrigger:
    """A scheduler trigger binding extracted directly from robot-container code."""

    controller_expression: str
    activation: str
    command_expression: str
    anchor: SourceAnchor
    confidence: str = "exact"


@dataclass(slots=True)
class ScanResult:
    """Current, regenerable code facts from one robot-project scan."""

    project_root: Path
    symbols: list[ScannedSymbol] = field(default_factory=list)
    relationships: list[ScannedRelationship] = field(default_factory=list)
    triggers: list[ScannedTrigger] = field(default_factory=list)
    diagnostics: list[ScanDiagnostic] = field(default_factory=list)
    files_scanned: int = 0

    def symbols_of_kind(self, kind: str) -> list[ScannedSymbol]:
        return [symbol for symbol in self.symbols if symbol.kind == kind]
