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
            result.statuses[element.id] = self._status_for(element, candidate, project, scan)
            unmatched_symbols.pop(candidate.anchor.qualified_symbol)
        result.code_only = list(unmatched_symbols.values())
        return result

    @staticmethod
    def _status_for(
        element: Command | Subsystem,
        symbol: ScannedSymbol,
        project: ArchitectureProject,
        scan: ScanResult,
    ) -> ComparisonState:
        """Roll directly comparable extracted facts up into an element status."""
        if element.name.design is not None and (
            ReconciliationService._normalize(element.name.design)
            != ReconciliationService._normalize(symbol.name)
        ):
            return ComparisonState.MODIFIED
        if isinstance(element, Command):
            if not ReconciliationService._requirements_match(element, project, symbol, scan):
                return ComparisonState.MODIFIED
            if not ReconciliationService._triggers_match(element, project, symbol, scan):
                return ComparisonState.MODIFIED
        elif not ReconciliationService._devices_match(element, project, symbol, scan):
            return ComparisonState.MODIFIED
        return ComparisonState.MATCHED

    @staticmethod
    def _requirements_match(
        command: Command, project: ArchitectureProject, symbol: ScannedSymbol, scan: ScanResult
    ) -> bool:
        if not command.requirement_ids:
            return True
        designed_requirements = {
            ReconciliationService._normalize(subsystem.name.effective or "")
            for subsystem in project.subsystems
            if subsystem.id in command.requirement_ids
        }
        code_requirements = {
            ReconciliationService._normalize(relationship.target_expression.rsplit(".", 1)[-1])
            for relationship in scan.relationships
            if relationship.kind == "requires"
            and relationship.source_symbol == symbol.anchor.qualified_symbol
        }
        return designed_requirements == code_requirements

    @staticmethod
    def _devices_match(
        subsystem: Subsystem, project: ArchitectureProject, symbol: ScannedSymbol, scan: ScanResult
    ) -> bool:
        designed_devices = [
            device for device in project.devices if device.owner_subsystem_id == subsystem.id
        ]
        if not designed_devices:
            return True
        code_devices = [
            device
            for device in scan.devices
            if ReconciliationService._device_belongs_to_symbol(device.owner_symbol, symbol)
        ]
        for designed in designed_devices:
            matching_types = [
                device
                for device in code_devices
                if ReconciliationService._normalize(device.device_type)
                == ReconciliationService._normalize(designed.device_type.effective or "")
            ]
            if not matching_types:
                return False
            designed_mode = designed.mode.effective
            if designed_mode and not any(
                device.mode is None
                or ReconciliationService._normalize(device.mode)
                == ReconciliationService._normalize(designed_mode)
                for device in matching_types
            ):
                return False
        return True

    @staticmethod
    def _triggers_match(
        command: Command, project: ArchitectureProject, symbol: ScannedSymbol, scan: ScanResult
    ) -> bool:
        designed_triggers = [
            trigger for trigger in project.triggers if trigger.command_id == command.id
        ]
        if not designed_triggers:
            return True
        for designed in designed_triggers:
            expression = ReconciliationService._normalize(designed.expression.effective or "")
            activation = ReconciliationService._normalize(designed.activation.effective or "")
            if not any(
                expression == ReconciliationService._normalize(trigger.controller_expression)
                and activation == ReconciliationService._normalize(trigger.activation)
                and ReconciliationService._normalize(symbol.name)
                in ReconciliationService._normalize(trigger.command_expression)
                for trigger in scan.triggers
            ):
                return False
        return True

    @staticmethod
    def _device_belongs_to_symbol(owner_symbol: str, subsystem_symbol: ScannedSymbol) -> bool:
        if owner_symbol == subsystem_symbol.anchor.qualified_symbol:
            return True
        owner_type = ReconciliationService._normalize(owner_symbol.rsplit(".", 1)[-1])
        subsystem_name = ReconciliationService._normalize(subsystem_symbol.name)
        suffix = owner_type[len(subsystem_name) :]
        return owner_type.startswith(subsystem_name) and "io" in suffix

    @staticmethod
    def accept_matches(project: ArchitectureProject, result: ReconciliationResult) -> int:
        """Persist only explicitly accepted, unambiguous code bindings."""
        elements = {item.id: item for item in [*project.commands, *project.subsystems]}
        accepted = 0
        for element_id, symbol in result.matches.items():
            element = elements[element_id]
            if element.code_binding != symbol.anchor:
                element.code_binding = symbol.anchor
                accepted += 1
        return accepted

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
