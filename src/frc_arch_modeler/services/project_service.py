"""Use cases for creating, opening, and saving architecture models."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from frc_arch_modeler.domain.model import (
    ArchitectureProject,
    BehaviorDiagram,
    BehaviorState,
    BehaviorTransition,
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
        """Create an unsaved, design-only project with the standard robot-mode behavior view."""
        project = ArchitectureProject(name=name)
        self.seed_default_behavior_diagram(project)
        return project

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

    def add_behavior_diagram(
        self, project: ArchitectureProject, name: str, owner_command_id: UUID | None = None
    ) -> BehaviorDiagram:
        """Add a separately editable behavioral view, optionally scoped to one command."""
        diagram = BehaviorDiagram(name=name, owner_command_id=owner_command_id)
        project.behavior_diagrams.append(diagram)
        return diagram

    def rename_behavior_diagram(self, diagram: BehaviorDiagram, name: str) -> None:
        """Rename a behavior diagram in place; caller validates the new name."""
        diagram.name = name

    def add_behavior_state(
        self, diagram: BehaviorDiagram, name: str, kind: str = "state"
    ) -> BehaviorState:
        """Add a design-only state (or start/end/decision/synchronization pseudostate)."""
        state = BehaviorState(name=FieldValue(design=name), kind=kind)
        diagram.states.append(state)
        return state

    def add_behavior_transition(
        self,
        diagram: BehaviorDiagram,
        source_state_id: UUID,
        target_state_id: UUID,
        trigger_label: str,
        command_id: UUID | None = None,
    ) -> BehaviorTransition:
        """Add a directed, triggered edge between two states in the same diagram."""
        transition = BehaviorTransition(
            source_state_id, target_state_id, trigger_label, command_id=command_id
        )
        diagram.transitions.append(transition)
        return transition

    def seed_default_behavior_diagram(self, project: ArchitectureProject) -> BehaviorDiagram:
        """Seed the standard FRC match-mode state machine so the behavior view starts populated."""
        diagram = self.add_behavior_diagram(project, "Robot Modes")
        disabled = self.add_behavior_state(diagram, "Disabled")
        autonomous = self.add_behavior_state(diagram, "Autonomous")
        teleop = self.add_behavior_state(diagram, "Teleop")
        test = self.add_behavior_state(diagram, "Test")
        self.add_behavior_transition(
            diagram, disabled.id, autonomous.id, "Autonomous period starts"
        )
        self.add_behavior_transition(diagram, autonomous.id, teleop.id, "Teleop period starts")
        self.add_behavior_transition(diagram, teleop.id, disabled.id, "Match ends")
        self.add_behavior_transition(diagram, disabled.id, test.id, "Test mode enabled")
        self.add_behavior_transition(diagram, test.id, disabled.id, "Test mode disabled")
        return diagram
