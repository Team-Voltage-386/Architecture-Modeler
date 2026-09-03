"""One-click starting points for common FRC subsystems.

Templates are plain data — no domain subclasses, no new entity types — describing the
devices a subsystem needs. `instantiate_subsystem_template` expands one into a
`Subsystem` and its `Device`s, proposing the next free address per bus as it goes;
the caller inserts the results into the project through the normal undo commands.
"""

from __future__ import annotations

from dataclasses import dataclass

from frc_arch_modeler.domain.model import ArchitectureProject, Device, FieldValue, Subsystem
from frc_arch_modeler.services.allocation_service import used_addresses


@dataclass(frozen=True, slots=True)
class DeviceTemplate:
    """One device a subsystem template creates, before an owner or address exists."""

    name: str
    device_type: str
    bus: str | None = None


@dataclass(frozen=True, slots=True)
class SubsystemTemplate:
    """A named, editable starting point for a common FRC subsystem."""

    name: str
    description: str
    devices: tuple[DeviceTemplate, ...] = ()


def _swerve_module(prefix: str) -> tuple[DeviceTemplate, ...]:
    return (
        DeviceTemplate(f"{prefix} Drive Motor", "TalonFX", "canivore"),
        DeviceTemplate(f"{prefix} Steer Motor", "TalonFX", "canivore"),
        DeviceTemplate(f"{prefix} Steer Encoder", "CANcoder", "canivore"),
    )


SUBSYSTEM_TEMPLATES: tuple[SubsystemTemplate, ...] = (
    SubsystemTemplate(
        "Swerve Drivetrain",
        "Four swerve modules — drive motor, steer motor, steer encoder each — plus a "
        "gyro for field-relative driving.",
        (
            *_swerve_module("Front Left"),
            *_swerve_module("Front Right"),
            *_swerve_module("Back Left"),
            *_swerve_module("Back Right"),
            DeviceTemplate("Gyro", "Pigeon2", "canivore"),
        ),
    ),
    SubsystemTemplate(
        "Differential Drivetrain",
        "Left and right drive motor pairs plus a gyro for tank-style driving.",
        (
            DeviceTemplate("Left Drive Motor 1", "TalonFX", "canivore"),
            DeviceTemplate("Left Drive Motor 2", "TalonFX", "canivore"),
            DeviceTemplate("Right Drive Motor 1", "TalonFX", "canivore"),
            DeviceTemplate("Right Drive Motor 2", "TalonFX", "canivore"),
            DeviceTemplate("Gyro", "Pigeon2", "canivore"),
        ),
    ),
    SubsystemTemplate(
        "Roller Intake",
        "A single roller motor with a beam-break sensor to detect a held game piece.",
        (
            DeviceTemplate("Intake Motor", "SparkMax", "canivore"),
            DeviceTemplate("Beam Break Sensor", "DigitalInput", "rio-dio"),
        ),
    ),
    SubsystemTemplate(
        "Elevator",
        "A two-motor elevator with a through-bore encoder and a bottom limit switch.",
        (
            DeviceTemplate("Elevator Motor 1", "SparkFlex", "canivore"),
            DeviceTemplate("Elevator Motor 2", "SparkFlex", "canivore"),
            DeviceTemplate("Elevator Encoder", "DutyCycleEncoder", "rio-dio"),
            DeviceTemplate("Bottom Limit Switch", "DigitalInput", "rio-dio"),
        ),
    ),
    SubsystemTemplate(
        "Flywheel Shooter",
        "Top and bottom flywheel motors with a feeder motor to launch game pieces.",
        (
            DeviceTemplate("Top Flywheel Motor", "TalonFX", "canivore"),
            DeviceTemplate("Bottom Flywheel Motor", "TalonFX", "canivore"),
            DeviceTemplate("Feeder Motor", "SparkMax", "canivore"),
        ),
    ),
    SubsystemTemplate(
        "Winch Climber",
        "A single winch motor with a limit switch marking the fully retracted position.",
        (
            DeviceTemplate("Climber Motor", "TalonFX", "canivore"),
            DeviceTemplate("Climber Limit Switch", "DigitalInput", "rio-dio"),
        ),
    ),
    SubsystemTemplate(
        "Vision",
        "A coprocessor-driven camera for AprilTag and target tracking.",
        (DeviceTemplate("Camera", "PhotonCamera"),),
    ),
    SubsystemTemplate(
        "LEDs",
        "An addressable LED strip for driver and human player signaling.",
        (DeviceTemplate("LED Strip", "AddressableLED", "rio-pwm"),),
    ),
)


def instantiate_subsystem_template(
    project: ArchitectureProject, template: SubsystemTemplate, subsystem_name: str | None = None
) -> tuple[Subsystem, list[Device]]:
    """Build the subsystem and devices `template` describes, unattached to `project`.

    Addresses are proposed per bus, skipping both addresses already used in the project
    and ones already proposed earlier in this same batch, so thirteen devices never
    collide with each other or with existing hardware. The caller inserts the results
    into the project (and its own undo entry) — this function never mutates `project`.
    """
    subsystem = Subsystem(name=FieldValue(design=subsystem_name or template.name))
    devices: list[Device] = []
    reserved_by_bus: dict[str, set[int]] = {}
    for device_template in template.devices:
        address: str | None = None
        if device_template.bus:
            reserved = reserved_by_bus.setdefault(
                device_template.bus, used_addresses(project, device_template.bus)
            )
            candidate = 1
            while candidate in reserved:
                candidate += 1
            reserved.add(candidate)
            address = str(candidate)
        devices.append(
            Device(
                name=FieldValue(design=device_template.name),
                device_type=FieldValue(design=device_template.device_type),
                owner_subsystem_id=subsystem.id,
                bus=FieldValue(design=device_template.bus) if device_template.bus else FieldValue(),
                address=FieldValue(design=address) if address is not None else FieldValue(),
            )
        )
    return subsystem, devices
