"""Explicit migrations for persisted architecture model schemas."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from frc_arch_modeler.domain.model import SCHEMA_VERSION


def migrate_model_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Upgrade a payload without discarding unknown fields.

    Version 0 predates the explicit ``schemaVersion`` field and is otherwise
    structurally compatible with version 1.
    """
    migrated = deepcopy(payload)
    version = int(migrated.get("schemaVersion", 0))
    if version > SCHEMA_VERSION:
        raise ValueError(f"Model schema {version} is newer than this application.")
    while version < SCHEMA_VERSION:
        if version == 0:
            migrated["schemaVersion"] = 1
            version = 1
        else:
            raise ValueError(f"No migration is available from schema {version}.")
    return migrated
