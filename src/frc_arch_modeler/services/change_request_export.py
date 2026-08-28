"""Focused Markdown implementation briefs derived from design/code deltas."""

from __future__ import annotations

from pathlib import Path

from frc_arch_modeler.domain.model import ArchitectureProject, Command, ComparisonState, Subsystem
from frc_arch_modeler.importers.base import ScannedSymbol, ScanResult
from frc_arch_modeler.services.reconcile_service import ReconciliationResult


class ChangeRequestExportService:
    """Export a concise, deterministic prompt for an external coding tool."""

    filename = "change-request.md"

    def export(
        self,
        root: Path,
        project: ArchitectureProject,
        scan: ScanResult,
        comparison: ReconciliationResult,
    ) -> Path:
        destination = root / ".frc-architecture" / "exports" / self.filename
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(self.render(project, scan, comparison), encoding="utf-8")
        return destination

    def render(
        self, project: ArchitectureProject, scan: ScanResult, comparison: ReconciliationResult
    ) -> str:
        design_only = [
            element
            for element in [*project.subsystems, *project.commands]
            if comparison.statuses.get(element.id) == ComparisonState.DESIGN_ONLY
        ]
        lines = [
            f"# AI Change Request: {project.name}",
            "",
            "## Objective",
            "",
            "Implement the user-authored architecture elements that are not present "
            "in the current code scan.",
            "",
            "## Robot Project",
            "",
            f"- Project directory: `{scan.project_root.name}`",
            "- Target: Java/WPILib command-based robot code",
            "",
            "## Required Design Changes",
            "",
        ]
        if design_only:
            for element in self._sorted(design_only):
                lines.extend(self._design_element_lines(element, project))
        else:
            lines.append("_No unmatched design elements. Review code-only facts below._")
        lines.extend(["", "## Current Code-Only Facts", ""])
        if comparison.code_only:
            code_only = sorted(
                comparison.code_only, key=lambda item: (item.kind, item.name.casefold())
            )
            for symbol in code_only:
                lines.append(self._symbol_line(symbol))
        else:
            lines.append("_None._")
        lines.extend(["", "## Constraints", ""])
        lines.extend(
            [
                "- Follow existing WPILib command-based conventions and project package structure.",
                "- Preserve existing IO abstraction and simulation/replay patterns when present.",
                "- Do not modify `.frc-architecture/` generated exports or "
                "user-authored model files.",
                "- Inspect source anchors before changing related code; do not infer "
                "unresolved behavior.",
                "",
                "## Acceptance Criteria",
                "",
            ]
        )
        if design_only:
            for element in self._sorted(design_only):
                name = element.name.effective
                lines.append(f"- `{name}` is represented by a matching architecture symbol.")
        else:
            lines.append("- Refreshing the architecture scan yields no unmatched design elements.")
        lines.extend(
            [
                "- Command requirements match the requested subsystem relationships.",
                "- The Gradle project validation commands complete successfully.",
                "",
                "## Suggested Validation",
                "",
                "```powershell",
                ".\\gradlew.bat test",
                ".\\gradlew.bat build",
                "```",
                "",
            ]
        )
        return "\n".join(lines)

    @staticmethod
    def _sorted(elements: list[Command | Subsystem]) -> list[Command | Subsystem]:
        return sorted(
            elements, key=lambda item: ((item.name.effective or "").casefold(), str(item.id))
        )

    def _design_element_lines(
        self, element: Command | Subsystem, project: ArchitectureProject
    ) -> list[str]:
        kind = "Subsystem" if isinstance(element, Subsystem) else "Command"
        lines = [f"### {kind}: {element.name.effective}", ""]
        lines.append(element.description.effective or "_No design description provided._")
        if isinstance(element, Command):
            names = {subsystem.id: subsystem.name.effective for subsystem in project.subsystems}
            requirements = [names[item] for item in element.requirement_ids if item in names]
            lines.append(f"- Requirements: {', '.join(requirements) or 'None specified'}")
        lines.append("")
        return lines

    @staticmethod
    def _symbol_line(symbol: ScannedSymbol) -> str:
        return (
            f"- {symbol.kind.replace('_', ' ')} `{symbol.name}` "
            f"at `{symbol.anchor.relative_path}:{symbol.anchor.start_line}`"
        )
