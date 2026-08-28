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

from frc_arch_modeler.domain.model import ArchitectureProject, Command, Subsystem
from frc_arch_modeler.importers.base import ScannedSymbol, ScanResult
from frc_arch_modeler.ui.theme import MUTED_TEXT, PANEL_BLACK, VOLTAGE_BLUE, VOLTAGE_YELLOW

BLOCK_WIDTH = 210
BLOCK_HEIGHT = 92
HORIZONTAL_GAP = 42
COMMAND_Y = 0
SUBSYSTEM_Y = 250


class ArchitectureBlock(QGraphicsRectItem):
    """Movable visual representation of one command or subsystem."""

    def __init__(self, element_id: UUID, label: str, kind: str, imported: bool = False) -> None:
        super().__init__(0, 0, BLOCK_WIDTH, BLOCK_HEIGHT)
        self.element_id = element_id
        self.kind = kind
        self.imported = imported
        self.minimized = False
        accent = VOLTAGE_YELLOW if kind == "command" else VOLTAGE_BLUE
        self.setBrush(QColor(PANEL_BLACK))
        style = Qt.PenStyle.DotLine if imported else Qt.PenStyle.SolidLine
        self.setPen(QPen(QColor(accent), 3 if kind == "command" else 2, style))
        self.setFlags(
            QGraphicsRectItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable
        )
        self.title = QGraphicsTextItem(label, self)
        self.title.setDefaultTextColor(QColor("#F4F6FA"))
        self.title.setTextWidth(BLOCK_WIDTH - 24)
        self.title.setPos(12, 12)
        source = "Imported " if imported else ""
        caption = f"{source}{kind.upper()}"
        self.caption = QGraphicsTextItem(caption, self)
        self.caption.setDefaultTextColor(QColor(accent))
        self.caption.setPos(12, 58)

    def set_minimized(self, minimized: bool) -> None:
        """Collapse optional detail while retaining an identifiable canvas block."""
        self.minimized = minimized
        self.setRect(0, 0, BLOCK_WIDTH, 42 if minimized else BLOCK_HEIGHT)
        self.caption.setVisible(not minimized)


class ArchitectureScene(QGraphicsScene):
    """Render design elements in semantic command and subsystem regions."""

    layout_changed = Signal()

    def __init__(self, parent: object | None = None) -> None:
        super().__init__(parent)
        self._drag_start_positions: dict[UUID, QPointF] = {}

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

    def render_project(
        self,
        project: ArchitectureProject | None,
        layout: dict[str, dict[str, Any]] | None = None,
        scan: ScanResult | None = None,
    ) -> None:
        """Replace scene contents with a deterministic initial model layout."""
        self.clear()
        if project is None:
            if scan is not None:
                self._add_imported_code(scan, 0, 0)
                self.setSceneRect(self.itemsBoundingRect().adjusted(-80, -80, 80, 80))
            return

        layout = layout or {}
        blocks: dict[UUID, ArchitectureBlock] = {}
        for index, command in enumerate(project.commands):
            block = self._add_block(command, "command", index, COMMAND_Y, layout)
            blocks[command.id] = block
        for index, subsystem in enumerate(project.subsystems):
            block = self._add_block(subsystem, "subsystem", index, SUBSYSTEM_Y, layout)
            blocks[subsystem.id] = block
        for command in project.commands:
            command_block = blocks[command.id]
            for subsystem_id in command.requirement_ids:
                subsystem_block = blocks.get(subsystem_id)
                if subsystem_block:
                    self._add_requirement_edge(command_block, subsystem_block)
        if scan is not None:
            self._add_imported_code(scan, len(project.commands), len(project.subsystems))
        self.setSceneRect(self.itemsBoundingRect().adjusted(-80, -80, 80, 80))

    def _add_block(
        self,
        element: Command | Subsystem,
        kind: str,
        index: int,
        y_position: int,
        layout: dict[str, dict[str, Any]],
    ) -> ArchitectureBlock:
        block = ArchitectureBlock(element.id, element.name.effective or "Unnamed", kind)
        item_layout = layout.get(str(element.id), {})
        block.setPos(
            float(item_layout.get("x", index * (BLOCK_WIDTH + HORIZONTAL_GAP))),
            float(item_layout.get("y", y_position)),
        )
        block.set_minimized(bool(item_layout.get("minimized", False)))
        self.addItem(block)
        return block

    def _add_imported_code(
        self, scan: ScanResult, command_offset: int, subsystem_offset: int
    ) -> None:
        imported_by_symbol: dict[str, ArchitectureBlock] = {}
        imported_subsystems: dict[str, ArchitectureBlock] = {}
        for kind, offset, y_position in (
            ("command", command_offset, COMMAND_Y),
            ("subsystem", subsystem_offset, SUBSYSTEM_Y),
        ):
            for index, symbol in enumerate(scan.symbols_of_kind(kind)):
                block = self._add_imported_block(symbol, kind, index + offset, y_position)
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
        self, symbol: ScannedSymbol, kind: str, index: int, y_position: int
    ) -> ArchitectureBlock:
        block = ArchitectureBlock(
            uuid5(NAMESPACE_URL, symbol.anchor.qualified_symbol), symbol.name, kind, imported=True
        )
        block.setPos(index * (BLOCK_WIDTH + HORIZONTAL_GAP), y_position)
        self.addItem(block)
        return block

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
        edge.setPen(QPen(QColor(color), 1.5, Qt.PenStyle.DashLine))
        edge.setZValue(-1)
        self.addItem(edge)
