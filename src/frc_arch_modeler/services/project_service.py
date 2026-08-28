"""Use cases for creating, opening, and saving architecture models."""

from __future__ import annotations

from pathlib import Path

from frc_arch_modeler.domain.model import ArchitectureProject
from frc_arch_modeler.persistence.project_store import ProjectStore


class ProjectService:
    """Keep model lifecycle behavior independent of the Qt user interface."""

    def create(self, name: str) -> ArchitectureProject:
        """Create an unsaved, design-only project."""
        return ArchitectureProject(name=name)

    def open(self, root: Path) -> ArchitectureProject:
        """Open an existing sidecar model from its selected root."""
        return ProjectStore(root).load()

    def save(self, root: Path, project: ArchitectureProject) -> Path:
        """Persist a project in the standard sidecar directory."""
        return ProjectStore(root).save(project)
