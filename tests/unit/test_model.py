from frc_arch_modeler.domain.model import (
    ArchitectureProject,
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
