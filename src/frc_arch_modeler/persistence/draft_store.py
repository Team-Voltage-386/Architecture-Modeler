"""Recoverable autosave storage kept separate from an explicit model save."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from frc_arch_modeler.domain.model import ArchitectureProject
from frc_arch_modeler.persistence.migrations import migrate_model_payload
from frc_arch_modeler.persistence.project_store import ProjectStore


class DraftStore:
    """Atomically maintain a disposable unsaved draft beside the model sidecar."""

    filename = "draft.json"

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    @property
    def draft_path(self) -> Path:
        return self.root / ProjectStore.directory_name / self.filename

    def save(self, project: ArchitectureProject) -> Path:
        destination = self.draft_path
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

    def load(self) -> ArchitectureProject | None:
        if not self.draft_path.is_file():
            return None
        with self.draft_path.open(encoding="utf-8") as draft_file:
            return ArchitectureProject.from_dict(migrate_model_payload(json.load(draft_file)))

    def discard(self) -> None:
        """Remove only the recoverable draft after an explicit model save/discard."""
        self.draft_path.unlink(missing_ok=True)
