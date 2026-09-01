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
    AMBIGUOUS = "ambiguous"
    SCAN_ERROR = "scan_error"


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
class Device:
    """A portable, design-layer hardware fact owned by a logical subsystem."""

    name: FieldValue
    device_type: FieldValue
    owner_subsystem_id: UUID
    mode: FieldValue = field(default_factory=FieldValue)
    id: UUID = field(default_factory=uuid4)
    code_binding: SourceAnchor | None = None

    def __post_init__(self) -> None:
        if not (self.name.effective or "").strip() or not (
            self.device_type.effective or ""
        ).strip():
            raise ValueError("Devices need an effective name and type.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "name": self.name.to_dict(),
            "deviceType": self.device_type.to_dict(),
            "ownerSubsystemId": str(self.owner_subsystem_id),
            "mode": self.mode.to_dict(),
            "codeBinding": self.code_binding.to_dict() if self.code_binding else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Device:
        binding = data.get("codeBinding")
        return cls(
            id=UUID(data["id"]),
            name=FieldValue.from_dict(data["name"]),
            device_type=FieldValue.from_dict(data["deviceType"]),
            owner_subsystem_id=UUID(data["ownerSubsystemId"]),
            mode=FieldValue.from_dict(data.get("mode", {})),
            code_binding=SourceAnchor.from_dict(binding) if binding else None,
        )


@dataclass(slots=True)
class TriggerBinding:
    """A designed controller/trigger connection to a command."""

    expression: FieldValue
    activation: FieldValue
    command_id: UUID
    id: UUID = field(default_factory=uuid4)
    code_binding: SourceAnchor | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "expression": self.expression.to_dict(),
            "activation": self.activation.to_dict(),
            "commandId": str(self.command_id),
            "codeBinding": self.code_binding.to_dict() if self.code_binding else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TriggerBinding:
        binding = data.get("codeBinding")
        return cls(
            id=UUID(data["id"]),
            expression=FieldValue.from_dict(data["expression"]),
            activation=FieldValue.from_dict(data["activation"]),
            command_id=UUID(data["commandId"]),
            code_binding=SourceAnchor.from_dict(binding) if binding else None,
        )


@dataclass(slots=True)
class Relationship:
    """A typed design relationship kept separately from inferred code evidence."""

    relationship_type: str
    source_id: UUID
    target_id: UUID
    id: UUID = field(default_factory=uuid4)
    code_binding: SourceAnchor | None = None

    def __post_init__(self) -> None:
        if not self.relationship_type.strip():
            raise ValueError("Relationships need a type.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "relationshipType": self.relationship_type,
            "sourceId": str(self.source_id),
            "targetId": str(self.target_id),
            "codeBinding": self.code_binding.to_dict() if self.code_binding else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Relationship:
        binding = data.get("codeBinding")
        return cls(
            id=UUID(data["id"]),
            relationship_type=str(data["relationshipType"]),
            source_id=UUID(data["sourceId"]),
            target_id=UUID(data["targetId"]),
            code_binding=SourceAnchor.from_dict(binding) if binding else None,
        )


#: SysML-style pseudostates supported alongside a plain named state. "start"/"end" are the
#: initial/final markers, "decision" branches on a guard condition, and "synchronization" is a
#: fork/join bar for concurrent flows.
BEHAVIOR_STATE_KINDS = frozenset({"state", "start", "end", "decision", "synchronization"})


@dataclass(slots=True)
class BehaviorState:
    """One node in an authored robot-mode state diagram (a behavioral, not structural, view)."""

    name: FieldValue
    id: UUID = field(default_factory=uuid4)
    description: FieldValue = field(default_factory=FieldValue)
    kind: str = "state"

    def __post_init__(self) -> None:
        if not (self.name.effective or "").strip():
            raise ValueError("Behavior states need an effective name.")
        if self.kind not in BEHAVIOR_STATE_KINDS:
            raise ValueError(f"Unsupported behavior state kind: {self.kind}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "name": self.name.to_dict(),
            "description": self.description.to_dict(),
            "kind": self.kind,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BehaviorState:
        return cls(
            id=UUID(data["id"]),
            name=FieldValue.from_dict(data["name"]),
            description=FieldValue.from_dict(data.get("description", {})),
            kind=data.get("kind", "state"),
        )


@dataclass(slots=True)
class BehaviorTransition:
    """An authored, directed edge between two behavior states and its triggering event.

    The label may be empty: transitions leaving a start pseudostate or crossing a
    synchronization bar are conventionally unlabeled in SysML/UML notation.
    """

    source_state_id: UUID
    target_state_id: UUID
    trigger_label: str
    id: UUID = field(default_factory=uuid4)
    command_id: UUID | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "sourceStateId": str(self.source_state_id),
            "targetStateId": str(self.target_state_id),
            "triggerLabel": self.trigger_label,
            "commandId": str(self.command_id) if self.command_id else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BehaviorTransition:
        command_id = data.get("commandId")
        return cls(
            id=UUID(data["id"]),
            source_state_id=UUID(data["sourceStateId"]),
            target_state_id=UUID(data["targetStateId"]),
            trigger_label=str(data["triggerLabel"]),
            command_id=UUID(command_id) if command_id else None,
        )


@dataclass(slots=True)
class BehaviorDiagram:
    """A SysML-inspired state diagram, editable separately from the structural model."""

    name: str
    states: list[BehaviorState] = field(default_factory=list)
    transitions: list[BehaviorTransition] = field(default_factory=list)
    owner_command_id: UUID | None = None
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Behavior diagrams need a name.")
        state_ids = {state.id for state in self.states}
        if len(state_ids) != len(self.states):
            raise ValueError("Behavior states must have unique IDs within a diagram.")
        if any(
            transition.source_state_id not in state_ids
            or transition.target_state_id not in state_ids
            for transition in self.transitions
        ):
            raise ValueError("Behavior transitions must connect states in the same diagram.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "name": self.name,
            "states": [state.to_dict() for state in self.states],
            "transitions": [transition.to_dict() for transition in self.transitions],
            "ownerCommandId": str(self.owner_command_id) if self.owner_command_id else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BehaviorDiagram:
        owner_command_id = data.get("ownerCommandId")
        return cls(
            id=UUID(data["id"]),
            name=str(data["name"]),
            states=[BehaviorState.from_dict(item) for item in data.get("states", [])],
            transitions=[
                BehaviorTransition.from_dict(item) for item in data.get("transitions", [])
            ],
            owner_command_id=UUID(owner_command_id) if owner_command_id else None,
        )


@dataclass(slots=True)
class ArchitectureProject:
    """Persisted user-authored model, deliberately separate from scan snapshots."""

    name: str
    commands: list[Command] = field(default_factory=list)
    subsystems: list[Subsystem] = field(default_factory=list)
    devices: list[Device] = field(default_factory=list)
    triggers: list[TriggerBinding] = field(default_factory=list)
    relationships: list[Relationship] = field(default_factory=list)
    behavior_diagrams: list[BehaviorDiagram] = field(default_factory=list)
    id: UUID = field(default_factory=uuid4)
    schema_version: int = SCHEMA_VERSION
    unknown_fields: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"Unsupported schema version: {self.schema_version}")
        if not self.name.strip():
            raise ValueError("Project name cannot be empty.")
        element_ids = [
            item.id
            for item in [
                *self.commands,
                *self.subsystems,
                *self.devices,
                *self.triggers,
                *self.relationships,
                *self.behavior_diagrams,
                *[state for diagram in self.behavior_diagrams for state in diagram.states],
                *[
                    transition
                    for diagram in self.behavior_diagrams
                    for transition in diagram.transitions
                ],
            ]
        ]
        if len(element_ids) != len(set(element_ids)):
            raise ValueError("Architecture entities must have globally unique IDs.")
        subsystem_ids = {item.id for item in self.subsystems}
        command_ids = {item.id for item in self.commands}
        if any(device.owner_subsystem_id not in subsystem_ids for device in self.devices):
            raise ValueError("Devices must be owned by a subsystem in the project.")
        if any(trigger.command_id not in command_ids for trigger in self.triggers):
            raise ValueError("Triggers must target a command in the project.")
        known_ids = set(element_ids)
        if any(
            relationship.source_id not in known_ids or relationship.target_id not in known_ids
            for relationship in self.relationships
        ):
            raise ValueError("Relationships must connect entities in the project.")
        if any(
            transition.command_id is not None and transition.command_id not in command_ids
            for diagram in self.behavior_diagrams
            for transition in diagram.transitions
        ):
            raise ValueError("Behavior transitions must reference a command in the project.")
        if any(
            diagram.owner_command_id is not None and diagram.owner_command_id not in command_ids
            for diagram in self.behavior_diagrams
        ):
            raise ValueError("Behavior diagrams must reference a command in the project.")

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.unknown_fields,
            "schemaVersion": self.schema_version,
            "id": str(self.id),
            "name": self.name,
            "commands": [item.to_dict() for item in self.commands],
            "subsystems": [item.to_dict() for item in self.subsystems],
            "devices": [item.to_dict() for item in self.devices],
            "triggers": [item.to_dict() for item in self.triggers],
            "relationships": [item.to_dict() for item in self.relationships],
            "behaviorDiagrams": [item.to_dict() for item in self.behavior_diagrams],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ArchitectureProject:
        known_keys = {
            "schemaVersion",
            "id",
            "name",
            "commands",
            "subsystems",
            "devices",
            "triggers",
            "relationships",
            "behaviorDiagrams",
        }
        return cls(
            schema_version=int(data["schemaVersion"]),
            id=UUID(data["id"]),
            name=str(data["name"]),
            commands=[Command.from_dict(item) for item in data.get("commands", [])],
            subsystems=[Subsystem.from_dict(item) for item in data.get("subsystems", [])],
            devices=[Device.from_dict(item) for item in data.get("devices", [])],
            triggers=[TriggerBinding.from_dict(item) for item in data.get("triggers", [])],
            relationships=[Relationship.from_dict(item) for item in data.get("relationships", [])],
            behavior_diagrams=[
                BehaviorDiagram.from_dict(item) for item in data.get("behaviorDiagrams", [])
            ],
            unknown_fields={key: value for key, value in data.items() if key not in known_keys},
        )
