"""Deterministic graphics-scene rendering for the design architecture canvas."""

from __future__ import annotations

from uuid import UUID

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainterPath, QPen
from PySide6.QtWidgets import (
    QGraphicsPathItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsTextItem,
)

from frc_arch_modeler.domain.model import ArchitectureProject, Command, Subsystem
from frc_arch_modeler.ui.theme import MUTED_TEXT, PANEL_BLACK, VOLTAGE_BLUE, VOLTAGE_YELLOW

BLOCK_WIDTH = 210
BLOCK_HEIGHT = 92
HORIZONTAL_GAP = 42
COMMAND_Y = 0
SUBSYSTEM_Y = 250


class ArchitectureBlock(QGraphicsRectItem):
    """Movable visual representation of one command or subsystem."""

    def __init__(self, element_id: UUID, label: str, kind: str) -> None:
        super().__init__(0, 0, BLOCK_WIDTH, BLOCK_HEIGHT)
        self.element_id = element_id
        self.kind = kind
        accent = VOLTAGE_YELLOW if kind == "command" else VOLTAGE_BLUE
        self.setBrush(QColor(PANEL_BLACK))
        self.setPen(QPen(QColor(accent), 2))
        self.setFlags(
            QGraphicsRectItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable
        )
        title = QGraphicsTextItem(label, self)
        title.setDefaultTextColor(QColor("#F4F6FA"))
        title.setTextWidth(BLOCK_WIDTH - 24)
        title.setPos(12, 12)
        caption = QGraphicsTextItem(kind.capitalize(), self)
        caption.setDefaultTextColor(QColor(MUTED_TEXT))
        caption.setPos(12, 58)


class ArchitectureScene(QGraphicsScene):
    """Render design elements in semantic command and subsystem regions."""

    def render_project(self, project: ArchitectureProject | None) -> None:
        """Replace scene contents with a deterministic initial model layout."""
        self.clear()
        if project is None:
            return

        blocks: dict[UUID, ArchitectureBlock] = {}
        for index, command in enumerate(project.commands):
            block = self._add_block(command, "command", index, COMMAND_Y)
            blocks[command.id] = block
        for index, subsystem in enumerate(project.subsystems):
            block = self._add_block(subsystem, "subsystem", index, SUBSYSTEM_Y)
            blocks[subsystem.id] = block
        for command in project.commands:
            command_block = blocks[command.id]
            for subsystem_id in command.requirement_ids:
                subsystem_block = blocks.get(subsystem_id)
                if subsystem_block:
                    self._add_requirement_edge(command_block, subsystem_block)
        self.setSceneRect(self.itemsBoundingRect().adjusted(-80, -80, 80, 80))

    def _add_block(
        self, element: Command | Subsystem, kind: str, index: int, y_position: int
    ) -> ArchitectureBlock:
        block = ArchitectureBlock(element.id, element.name.effective or "Unnamed", kind)
        block.setPos(index * (BLOCK_WIDTH + HORIZONTAL_GAP), y_position)
        self.addItem(block)
        return block

    def _add_requirement_edge(
        self, command: ArchitectureBlock, subsystem: ArchitectureBlock
    ) -> None:
        start = command.sceneBoundingRect().bottomLeft() + QPointF(BLOCK_WIDTH / 2, 0)
        end = subsystem.sceneBoundingRect().topLeft() + QPointF(BLOCK_WIDTH / 2, 0)
        path = QPainterPath(start)
        midpoint = (start.y() + end.y()) / 2
        path.cubicTo(QPointF(start.x(), midpoint), QPointF(end.x(), midpoint), end)
        edge = QGraphicsPathItem(path)
        edge.setPen(QPen(QColor(MUTED_TEXT), 1.5, Qt.PenStyle.DashLine))
        edge.setZValue(-1)
        self.addItem(edge)
