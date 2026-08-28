"""Use cases for creating, opening, and saving architecture models."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from frc_arch_modeler.domain.model import (
    ArchitectureProject,
    Command,
    Device,
    FieldValue,
    Relationship,
    Subsystem,
    TriggerBinding,
)
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

    def add_device(
        self,
        project: ArchitectureProject,
        owner_subsystem_id: UUID,
        name: str,
        device_type: str,
        mode: str | None = None,
    ) -> Device:
        """Add portable, user-authored hardware to its logical subsystem."""
        device = Device(
            name=FieldValue(design=name),
            device_type=FieldValue(design=device_type),
            owner_subsystem_id=owner_subsystem_id,
            mode=FieldValue(design=mode) if mode else FieldValue(),
        )
        project.devices.append(device)
        return device

    def add_trigger(
        self,
        project: ArchitectureProject,
        command_id: UUID,
        expression: str,
        activation: str,
    ) -> TriggerBinding:
        """Add a user-authored controller binding to a command."""
        trigger = TriggerBinding(
            expression=FieldValue(design=expression),
            activation=FieldValue(design=activation),
            command_id=command_id,
        )
        project.triggers.append(trigger)
        return trigger

    def add_relationship(
        self, project: ArchitectureProject, relationship_type: str, source_id: UUID, target_id: UUID
    ) -> Relationship:
        """Add an explicit, non-code-derived architecture relationship."""
        relationship = Relationship(relationship_type, source_id, target_id)
        project.relationships.append(relationship)
        return relationship
