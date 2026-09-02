from frc_arch_modeler.domain.model import ArchitectureProject, Device, FieldValue, Subsystem
from frc_arch_modeler.services.allocation_service import (
    SEVERITY_ERROR,
    SEVERITY_INCOMPLETE,
    SEVERITY_WARNING,
    AllocationService,
    findings_by_device,
    other_device_ids,
)


def _device(subsystem, **overrides):
    fields = {
        "name": FieldValue(design="Device"),
        "device_type": FieldValue(design="TalonFX"),
        "owner_subsystem_id": subsystem.id,
        "bus": FieldValue(design="canivore"),
        "address": FieldValue(design="1"),
    }
    fields.update(overrides)
    return Device(**fields)


def test_no_findings_for_a_clean_project_with_no_conflicts() -> None:
    drive = Subsystem(name=FieldValue(design="Drive"))
    left = _device(drive, name=FieldValue(design="Left Motor"), address=FieldValue(design="1"))
    right = _device(drive, name=FieldValue(design="Right Motor"), address=FieldValue(design="2"))
    project = ArchitectureProject(name="Robot", subsystems=[drive], devices=[left, right])

    findings = AllocationService().check(project)

    assert findings == []


def test_two_devices_sharing_bus_and_can_id_are_flagged_as_a_duplicate_can_id_error() -> None:
    drive = Subsystem(name=FieldValue(design="Drive"))
    left = _device(
        drive,
        name=FieldValue(design="Left Motor"),
        bus=FieldValue(design="canivore"),
        address=FieldValue(design="5"),
    )
    right = _device(
        drive,
        name=FieldValue(design="Right Motor"),
        bus=FieldValue(design="canivore"),
        address=FieldValue(design="5"),
    )
    project = ArchitectureProject(name="Robot", subsystems=[drive], devices=[left, right])

    findings = AllocationService().check(project)

    duplicate = [finding for finding in findings if finding.kind == "duplicate_can_id"]
    assert len(duplicate) == 1
    assert duplicate[0].severity == SEVERITY_ERROR
    assert set(duplicate[0].device_ids) == {left.id, right.id}


def test_two_devices_sharing_a_pdh_breaker_channel_are_flagged_distinctly_from_a_can_id() -> None:
    drive = Subsystem(name=FieldValue(design="Drive"))
    left = _device(
        drive,
        name=FieldValue(design="Left Solenoid"),
        device_type=FieldValue(design="Solenoid"),
        bus=FieldValue(design="pdh"),
        address=FieldValue(design="3"),
    )
    right = _device(
        drive,
        name=FieldValue(design="Right Solenoid"),
        device_type=FieldValue(design="Solenoid"),
        bus=FieldValue(design="pdh"),
        address=FieldValue(design="3"),
    )
    project = ArchitectureProject(name="Robot", subsystems=[drive], devices=[left, right])

    findings = AllocationService().check(project)

    duplicate = [finding for finding in findings if finding.kind == "duplicate_breaker_channel"]
    assert len(duplicate) == 1
    assert duplicate[0].severity == SEVERITY_ERROR
    assert set(duplicate[0].device_ids) == {left.id, right.id}
    assert not any(finding.kind == "duplicate_can_id" for finding in findings)


def test_devices_on_different_buses_with_the_same_address_are_not_flagged_as_duplicates() -> None:
    drive = Subsystem(name=FieldValue(design="Drive"))
    left = _device(drive, bus=FieldValue(design="canivore"), address=FieldValue(design="5"))
    right = _device(drive, bus=FieldValue(design="rio"), address=FieldValue(design="5"))
    project = ArchitectureProject(name="Robot", subsystems=[drive], devices=[left, right])

    findings = AllocationService().check(project)

    assert not any(finding.kind.startswith("duplicate_") for finding in findings)


def test_a_can_motor_controller_with_no_address_is_flagged_as_incomplete_not_an_error() -> None:
    drive = Subsystem(name=FieldValue(design="Drive"))
    motor = _device(
        drive,
        name=FieldValue(design="Left Motor"),
        device_type=FieldValue(design="TalonFX"),
        address=FieldValue(),
    )
    project = ArchitectureProject(name="Robot", subsystems=[drive], devices=[motor])

    findings = AllocationService().check(project)

    assert len(findings) == 1
    assert findings[0].kind == "incomplete_address"
    assert findings[0].severity == SEVERITY_INCOMPLETE
    assert findings[0].device_ids == (motor.id,)


def test_a_solenoid_with_no_address_is_not_flagged_as_incomplete() -> None:
    drive = Subsystem(name=FieldValue(design="Drive"))
    solenoid = _device(
        drive,
        device_type=FieldValue(design="Solenoid"),
        address=FieldValue(),
    )
    project = ArchitectureProject(name="Robot", subsystems=[drive], devices=[solenoid])

    findings = AllocationService().check(project)

    assert findings == []


def test_a_device_whose_owner_subsystem_no_longer_exists_is_a_model_integrity_error() -> None:
    drive = Subsystem(name=FieldValue(design="Drive"))
    device = _device(drive)
    project = ArchitectureProject(name="Robot", subsystems=[drive], devices=[device])
    # Simulate an in-place mutation bug: the subsystem is removed without cascading
    # the device removal, leaving a dangling owner reference that ArchitectureProject's
    # constructor-time validation cannot catch after the fact.
    project.subsystems.remove(drive)

    findings = AllocationService().check(project)

    orphaned = [finding for finding in findings if finding.kind == "orphan_subsystem"]
    assert len(orphaned) == 1
    assert orphaned[0].severity == SEVERITY_ERROR
    assert orphaned[0].device_ids == (device.id,)


def test_summed_breaker_amps_over_the_configured_budget_is_a_warning() -> None:
    drive = Subsystem(name=FieldValue(design="Drive"))
    devices = [
        _device(
            drive,
            name=FieldValue(design=f"Motor {index}"),
            address=FieldValue(design=str(index)),
            breaker_amps=FieldValue(design="30"),
        )
        for index in range(5)
    ]
    project = ArchitectureProject(name="Robot", subsystems=[drive], devices=devices)

    findings = AllocationService(total_breaker_amps=120.0).check(project)

    budget = [finding for finding in findings if finding.kind == "breaker_budget_exceeded"]
    assert len(budget) == 1
    assert budget[0].severity == SEVERITY_WARNING
    assert set(budget[0].device_ids) == {device.id for device in devices}


def test_summed_mass_over_the_configured_budget_is_a_warning() -> None:
    drive = Subsystem(name=FieldValue(design="Drive"))
    devices = [
        _device(
            drive,
            name=FieldValue(design=f"Part {index}"),
            address=FieldValue(design=str(index)),
            mass_kg=FieldValue(design="10"),
        )
        for index in range(6)
    ]
    project = ArchitectureProject(name="Robot", subsystems=[drive], devices=devices)

    findings = AllocationService(total_mass_kg=56.7).check(project)

    budget = [finding for finding in findings if finding.kind == "mass_budget_exceeded"]
    assert len(budget) == 1
    assert budget[0].severity == SEVERITY_WARNING
    assert set(budget[0].device_ids) == {device.id for device in devices}


def test_budgets_within_the_configured_limits_produce_no_findings() -> None:
    drive = Subsystem(name=FieldValue(design="Drive"))
    device = _device(
        drive, breaker_amps=FieldValue(design="30"), mass_kg=FieldValue(design="5")
    )
    project = ArchitectureProject(name="Robot", subsystems=[drive], devices=[device])

    findings = AllocationService(total_breaker_amps=120.0, total_mass_kg=56.7).check(project)

    assert findings == []


def test_unparseable_breaker_and_mass_values_are_ignored_by_the_budget_check() -> None:
    drive = Subsystem(name=FieldValue(design="Drive"))
    device = _device(
        drive, breaker_amps=FieldValue(design="lots"), mass_kg=FieldValue(design="heavy")
    )
    project = ArchitectureProject(name="Robot", subsystems=[drive], devices=[device])

    findings = AllocationService(total_breaker_amps=0.0, total_mass_kg=0.0).check(project)

    assert findings == []


def test_a_project_with_no_devices_produces_no_findings() -> None:
    project = ArchitectureProject(name="Robot")

    assert AllocationService().check(project) == []


def test_findings_by_device_indexes_a_duplicate_finding_under_both_device_ids() -> None:
    drive = Subsystem(name=FieldValue(design="Drive"))
    left = _device(drive, bus=FieldValue(design="canivore"), address=FieldValue(design="5"))
    right = _device(drive, bus=FieldValue(design="canivore"), address=FieldValue(design="5"))
    project = ArchitectureProject(name="Robot", subsystems=[drive], devices=[left, right])

    grouped = findings_by_device(AllocationService().check(project))

    assert set(grouped) == {left.id, right.id}
    assert grouped[left.id] == grouped[right.id]


def test_other_device_ids_returns_the_conflicting_partner_and_excludes_self() -> None:
    drive = Subsystem(name=FieldValue(design="Drive"))
    left = _device(drive, bus=FieldValue(design="canivore"), address=FieldValue(design="5"))
    right = _device(drive, bus=FieldValue(design="canivore"), address=FieldValue(design="5"))
    project = ArchitectureProject(name="Robot", subsystems=[drive], devices=[left, right])
    grouped = findings_by_device(AllocationService().check(project))

    assert other_device_ids(left.id, grouped[left.id]) == [right.id]
    assert other_device_ids(right.id, grouped[right.id]) == [left.id]


def test_other_device_ids_is_empty_for_a_single_device_finding() -> None:
    drive = Subsystem(name=FieldValue(design="Drive"))
    motor = _device(drive, device_type=FieldValue(design="TalonFX"), address=FieldValue())
    project = ArchitectureProject(name="Robot", subsystems=[drive], devices=[motor])
    grouped = findings_by_device(AllocationService().check(project))

    assert other_device_ids(motor.id, grouped[motor.id]) == []
