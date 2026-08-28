"""Atomic storage for the user-authored model file."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from frc_arch_modeler.domain.model import ArchitectureProject
from frc_arch_modeler.persistence.migrations import migrate_model_payload


class ProjectStore:
    """Read and atomically replace ``.frc-architecture/model.json``."""

    directory_name = ".frc-architecture"
    model_filename = "model.json"

    def __init__(self, root: Path) -> None:
        self.root = root

    @property
    def model_path(self) -> Path:
        return self.root / self.directory_name / self.model_filename

    def save(self, project: ArchitectureProject) -> Path:
        """Write a complete model through a sibling temporary file then replace it."""
        destination = self.model_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(project.to_dict(), indent=2, ensure_ascii=False) + "\n"
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

    def load(self) -> ArchitectureProject:
        """Load and validate a saved model."""
        with self.model_path.open(encoding="utf-8") as model_file:
            return ArchitectureProject.from_dict(migrate_model_payload(json.load(model_file)))
