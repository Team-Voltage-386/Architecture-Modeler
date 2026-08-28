"""Validated, language-neutral entities for saved architecture intent."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import PurePath
from typing import Any
from uuid import UUID, uuid4

SCHEMA_VERSION = 1


class ComparisonState(StrEnum):
    """How a design field compares to the latest code-derived value."""

    MATCHED = "matched"
    MODIFIED = "modified"
    DESIGN_ONLY = "design_only"
    CODE_ONLY = "code_only"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True, slots=True)
class SourceAnchor:
    """Portable evidence pointing at a symbol or range in source code."""

    relative_path: str
    qualified_symbol: str
    start_line: int
    end_line: int
    signature: str | None = None
    source_hash: str | None = None

    def __post_init__(self) -> None:
        path = PurePath(self.relative_path)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("Source anchors must use a relative path inside the project.")
        if self.start_line < 1 or self.end_line < self.start_line:
            raise ValueError("Source anchor lines must be positive and ordered.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "relativePath": self.relative_path,
            "qualifiedSymbol": self.qualified_symbol,
            "signature": self.signature,
            "startLine": self.start_line,
            "endLine": self.end_line,
            "sourceHash": self.source_hash,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SourceAnchor:
        return cls(
            relative_path=str(data["relativePath"]),
            qualified_symbol=str(data["qualifiedSymbol"]),
            signature=data.get("signature"),
            start_line=int(data["startLine"]),
            end_line=int(data["endLine"]),
            source_hash=data.get("sourceHash"),
        )


@dataclass(slots=True)
class FieldValue:
    """Separates user-authored intent from code-scanned fact."""

    design: str | None = None
    scanned: str | None = None
    evidence: SourceAnchor | None = None
    confidence: str | None = None

    @property
    def effective(self) -> str | None:
        """Return the design override when present, otherwise the scanned value."""
        return self.design if self.design is not None else self.scanned

    @property
    def comparison_state(self) -> ComparisonState:
        if self.design is None and self.scanned is None:
            return ComparisonState.UNRESOLVED
        if self.design is None:
            return ComparisonState.CODE_ONLY
        if self.scanned is None:
            return ComparisonState.DESIGN_ONLY
        if self.design == self.scanned:
            return ComparisonState.MATCHED
        return ComparisonState.MODIFIED

    def to_dict(self) -> dict[str, Any]:
        return {
            "design": self.design,
            "scanned": self.scanned,
            "evidence": self.evidence.to_dict() if self.evidence else None,
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FieldValue:
        evidence = data.get("evidence")
        return cls(
            design=data.get("design"),
            scanned=data.get("scanned"),
            evidence=SourceAnchor.from_dict(evidence) if evidence else None,
            confidence=data.get("confidence"),
        )


@dataclass(slots=True)
class _ArchitectureElement:
    """Common stable identity and editable fields for architecture elements."""

    name: FieldValue
    description: FieldValue = field(default_factory=FieldValue)
    id: UUID = field(default_factory=uuid4)
    code_binding: SourceAnchor | None = None

    def __post_init__(self) -> None:
        if self.name.effective is None or not self.name.effective.strip():
            raise ValueError("Architecture elements need an effective name.")

    def _to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "name": self.name.to_dict(),
            "description": self.description.to_dict(),
            "codeBinding": self.code_binding.to_dict() if self.code_binding else None,
        }


@dataclass(slots=True)
class Command(_ArchitectureElement):
    """A command and its intentional scheduler requirements."""

    requirement_ids: list[UUID] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {**self._to_dict(), "requirementIds": [str(item) for item in self.requirement_ids]}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Command:
        binding = data.get("codeBinding")
        return cls(
            id=UUID(data["id"]),
            name=FieldValue.from_dict(data["name"]),
            description=FieldValue.from_dict(data.get("description", {})),
            code_binding=SourceAnchor.from_dict(binding) if binding else None,
            requirement_ids=[UUID(item) for item in data.get("requirementIds", [])],
        )


@dataclass(slots=True)
class Subsystem(_ArchitectureElement):
    """A subsystem design entity; device extraction will extend this in Phase 2."""

    def to_dict(self) -> dict[str, Any]:
        return self._to_dict()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Subsystem:
        binding = data.get("codeBinding")
        return cls(
            id=UUID(data["id"]),
            name=FieldValue.from_dict(data["name"]),
            description=FieldValue.from_dict(data.get("description", {})),
            code_binding=SourceAnchor.from_dict(binding) if binding else None,
        )


@dataclass(slots=True)
class ArchitectureProject:
    """Persisted user-authored model, deliberately separate from scan snapshots."""

    name: str
    commands: list[Command] = field(default_factory=list)
    subsystems: list[Subsystem] = field(default_factory=list)
    id: UUID = field(default_factory=uuid4)
    schema_version: int = SCHEMA_VERSION
    unknown_fields: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"Unsupported schema version: {self.schema_version}")
        if not self.name.strip():
            raise ValueError("Project name cannot be empty.")
        element_ids = [item.id for item in [*self.commands, *self.subsystems]]
        if len(element_ids) != len(set(element_ids)):
            raise ValueError("Commands and subsystems must have globally unique IDs.")

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.unknown_fields,
            "schemaVersion": self.schema_version,
            "id": str(self.id),
            "name": self.name,
            "commands": [item.to_dict() for item in self.commands],
            "subsystems": [item.to_dict() for item in self.subsystems],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ArchitectureProject:
        known_keys = {"schemaVersion", "id", "name", "commands", "subsystems"}
        return cls(
            schema_version=int(data["schemaVersion"]),
            id=UUID(data["id"]),
            name=str(data["name"]),
            commands=[Command.from_dict(item) for item in data.get("commands", [])],
            subsystems=[Subsystem.from_dict(item) for item in data.get("subsystems", [])],
            unknown_fields={key: value for key, value in data.items() if key not in known_keys},
        )
