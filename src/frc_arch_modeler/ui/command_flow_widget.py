"""Small read-only visual for truthful command lifecycle flow."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from frc_arch_modeler.ui.theme import (
    MUTED_TEXT,
    OFF_WHITE,
    PANEL_BLACK,
    VOLTAGE_BLUE,
    VOLTAGE_YELLOW,
)


class CommandFlowWidget(QWidget):
    """Draw concise lifecycle nodes without implying absent overrides exist."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._phases: list[str] = []
        self.setMinimumHeight(72)
        self.setAccessibleName("Imported command lifecycle flow")

    def set_phases(self, phases: list[str]) -> None:
        self._phases = phases
        self.setVisible(bool(phases))
        self.update()

    def paintEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if not self._phases:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        bounds = self.rect().adjusted(2, 8, -2, -8)
        count = len(self._phases)
        gap = 8
        node_width = max(42, (bounds.width() - gap * (count - 1)) // count)
        node_height = min(42, bounds.height())
        y = bounds.y() + (bounds.height() - node_height) // 2
        for index, phase in enumerate(self._phases):
            x = bounds.x() + index * (node_width + gap)
            inherited = "(inherited)" in phase
            color = QColor(MUTED_TEXT if inherited else VOLTAGE_YELLOW)
            painter.setBrush(QColor(PANEL_BLACK))
            style = Qt.PenStyle.DashLine if inherited else Qt.PenStyle.SolidLine
            painter.setPen(QPen(color, 1.5, style))
            painter.drawRoundedRect(x, y, node_width, node_height, 4, 4)
            painter.setPen(QColor(OFF_WHITE))
            painter.drawText(
                x + 3,
                y + 3,
                node_width - 6,
                node_height - 6,
                Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                phase.replace(" (inherited)", "*"),
            )
            if index < count - 1:
                arrow_start = x + node_width
                arrow_end = arrow_start + gap
                painter.setPen(QPen(QColor(VOLTAGE_BLUE), 1.5))
                center_y = y + node_height // 2
                painter.drawLine(arrow_start + 1, center_y, arrow_end - 1, center_y)
                painter.drawLine(arrow_end - 4, center_y - 3, arrow_end - 1, center_y)
                painter.drawLine(arrow_end - 4, center_y + 3, arrow_end - 1, center_y)

    def mouseDoubleClickEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        index = self._phase_index_at(event.position().x())
        if index is not None:
            self.phase_activated.emit(self._phases[index])
        super().mouseDoubleClickEvent(event)

    def _phase_index_at(self, x_position: float) -> int | None:
        if not self._phases:
            return None
        bounds = self.rect().adjusted(2, 8, -2, -8)
        gap = 8
        node_width = max(42, (bounds.width() - gap * (len(self._phases) - 1)) // len(self._phases))
        for index in range(len(self._phases)):
            left = bounds.x() + index * (node_width + gap)
            if left <= x_position <= left + node_width:
                return index
        return None
    phase_activated = Signal(str)
