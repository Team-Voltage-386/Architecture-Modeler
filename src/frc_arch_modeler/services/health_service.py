"""Pure detection of modeling mistakes across a whole project.

Every rule a mentor would otherwise have to say out loud lives here, computed from the
saved design alone: no Qt, no code scan, no layout. The Model Health panel renders what
this returns and contains no rule logic of its own, so a rule can be unit-tested against
a small constructed project without a running application.

Hardware allocation problems are not restated here — `AllocationService` already owns
them, and `check` folds its findings in. The two robot-wide budget totals it reports
(summed breaker amps, summed device mass) are deliberately left out: they are an
informational tally about the whole robot rather than a defect in a specific element,
they have no element to reveal on a canvas, and they are already surfaced per device by
the Hardware table and the canvas alert badges.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from frc_arch_modeler.domain.model import (
    ArchitectureProject,
    BehaviorDiagram,
    BehaviorState,
)
from frc_arch_modeler.services.allocation_service import (
    SEVERITY_ERROR,
    SEVERITY_INCOMPLETE,
    SEVERITY_WARNING,
    AllocationFinding,
    AllocationService,
    next_free_address,
)

#: Fix action ids. A fix is offered only where the correction is unambiguous and safe;
#: the panel turns one into an undoable command and never applies it on its own.
FIX_ASSIGN_NEXT_FREE_ADDRESS = "assign_next_free_address"
FIX_REMOVE_ORPHANED_RELATIONSHIP = "remove_orphaned_relationship"

#: Most-actionable severity first, so the panel's groups and the findings inside them
#: read top-down in the order a student should work through them.
SEVERITY_RANK = {SEVERITY_ERROR: 0, SEVERITY_WARNING: 1, SEVERITY_INCOMPLETE: 2}

#: Allocation findings about the whole robot rather than one element (see module docstring).
_ROBOT_BUDGET_KINDS = frozenset({"breaker_budget_exceeded", "mass_budget_exceeded"})

#: Names the application itself proposes when creating an element. A name still equal to
#: one of these means nobody has said what the element actually is.
_DEFAULT_NAMES = frozenset(
    {
        "unnamed",
        "unnamedcommand",
        "untitled",
        "untitleddiagram",
        "newdiagram",
        "newbehaviordiagram",
        "newcommand",
        "newsubsystem",
        "newdevice",
        "newstate",
        "newtrigger",
    }
)

#: Pseudostates whose adjacent transitions are conventionally unlabeled in SysML/UML:
#: the flow out of a start marker, and the flows across a fork/join bar or merge point.
_UNLABELED_TRANSITION_KINDS = frozenset({"start", "join", "synchronization"})


@dataclass(frozen=True, slots=True)
class HealthFinding:
    """One modeling problem, independent of any presentation layer.

    ``entity_ids`` names the elements the finding is about, most important first, so the
    panel can select and reveal ``entity_ids[0]``. ``diagram_id`` is set when those
    elements live inside a behavior diagram, which tells the panel which canvas — and
    which diagram on it — owns them.
    """

    kind: str
    severity: str
    message: str
    entity_ids: tuple[UUID, ...]
    diagram_id: UUID | None = None
    fix_action: str | None = None
    fix_label: str | None = None
    fix_value: str | None = None

    @property
    def sort_key(self) -> tuple:
        """Total order over findings: most-actionable severity first, then by rule.

        Nothing in it depends on iteration order or on `uuid4`, so two runs over the
        same model produce the same list and a test can assert on it.
        """
        return (
            SEVERITY_RANK.get(self.severity, len(SEVERITY_RANK)),
            self.kind,
            self.message,
            tuple(str(entity_id) for entity_id in self.entity_ids),
        )


class HealthService:
    """Every model-health rule the tool teaches, in one place and free of Qt."""

    def __init__(self, allocation_service: AllocationService | None = None) -> None:
        self.allocation_service = allocation_service or AllocationService()

    def check(self, project: ArchitectureProject | None) -> list[HealthFinding]:
        """Every finding for `project`, in a stable, deterministic order."""
        if project is None:
            return []
        findings = [
            *self._allocation_findings(project),
            *self._subsystem_findings(project),
            *self._command_findings(project),
            *self._relationship_findings(project),
            *self._behavior_findings(project),
            *self._default_name_findings(project),
        ]
        return sorted(findings, key=lambda finding: finding.sort_key)

    # -- hardware ---------------------------------------------------------

    def _allocation_findings(self, project: ArchitectureProject) -> list[HealthFinding]:
        """Reuse the allocation rules rather than restating them."""
        devices = {device.id: device for device in project.devices}
        findings: list[HealthFinding] = []
        for allocation in self.allocation_service.check(project):
            if allocation.kind in _ROBOT_BUDGET_KINDS:
                continue
            findings.append(self._from_allocation(allocation, project, devices))
        return findings

    @staticmethod
    def _from_allocation(
        allocation: AllocationFinding, project: ArchitectureProject, devices: dict
    ) -> HealthFinding:
        """Offer the next free address only where the device already names a bus.

        Without a bus there is no numbering space to pick from, so the fix would be a
        guess rather than a correction.
        """
        fix_action = fix_label = fix_value = None
        device = devices.get(allocation.device_ids[0]) if allocation.device_ids else None
        if allocation.kind == "incomplete_address" and device is not None:
            bus = (device.bus.effective or "").strip()
            if bus:
                fix_value = next_free_address(project, bus)
                fix_action = FIX_ASSIGN_NEXT_FREE_ADDRESS
                fix_label = f"Assign address {fix_value} on {bus}"
        return HealthFinding(
            kind=allocation.kind,
            severity=allocation.severity,
            message=allocation.message,
            entity_ids=allocation.device_ids,
            fix_action=fix_action,
            fix_label=fix_label,
            fix_value=fix_value,
        )

    # -- structure --------------------------------------------------------

    @staticmethod
    def _subsystem_findings(project: ArchitectureProject) -> list[HealthFinding]:
        required = {
            requirement_id
            for command in project.commands
            for requirement_id in command.requirement_ids
        }
        return [
            HealthFinding(
                kind="subsystem_not_required",
                severity=SEVERITY_WARNING,
                message=(
                    f"No command requires {_name(subsystem)} — a subsystem nothing "
                    "requires is never scheduled, so none of its hardware ever moves."
                ),
                entity_ids=(subsystem.id,),
            )
            for subsystem in project.subsystems
            if subsystem.id not in required
        ]

    @staticmethod
    def _command_findings(project: ArchitectureProject) -> list[HealthFinding]:
        triggered = {trigger.command_id for trigger in project.triggers}
        in_behavior = {
            diagram.owner_command_id
            for diagram in project.behavior_diagrams
            if diagram.owner_command_id is not None
        } | {
            transition.command_id
            for diagram in project.behavior_diagrams
            for transition in diagram.transitions
            if transition.command_id is not None
        }
        findings: list[HealthFinding] = []
        for command in project.commands:
            if not command.requirement_ids:
                findings.append(
                    HealthFinding(
                        kind="command_without_requirements",
                        severity=SEVERITY_WARNING,
                        message=(
                            f"{_name(command)} requires no subsystem — without a "
                            "requirement the scheduler cannot stop another command "
                            "driving the same hardware at the same time."
                        ),
                        entity_ids=(command.id,),
                    )
                )
            if command.id not in triggered and command.id not in in_behavior:
                findings.append(
                    HealthFinding(
                        kind="command_never_started",
                        severity=SEVERITY_WARNING,
                        message=(
                            f"Nothing starts {_name(command)} — it has no trigger and "
                            "no behavior diagram refers to it."
                        ),
                        entity_ids=(command.id,),
                    )
                )
        return findings

    @staticmethod
    def _relationship_findings(project: ArchitectureProject) -> list[HealthFinding]:
        """A relationship left pointing at an element a delete removed.

        The model rejects this on load, so it can only appear mid-session; detecting it
        keeps a half-finished cascade from being saved.
        """
        # The same set the model itself validates relationships against, so this rule
        # can only fire where loading the model would also have rejected it.
        known_ids = {
            item.id
            for item in [
                *project.commands,
                *project.subsystems,
                *project.devices,
                *project.triggers,
                *project.behavior_diagrams,
                *[state for diagram in project.behavior_diagrams for state in diagram.states],
                *[
                    transition
                    for diagram in project.behavior_diagrams
                    for transition in diagram.transitions
                ],
            ]
        }
        return [
            HealthFinding(
                kind="orphaned_relationship",
                severity=SEVERITY_ERROR,
                message=(
                    f"A '{relationship.relationship_type}' relationship points at an "
                    "element that is no longer in the model."
                ),
                entity_ids=(relationship.id,),
                fix_action=FIX_REMOVE_ORPHANED_RELATIONSHIP,
                fix_label="Remove this relationship",
            )
            for relationship in project.relationships
            if relationship.source_id not in known_ids or relationship.target_id not in known_ids
        ]

    # -- behavior ---------------------------------------------------------

    @staticmethod
    def _behavior_findings(project: ArchitectureProject) -> list[HealthFinding]:
        findings: list[HealthFinding] = []
        for diagram in project.behavior_diagrams:
            findings.extend(HealthService._diagram_findings(diagram))
        return findings

    @staticmethod
    def _diagram_findings(diagram: BehaviorDiagram) -> list[HealthFinding]:
        findings: list[HealthFinding] = []
        start_ids = [state.id for state in diagram.states if state.kind == "start"]
        # An entirely empty diagram is a diagram nobody has begun, not one drawn wrong.
        if diagram.states and not start_ids:
            findings.append(
                HealthFinding(
                    kind="behavior_diagram_without_start",
                    severity=SEVERITY_WARNING,
                    message=(
                        f"'{diagram.name}' has no start state — a reader cannot tell "
                        "which state the robot is in before anything happens."
                    ),
                    entity_ids=(diagram.id,),
                    diagram_id=diagram.id,
                )
            )
        findings.extend(HealthService._unreachable_state_findings(diagram, start_ids))
        findings.extend(HealthService._unlabeled_transition_findings(diagram))
        return findings

    @staticmethod
    def _unreachable_state_findings(
        diagram: BehaviorDiagram, start_ids: list[UUID]
    ) -> list[HealthFinding]:
        """Reachability is only meaningful once a diagram says where it begins."""
        if not start_ids:
            return []
        outgoing: dict[UUID, list[UUID]] = {}
        for transition in diagram.transitions:
            outgoing.setdefault(transition.source_state_id, []).append(
                transition.target_state_id
            )
        reachable = set(start_ids)
        pending = list(start_ids)
        while pending:
            for target_id in outgoing.get(pending.pop(), ()):
                if target_id not in reachable:
                    reachable.add(target_id)
                    pending.append(target_id)
        return [
            HealthFinding(
                kind="unreachable_behavior_state",
                severity=SEVERITY_WARNING,
                message=(
                    f"{_name(state)} in '{diagram.name}' cannot be reached from the "
                    "start state — no chain of transitions leads to it."
                ),
                entity_ids=(state.id,),
                diagram_id=diagram.id,
            )
            for state in diagram.states
            if state.id not in reachable
        ]

    @staticmethod
    def _unlabeled_transition_findings(diagram: BehaviorDiagram) -> list[HealthFinding]:
        states = {state.id: state for state in diagram.states}
        findings: list[HealthFinding] = []
        for transition in diagram.transitions:
            if transition.trigger_label.strip():
                continue
            endpoints = (
                states.get(transition.source_state_id),
                states.get(transition.target_state_id),
            )
            if any(
                state is not None and state.kind in _UNLABELED_TRANSITION_KINDS
                for state in endpoints
            ):
                continue
            source = _name(endpoints[0]) if endpoints[0] is not None else "an unknown state"
            target = _name(endpoints[1]) if endpoints[1] is not None else "an unknown state"
            findings.append(
                HealthFinding(
                    kind="unlabeled_transition",
                    severity=SEVERITY_INCOMPLETE,
                    message=(
                        f"The transition from {source} to {target} in '{diagram.name}' "
                        "has no trigger — say what event causes it."
                    ),
                    entity_ids=(transition.id,),
                    diagram_id=diagram.id,
                )
            )
        return findings

    # -- naming -----------------------------------------------------------

    @staticmethod
    def _default_name_findings(project: ArchitectureProject) -> list[HealthFinding]:
        findings: list[HealthFinding] = []
        for label, elements in (
            ("Command", project.commands),
            ("Subsystem", project.subsystems),
            ("Device", project.devices),
        ):
            for element in elements:
                if _is_default_name(element.name.effective):
                    findings.append(_default_name_finding(label, _name(element), element.id))
        for diagram in project.behavior_diagrams:
            if _is_default_name(diagram.name):
                findings.append(
                    _default_name_finding(
                        "Behavior diagram", diagram.name, diagram.id, diagram.id
                    )
                )
            for state in diagram.states:
                if _is_default_name(state.name.effective):
                    findings.append(
                        _default_name_finding(
                            "Behavior state", _name(state), state.id, diagram.id
                        )
                    )
        return findings


def _default_name_finding(
    label: str, name: str, entity_id: UUID, diagram_id: UUID | None = None
) -> HealthFinding:
    return HealthFinding(
        kind="default_name",
        severity=SEVERITY_INCOMPLETE,
        message=(
            f"{label} '{name}' still has the name the tool proposed — rename it to "
            "what it actually does."
        ),
        entity_ids=(entity_id,),
        diagram_id=diagram_id,
    )


def _is_default_name(name: str | None) -> bool:
    return _normalize(name or "") in _DEFAULT_NAMES


def _normalize(value: str) -> str:
    return "".join(character for character in value.casefold() if character.isalnum())


def _name(element: BehaviorState | object) -> str:
    """The displayed name of any `FieldValue`-named element, matching the canvas."""
    return element.name.effective or "Unnamed"  # type: ignore[attr-defined]


def findings_by_entity(findings: list[HealthFinding]) -> dict[UUID, list[HealthFinding]]:
    """Group findings by every entity they name, for per-element badges and tooltips."""
    grouped: dict[UUID, list[HealthFinding]] = {}
    for finding in findings:
        for entity_id in finding.entity_ids:
            grouped.setdefault(entity_id, []).append(finding)
    return grouped
