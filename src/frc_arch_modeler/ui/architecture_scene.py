"""Deterministic graphics-scene rendering for the design architecture canvas."""

from __future__ import annotations

from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QColor, QKeyEvent, QPainterPath, QPen
from PySide6.QtWidgets import (
    QGraphicsPathItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QMenu,
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
            ComparisonState.AMBIGUOUS: UNRESOLVED_MAGENTA,
            ComparisonState.SCAN_ERROR: "#FF5C5C",
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
            | QGraphicsRectItem.GraphicsItemFlag.ItemIsFocusable
        )
        self.title = QGraphicsTextItem(label, self)
        self.title.setDefaultTextColor(QColor("#F4F6FA"))
        self.title.setTextWidth(BLOCK_WIDTH - 24)
        self.title.setPos(12, 12)
        self.summary = QGraphicsTextItem(self)
        self.summary.setDefaultTextColor(QColor(MUTED_TEXT))
        self.summary.setTextWidth(BLOCK_WIDTH - 24)
        compact_lines = [line for line in (detail_lines or []) if line][:3]
        self.summary.setPlainText("\n".join(compact_lines))
        self.summary.setPos(12, 36)
        status_labels = {
            ComparisonState.MATCHED: "✓ MATCHED",
            ComparisonState.MODIFIED: "Δ MODIFIED",
            ComparisonState.DESIGN_ONLY: "+ DESIGN ONLY",
            ComparisonState.UNRESOLVED: "? UNRESOLVED",
            ComparisonState.AMBIGUOUS: "? AMBIGUOUS",
            ComparisonState.SCAN_ERROR: "! SCAN ERROR",
            ComparisonState.CODE_ONLY: "↓ CODE ONLY",
        }
        caption = status_labels.get(comparison_state, "IMPORTED" if imported else "")
        self.caption = QGraphicsTextItem(caption, self)
        self.caption.setDefaultTextColor(QColor(accent))
        self.caption.setPos(12, 94 if compact_lines else 58)

    def set_minimized(self, minimized: bool) -> None:
        """Collapse optional detail while retaining an identifiable canvas block."""
        self.minimized = minimized
        self.setRect(0, 0, BLOCK_WIDTH, 42 if minimized else BLOCK_HEIGHT)
        self.caption.setVisible(not minimized)
        self.summary.setVisible(not minimized)


class ArchitectureScene(QGraphicsScene):
    """Render design elements in semantic command and subsystem regions."""

    layout_changed = Signal()
    layout_move_completed = Signal(object, object)
    block_double_clicked = Signal()
    delete_requested = Signal()

    def __init__(self, parent: object | None = None) -> None:
        super().__init__(parent)
        self._drag_start_positions: dict[UUID, QPointF] = {}
        self._edges: list[QGraphicsPathItem] = []
        self.show_command_forms = False
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
        self._update_edge_paths()
        moved_blocks = {
            block.element_id: QPointF(block.pos())
            for block in self.selected_blocks()
            if (position := self._drag_start_positions.get(block.element_id)) is not None
            and block.pos() != position
        }
        if moved_blocks:
            self.layout_move_completed.emit(
                {element_id: self._drag_start_positions[element_id] for element_id in moved_blocks},
                moved_blocks,
            )
        self._drag_start_positions = {}

    def mouseMoveEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        """Keep relationship paths visually attached while a selected block is dragged."""
        super().mouseMoveEvent(event)
        if self._drag_start_positions:
            self._update_edge_paths()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Move selected blocks from the keyboard through the normal undoable layout path."""
        offsets = {
            Qt.Key.Key_Left: QPointF(-1, 0),
            Qt.Key.Key_Right: QPointF(1, 0),
            Qt.Key.Key_Up: QPointF(0, -1),
            Qt.Key.Key_Down: QPointF(0, 1),
        }
        direction = offsets.get(event.key())
        blocks = self.selected_blocks()
        if direction is None or not blocks:
            super().keyPressEvent(event)
            return
        distance = 50 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 10
        before = {block.element_id: QPointF(block.pos()) for block in blocks}
        after = {
            block.element_id: block.pos() + direction * distance
            for block in blocks
        }
        self.apply_block_positions(after)
        self.layout_move_completed.emit(before, after)
        event.accept()

    def apply_block_positions(self, positions: dict[UUID, QPointF]) -> None:
        """Apply persisted/undoable positions without recreating the architecture scene."""
        for item in self.items():
            if isinstance(item, ArchitectureBlock) and item.element_id in positions:
                item.setPos(positions[item.element_id])
        self._update_edge_paths()

    def mouseDoubleClickEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        """Expose a compact-details affordance without coupling blocks to a window."""
        item = self.itemAt(event.scenePos(), self.views()[0].transform()) if self.views() else None
        while item is not None and not isinstance(item, ArchitectureBlock):
            item = item.parentItem()
        if isinstance(item, ArchitectureBlock):
            self.block_double_clicked.emit()
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        """Offer deletion only for the authored block the user right-clicked."""
        item = self.itemAt(event.scenePos(), self.views()[0].transform()) if self.views() else None
        while item is not None and not isinstance(item, ArchitectureBlock):
            item = item.parentItem()
        if isinstance(item, ArchitectureBlock) and not item.imported:
            self.clearSelection()
            item.setSelected(True)
            menu = QMenu()
            delete_action = menu.addAction("Delete Selected")
            delete_action.triggered.connect(self.delete_requested.emit)
            menu.exec(event.screenPos())
            event.accept()
            return
        super().contextMenuEvent(event)

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
            block = self._add_block(
                command,
                "command",
                index,
                COMMAND_Y,
                layout,
                statuses,
                [
                    f"{trigger.expression.effective or 'Trigger'} · "
                    f"{trigger.activation.effective or 'Unspecified'}"
                    for trigger in project.triggers
                    if trigger.command_id == command.id
                ],
            )
            blocks[command.id] = block
        for index, subsystem in enumerate(project.subsystems):
            block = self._add_block(
                subsystem,
                "subsystem",
                index,
                SUBSYSTEM_Y,
                layout,
                statuses,
                [
                    f"{device.device_type.effective or 'Device'}: "
                    f"{device.name.effective or 'Unnamed'}"
                    for device in project.devices
                    if device.owner_subsystem_id == subsystem.id
                ],
            )
            blocks[subsystem.id] = block
        for command in project.commands:
            command_block = blocks[command.id]
            for subsystem_id in command.requirement_ids:
                subsystem_block = blocks.get(subsystem_id)
                if subsystem_block:
                    self._add_requirement_edge(
                        command_block, subsystem_block, evidence="Designed requirement"
                    )
        for relationship in project.relationships:
            source = blocks.get(relationship.source_id)
            target = blocks.get(relationship.target_id)
            if source is not None and target is not None:
                self._add_design_relationship_edge(source, target, relationship.relationship_type)
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
        design_detail_lines: list[str] | None = None,
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
            detail_lines=[element.description.effective or "", *(design_detail_lines or [])],
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
        subsystem_symbols = scan.symbols_of_kind("subsystem")
        for device in scan.devices:
            owner_symbol = self._logical_device_owner(device.owner_symbol, subsystem_symbols)
            evidence_by_symbol.setdefault(owner_symbol, []).extend(
                [device.device_type, device.constructor_arguments, device.resolved_arguments or ""]
            )
            arguments = device.resolved_arguments or device.constructor_arguments
            mode = f" [{device.mode}]" if device.mode else ""
            device_lines_by_symbol.setdefault(owner_symbol, []).append(
                f"{device.device_type}{mode}: {arguments}"
            )
        for trigger in scan.triggers:
            evidence_by_symbol.setdefault(trigger.anchor.qualified_symbol, []).extend(
                [trigger.controller_expression, trigger.activation, trigger.command_expression]
            )
        imported_commands = [
            *scan.symbols_of_kind("command"),
            *scan.symbols_of_kind("command_factory"),
        ]
        if self.show_command_forms:
            imported_commands.extend(scan.symbols_of_kind("command_composition"))
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
            ("subsystem", subsystem_symbols, subsystem_offset, SUBSYSTEM_Y),
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
                self._add_requirement_edge(
                    command,
                    subsystem,
                    imported=True,
                    evidence=f"addRequirements({relationship.target_expression})",
                )

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

    @classmethod
    def _logical_device_owner(cls, owner_symbol: str, subsystems: list[ScannedSymbol]) -> str:
        """Map an IO implementation back to its logical subsystem when unambiguous."""
        owner_type = owner_symbol.rsplit(".", 1)[-1]
        normalized_owner = cls._normalized(owner_type)
        matches = [
            symbol.anchor.qualified_symbol
            for symbol in subsystems
            if normalized_owner.startswith(cls._normalized(symbol.name))
            and "io" in normalized_owner[len(cls._normalized(symbol.name)) :]
        ]
        return matches[0] if len(matches) == 1 else owner_symbol

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
            "? AMBIGUOUS": ComparisonState.AMBIGUOUS,
            "! SCAN ERROR": ComparisonState.SCAN_ERROR,
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
        self,
        command: ArchitectureBlock,
        subsystem: ArchitectureBlock,
        imported: bool = False,
        evidence: str = "Requirement relationship",
    ) -> None:
        edge = QGraphicsPathItem(self._requirement_path(command, subsystem))
        color = VOLTAGE_BLUE if imported else MUTED_TEXT
        default_pen = QPen(QColor(color), 1.5, Qt.PenStyle.DashLine)
        edge.setPen(default_pen)
        edge.setData(0, {command.element_id, subsystem.element_id})
        edge.setData(1, default_pen)
        edge.setData(2, "requirement")
        edge.setData(3, (command.element_id, subsystem.element_id))
        edge.setToolTip(evidence)
        edge.setZValue(-1)
        self.addItem(edge)
        self._edges.append(edge)

    def _add_design_relationship_edge(
        self, source: ArchitectureBlock, target: ArchitectureBlock, relationship_type: str
    ) -> None:
        """Render an explicit authored relationship without confusing it with requires."""
        edge = QGraphicsPathItem(self._design_relationship_path(source, target))
        pen = QPen(QColor(MUTED_TEXT), 1.25, Qt.PenStyle.DotLine)
        edge.setPen(pen)
        edge.setData(0, {source.element_id, target.element_id})
        edge.setData(1, pen)
        edge.setData(2, "design_relationship")
        edge.setData(3, (source.element_id, target.element_id))
        edge.setToolTip(f"Designed {relationship_type.replace('_', ' ')} relationship")
        edge.setZValue(-1)
        self.addItem(edge)
        self._edges.append(edge)

    @staticmethod
    def _requirement_path(command: ArchitectureBlock, subsystem: ArchitectureBlock) -> QPainterPath:
        start = command.sceneBoundingRect().bottomLeft() + QPointF(BLOCK_WIDTH / 2, 0)
        end = subsystem.sceneBoundingRect().topLeft() + QPointF(BLOCK_WIDTH / 2, 0)
        path = QPainterPath(start)
        midpoint = (start.y() + end.y()) / 2
        path.cubicTo(QPointF(start.x(), midpoint), QPointF(end.x(), midpoint), end)
        return path

    @staticmethod
    def _design_relationship_path(
        source: ArchitectureBlock, target: ArchitectureBlock
    ) -> QPainterPath:
        start = source.sceneBoundingRect().center()
        end = target.sceneBoundingRect().center()
        path = QPainterPath(start)
        midpoint = (start.x() + end.x()) / 2
        path.cubicTo(QPointF(midpoint, start.y()), QPointF(midpoint, end.y()), end)
        return path

    def _update_edge_paths(self) -> None:
        """Rebuild curves from their endpoints after a block position changes."""
        blocks = {
            item.element_id: item
            for item in self.items()
            if isinstance(item, ArchitectureBlock)
        }
        for edge in self._edges:
            endpoint_ids = edge.data(3)
            if not isinstance(endpoint_ids, tuple) or len(endpoint_ids) != 2:
                continue
            source = blocks.get(endpoint_ids[0])
            target = blocks.get(endpoint_ids[1])
            if source is None or target is None:
                continue
            if edge.data(2) == "requirement":
                edge.setPath(self._requirement_path(source, target))
            else:
                edge.setPath(self._design_relationship_path(source, target))
