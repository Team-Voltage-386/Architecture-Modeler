"""Each Model Health rule, proved to fire and proved to stay quiet on a healthy model."""

from uuid import uuid4

from frc_arch_modeler.domain.model import (
    ArchitectureProject,
    BehaviorDiagram,
    BehaviorState,
    BehaviorTransition,
    Command,
    Device,
    FieldValue,
    Relationship,
    Subsystem,
    TriggerBinding,
)
from frc_arch_modeler.services.allocation_service import (
    SEVERITY_ERROR,
    SEVERITY_INCOMPLETE,
    SEVERITY_WARNING,
)
from frc_arch_modeler.services.health_service import (
    FIX_ASSIGN_NEXT_FREE_ADDRESS,
    FIX_REMOVE_ORPHANED_RELATIONSHIP,
    HealthService,
    findings_by_entity,
)


def _state(name: str, kind: str = "state") -> BehaviorState:
    return BehaviorState(name=FieldValue(design=name), kind=kind)


def _device(subsystem: Subsystem, name: str, **overrides) -> Device:
    fields = {
        "name": FieldValue(design=name),
        "device_type": FieldValue(design="TalonFX"),
        "owner_subsystem_id": subsystem.id,
        "bus": FieldValue(design="canivore"),
        "address": FieldValue(design="1"),
    }
    fields.update(overrides)
    return Device(**fields)


def _healthy_project() -> ArchitectureProject:
    """A small model that satisfies every rule, used as the negative case throughout."""
    drivetrain = Subsystem(name=FieldValue(design="Drivetrain"))
    drive = Command(
        name=FieldValue(design="Teleop Drive"), requirement_ids=[drivetrain.id]
    )
    trigger = TriggerBinding(
        expression=FieldValue(design="driver.a()"),
        activation=FieldValue(design="onTrue"),
        command_id=drive.id,
    )
    start = _state("Start", kind="start")
    disabled = _state("Disabled")
    teleop = _state("Teleop")
    diagram = BehaviorDiagram(
        name="Robot Modes",
        states=[start, disabled, teleop],
        transitions=[
            BehaviorTransition(start.id, disabled.id, ""),
            BehaviorTransition(disabled.id, teleop.id, "Teleop period starts"),
        ],
    )
    return ArchitectureProject(
        name="Robot",
        commands=[drive],
        subsystems=[drivetrain],
        devices=[_device(drivetrain, "Left Motor")],
        triggers=[trigger],
        behavior_diagrams=[diagram],
    )


def _kinds(project: ArchitectureProject) -> list[str]:
    return [finding.kind for finding in HealthService().check(project)]


def test_a_healthy_model_reports_no_findings_at_all() -> None:
    assert HealthService().check(_healthy_project()) == []


def test_no_project_reports_no_findings() -> None:
    assert HealthService().check(None) == []


def test_a_subsystem_no_command_requires_is_reported() -> None:
    project = _healthy_project()
    vision = Subsystem(name=FieldValue(design="Vision"))
    project.subsystems.append(vision)

    findings = [
        finding
        for finding in HealthService().check(project)
        if finding.kind == "subsystem_not_required"
    ]

    assert len(findings) == 1
    assert findings[0].severity == SEVERITY_WARNING
    assert findings[0].entity_ids == (vision.id,)
    assert "No command requires Vision" in findings[0].message


def test_a_command_with_no_requirements_is_reported() -> None:
    project = _healthy_project()
    project.commands[0].requirement_ids = []

    findings = [
        finding
        for finding in HealthService().check(project)
        if finding.kind == "command_without_requirements"
    ]

    assert len(findings) == 1
    assert findings[0].severity == SEVERITY_WARNING
    assert findings[0].entity_ids == (project.commands[0].id,)


def test_a_command_with_no_trigger_and_no_behavior_diagram_is_reported() -> None:
    project = _healthy_project()
    project.triggers.clear()

    findings = [
        finding
        for finding in HealthService().check(project)
        if finding.kind == "command_never_started"
    ]

    assert len(findings) == 1
    assert "Nothing starts Teleop Drive" in findings[0].message


def test_a_command_owning_a_behavior_diagram_is_not_reported_as_never_started() -> None:
    project = _healthy_project()
    project.triggers.clear()
    project.behavior_diagrams.append(
        BehaviorDiagram(name="Drive Routine", owner_command_id=project.commands[0].id)
    )

    assert "command_never_started" not in _kinds(project)


def test_a_command_referenced_by_a_transition_is_not_reported_as_never_started() -> None:
    project = _healthy_project()
    project.triggers.clear()
    diagram = project.behavior_diagrams[0]
    diagram.transitions[-1].command_id = project.commands[0].id

    assert "command_never_started" not in _kinds(project)


def test_a_device_whose_type_needs_an_address_and_has_none_is_reported_with_a_fix() -> None:
    project = _healthy_project()
    project.devices.append(
        _device(project.subsystems[0], "Right Motor", address=FieldValue())
    )

    findings = [
        finding
        for finding in HealthService().check(project)
        if finding.kind == "incomplete_address"
    ]

    assert len(findings) == 1
    assert findings[0].severity == SEVERITY_INCOMPLETE
    assert findings[0].fix_action == FIX_ASSIGN_NEXT_FREE_ADDRESS
    assert findings[0].fix_value == "2"
    assert findings[0].fix_label == "Assign address 2 on canivore"


def test_a_device_with_no_bus_is_reported_without_a_fix_to_guess_at() -> None:
    project = _healthy_project()
    project.devices.append(
        _device(
            project.subsystems[0], "Right Motor", bus=FieldValue(), address=FieldValue()
        )
    )

    findings = [
        finding
        for finding in HealthService().check(project)
        if finding.kind == "incomplete_address"
    ]

    assert len(findings) == 1
    assert findings[0].fix_action is None


def test_two_devices_sharing_a_can_id_are_reported_as_an_error() -> None:
    project = _healthy_project()
    project.devices.append(_device(project.subsystems[0], "Right Motor"))

    findings = [
        finding
        for finding in HealthService().check(project)
        if finding.kind == "duplicate_can_id"
    ]

    assert len(findings) == 1
    assert findings[0].severity == SEVERITY_ERROR
    assert len(findings[0].entity_ids) == 2


def test_two_devices_sharing_a_breaker_channel_are_reported_as_an_error() -> None:
    project = _healthy_project()
    for name in ("Left Breaker", "Right Breaker"):
        project.devices.append(
            _device(
                project.subsystems[0],
                name,
                bus=FieldValue(design="pdh"),
                address=FieldValue(design="4"),
            )
        )

    assert "duplicate_breaker_channel" in _kinds(project)


def test_the_robot_wide_breaker_and_mass_budgets_are_left_to_the_hardware_view() -> None:
    """They are a tally about the whole robot, with no single element to reveal."""
    project = _healthy_project()
    project.devices[0].breaker_amps.design = "500"
    project.devices[0].mass_kg.design = "500"

    assert HealthService().check(project) == []


def test_a_behavior_diagram_with_no_start_state_is_reported() -> None:
    project = _healthy_project()
    diagram = project.behavior_diagrams[0]
    start = diagram.states[0]
    diagram.transitions = [
        transition
        for transition in diagram.transitions
        if transition.source_state_id != start.id
    ]
    diagram.states.remove(start)

    findings = [
        finding
        for finding in HealthService().check(project)
        if finding.kind == "behavior_diagram_without_start"
    ]

    assert len(findings) == 1
    assert findings[0].entity_ids == (diagram.id,)
    assert findings[0].diagram_id == diagram.id


def test_an_empty_behavior_diagram_is_not_yet_reported_as_missing_a_start() -> None:
    project = _healthy_project()
    project.behavior_diagrams.append(BehaviorDiagram(name="Autonomous Routines"))

    assert "behavior_diagram_without_start" not in _kinds(project)


def test_a_behavior_state_unreachable_from_the_start_is_reported() -> None:
    project = _healthy_project()
    diagram = project.behavior_diagrams[0]
    stranded = _state("Test")
    diagram.states.append(stranded)

    findings = [
        finding
        for finding in HealthService().check(project)
        if finding.kind == "unreachable_behavior_state"
    ]

    assert len(findings) == 1
    assert findings[0].entity_ids == (stranded.id,)
    assert findings[0].diagram_id == diagram.id
    assert "cannot be reached from the start state" in findings[0].message


def test_reachability_is_not_checked_until_a_diagram_says_where_it_begins() -> None:
    project = _healthy_project()
    diagram = project.behavior_diagrams[0]
    start = diagram.states[0]
    diagram.transitions = [
        transition
        for transition in diagram.transitions
        if transition.source_state_id != start.id
    ]
    diagram.states.remove(start)

    assert "unreachable_behavior_state" not in _kinds(project)


def test_a_transition_with_an_empty_label_between_two_named_states_is_reported() -> None:
    project = _healthy_project()
    diagram = project.behavior_diagrams[0]
    diagram.transitions[-1].trigger_label = "   "

    findings = [
        finding
        for finding in HealthService().check(project)
        if finding.kind == "unlabeled_transition"
    ]

    assert len(findings) == 1
    assert findings[0].severity == SEVERITY_INCOMPLETE
    assert findings[0].entity_ids == (diagram.transitions[-1].id,)
    assert "from Disabled to Teleop" in findings[0].message


def test_an_empty_label_next_to_a_start_join_or_sync_node_is_conventional_and_quiet() -> None:
    project = _healthy_project()
    diagram = project.behavior_diagrams[0]
    merge = _state("Merge", kind="join")
    bar = _state("Fork", kind="synchronization")
    diagram.states.extend([merge, bar])
    diagram.transitions.append(BehaviorTransition(diagram.states[2].id, merge.id, ""))
    diagram.transitions.append(BehaviorTransition(merge.id, bar.id, ""))

    assert "unlabeled_transition" not in _kinds(project)


def test_an_element_still_carrying_a_default_name_is_reported() -> None:
    project = _healthy_project()
    project.commands.append(
        Command(
            name=FieldValue(design="New Command"),
            requirement_ids=[project.subsystems[0].id],
        )
    )
    project.triggers.append(
        TriggerBinding(
            expression=FieldValue(design="driver.b()"),
            activation=FieldValue(design="onTrue"),
            command_id=project.commands[-1].id,
        )
    )

    findings = [
        finding for finding in HealthService().check(project) if finding.kind == "default_name"
    ]

    assert len(findings) == 1
    assert findings[0].severity == SEVERITY_INCOMPLETE
    assert findings[0].entity_ids == (project.commands[-1].id,)
    assert "still has the name the tool proposed" in findings[0].message


def test_a_default_named_behavior_diagram_and_state_are_reported_against_their_diagram() -> None:
    project = _healthy_project()
    placeholder = _state("New State")
    diagram = BehaviorDiagram(name="Untitled Diagram", states=[placeholder])
    project.behavior_diagrams.append(diagram)

    findings = [
        finding for finding in HealthService().check(project) if finding.kind == "default_name"
    ]

    assert {finding.entity_ids for finding in findings} == {
        (diagram.id,),
        (placeholder.id,),
    }
    assert all(finding.diagram_id == diagram.id for finding in findings)


def test_a_relationship_left_pointing_at_a_deleted_element_is_reported_with_a_fix() -> None:
    project = _healthy_project()
    orphan = Relationship("calls", project.commands[0].id, uuid4())
    project.relationships.append(orphan)

    findings = [
        finding
        for finding in HealthService().check(project)
        if finding.kind == "orphaned_relationship"
    ]

    assert len(findings) == 1
    assert findings[0].severity == SEVERITY_ERROR
    assert findings[0].entity_ids == (orphan.id,)
    assert findings[0].fix_action == FIX_REMOVE_ORPHANED_RELATIONSHIP


def test_findings_are_ordered_by_severity_then_deterministically_within_it() -> None:
    project = _healthy_project()
    project.commands[0].requirement_ids = []
    project.subsystems.append(Subsystem(name=FieldValue(design="Vision")))
    project.devices.append(
        _device(project.subsystems[0], "Right Motor", address=FieldValue())
    )
    project.relationships.append(Relationship("calls", project.commands[0].id, uuid4()))

    findings = HealthService().check(project)

    assert [finding.severity for finding in findings] == [
        SEVERITY_ERROR,
        SEVERITY_WARNING,
        SEVERITY_WARNING,
        SEVERITY_WARNING,
        SEVERITY_INCOMPLETE,
    ]
    assert [finding.kind for finding in findings] == [
        "orphaned_relationship",
        "command_without_requirements",
        "subsystem_not_required",
        "subsystem_not_required",
        "incomplete_address",
    ]
    # Within one kind, findings are ordered by message, not by iteration or uuid order.
    assert "Drivetrain" in findings[2].message
    assert "Vision" in findings[3].message
    assert HealthService().check(project) == findings


def test_findings_can_be_grouped_by_every_entity_they_name() -> None:
    project = _healthy_project()
    project.devices.append(_device(project.subsystems[0], "Right Motor"))

    grouped = findings_by_entity(HealthService().check(project))

    assert set(grouped) == {device.id for device in project.devices}
    assert all(findings[0].kind == "duplicate_can_id" for findings in grouped.values())
