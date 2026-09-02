"""Pure detection of hardware allocation problems across a project's devices.

No Qt import: findings drive both the Hardware table and canvas `DeviceBlock` badges
today, and are shaped to be reusable by the Model Health panel later.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from uuid import UUID

from frc_arch_modeler.domain.model import ArchitectureProject, Device

SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"
SEVERITY_INCOMPLETE = "incomplete"

#: Main breaker rating in amps for a standard FRC PDP/PDH. The FRC Robot Construction
#: Rules that set this change from season to season, so it is a constructor default,
#: not a hard-coded constant — override it when a season's rules differ.
DEFAULT_TOTAL_BREAKER_AMPS = 120.0

#: Maximum robot weight in kg (125 lb) under the FRC Robot Construction Rules. This
#: changes from season to season, so it is a constructor default, not a hard-coded
#: constant — override it when a season's rules differ.
DEFAULT_TOTAL_MASS_KG = 56.7

_MOTOR_CONTROLLER_KEYWORDS = (
    "sparkmax",
    "sparkflex",
    "talonfx",
    "talonsrx",
    "victorspx",
    "cansparkmax",
    "cansparkflex",
    "motorcontroller",
)
_ENCODER_KEYWORDS = ("encoder", "cancoder")
_IMU_KEYWORDS = ("imu", "pigeon", "ahrs", "gyro")
_NEEDS_ADDRESS_KEYWORDS = _MOTOR_CONTROLLER_KEYWORDS + _ENCODER_KEYWORDS + _IMU_KEYWORDS

_POWER_BUS_NAMES = {"pdh", "pdp"}
_CAN_BUS_NAMES = {"rio", "canivore"}


@dataclass(frozen=True, slots=True)
class AllocationFinding:
    """One hardware allocation problem, independent of any presentation layer."""

    kind: str
    severity: str
    message: str
    device_ids: tuple[UUID, ...]


class AllocationService:
    """Detects hardware allocation errors that cost FRC teams matches."""

    def __init__(
        self,
        total_breaker_amps: float = DEFAULT_TOTAL_BREAKER_AMPS,
        total_mass_kg: float = DEFAULT_TOTAL_MASS_KG,
    ) -> None:
        self.total_breaker_amps = total_breaker_amps
        self.total_mass_kg = total_mass_kg

    def check(self, project: ArchitectureProject) -> list[AllocationFinding]:
        findings: list[AllocationFinding] = []
        findings.extend(self._duplicate_address_findings(project.devices))
        findings.extend(self._incomplete_address_findings(project.devices))
        findings.extend(self._orphan_owner_findings(project))
        findings.extend(self._budget_findings(project.devices))
        return findings

    @staticmethod
    def _duplicate_address_findings(devices: list[Device]) -> list[AllocationFinding]:
        groups: dict[tuple[str, str], list[Device]] = defaultdict(list)
        for device in devices:
            bus = (device.bus.effective or "").strip()
            address = (device.address.effective or "").strip()
            if not bus or not address:
                continue
            groups[(_normalize(bus), address)].append(device)

        findings: list[AllocationFinding] = []
        for (normalized_bus, address), group in groups.items():
            if len(group) < 2:
                continue
            device_ids = tuple(device.id for device in group)
            names = ", ".join(device.name.effective or "Unnamed" for device in group)
            bus_label = group[0].bus.effective or normalized_bus
            if normalized_bus in _POWER_BUS_NAMES:
                kind = "duplicate_breaker_channel"
                message = (
                    f"{names} share breaker channel {address} on {bus_label} — a shared "
                    "breaker can't isolate either device's current draw."
                )
            elif normalized_bus in _CAN_BUS_NAMES:
                kind = "duplicate_can_id"
                message = (
                    f"{names} share CAN ID {address} on {bus_label} — a duplicate CAN ID "
                    "stops the robot moving on the field."
                )
            else:
                kind = "duplicate_channel"
                message = f"{names} share address {address} on {bus_label}."
            findings.append(AllocationFinding(kind, SEVERITY_ERROR, message, device_ids))
        return findings

    @staticmethod
    def _incomplete_address_findings(devices: list[Device]) -> list[AllocationFinding]:
        findings: list[AllocationFinding] = []
        for device in devices:
            if (device.address.effective or "").strip():
                continue
            normalized_type = _normalize(device.device_type.effective or "")
            if not any(keyword in normalized_type for keyword in _NEEDS_ADDRESS_KEYWORDS):
                continue
            name = device.name.effective or "Unnamed"
            device_type = device.device_type.effective
            findings.append(
                AllocationFinding(
                    "incomplete_address",
                    SEVERITY_INCOMPLETE,
                    f"{name} is a {device_type} with no bus address set.",
                    (device.id,),
                )
            )
        return findings

    @staticmethod
    def _orphan_owner_findings(project: ArchitectureProject) -> list[AllocationFinding]:
        subsystem_ids = {subsystem.id for subsystem in project.subsystems}
        findings: list[AllocationFinding] = []
        for device in project.devices:
            if device.owner_subsystem_id in subsystem_ids:
                continue
            name = device.name.effective or "Unnamed"
            findings.append(
                AllocationFinding(
                    "orphan_subsystem",
                    SEVERITY_ERROR,
                    f"{name} is owned by a subsystem that no longer exists in the model.",
                    (device.id,),
                )
            )
        return findings

    def _budget_findings(self, devices: list[Device]) -> list[AllocationFinding]:
        findings: list[AllocationFinding] = []

        amp_total = 0.0
        amp_ids: list[UUID] = []
        mass_total = 0.0
        mass_ids: list[UUID] = []
        for device in devices:
            amps = _parse_number(device.breaker_amps.effective)
            if amps is not None:
                amp_total += amps
                amp_ids.append(device.id)
            mass = _parse_number(device.mass_kg.effective)
            if mass is not None:
                mass_total += mass
                mass_ids.append(device.id)

        if amp_ids and amp_total > self.total_breaker_amps:
            findings.append(
                AllocationFinding(
                    "breaker_budget_exceeded",
                    SEVERITY_WARNING,
                    f"Summed breaker ratings are {amp_total:g} A, over the "
                    f"{self.total_breaker_amps:g} A budget.",
                    tuple(amp_ids),
                )
            )
        if mass_ids and mass_total > self.total_mass_kg:
            findings.append(
                AllocationFinding(
                    "mass_budget_exceeded",
                    SEVERITY_WARNING,
                    f"Summed device mass is {mass_total:g} kg, over the "
                    f"{self.total_mass_kg:g} kg budget.",
                    tuple(mass_ids),
                )
            )
        return findings


def _normalize(value: str) -> str:
    return "".join(character for character in value.casefold() if character.isalnum())


def _parse_number(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def findings_by_device(
    findings: Iterable[AllocationFinding],
) -> dict[UUID, list[AllocationFinding]]:
    """Group findings by every device id they involve, for per-row/per-block badges."""
    grouped: dict[UUID, list[AllocationFinding]] = defaultdict(list)
    for finding in findings:
        for device_id in finding.device_ids:
            grouped[device_id].append(finding)
    return dict(grouped)


def other_device_ids(device_id: UUID, findings: Iterable[AllocationFinding]) -> list[UUID]:
    """The other devices named alongside ``device_id`` in these findings, in order.

    Used to jump from a device's alert badge straight to the device it conflicts with.
    """
    seen: set[UUID] = set()
    others: list[UUID] = []
    for finding in findings:
        for other_id in finding.device_ids:
            if other_id != device_id and other_id not in seen:
                seen.add(other_id)
                others.append(other_id)
    return others
