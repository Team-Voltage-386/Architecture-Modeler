"""Non-destructive reconciliation between authored design and imported code facts."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from frc_arch_modeler.domain.model import ArchitectureProject, Command, ComparisonState, Subsystem
from frc_arch_modeler.importers.base import ScannedSymbol, ScanResult


@dataclass(slots=True)
class ReconciliationResult:
    """Suggested matches; accepting bindings remains an explicit future action."""

    matches: dict[UUID, ScannedSymbol] = field(default_factory=dict)
    statuses: dict[UUID, ComparisonState] = field(default_factory=dict)
    code_only: list[ScannedSymbol] = field(default_factory=list)


class ReconciliationService:
    """Match design elements with code using only deterministic, explainable evidence."""

    def reconcile(self, project: ArchitectureProject, scan: ScanResult) -> ReconciliationResult:
        result = ReconciliationResult()
        unmatched_symbols = {
            symbol.anchor.qualified_symbol: symbol
            for symbol in scan.symbols
            if symbol.kind in {"command", "subsystem"}
        }
        for element in [*project.commands, *project.subsystems]:
            expected_kind = "command" if isinstance(element, Command) else "subsystem"
            candidate = self._match(element, expected_kind, unmatched_symbols.values())
            if candidate is None:
                result.statuses[element.id] = ComparisonState.DESIGN_ONLY
                continue
            result.matches[element.id] = candidate
            result.statuses[element.id] = ComparisonState.MATCHED
            unmatched_symbols.pop(candidate.anchor.qualified_symbol)
        result.code_only = list(unmatched_symbols.values())
        return result

    @staticmethod
    def _match(
        element: Command | Subsystem, expected_kind: str, symbols: object
    ) -> ScannedSymbol | None:
        candidates = [symbol for symbol in symbols if symbol.kind == expected_kind]
        if element.code_binding is not None:
            bound = [
                symbol
                for symbol in candidates
                if symbol.anchor.qualified_symbol == element.code_binding.qualified_symbol
            ]
            if len(bound) == 1:
                return bound[0]
        target_name = ReconciliationService._normalize(element.name.effective or "")
        named = [
            symbol
            for symbol in candidates
            if ReconciliationService._normalize(symbol.name) == target_name
        ]
        return named[0] if len(named) == 1 else None

    @staticmethod
    def _normalize(value: str) -> str:
        return "".join(character for character in value.casefold() if character.isalnum())
