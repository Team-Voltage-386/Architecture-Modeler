"""Use cases for creating, opening, and saving architecture models."""

from __future__ import annotations

from pathlib import Path

from frc_arch_modeler.domain.model import ArchitectureProject, Command, FieldValue, Subsystem
from frc_arch_modeler.persistence.binding_store import BindingStore
from frc_arch_modeler.persistence.project_store import ProjectStore


class ProjectService:
    """Keep model lifecycle behavior independent of the Qt user interface."""

    def create(self, name: str) -> ArchitectureProject:
        """Create an unsaved, design-only project."""
        return ArchitectureProject(name=name)

    def open(self, root: Path) -> ArchitectureProject:
        """Open an existing sidecar model from its selected root."""
        project = ProjectStore(root).load()
        BindingStore(root).apply(project)
        return project

    def save(self, root: Path, project: ArchitectureProject) -> Path:
        """Persist a project in the standard sidecar directory."""
        destination = ProjectStore(root).save(project)
        BindingStore(root).save(project)
        return destination

    def add_command(self, project: ArchitectureProject, name: str) -> Command:
        """Add a design-only command to an existing model."""
        command = Command(name=FieldValue(design=name))
        project.commands.append(command)
        return command

    def add_subsystem(self, project: ArchitectureProject, name: str) -> Subsystem:
        """Add a design-only subsystem to an existing model."""
        subsystem = Subsystem(name=FieldValue(design=name))
        project.subsystems.append(subsystem)
        return subsystem
