"""Explicit migrations for persisted architecture model schemas."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from frc_arch_modeler.domain.model import SCHEMA_VERSION

#: Device fields introduced by schema 2, stored as empty ``FieldValue`` payloads so a
#: migrated model is shaped exactly like a freshly authored one.
_DEVICE_FIELDS_ADDED_IN_2 = ("bus", "address", "breakerAmps", "massKg", "notes")


def _empty_field_value() -> dict[str, Any]:
    return {"design": None, "scanned": None, "evidence": None, "confidence": None}


def migrate_model_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Upgrade a payload without discarding unknown fields.

    Version 0 predates the explicit ``schemaVersion`` field and is otherwise
    structurally compatible with version 1. Version 2 adds the layered wiring and
    budget fields to every device.
    """
    migrated = deepcopy(payload)
    version = int(migrated.get("schemaVersion", 0))
    if version > SCHEMA_VERSION:
        raise ValueError(f"Model schema {version} is newer than this application.")
    while version < SCHEMA_VERSION:
        if version == 0:
            migrated["schemaVersion"] = 1
            version = 1
        elif version == 1:
            _migrate_1_to_2(migrated)
            version = 2
        else:
            raise ValueError(f"No migration is available from schema {version}.")
    return migrated


def _migrate_1_to_2(migrated: dict[str, Any]) -> None:
    """Give every stored device empty bus, address, breaker, mass, and notes fields."""
    devices = migrated.get("devices")
    if isinstance(devices, list):
        for device in devices:
            if not isinstance(device, dict):
                continue
            for key in _DEVICE_FIELDS_ADDED_IN_2:
                device.setdefault(key, _empty_field_value())
    migrated["schemaVersion"] = 2
