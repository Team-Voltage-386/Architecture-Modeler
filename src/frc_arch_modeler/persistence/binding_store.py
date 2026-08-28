"""Atomic persistence for accepted design-to-code bindings."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from uuid import UUID

from frc_arch_modeler.domain.model import ArchitectureProject, SourceAnchor
from frc_arch_modeler.persistence.project_store import ProjectStore


class BindingStore:
    """Keep accepted mappings separate from the user-authored model payload."""

    filename = "bindings.json"
    schema_version = 1

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    @property
    def bindings_path(self) -> Path:
        return self.root / ProjectStore.directory_name / self.filename

    def save(self, project: ArchitectureProject) -> Path:
        destination = self.bindings_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        bindings = {
            str(element.id): element.code_binding.to_dict()
            for element in [
                *project.commands,
                *project.subsystems,
                *project.devices,
                *project.triggers,
                *project.relationships,
            ]
            if element.code_binding is not None
        }
        payload = json.dumps(
            {"schemaVersion": self.schema_version, "bindings": bindings},
            indent=2,
            ensure_ascii=False,
        ) + "\n"
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=destination.parent, delete=False
        ) as temporary:
            temporary.write(payload)
            temporary_path = Path(temporary.name)
        try:
            os.replace(temporary_path, destination)
        except BaseException:
            temporary_path.unlink(missing_ok=True)
            raise
        return destination

    def load(self) -> dict[UUID, SourceAnchor]:
        if not self.bindings_path.is_file():
            return {}
        try:
            payload = json.loads(self.bindings_path.read_text(encoding="utf-8"))
            if payload.get("schemaVersion") != self.schema_version:
                raise ValueError("Unsupported bindings schema version.")
            bindings = payload.get("bindings", {})
            if not isinstance(bindings, dict):
                raise ValueError("Bindings must be an object.")
            return {
                UUID(element_id): SourceAnchor.from_dict(anchor)
                for element_id, anchor in bindings.items()
            }
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
            raise ValueError(f"Could not load bindings '{self.bindings_path}': {error}") from error

    def apply(self, project: ArchitectureProject) -> None:
        """Overlay sidecar mappings onto elements that still exist in the model."""
        elements = {
            element.id: element
            for element in [
                *project.commands,
                *project.subsystems,
                *project.devices,
                *project.triggers,
                *project.relationships,
            ]
        }
        for element_id, anchor in self.load().items():
            if element_id in elements:
                elements[element_id].code_binding = anchor
