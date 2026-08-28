"""Deterministic graphics-scene rendering for the design architecture canvas."""

from __future__ import annotations

from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QColor, QPainterPath, QPen
from PySide6.QtWidgets import (
    QGraphicsPathItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsTextItem,
)

from frc_arch_modeler.domain.model import ArchitectureProject, Command, ComparisonState, Subsystem
from frc_arch_modeler.importers.base import ScannedSymbol, ScanResult
from frc_arch_modeler.ui.theme import MUTED_TEXT, PANEL_BLACK, VOLTAGE_BLUE, VOLTAGE_YELLOW

BLOCK_WIDTH = 210
BLOCK_HEIGHT = 116
HORIZONTAL_GAP = 42
COMMAND_Y = 0
SUBSYSTEM_Y = 250
MATCHED_GREEN = "#35C759"
MODIFIED_AMBER = "#FFAA33"
UNRESOLVED_MAGENTA = "#E75BCB"


class ArchitectureBlock(QGraphicsRectItem):
    """Movable visual representation of one command or subsystem."""

    def __init__(
        self,
        element_id: UUID,
        label: str,
        kind: str,
        imported: bool = False,
        comparison_state: ComparisonState | None = None,
        source_anchor: object | None = None,
        code_summary: str | None = None,
        search_text: str = "",
        detail_lines: list[str] | None = None,
    ) -> None:
        super().__init__(0, 0, BLOCK_WIDTH, BLOCK_HEIGHT)
        self.element_id = element_id
        self.kind = kind
        self.imported = imported
        self.source_anchor = source_anchor
        self.code_summary = code_summary
        self.search_text = search_text.casefold()
        self.minimized = False
        accents = {
            ComparisonState.MATCHED: MATCHED_GREEN,
            ComparisonState.MODIFIED: MODIFIED_AMBER,
            ComparisonState.DESIGN_ONLY: VOLTAGE_YELLOW,
            ComparisonState.UNRESOLVED: UNRESOLVED_MAGENTA,
        }
        default_accent = VOLTAGE_YELLOW if kind == "command" else VOLTAGE_BLUE
        accent = accents.get(comparison_state, default_accent)
        self.setBrush(QColor(PANEL_BLACK))
        if imported:
            style = Qt.PenStyle.DotLine
        elif comparison_state == ComparisonState.DESIGN_ONLY:
            style = Qt.PenStyle.DashLine
        elif comparison_state == ComparisonState.MODIFIED:
            style = Qt.PenStyle.DashDotLine
        else:
            style = Qt.PenStyle.SolidLine
        self.setPen(QPen(QColor(accent), 3 if kind == "command" else 2, style))
        self.setFlags(
            QGraphicsRectItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable
        )
        self.title = QGraphicsTextItem(label, self)
        self.title.setDefaultTextColor(QColor("#F4F6FA"))
        self.title.setTextWidth(BLOCK_WIDTH - 24)
        self.title.setPos(12, 12)
        self.summary = QGraphicsTextItem(self)
        self.summary.setDefaultTextColor(QColor(MUTED_TEXT))
        self.summary.setTextWidth(BLOCK_WIDTH - 24)
        compact_lines = [line for line in (detail_lines or []) if line][:2]
        self.summary.setPlainText("\n".join(compact_lines))
        self.summary.setPos(12, 36)
        status_labels = {
            ComparisonState.MATCHED: "✓ MATCHED",
            ComparisonState.MODIFIED: "Δ MODIFIED",
            ComparisonState.DESIGN_ONLY: "+ DESIGN ONLY",
            ComparisonState.UNRESOLVED: "? UNRESOLVED",
            ComparisonState.CODE_ONLY: "↓ CODE ONLY",
        }
        caption = status_labels.get(
            comparison_state, f"{'Imported ' if imported else ''}{kind.upper()}"
        )
        self.caption = QGraphicsTextItem(caption, self)
        self.caption.setDefaultTextColor(QColor(accent))
        self.caption.setPos(12, 78 if compact_lines else 58)

    def set_minimized(self, minimized: bool) -> None:
        """Collapse optional detail while retaining an identifiable canvas block."""
        self.minimized = minimized
        self.setRect(0, 0, BLOCK_WIDTH, 42 if minimized else BLOCK_HEIGHT)
        self.caption.setVisible(not minimized)
        self.summary.setVisible(not minimized)


class ArchitectureScene(QGraphicsScene):
    """Render design elements in semantic command and subsystem regions."""

    layout_changed = Signal()
    block_double_clicked = Signal()

    def __init__(self, parent: object | None = None) -> None:
        super().__init__(parent)
        self._drag_start_positions: dict[UUID, QPointF] = {}
        self._edges: list[QGraphicsPathItem] = []
        self._search_query = ""
        self._visible_states = set(ComparisonState)
        self.selectionChanged.connect(self._update_edge_visibility)

    def mousePressEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_positions = {
                block.element_id: QPointF(block.pos()) for block in self.selected_blocks()
            }
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().mouseReleaseEvent(event)
        if any(
            block.pos() != position
            for block in self.selected_blocks()
            if (position := self._drag_start_positions.get(block.element_id)) is not None
        ):
            self.layout_changed.emit()
        self._drag_start_positions = {}

    def mouseDoubleClickEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        """Expose a compact-details affordance without coupling blocks to a window."""
        item = self.itemAt(event.scenePos(), self.views()[0].transform()) if self.views() else None
        while item is not None and not isinstance(item, ArchitectureBlock):
            item = item.parentItem()
        if isinstance(item, ArchitectureBlock):
            self.block_double_clicked.emit()
        super().mouseDoubleClickEvent(event)

    def render_project(
        self,
        project: ArchitectureProject | None,
        layout: dict[str, dict[str, Any]] | None = None,
        scan: ScanResult | None = None,
        statuses: dict[UUID, ComparisonState] | None = None,
        code_only_symbols: set[str] | None = None,
    ) -> None:
        """Replace scene contents with a deterministic initial model layout."""
        self.clear()
        self._edges = []
        if project is None:
            if scan is not None:
                self._add_imported_code(scan, 0, 0)
                self.setSceneRect(self.itemsBoundingRect().adjusted(-80, -80, 80, 80))
            return

        layout = layout or {}
        statuses = statuses or {}
        code_only_symbols = code_only_symbols or set()
        blocks: dict[UUID, ArchitectureBlock] = {}
        for index, command in enumerate(project.commands):
            block = self._add_block(command, "command", index, COMMAND_Y, layout, statuses)
            blocks[command.id] = block
        for index, subsystem in enumerate(project.subsystems):
            block = self._add_block(subsystem, "subsystem", index, SUBSYSTEM_Y, layout, statuses)
            blocks[subsystem.id] = block
        for command in project.commands:
            command_block = blocks[command.id]
            for subsystem_id in command.requirement_ids:
                subsystem_block = blocks.get(subsystem_id)
                if subsystem_block:
                    self._add_requirement_edge(command_block, subsystem_block)
        if scan is not None:
            self._add_imported_code(
                scan, len(project.commands), len(project.subsystems), code_only_symbols
            )
        self.setSceneRect(self.itemsBoundingRect().adjusted(-80, -80, 80, 80))
        self._apply_filters()

    def _add_block(
        self,
        element: Command | Subsystem,
        kind: str,
        index: int,
        y_position: int,
        layout: dict[str, dict[str, Any]],
        statuses: dict[UUID, ComparisonState],
    ) -> ArchitectureBlock:
        block = ArchitectureBlock(
            element.id,
            element.name.effective or "Unnamed",
            kind,
            comparison_state=statuses.get(element.id),
            search_text=" ".join(
                filter(
                    None,
                    [
                        element.name.effective,
                        element.description.effective,
                        statuses.get(element.id),
                    ],
                )
            ),
            detail_lines=[element.description.effective or ""],
        )
        item_layout = layout.get(str(element.id), {})
        block.setPos(
            float(item_layout.get("x", index * (BLOCK_WIDTH + HORIZONTAL_GAP))),
            float(item_layout.get("y", y_position)),
        )
        block.set_minimized(bool(item_layout.get("minimized", False)))
        self.addItem(block)
        return block

    def _add_imported_code(
        self,
        scan: ScanResult,
        command_offset: int,
        subsystem_offset: int,
        code_only_symbols: set[str] | None = None,
    ) -> None:
        code_only_symbols = code_only_symbols or set()
        imported_by_symbol: dict[str, ArchitectureBlock] = {}
        imported_subsystems: dict[str, ArchitectureBlock] = {}
        evidence_by_symbol: dict[str, list[str]] = {}
        device_lines_by_symbol: dict[str, list[str]] = {}
        for device in scan.devices:
            evidence_by_symbol.setdefault(device.owner_symbol, []).extend(
                [device.device_type, device.constructor_arguments, device.resolved_arguments or ""]
            )
            arguments = device.resolved_arguments or device.constructor_arguments
            device_lines_by_symbol.setdefault(device.owner_symbol, []).append(
                f"{device.device_type}: {arguments}"
            )
        for trigger in scan.triggers:
            evidence_by_symbol.setdefault(trigger.anchor.qualified_symbol, []).extend(
                [trigger.controller_expression, trigger.activation, trigger.command_expression]
            )
        imported_commands = [
            *scan.symbols_of_kind("command"),
            *scan.symbols_of_kind("command_factory"),
            *scan.symbols_of_kind("command_composition"),
        ]
        trigger_lines_by_symbol = {
            symbol.anchor.qualified_symbol: [
                f"{trigger.controller_expression} · {trigger.activation}"
                for trigger in scan.triggers
                if self._normalized(symbol.name) in self._normalized(trigger.command_expression)
            ]
            for symbol in imported_commands
        }
        for kind, symbols, offset, y_position in (
            ("command", imported_commands, command_offset, COMMAND_Y),
            ("subsystem", scan.symbols_of_kind("subsystem"), subsystem_offset, SUBSYSTEM_Y),
        ):
            for index, symbol in enumerate(symbols):
                block = self._add_imported_block(
                    symbol,
                    kind,
                    index + offset,
                    y_position,
                    ComparisonState.CODE_ONLY
                    if symbol.anchor.qualified_symbol in code_only_symbols
                    else None,
                    evidence_by_symbol.get(symbol.anchor.qualified_symbol, []),
                    device_lines_by_symbol.get(symbol.anchor.qualified_symbol, [])
                    if kind == "subsystem"
                    else trigger_lines_by_symbol.get(symbol.anchor.qualified_symbol, []),
                )
                imported_by_symbol[symbol.anchor.qualified_symbol] = block
                if kind == "subsystem":
                    imported_subsystems[symbol.name.casefold()] = block
        for relationship in scan.relationships:
            if relationship.kind != "requires":
                continue
            command = imported_by_symbol.get(relationship.source_symbol)
            target = relationship.target_expression.rsplit(".", maxsplit=1)[-1].casefold()
            subsystem = imported_subsystems.get(target)
            if command is not None and subsystem is not None:
                self._add_requirement_edge(command, subsystem, imported=True)

    def _add_imported_block(
        self,
        symbol: ScannedSymbol,
        kind: str,
        index: int,
        y_position: int,
        comparison_state: ComparisonState | None = None,
        evidence: list[str] | None = None,
        detail_lines: list[str] | None = None,
    ) -> ArchitectureBlock:
        block = ArchitectureBlock(
            uuid5(NAMESPACE_URL, symbol.anchor.qualified_symbol),
            symbol.name,
            kind,
            imported=True,
            comparison_state=comparison_state,
            source_anchor=symbol.anchor,
            code_summary=symbol.documentation,
            search_text=" ".join(
                filter(
                    None,
                    [symbol.name, symbol.kind, symbol.documentation or "", *(evidence or [])],
                )
            ),
            detail_lines=detail_lines,
        )
        block.setPos(index * (BLOCK_WIDTH + HORIZONTAL_GAP), y_position)
        self.addItem(block)
        return block

    @staticmethod
    def _normalized(value: str) -> str:
        return "".join(character for character in value.casefold() if character.isalnum())

    def layout_state(self) -> dict[str, dict[str, Any]]:
        """Return independently persistable presentation state for all blocks."""
        return {
            str(item.element_id): {
                "x": item.pos().x(),
                "y": item.pos().y(),
                "minimized": item.minimized,
            }
            for item in self.items()
            if isinstance(item, ArchitectureBlock) and not item.imported
        }

    def selected_blocks(self) -> list[ArchitectureBlock]:
        return [item for item in self.selectedItems() if isinstance(item, ArchitectureBlock)]

    def set_selected_minimized(self, minimized: bool) -> bool:
        """Minimize or restore selected blocks, returning whether anything changed."""
        blocks = self.selected_blocks()
        for block in blocks:
            block.set_minimized(minimized)
        if blocks:
            self.setSceneRect(self.itemsBoundingRect().adjusted(-80, -80, 80, 80))
        return bool(blocks)

    def filter_blocks(self, query: str) -> None:
        """Filter visual blocks by their displayed name without changing the model."""
        self._search_query = query.casefold().strip()
        self._apply_filters()

    def set_status_filter(self, visible_states: set[ComparisonState]) -> None:
        """Show only requested comparison states while retaining the current search."""
        self._visible_states = set(visible_states)
        self._apply_filters()

    def _apply_filters(self) -> None:
        visible_ids: set[UUID] = set()
        for item in self.items():
            if isinstance(item, ArchitectureBlock):
                caption = item.caption.toPlainText().casefold()
                name = item.title.toPlainText().casefold()
                matches_search = (
                    not self._search_query
                    or self._search_query in name
                    or self._search_query in caption
                    or self._search_query in item.search_text
                )
                visible = (
                    matches_search and self._block_state(item) in self._visible_states
                )
                item.setVisible(visible)
                if visible:
                    visible_ids.add(item.element_id)
        for edge in self._edges:
            endpoint_ids = edge.data(0)
            edge.setVisible(endpoint_ids <= visible_ids)

    @staticmethod
    def _block_state(block: ArchitectureBlock) -> ComparisonState:
        labels = {
            "✓ MATCHED": ComparisonState.MATCHED,
            "Δ MODIFIED": ComparisonState.MODIFIED,
            "+ DESIGN ONLY": ComparisonState.DESIGN_ONLY,
            "? UNRESOLVED": ComparisonState.UNRESOLVED,
            "↓ CODE ONLY": ComparisonState.CODE_ONLY,
        }
        return labels.get(block.caption.toPlainText(), ComparisonState.UNRESOLVED)

    def _update_edge_visibility(self) -> None:
        selected_ids = {block.element_id for block in self.selected_blocks()}
        for edge in self._edges:
            endpoint_ids = edge.data(0)
            is_connected = bool(selected_ids & endpoint_ids)
            edge.setOpacity(1.0 if not selected_ids or is_connected else 0.16)
            edge.setPen(edge.data(1))
            if selected_ids and is_connected:
                active_pen = QPen(edge.data(1))
                active_pen.setStyle(Qt.PenStyle.SolidLine)
                active_pen.setWidthF(2.5)
                edge.setPen(active_pen)

    def _add_requirement_edge(
        self, command: ArchitectureBlock, subsystem: ArchitectureBlock, imported: bool = False
    ) -> None:
        start = command.sceneBoundingRect().bottomLeft() + QPointF(BLOCK_WIDTH / 2, 0)
        end = subsystem.sceneBoundingRect().topLeft() + QPointF(BLOCK_WIDTH / 2, 0)
        path = QPainterPath(start)
        midpoint = (start.y() + end.y()) / 2
        path.cubicTo(QPointF(start.x(), midpoint), QPointF(end.x(), midpoint), end)
        edge = QGraphicsPathItem(path)
        color = VOLTAGE_BLUE if imported else MUTED_TEXT
        default_pen = QPen(QColor(color), 1.5, Qt.PenStyle.DashLine)
        edge.setPen(default_pen)
        edge.setData(0, {command.element_id, subsystem.element_id})
        edge.setData(1, default_pen)
        edge.setZValue(-1)
        self.addItem(edge)
        self._edges.append(edge)
