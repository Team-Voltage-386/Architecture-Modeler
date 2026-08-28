"""Deterministic human-readable exports of architecture design intent."""

from __future__ import annotations

from pathlib import Path

from frc_arch_modeler.domain.model import ArchitectureProject, Command, Subsystem


class ArchitectureExportService:
    """Generate the design-only Architecture Markdown artifact."""

    export_directory = "exports"
    architecture_filename = "architecture.md"

    def export(self, root: Path, project: ArchitectureProject) -> Path:
        destination = (
            root / ".frc-architecture" / self.export_directory / self.architecture_filename
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(self.render(project), encoding="utf-8")
        return destination

    def render(self, project: ArchitectureProject) -> str:
        """Render stable Markdown independent of canvas presentation state."""
        subsystems = self._sorted(project.subsystems)
        commands = self._sorted(project.commands)
        subsystem_names = {
            subsystem.id: subsystem.name.effective or "Unnamed" for subsystem in subsystems
        }
        lines = [
            f"# Architecture: {project.name}",
            "",
            "Generated from the user-authored design model. No robot source code was modified.",
            "",
            "## Overview",
            "",
            f"- Subsystems: {len(subsystems)}",
            f"- Commands: {len(commands)}",
            "- Status: design-only (code has not been imported)",
            "",
            "## Subsystems",
            "",
        ]
        if subsystems:
            for subsystem in subsystems:
                lines.extend(self._subsystem_lines(subsystem))
        else:
            lines.append("_No subsystems defined._")
        lines.extend(["", "## Commands", ""])
        if commands:
            for command in commands:
                lines.extend(self._command_lines(command, subsystem_names))
        else:
            lines.append("_No commands defined._")
        lines.extend(
            ["", "## Relationship Matrix", "", "| Command | Requires subsystem |", "| --- | --- |"]
        )
        if commands:
            for command in commands:
                requirements = [
                    subsystem_names[item]
                    for item in command.requirement_ids
                    if item in subsystem_names
                ]
                command_name = command.name.effective or "Unnamed"
                requirement_text = ", ".join(requirements) or "None"
                lines.append(f"| {command_name} | {requirement_text} |")
        else:
            lines.append("| _No commands_ | None |")
        return "\n".join(lines) + "\n"

    @staticmethod
    def _sorted(elements: list[Command] | list[Subsystem]) -> list[Command] | list[Subsystem]:
        return sorted(
            elements, key=lambda item: ((item.name.effective or "").casefold(), str(item.id))
        )

    @staticmethod
    def _description(element: Command | Subsystem) -> str:
        return element.description.effective or "_Not specified._"

    def _subsystem_lines(self, subsystem: Subsystem) -> list[str]:
        return [
            f"### {subsystem.name.effective}",
            "",
            self._description(subsystem),
            "",
        ]

    def _command_lines(self, command: Command, subsystem_names: dict[object, str]) -> list[str]:
        requirements = [
            subsystem_names[item] for item in command.requirement_ids if item in subsystem_names
        ]
        return [
            f"### {command.name.effective}",
            "",
            self._description(command),
            "",
            f"- Requirements: {', '.join(requirements) or 'None'}",
            "",
        ]
