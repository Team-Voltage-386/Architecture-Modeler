"""Deterministic human-readable exports of architecture design intent."""

from __future__ import annotations

from pathlib import Path

from frc_arch_modeler.domain.model import ArchitectureProject, Command, Subsystem
from frc_arch_modeler.importers.base import ScanResult
from frc_arch_modeler.services.reconcile_service import ReconciliationResult


class ArchitectureExportService:
    """Generate the design-only Architecture Markdown artifact."""

    export_directory = "exports"
    architecture_filename = "architecture.md"

    def export(
        self,
        root: Path,
        project: ArchitectureProject,
        scan: ScanResult | None = None,
        comparison: ReconciliationResult | None = None,
    ) -> Path:
        destination = (
            root / ".frc-architecture" / self.export_directory / self.architecture_filename
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(self.render(project, scan, comparison), encoding="utf-8")
        return destination

    def render(
        self,
        project: ArchitectureProject,
        scan: ScanResult | None = None,
        comparison: ReconciliationResult | None = None,
    ) -> str:
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
            (
                "- Status: current code scan included"
                if scan
                else "- Status: design-only (code has not been imported)"
            ),
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
        if scan is not None:
            lines.extend(self._scan_lines(project, scan, comparison))
        return "\n".join(lines) + "\n"

    def _scan_lines(
        self,
        project: ArchitectureProject,
        scan: ScanResult,
        comparison: ReconciliationResult | None,
    ) -> list[str]:
        factory_count = len(scan.symbols_of_kind("command_factory"))
        composition_count = len(scan.symbols_of_kind("command_composition"))
        lines = [
            "",
            "## Imported Code Summary",
            "",
            f"- Files scanned: {scan.files_scanned}",
            f"- Imported subsystems: {len(scan.symbols_of_kind('subsystem'))}",
            f"- Imported commands: {len(scan.symbols_of_kind('command'))}",
            f"- Command factories/forms: {factory_count + composition_count}",
            f"- Diagnostics: {len(scan.diagnostics)}",
            "",
            "## Design / Code Discrepancies",
            "",
            "| Design element | Kind | Status | Code evidence |",
            "| --- | --- | --- | --- |",
        ]
        if comparison is None:
            lines.append("| _Comparison has not been run_ | — | unresolved | — |")
        else:
            for element in self._sorted([*project.subsystems, *project.commands]):
                symbol = comparison.matches.get(element.id)
                evidence = (
                    f"`{symbol.anchor.relative_path}:{symbol.anchor.start_line}`"
                    if symbol is not None
                    else "—"
                )
                kind = "Subsystem" if isinstance(element, Subsystem) else "Command"
                lines.append(
                    f"| {element.name.effective} | {kind} | "
                    f"{comparison.statuses.get(element.id, 'unresolved')} | {evidence} |"
                )
            for symbol in sorted(comparison.code_only, key=lambda item: (item.kind, item.name)):
                lines.append(
                    f"| {symbol.name} | {symbol.kind.replace('_', ' ')} | code_only | "
                    f"`{symbol.anchor.relative_path}:{symbol.anchor.start_line}` |"
                )
        lines.extend(["", "## Parser Diagnostics", ""])
        if scan.diagnostics:
            for diagnostic in scan.diagnostics:
                location = diagnostic.relative_path or "project"
                lines.append(f"- {diagnostic.severity}: {diagnostic.message} ({location})")
        else:
            lines.append("_None._")
        return lines

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
