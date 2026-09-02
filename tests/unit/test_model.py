import json

import pytest

from frc_arch_modeler.domain.model import (
    SCHEMA_VERSION,
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

    assert migrated["schemaVersion"] == SCHEMA_VERSION
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


def _version_one_model_payload() -> dict:
    """A realistic model.json as it was written before devices gained wiring fields."""
    return {
        "schemaVersion": 1,
        "id": "11111111-1111-4111-8111-111111111111",
        "name": "Competition Robot",
        "commands": [
            {
                "id": "22222222-2222-4222-8222-222222222222",
                "name": {
                    "design": "Teleop Drive",
                    "scanned": "TeleopDrive",
                    "evidence": None,
                    "confidence": "high",
                },
                "description": {
                    "design": "Joystick control during teleop.",
                    "scanned": None,
                    "evidence": None,
                    "confidence": None,
                },
                "codeBinding": None,
                "requirementIds": ["33333333-3333-4333-8333-333333333333"],
            }
        ],
        "subsystems": [
            {
                "id": "33333333-3333-4333-8333-333333333333",
                "name": {
                    "design": "Drive",
                    "scanned": "Drive",
                    "evidence": None,
                    "confidence": "high",
                },
                "description": {
                    "design": None,
                    "scanned": None,
                    "evidence": None,
                    "confidence": None,
                },
                "codeBinding": {
                    "relativePath": "src/main/java/frc/robot/subsystems/Drive.java",
                    "qualifiedSymbol": "frc.robot.subsystems.Drive",
                    "signature": None,
                    "startLine": 18,
                    "endLine": 96,
                    "sourceHash": "abc123",
                },
            }
        ],
        "devices": [
            {
                "id": "44444444-4444-4444-8444-444444444444",
                "name": {
                    "design": "Left front drive",
                    "scanned": None,
                    "evidence": None,
                    "confidence": None,
                },
                "deviceType": {
                    "design": "SparkMax",
                    "scanned": "SparkMax",
                    "evidence": None,
                    "confidence": "high",
                },
                "ownerSubsystemId": "33333333-3333-4333-8333-333333333333",
                "mode": {
                    "design": "REAL",
                    "scanned": None,
                    "evidence": None,
                    "confidence": None,
                },
                "codeBinding": None,
            }
        ],
        "triggers": [],
        "relationships": [],
        "behaviorDiagrams": [],
        "teamConventions": {"namingGuide": "subsystem-first"},
    }


def test_migration_gives_a_version_one_device_empty_wiring_and_budget_fields() -> None:
    migrated = migrate_model_payload(_version_one_model_payload())

    device = migrated["devices"][0]
    assert migrated["schemaVersion"] == SCHEMA_VERSION
    assert device["mode"]["design"] == "REAL"
    for key in ("bus", "address", "breakerAmps", "massKg", "notes"):
        assert device[key] == {
            "design": None,
            "scanned": None,
            "evidence": None,
            "confidence": None,
        }
    assert migrated["teamConventions"] == {"namingGuide": "subsystem-first"}


def test_a_version_one_model_on_disk_opens_and_resaves_at_the_new_version(tmp_path) -> None:
    model_path = tmp_path / ".frc-architecture" / "model.json"
    model_path.parent.mkdir(parents=True)
    model_path.write_text(json.dumps(_version_one_model_payload(), indent=2), encoding="utf-8")

    loaded = ProjectStore(tmp_path).load()

    device = loaded.devices[0]
    assert loaded.schema_version == SCHEMA_VERSION
    assert device.mode.effective == "REAL"
    assert device.bus.effective is None
    assert device.address.effective is None
    assert device.breaker_amps.effective is None
    assert device.mass_kg.effective is None
    assert device.notes.effective is None
    assert loaded.unknown_fields == {"teamConventions": {"namingGuide": "subsystem-first"}}

    device.bus.design = "canivore"
    device.address.design = "5"
    ProjectStore(tmp_path).save(loaded)
    reopened = ProjectStore(tmp_path).load()

    assert json.loads(model_path.read_text(encoding="utf-8"))["schemaVersion"] == SCHEMA_VERSION
    assert reopened.to_dict() == loaded.to_dict()
    assert reopened.devices[0].bus.effective == "canivore"
    assert reopened.devices[0].address.effective == "5"
    assert reopened.commands[0].description.effective == "Joystick control during teleop."


def test_device_round_trip_preserves_the_wiring_and_budget_fields(tmp_path) -> None:
    drive = Subsystem(name=FieldValue(design="Drive"))
    device = Device(
        name=FieldValue(design="Left front drive"),
        device_type=FieldValue(design="SparkMax"),
        owner_subsystem_id=drive.id,
        mode=FieldValue(design="REAL"),
        bus=FieldValue(design="canivore"),
        address=FieldValue(design="5"),
        breaker_amps=FieldValue(design="40"),
        mass_kg=FieldValue(design="0.94"),
        notes=FieldValue(design="Shares a breaker with the rear motor."),
    )
    project = ArchitectureProject(name="Robot", subsystems=[drive], devices=[device])

    ProjectStore(tmp_path).save(project)
    reopened = ProjectStore(tmp_path).load()

    assert reopened.to_dict() == project.to_dict()
    assert reopened.devices[0].breaker_amps.effective == "40"
    assert reopened.devices[0].notes.effective == "Shares a breaker with the rear motor."
