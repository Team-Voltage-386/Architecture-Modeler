from frc_arch_modeler.domain.model import ArchitectureProject, Device, FieldValue, Subsystem
from frc_arch_modeler.services.allocation_service import AllocationService
from frc_arch_modeler.services.template_service import (
    SUBSYSTEM_TEMPLATES,
    DeviceTemplate,
    SubsystemTemplate,
    instantiate_subsystem_template,
)


def _template_by_name(name: str) -> SubsystemTemplate:
    return next(template for template in SUBSYSTEM_TEMPLATES if template.name == name)


def test_every_subsystem_template_has_a_name_description_and_at_least_one_device() -> None:
    for template in SUBSYSTEM_TEMPLATES:
        assert template.name.strip()
        assert template.description.strip()
        assert template.devices
        for device in template.devices:
            assert device.name.strip()
            assert device.device_type.strip()


def test_swerve_drivetrain_template_has_thirteen_devices() -> None:
    template = _template_by_name("Swerve Drivetrain")

    assert len(template.devices) == 13


def test_instantiating_a_template_creates_a_subsystem_owning_every_device() -> None:
    project = ArchitectureProject(name="Robot")
    template = _template_by_name("Swerve Drivetrain")

    subsystem, devices = instantiate_subsystem_template(project, template)

    assert subsystem.name.effective == "Swerve Drivetrain"
    assert len(devices) == 13
    assert all(device.owner_subsystem_id == subsystem.id for device in devices)


def test_instantiating_a_template_uses_the_given_subsystem_name_not_the_template_name() -> None:
    project = ArchitectureProject(name="Robot")
    template = _template_by_name("Roller Intake")

    subsystem, _devices = instantiate_subsystem_template(project, template, "Coral Intake")

    assert subsystem.name.effective == "Coral Intake"


def test_instantiating_a_template_never_mutates_the_project() -> None:
    project = ArchitectureProject(name="Robot")
    template = _template_by_name("Vision")

    instantiate_subsystem_template(project, template)

    assert project.subsystems == []
    assert project.devices == []


def test_a_freshly_instantiated_swerve_template_produces_no_allocation_findings() -> None:
    project = ArchitectureProject(name="Robot")
    template = _template_by_name("Swerve Drivetrain")

    subsystem, devices = instantiate_subsystem_template(project, template)
    project = ArchitectureProject(name="Robot", subsystems=[subsystem], devices=devices)

    findings = AllocationService().check(project)

    assert findings == []


def test_instantiating_a_template_proposes_addresses_that_skip_existing_gaps() -> None:
    drive = Subsystem(name=FieldValue(design="Existing Drive"))
    existing = Device(
        name=FieldValue(design="Existing Motor"),
        device_type=FieldValue(design="TalonFX"),
        owner_subsystem_id=drive.id,
        bus=FieldValue(design="canivore"),
        address=FieldValue(design="1"),
    )
    project = ArchitectureProject(name="Robot", subsystems=[drive], devices=[existing])
    template = SubsystemTemplate(
        "Two Motors",
        "Two CAN motors for the address-gap test.",
        (
            DeviceTemplate("Motor A", "TalonFX", "canivore"),
            DeviceTemplate("Motor B", "TalonFX", "canivore"),
        ),
    )

    _subsystem, devices = instantiate_subsystem_template(project, template)

    assert [device.address.effective for device in devices] == ["2", "3"]


def test_instantiating_a_template_assigns_addresses_independently_per_bus() -> None:
    project = ArchitectureProject(name="Robot")
    template = SubsystemTemplate(
        "Mixed Bus",
        "One CAN device and one DIO device for the per-bus test.",
        (
            DeviceTemplate("CAN Motor", "TalonFX", "canivore"),
            DeviceTemplate("DIO Sensor", "DigitalInput", "rio-dio"),
        ),
    )

    _subsystem, devices = instantiate_subsystem_template(project, template)

    addresses = {device.name.effective: device.address.effective for device in devices}
    assert addresses == {"CAN Motor": "1", "DIO Sensor": "1"}


def test_a_device_template_with_no_bus_gets_no_proposed_address() -> None:
    project = ArchitectureProject(name="Robot")
    template = _template_by_name("Vision")

    _subsystem, devices = instantiate_subsystem_template(project, template)

    assert all(device.bus.effective is None for device in devices)
    assert all(device.address.effective is None for device in devices)
