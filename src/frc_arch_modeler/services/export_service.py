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
        command_names = {command.id: command.name.effective or "Unnamed" for command in commands}
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
                lines.extend(
                    self._subsystem_lines(
                        subsystem,
                        [
                            device
                            for device in project.devices
                            if device.owner_subsystem_id == subsystem.id
                        ],
                    )
                )
        else:
            lines.append("_No subsystems defined._")
        lines.extend(["", "## Commands", ""])
        if commands:
            for command in commands:
                lines.extend(
                    self._command_lines(
                        command,
                        subsystem_names,
                        [
                            trigger
                            for trigger in project.triggers
                            if trigger.command_id == command.id
                        ],
                    )
                )
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
        lines.extend(
            [
                "",
                "## Design Relationships",
                "",
                "| Type | Source | Target |",
                "| --- | --- | --- |",
            ]
        )
        if project.relationships:
            names = {**subsystem_names, **command_names}
            names.update(
                {device.id: device.name.effective or "Unnamed" for device in project.devices}
            )
            names.update(
                {
                    trigger.id: trigger.expression.effective or "Unnamed trigger"
                    for trigger in project.triggers
                }
            )
            for relationship in sorted(
                project.relationships,
                key=lambda item: (item.relationship_type, str(item.source_id), str(item.target_id)),
            ):
                lines.append(
                    f"| {relationship.relationship_type} | "
                    f"{names.get(relationship.source_id, 'Unknown')} | "
                    f"{names.get(relationship.target_id, 'Unknown')} |"
                )
        else:
            lines.append("| _None_ | â€” | â€” |")
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
        lines.extend(["", "## Imported Hardware", ""])
        if scan.devices:
            lines.extend(
                [
                    "| Logical owner | Device | Constructor evidence | Source |",
                    "| --- | --- | --- | --- |",
                ]
            )
            for device in sorted(
                scan.devices,
                key=lambda item: (
                    item.owner_symbol.casefold(),
                    item.device_type,
                    item.anchor.start_line,
                ),
            ):
                mode = f" ({device.mode})" if device.mode else ""
                arguments = device.resolved_arguments or device.constructor_arguments
                lines.append(
                    f"| {device.owner_symbol} | {device.device_type}{mode} | `{arguments}` | "
                    f"`{device.anchor.relative_path}:{device.anchor.start_line}` |"
                )
        else:
            lines.append("_None discovered._")
        lines.extend(["", "## Imported Trigger Bindings", ""])
        if scan.triggers:
            lines.extend(
                [
                    "| Trigger | Activation | Command expression | Source |",
                    "| --- | --- | --- | --- |",
                ]
            )
            for trigger in sorted(
                scan.triggers,
                key=lambda item: (
                    item.controller_expression.casefold(),
                    item.activation,
                    item.anchor.relative_path,
                    item.anchor.start_line,
                ),
            ):
                lines.append(
                    f"| {trigger.controller_expression} | {trigger.activation} | "
                    f"`{trigger.command_expression}` | "
                    f"`{trigger.anchor.relative_path}:{trigger.anchor.start_line}` |"
                )
        else:
            lines.append("_None discovered._")
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

    def _subsystem_lines(self, subsystem: Subsystem, devices) -> list:  # type: ignore[no-untyped-def]
        lines = [
            f"### {subsystem.name.effective}",
            "",
            self._description(subsystem),
        ]
        if devices:
            lines.extend(["", "- Devices:"])
            for device in sorted(devices, key=lambda item: (item.name.effective or "").casefold()):
                mode = f" ({device.mode.effective})" if device.mode.effective else ""
                lines.append(
                    f"  - {device.name.effective}: {device.device_type.effective}{mode}"
                )
        lines.append("")
        return lines

    def _command_lines(
        self, command: Command, subsystem_names: dict[object, str], triggers
    ) -> list:  # type: ignore[no-untyped-def]
        requirements = [
            subsystem_names[item] for item in command.requirement_ids if item in subsystem_names
        ]
        lines = [
            f"### {command.name.effective}",
            "",
            self._description(command),
            "",
            f"- Requirements: {', '.join(requirements) or 'None'}",
        ]
        if triggers:
            lines.append("- Triggers:")
            for trigger in sorted(
                triggers, key=lambda item: (item.expression.effective or "").casefold()
            ):
                lines.append(
                    f"  - {trigger.expression.effective or 'Unspecified'} â€” "
                    f"{trigger.activation.effective or 'Unspecified'}"
                )
        lines.append("")
        return lines
