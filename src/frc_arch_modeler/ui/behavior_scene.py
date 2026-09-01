"""Deterministic graphics-scene rendering for authored robot-mode behavior diagrams.

A behavior diagram is a separate, SysML-inspired view of the same design model: states
are robot operating modes, and transitions are the events that move between them. It is
edited independently of the structural architecture canvas but shares its interaction
style (drag blocks, drag-to-connect from a connector handle, select to focus edges).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsPathItem,
    QGraphicsPolygonItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QMenu,
)

from frc_arch_modeler.domain.model import BehaviorDiagram
from frc_arch_modeler.ui.architecture_scene import ArchitectureScene, ConnectorHandle
from frc_arch_modeler.ui.theme import MUTED_TEXT, OFF_WHITE, PANEL_BLACK, VOLTAGE_YELLOW

STATE_WIDTH = 160
STATE_HEIGHT = 64
PSEUDOSTATE_DIAMETER = 30
DECISION_SIZE = 56
SYNC_WIDTH = 90
SYNC_HEIGHT = 14
HORIZONTAL_GAP = 70
ROW_GAP = 130
STATES_PER_ROW = 3

# Bounding box for each SysML-style node kind; pseudostates are deliberately small and
# unobtrusive next to a named state's rounded rectangle.
_NODE_DIMENSIONS: dict[str, tuple[float, float]] = {
    "state": (STATE_WIDTH, STATE_HEIGHT),
    "start": (PSEUDOSTATE_DIAMETER, PSEUDOSTATE_DIAMETER),
    "end": (PSEUDOSTATE_DIAMETER, PSEUDOSTATE_DIAMETER),
    "decision": (DECISION_SIZE, DECISION_SIZE),
    "synchronization": (SYNC_WIDTH, SYNC_HEIGHT),
}


class StateBlock(QGraphicsRectItem):
    """A draggable node in a behavior diagram: a named state or a SysML pseudostate."""

    def __init__(self, state_id: UUID, label: str, kind: str = "state") -> None:
        width, height = _NODE_DIMENSIONS.get(kind, _NODE_DIMENSIONS["state"])
        super().__init__(0, 0, width, height)
        self.state_id = state_id
        self.kind = kind
        self.imported = False
        self.setFlags(
            QGraphicsRectItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsRectItem.GraphicsItemFlag.ItemIsFocusable
        )
        if kind == "start":
            self.setBrush(QColor(VOLTAGE_YELLOW))
            self.setPen(QPen(QColor(VOLTAGE_YELLOW), 1))
        elif kind == "synchronization":
            self.setBrush(QColor(OFF_WHITE))
            self.setPen(QPen(QColor(OFF_WHITE), 1))
        else:
            self.setBrush(QColor(PANEL_BLACK))
            self.setPen(QPen(QColor(VOLTAGE_YELLOW), 2))
        if kind == "state":
            self.title = QGraphicsTextItem(label, self)
            self.title.setDefaultTextColor(QColor("#F4F6FA"))
            self.title.setTextWidth(width - 16)
            self.title.setPos(8, height / 2 - 14)
        elif kind == "decision":
            # The diamond's guard condition is expressed by its outgoing transition
            # labels, not a caption on the node itself.
            self.title = None
        else:
            # Pseudostate shapes are too small to hold text; caption sits below instead.
            self.title = QGraphicsTextItem(label, self)
            self.title.setDefaultTextColor(QColor(MUTED_TEXT))
            title_width = self.title.boundingRect().width()
            self.title.setPos(width / 2 - title_width / 2, height + 4)
        self.connector_handle = ConnectorHandle(self)
        self.connector_handle.reposition()

    def paint(self, painter: QPainter, option: object, widget: object = None) -> None:  # type: ignore[no-untyped-def]
        """Draw the SysML notation for this node's kind."""
        painter.setPen(self.pen())
        painter.setBrush(self.brush())
        if self.kind == "state":
            painter.drawRoundedRect(self.rect(), 16, 16)
        elif self.kind in ("start", "synchronization"):
            if self.kind == "start":
                painter.drawEllipse(self.rect())
            else:
                painter.drawRect(self.rect())
        elif self.kind == "end":
            painter.drawEllipse(self.rect())
            painter.setBrush(QColor(VOLTAGE_YELLOW))
            painter.drawEllipse(self.rect().adjusted(6, 6, -6, -6))
        elif self.kind == "decision":
            painter.drawPolygon(self._diamond_shape())

    def _diamond_shape(self) -> QPolygonF:
        rect = self.rect()
        center = rect.center()
        return QPolygonF(
            [
                QPointF(rect.left(), center.y()),
                QPointF(center.x(), rect.top()),
                QPointF(rect.right(), center.y()),
                QPointF(center.x(), rect.bottom()),
            ]
        )


class TransitionEdge(QGraphicsPathItem):
    """One drawn transition line, owning its arrow, label and endpoint handles.

    Every related item is held as a plain Python attribute rather than through
    ``QGraphicsItem.setData()``. Round-tripping a graphics item through setData/data
    boxes it in a QVariant; for a QObject-derived item such as the QGraphicsTextItem
    label that hands back a wrapper with the wrong ownership, so the C++ object is
    freed underneath us and the process later dies inside the allocator. Ordinary
    attributes keep real references and sidestep the conversion entirely.
    """

    def __init__(self, transition_id: object, source_id: UUID, target_id: UUID) -> None:
        super().__init__()
        self.transition_id = transition_id
        self.endpoint_ids: tuple[UUID, UUID] = (source_id, target_id)
        self.base_pen: QPen | None = None
        self.marker: QGraphicsPolygonItem | None = None
        self.label: QGraphicsTextItem | None = None
        self.source_handle: TransitionEndpointHandle | None = None
        self.target_handle: TransitionEndpointHandle | None = None
        self.setFlag(QGraphicsPathItem.GraphicsItemFlag.ItemIsSelectable, True)

    @property
    def handles(self) -> tuple[tuple[TransitionEndpointHandle | None, float], ...]:
        """Each endpoint handle paired with its position along the path."""
        return ((self.source_handle, 0.0), (self.target_handle, 1.0))


class TransitionEndpointHandle(QGraphicsEllipseItem):
    """A selected transition's draggable endpoint, for rewiring it to a different state."""

    RADIUS = 5.0

    def __init__(self, edge: TransitionEdge, end: str) -> None:
        super().__init__(-self.RADIUS, -self.RADIUS, self.RADIUS * 2, self.RADIUS * 2)
        self.edge = edge
        self.end = end
        self.setBrush(QColor(VOLTAGE_YELLOW))
        self.setPen(QPen(QColor(PANEL_BLACK), 1))
        self.setZValue(6)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setToolTip("Drag to reconnect this transition to a different state")
        self.setVisible(False)


class BehaviorScene(QGraphicsScene):
    """Render one authored robot-mode state diagram, separate from the structural canvas."""

    layout_move_completed = Signal(object, object)
    delete_requested = Signal()
    connection_requested = Signal(object, object, QPointF)
    state_double_clicked = Signal(object)
    transition_delete_requested = Signal(object)
    transition_reattach_requested = Signal(object, str, object)

    def __init__(self, parent: object | None = None) -> None:
        super().__init__(parent)
        self._drag_start_positions: dict[UUID, QPointF] = {}
        self._edges: list[TransitionEdge] = []
        self._connection_source: StateBlock | None = None
        self._connection_line: QGraphicsPathItem | None = None
        self._reattach_handle: TransitionEndpointHandle | None = None
        self._reattach_line: QGraphicsPathItem | None = None
        self._context_menu: QMenu | None = None
        self.selectionChanged.connect(self._update_edge_visibility)

    def mousePressEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if event.button() == Qt.MouseButton.LeftButton and self.views():
            hit = self.itemAt(event.scenePos(), self.views()[0].transform())
            if isinstance(hit, ConnectorHandle):
                self._begin_connection_drag(hit.owner, event.scenePos())
                event.accept()
                return
            if isinstance(hit, TransitionEndpointHandle):
                self._begin_reattach_drag(hit, event.scenePos())
                event.accept()
                return
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_positions = {
                block.state_id: QPointF(block.pos()) for block in self.selected_blocks()
            }
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if self._connection_source is not None:
            self._finish_connection_drag(event.scenePos())
            event.accept()
            return
        if self._reattach_handle is not None:
            self._finish_reattach_drag(event.scenePos())
            event.accept()
            return
        super().mouseReleaseEvent(event)
        if self._drag_start_positions:
            # Only recompute every edge's geometry when a block drag could actually have
            # happened -- not on every plain click. A plain click on empty space clears
            # the current selection first (via the base implementation just above), which
            # can synchronously hide a transition's endpoint handles; immediately
            # repositioning scene items afterward in that same reentrant chain has been
            # observed to corrupt Qt's scene index and crash the process.
            self._update_edge_paths()
        moved_blocks = {
            block.state_id: QPointF(block.pos())
            for block in self.selected_blocks()
            if (position := self._drag_start_positions.get(block.state_id)) is not None
            and block.pos() != position
        }
        if moved_blocks:
            self.layout_move_completed.emit(
                {state_id: self._drag_start_positions[state_id] for state_id in moved_blocks},
                moved_blocks,
            )
        self._drag_start_positions = {}

    def mouseMoveEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if self._connection_source is not None:
            self._update_connection_drag(event.scenePos())
            event.accept()
            return
        if self._reattach_handle is not None:
            self._update_reattach_drag(event.scenePos())
            event.accept()
            return
        super().mouseMoveEvent(event)
        if self._drag_start_positions:
            self._update_edge_paths()

    def mouseDoubleClickEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        item = self.itemAt(event.scenePos(), self.views()[0].transform()) if self.views() else None
        while item is not None and not isinstance(item, StateBlock):
            item = item.parentItem()
        if isinstance(item, StateBlock):
            self.state_double_clicked.emit(item)
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        hit = self.itemAt(event.scenePos(), self.views()[0].transform()) if self.views() else None
        item = hit
        while item is not None and not isinstance(item, StateBlock):
            item = item.parentItem()
        if isinstance(item, StateBlock):
            self.clearSelection()
            item.setSelected(True)
            menu = QMenu()
            delete_action = menu.addAction("Delete Selected")
            delete_action.triggered.connect(self.delete_requested.emit)
            # menu.exec() opens its own nested event loop synchronously, on the same
            # native call stack as the right-click that's still being dispatched. On
            # Windows this can leave the mouse grab in a bad state -- the menu never
            # appears, and a *later* click re-enters our own event handlers while that
            # stale nested loop is still unwinding underneath, corrupting the process.
            # popup() shows the menu without blocking, avoiding that reentrancy. Keep a
            # reference so the menu isn't garbage-collected while still on screen.
            self._context_menu = menu
            menu.popup(event.screenPos())
            event.accept()
            return
        edge = self._edge_for(hit)
        if edge is not None:
            self.clearSelection()
            edge.setSelected(True)
            transition_id = edge.transition_id
            menu = QMenu()
            delete_action = menu.addAction("Delete Transition")
            delete_action.triggered.connect(
                lambda: self.transition_delete_requested.emit(transition_id)
            )
            self._context_menu = menu
            menu.popup(event.screenPos())
            event.accept()
            return
        super().contextMenuEvent(event)

    def _edge_for(self, item: object) -> TransitionEdge | None:
        """Resolve a clicked item to the transition it belongs to.

        A short transition's trigger label, its arrowhead and its endpoint handles all
        sit on top of the thin line, so a right-click aimed at the line often lands on
        one of them. They should all mean the same transition.
        """
        if isinstance(item, TransitionEdge) and item in self._edges:
            return item
        owner = getattr(item, "edge", None)
        if isinstance(owner, TransitionEdge) and owner in self._edges:
            return owner
        return None

    def _begin_connection_drag(self, source: StateBlock, scene_pos: QPointF) -> None:
        self._connection_source = source
        self._connection_line = QGraphicsPathItem()
        self._connection_line.setPen(QPen(QColor(VOLTAGE_YELLOW), 1.5, Qt.PenStyle.DashLine))
        self._connection_line.setZValue(10)
        self.addItem(self._connection_line)
        self._update_connection_drag(scene_pos)

    def _update_connection_drag(self, scene_pos: QPointF) -> None:
        if self._connection_line is None or self._connection_source is None:
            return
        path = QPainterPath(self._connection_source.sceneBoundingRect().center())
        path.lineTo(scene_pos)
        self._connection_line.setPath(path)

    def _finish_connection_drag(self, scene_pos: QPointF) -> None:
        source = self._connection_source
        self._connection_source = None
        if self._connection_line is not None:
            self.removeItem(self._connection_line)
            self._connection_line = None
        if source is None:
            return
        target = self.itemAt(scene_pos, self.views()[0].transform()) if self.views() else None
        while target is not None and not isinstance(target, StateBlock):
            target = target.parentItem()
        if isinstance(target, StateBlock) and target is not source:
            self.connection_requested.emit(source, target, scene_pos)

    def _begin_reattach_drag(self, handle: TransitionEndpointHandle, scene_pos: QPointF) -> None:
        """Start dragging a selected transition's endpoint, Visio reshape-handle style."""
        self._reattach_handle = handle
        self._reattach_line = QGraphicsPathItem()
        self._reattach_line.setPen(QPen(QColor(VOLTAGE_YELLOW), 1.5, Qt.PenStyle.DashLine))
        self._reattach_line.setZValue(10)
        self.addItem(self._reattach_line)
        self._update_reattach_drag(scene_pos)

    def _update_reattach_drag(self, scene_pos: QPointF) -> None:
        if self._reattach_line is None or self._reattach_handle is None:
            return
        fixed_percent = 0.0 if self._reattach_handle.end == "target" else 1.0
        fixed_point = self._reattach_handle.edge.path().pointAtPercent(fixed_percent)
        path = QPainterPath(fixed_point)
        path.lineTo(scene_pos)
        self._reattach_line.setPath(path)

    def _finish_reattach_drag(self, scene_pos: QPointF) -> None:
        """Drop the dragged endpoint onto a state to rewire it, unless that's a no-op self-loop."""
        handle = self._reattach_handle
        self._reattach_handle = None
        if self._reattach_line is not None:
            self.removeItem(self._reattach_line)
            self._reattach_line = None
        if handle is None:
            return
        target = self.itemAt(scene_pos, self.views()[0].transform()) if self.views() else None
        while target is not None and not isinstance(target, StateBlock):
            target = target.parentItem()
        if not isinstance(target, StateBlock):
            return
        source_id, target_id = handle.edge.endpoint_ids
        fixed_id = target_id if handle.end == "source" else source_id
        if target.state_id == fixed_id:
            return
        self.transition_reattach_requested.emit(
            handle.edge.transition_id, handle.end, target.state_id
        )

    def render_diagram(
        self, diagram: BehaviorDiagram | None, layout: dict[str, dict[str, Any]] | None = None
    ) -> None:
        """Replace scene contents with a deterministic initial state-diagram layout."""
        # Deleting a selected transition below can synchronously fire selectionChanged
        # (edges are selectable), so drop our own edge cache before clear() runs rather
        # than after -- otherwise a handler reacting to that signal mid-clear() would
        # walk stale entries pointing at already-deleted C++ items.
        self._edges = []
        self.clear()
        if diagram is None:
            return
        layout = layout or {}
        blocks: dict[UUID, StateBlock] = {}
        for index, state in enumerate(diagram.states):
            block = StateBlock(state.id, state.name.effective or "Unnamed", state.kind)
            item_layout = layout.get(str(state.id), {})
            column = index % STATES_PER_ROW
            row = index // STATES_PER_ROW
            block.setPos(
                float(item_layout.get("x", column * (STATE_WIDTH + HORIZONTAL_GAP))),
                float(item_layout.get("y", row * ROW_GAP)),
            )
            self.addItem(block)
            blocks[state.id] = block
        for transition in diagram.transitions:
            source = blocks.get(transition.source_state_id)
            target = blocks.get(transition.target_state_id)
            if source is not None and target is not None:
                self._add_transition_edge(source, target, transition.trigger_label, transition.id)
        self.setSceneRect(self.itemsBoundingRect().adjusted(-80, -80, 80, 80))

    def selected_blocks(self) -> list[StateBlock]:
        return [item for item in self.selectedItems() if isinstance(item, StateBlock)]

    def layout_state(self) -> dict[str, dict[str, Any]]:
        """Return independently persistable presentation state for all state nodes."""
        return {
            str(item.state_id): {"x": item.pos().x(), "y": item.pos().y()}
            for item in self.items()
            if isinstance(item, StateBlock)
        }

    def apply_block_positions(self, positions: dict[UUID, QPointF]) -> None:
        """Apply persisted/undoable positions without recreating the behavior scene."""
        for item in self.items():
            if isinstance(item, StateBlock) and item.state_id in positions:
                item.setPos(positions[item.state_id])
        self._update_edge_paths()

    def _add_transition_edge(
        self, source: StateBlock, target: StateBlock, trigger_label: str, transition_id: object
    ) -> None:
        edge = TransitionEdge(transition_id, source.state_id, target.state_id)
        edge.setPath(self._transition_path(source, target))
        pen = QPen(QColor(MUTED_TEXT), 1.5, Qt.PenStyle.SolidLine)
        edge.setPen(pen)
        edge.base_pen = pen
        edge.setToolTip(trigger_label)
        edge.setZValue(-1)
        self.addItem(edge)
        self._edges.append(edge)

        marker = QGraphicsPolygonItem()
        marker.setPen(QPen(QColor(MUTED_TEXT), 1.25))
        marker.setBrush(QColor(MUTED_TEXT))
        marker.setZValue(2)
        marker.edge = edge
        self.addItem(marker)
        edge.marker = marker

        label = QGraphicsTextItem(trigger_label)
        label.setDefaultTextColor(QColor(MUTED_TEXT))
        label.setZValue(1)
        label.edge = edge
        # A short transition's label covers the line it belongs to. Let clicks fall
        # through to the line beneath so selecting/right-clicking near a label behaves
        # the same as hitting the line itself.
        label.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        marker.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.addItem(label)
        edge.label = label

        edge.source_handle = TransitionEndpointHandle(edge, "source")
        edge.target_handle = TransitionEndpointHandle(edge, "target")
        self.addItem(edge.source_handle)
        self.addItem(edge.target_handle)

        self._position_transition_decorations(edge, source, target)

    def _position_transition_decorations(
        self, edge: TransitionEdge, source: StateBlock, target: StateBlock
    ) -> None:
        source_rect = source.sceneBoundingRect()
        target_rect = target.sceneBoundingRect()
        if edge.marker is not None:
            tip = self._clip_for(target, target_rect, source_rect.center())
            direction = target_rect.center() - source_rect.center()
            edge.marker.setPolygon(ArchitectureScene._arrow_polygon(tip, direction))
        if edge.label is not None:
            midpoint = edge.path().pointAtPercent(0.5)
            label_width = edge.label.boundingRect().width()
            edge.label.setPos(midpoint.x() - label_width / 2, midpoint.y() - 18)
        # Hidden handles don't need repositioning; _update_edge_visibility() gives a
        # handle a fresh position at the moment it becomes visible again.
        for handle, percent in edge.handles:
            if handle is not None and handle.isVisible():
                handle.setPos(edge.path().pointAtPercent(percent))

    @staticmethod
    def _clip_for(block: StateBlock, rect: QRectF, towards: QPointF) -> QPointF:
        """Clip to the node's actual SysML shape, not just its bounding rectangle.

        A rectangle clip would land outside a decision diamond's slanted edges or a
        start/end circle's curve, leaving a visible gap between the line and the shape.
        """
        if block.kind in ("start", "end"):
            return BehaviorScene._clip_ellipse(rect, towards)
        if block.kind == "decision":
            return BehaviorScene._clip_diamond(rect, towards)
        return ArchitectureScene._clip_to_rect(rect, towards)

    @staticmethod
    def _clip_ellipse(rect: QRectF, towards: QPointF) -> QPointF:
        center = rect.center()
        dx = towards.x() - center.x()
        dy = towards.y() - center.y()
        if dx == 0 and dy == 0:
            return center
        half_width = rect.width() / 2
        half_height = rect.height() / 2
        denom = ((dx / half_width) ** 2 + (dy / half_height) ** 2) ** 0.5
        return QPointF(center.x() + dx / denom, center.y() + dy / denom)

    @staticmethod
    def _clip_diamond(rect: QRectF, towards: QPointF) -> QPointF:
        center = rect.center()
        dx = towards.x() - center.x()
        dy = towards.y() - center.y()
        if dx == 0 and dy == 0:
            return center
        half_width = rect.width() / 2
        half_height = rect.height() / 2
        denom = abs(dx) / half_width + abs(dy) / half_height
        scale = 1 / denom if denom else 0.0
        return QPointF(center.x() + dx * scale, center.y() + dy * scale)

    @classmethod
    def _transition_path(cls, source: StateBlock, target: StateBlock) -> QPainterPath:
        """Draw straight between the two near-side points, whichever way states are arranged."""
        source_rect = source.sceneBoundingRect()
        target_rect = target.sceneBoundingRect()
        start = cls._clip_for(source, source_rect, target_rect.center())
        end = cls._clip_for(target, target_rect, source_rect.center())
        path = QPainterPath(start)
        path.lineTo(end)
        return path

    def _update_edge_paths(self) -> None:
        blocks = {item.state_id: item for item in self.items() if isinstance(item, StateBlock)}
        for edge in self._edges:
            source = blocks.get(edge.endpoint_ids[0])
            target = blocks.get(edge.endpoint_ids[1])
            if source is None or target is None:
                continue
            edge.setPath(self._transition_path(source, target))
            self._position_transition_decorations(edge, source, target)

    def selected_transition_ids(self) -> list[object]:
        """Return the transition id of each currently selected transition line."""
        return [edge.transition_id for edge in self._edges if edge.isSelected()]

    def _update_edge_visibility(self) -> None:
        selected_ids = {block.state_id for block in self.selected_blocks()}
        for edge in self._edges:
            is_connected = bool(selected_ids & set(edge.endpoint_ids))
            opacity = 1.0 if not selected_ids or is_connected else 0.16
            edge.setOpacity(opacity)
            edge.setPen(edge.base_pen)
            if selected_ids and is_connected:
                active_pen = QPen(edge.base_pen)
                active_pen.setWidthF(2.5)
                edge.setPen(active_pen)
            for decoration in (edge.marker, edge.label):
                if decoration is not None:
                    decoration.setOpacity(opacity)
            for handle, percent in edge.handles:
                if handle is None:
                    continue
                should_show = edge.isSelected()
                if should_show and not handle.isVisible():
                    # _position_transition_decorations() skips repositioning while a
                    # handle is hidden, so give it an up-to-date position now, the
                    # moment it becomes visible again.
                    handle.setPos(edge.path().pointAtPercent(percent))
                handle.setVisible(should_show)
