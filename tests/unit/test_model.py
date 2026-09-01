import pytest

from frc_arch_modeler.domain.model import (
    ArchitectureProject,
    BehaviorDiagram,
    BehaviorState,
    BehaviorTransition,
    Command,
    ComparisonState,
    Device,
    FieldValue,
    Relationship,
    SourceAnchor,
    Subsystem,
    TriggerBinding,
)
from frc_arch_modeler.persistence.migrations import migrate_model_payload
from frc_arch_modeler.persistence.project_store import ProjectStore


def test_field_values_preserve_design_over_scanned_value() -> None:
    value = FieldValue(design="Drive robot", scanned="Drive")

    assert value.effective == "Drive robot"
    assert value.comparison_state is ComparisonState.MODIFIED


def test_project_round_trip_preserves_unknown_fields(tmp_path) -> None:
    drive = Subsystem(name=FieldValue(design="Drive"))
    command = Command(name=FieldValue(design="Teleop Drive"), requirement_ids=[drive.id])
    project = ArchitectureProject(
        name="Practice Bot",
        commands=[command],
        subsystems=[drive],
        unknown_fields={"futureField": {"kept": True}},
    )

    store = ProjectStore(tmp_path)
    path = store.save(project)
    loaded = store.load()

    assert path == tmp_path / ".frc-architecture" / "model.json"
    assert loaded.to_dict() == project.to_dict()
    assert loaded.unknown_fields == {"futureField": {"kept": True}}


def test_source_anchor_rejects_machine_specific_or_parent_paths() -> None:
    for unsafe_path in ("C:/robot/src/Drive.java", "../Drive.java"):
        try:
            SourceAnchor(unsafe_path, "robot.Drive", 1, 2)
        except ValueError:
            continue
        raise AssertionError(f"Expected {unsafe_path!r} to be rejected")


def test_migration_adds_schema_version_to_legacy_payload() -> None:
    project = ArchitectureProject(name="Robot")
    legacy = project.to_dict()
    legacy.pop("schemaVersion")
    legacy["futureField"] = {"value": 1}

    migrated = migrate_model_payload(legacy)

    assert migrated["schemaVersion"] == 1
    assert migrated["futureField"] == {"value": 1}


def test_project_round_trip_preserves_design_hardware_triggers_and_relationships(tmp_path) -> None:
    drive = Subsystem(name=FieldValue(design="Drive"))
    command = Command(name=FieldValue(design="Teleop Drive"), requirement_ids=[drive.id])
    device = Device(
        name=FieldValue(design="Left motor"),
        device_type=FieldValue(design="SparkMax"),
        owner_subsystem_id=drive.id,
        mode=FieldValue(design="REAL"),
    )
    trigger = TriggerBinding(
        expression=FieldValue(design="Driver A"),
        activation=FieldValue(design="onTrue"),
        command_id=command.id,
    )
    relationship = Relationship("owns_device", drive.id, device.id)
    project = ArchitectureProject(
        name="Robot",
        commands=[command],
        subsystems=[drive],
        devices=[device],
        triggers=[trigger],
        relationships=[relationship],
    )

    ProjectStore(tmp_path).save(project)

    assert ProjectStore(tmp_path).load().to_dict() == project.to_dict()


def test_behavior_transition_must_connect_states_in_the_same_diagram() -> None:
    disabled = BehaviorState(name=FieldValue(design="Disabled"))
    with pytest.raises(ValueError):
        BehaviorDiagram(
            name="Robot Modes",
            states=[disabled],
            transitions=[
                BehaviorTransition(disabled.id, BehaviorState(name=FieldValue(design="X")).id, "Go")
            ],
        )


def test_project_round_trips_behavior_diagram_with_command_evidence_link(tmp_path) -> None:
    command = Command(name=FieldValue(design="Autonomous Routine"))
    disabled = BehaviorState(name=FieldValue(design="Disabled"))
    autonomous = BehaviorState(name=FieldValue(design="Autonomous"))
    transition = BehaviorTransition(
        disabled.id, autonomous.id, "Autonomous period starts", command_id=command.id
    )
    diagram = BehaviorDiagram(
        name="Robot Modes", states=[disabled, autonomous], transitions=[transition]
    )
    project = ArchitectureProject(
        name="Robot", commands=[command], behavior_diagrams=[diagram]
    )

    ProjectStore(tmp_path).save(project)
    loaded = ProjectStore(tmp_path).load()

    assert loaded.to_dict() == project.to_dict()
    assert loaded.behavior_diagrams[0].transitions[0].command_id == command.id


def test_behavior_state_defaults_to_plain_state_kind() -> None:
    state = BehaviorState(name=FieldValue(design="Disabled"))

    assert state.kind == "state"


def test_behavior_state_accepts_sysml_pseudostate_kinds() -> None:
    for kind in ("start", "end", "decision", "synchronization"):
        state = BehaviorState(name=FieldValue(design=kind.title()), kind=kind)
        assert state.kind == kind


def test_behavior_state_rejects_unknown_kind() -> None:
    with pytest.raises(ValueError):
        BehaviorState(name=FieldValue(design="Bogus"), kind="not-a-real-kind")


def test_behavior_state_round_trips_kind(tmp_path) -> None:
    start = BehaviorState(name=FieldValue(design="Start"), kind="start")
    disabled = BehaviorState(name=FieldValue(design="Disabled"))
    diagram = BehaviorDiagram(
        name="Robot Modes",
        states=[start, disabled],
        transitions=[BehaviorTransition(start.id, disabled.id, "")],
    )
    project = ArchitectureProject(name="Robot", behavior_diagrams=[diagram])

    ProjectStore(tmp_path).save(project)
    loaded = ProjectStore(tmp_path).load()

    assert loaded.behavior_diagrams[0].states[0].kind == "start"
    assert loaded.behavior_diagrams[0].states[1].kind == "state"


def test_behavior_state_from_dict_defaults_missing_kind_to_state() -> None:
    legacy_id = str(BehaviorState(name=FieldValue(design="Legacy")).id)
    state = BehaviorState.from_dict({"id": legacy_id, "name": {"design": "Legacy"}})

    assert state.kind == "state"


def test_behavior_transition_allows_blank_trigger_label() -> None:
    """Transitions from a start pseudostate or across a sync bar are often unlabeled."""
    disabled = BehaviorState(name=FieldValue(design="Disabled"))
    start = BehaviorState(name=FieldValue(design="Start"), kind="start")
    transition = BehaviorTransition(start.id, disabled.id, "")

    assert transition.trigger_label == ""


def test_behavior_transition_command_id_must_reference_a_project_command() -> None:
    disabled = BehaviorState(name=FieldValue(design="Disabled"))
    autonomous = BehaviorState(name=FieldValue(design="Autonomous"))
    unrelated_command_id = Command(name=FieldValue(design="Other")).id
    diagram = BehaviorDiagram(
        name="Robot Modes",
        states=[disabled, autonomous],
        transitions=[
            BehaviorTransition(disabled.id, autonomous.id, "Go", command_id=unrelated_command_id)
        ],
    )
    with pytest.raises(ValueError):
        ArchitectureProject(name="Robot", behavior_diagrams=[diagram])


def test_old_project_payload_without_behavior_diagrams_loads_with_empty_list(tmp_path) -> None:
    project = ArchitectureProject(name="Legacy Robot")
    legacy_payload = project.to_dict()
    legacy_payload.pop("behaviorDiagrams")

    reloaded = ArchitectureProject.from_dict(legacy_payload)

    assert reloaded.behavior_diagrams == []


def test_behavior_diagram_round_trips_owner_command_id(tmp_path) -> None:
    command = Command(name=FieldValue(design="Autonomous Routine"))
    diagram = BehaviorDiagram(name="Auto Routine", owner_command_id=command.id)
    project = ArchitectureProject(name="Robot", commands=[command], behavior_diagrams=[diagram])

    ProjectStore(tmp_path).save(project)
    loaded = ProjectStore(tmp_path).load()

    assert loaded.behavior_diagrams[0].owner_command_id == command.id


def test_behavior_diagram_owner_command_id_defaults_to_none_for_legacy_payload() -> None:
    diagram = BehaviorDiagram(name="Robot Modes")
    payload = diagram.to_dict()
    payload.pop("ownerCommandId")

    loaded = BehaviorDiagram.from_dict(payload)

    assert loaded.owner_command_id is None


def test_project_rejects_behavior_diagram_owned_by_unknown_command() -> None:
    unrelated_command_id = Command(name=FieldValue(design="Other")).id
    diagram = BehaviorDiagram(name="Auto Routine", owner_command_id=unrelated_command_id)
    with pytest.raises(ValueError):
        ArchitectureProject(name="Robot", behavior_diagrams=[diagram])


def test_old_project_payload_without_owner_command_id_loads_as_root_diagram() -> None:
    diagram = BehaviorDiagram(name="Robot Modes")
    project = ArchitectureProject(name="Robot", behavior_diagrams=[diagram])
    legacy_payload = project.to_dict()
    legacy_payload["behaviorDiagrams"][0].pop("ownerCommandId")

    reloaded = ArchitectureProject.from_dict(legacy_payload)

    assert reloaded.behavior_diagrams[0].owner_command_id is None
