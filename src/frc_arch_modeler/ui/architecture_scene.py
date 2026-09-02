"""Deterministic graphics-scene rendering for the design architecture canvas."""

from __future__ import annotations

from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QKeyEvent, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsPathItem,
    QGraphicsPolygonItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QMenu,
)

from frc_arch_modeler.domain.model import (
    ArchitectureProject,
    Command,
    ComparisonState,
    Device,
    Subsystem,
)
from frc_arch_modeler.importers.base import ScannedSymbol, ScanResult
from frc_arch_modeler.services.allocation_service import AllocationFinding, other_device_ids
from frc_arch_modeler.ui import edge_routing
from frc_arch_modeler.ui.theme import (
    ALERT_RED,
    MUTED_TEXT,
    NEAR_BLACK,
    OFF_WHITE,
    PANEL_BLACK,
    VOLTAGE_BLUE,
    VOLTAGE_YELLOW,
)

BLOCK_WIDTH = 210
BLOCK_HEIGHT = 116
HORIZONTAL_GAP = 42
VERTICAL_GAP = 40
COMMAND_Y = 0
SUBSYSTEM_Y = 250
# The device tier: short blocks on a third row, grouped under their owning subsystem.
DEVICE_BLOCK_WIDTH = 168
DEVICE_BLOCK_HEIGHT = 40
DEVICE_HORIZONTAL_GAP = 16
DEVICE_GROUP_GAP = 44
DEVICE_TIER_GAP = 56
MATCHED_GREEN = "#35C759"
MODIFIED_AMBER = "#FFAA33"
UNRESOLVED_MAGENTA = "#E75BCB"

# UML-flavored notation for authored relationship types: (marker shape, filled).
RELATIONSHIP_MARKERS: dict[str, tuple[str, bool]] = {
    "calls": ("arrow", False),
    "triggers": ("arrow", True),
    "contains": ("diamond", False),
    "owns_device": ("diamond", True),
}

#: Device tier presentation, in the order the toolbar action cycles through them.
#: "grouped" is the default: a robot with forty-five devices then opens no busier than
#: one with none, because a grouped subsystem draws one chip instead of its devices.
DEVICE_VIEW_STATES = ("grouped", "expanded", "hidden")
#: Reserved, deliberately non-UUID ``layout.json`` key holding the device tier's state.
DEVICE_VIEW_LAYOUT_KEY = "deviceView"

#: Status is carried by border color *and* a border style, never by color alone.
STATUS_ACCENTS: dict[ComparisonState, str] = {
    ComparisonState.MATCHED: MATCHED_GREEN,
    ComparisonState.MODIFIED: MODIFIED_AMBER,
    ComparisonState.DESIGN_ONLY: VOLTAGE_YELLOW,
    ComparisonState.CODE_ONLY: VOLTAGE_BLUE,
    ComparisonState.UNRESOLVED: UNRESOLVED_MAGENTA,
    ComparisonState.AMBIGUOUS: UNRESOLVED_MAGENTA,
    ComparisonState.SCAN_ERROR: "#FF5C5C",
}
STATUS_LABELS: dict[ComparisonState, str] = {
    ComparisonState.MATCHED: "✓ MATCHED",
    ComparisonState.MODIFIED: "Δ MODIFIED",
    ComparisonState.DESIGN_ONLY: "+ DESIGN ONLY",
    ComparisonState.UNRESOLVED: "? UNRESOLVED",
    ComparisonState.AMBIGUOUS: "? AMBIGUOUS",
    ComparisonState.SCAN_ERROR: "! SCAN ERROR",
    ComparisonState.CODE_ONLY: "↓ CODE ONLY",
}


class ConnectorHandle(QGraphicsEllipseItem):
    """Small drag source enabling Visio-style click-and-drag connection drawing."""

    RADIUS = 5.0

    def __init__(self, owner: ArchitectureBlock) -> None:
        super().__init__(-self.RADIUS, -self.RADIUS, self.RADIUS * 2, self.RADIUS * 2, owner)
        self.owner = owner
        self.setBrush(QColor(VOLTAGE_YELLOW))
        self.setPen(QPen(QColor(PANEL_BLACK), 1))
        self.setZValue(5)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setToolTip("Drag to draw a relationship")

    def reposition(self) -> None:
        rect = self.owner.rect()
        self.setPos(rect.width(), rect.height() / 2)


class CanvasBlock(QGraphicsRectItem):
    """What every canvas tier has in common: identity, a title, a status and search text.

    Selection, filtering, layout persistence and edge routing are all written against
    this base, so adding a tier only means teaching a new subclass how to draw itself.
    """

    #: Set by every subclass; filtering reads both as displayed text.
    title: QGraphicsTextItem
    caption: QGraphicsTextItem

    def __init__(
        self,
        element_id: UUID,
        kind: str,
        width: float,
        height: float,
        imported: bool = False,
        comparison_state: ComparisonState | None = None,
        search_text: str = "",
    ) -> None:
        super().__init__(0, 0, width, height)
        self.element_id = element_id
        self.kind = kind
        self.imported = imported
        self.comparison_state = comparison_state
        self.search_text = search_text.casefold()
        self.minimized = False
        self.setFlags(
            QGraphicsRectItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsRectItem.GraphicsItemFlag.ItemIsFocusable
        )


class DeviceCountChip(QGraphicsRectItem):
    """The grouped view's click target: expands or collapses one subsystem's devices.

    It stands in for the device blocks themselves, so the default canvas carries one
    small chip per subsystem however many devices that subsystem owns.
    """

    def __init__(self, owner: ArchitectureBlock, count: int, expanded: bool) -> None:
        super().__init__(owner)
        self.owner = owner
        self.count = count
        self.expanded = expanded
        accent = VOLTAGE_YELLOW if expanded else MUTED_TEXT
        arrow = "\u25be" if expanded else "\u25b8"
        self.label = QGraphicsTextItem(
            f"{arrow} {count} device{'' if count == 1 else 's'}", self
        )
        self.label.document().setDocumentMargin(0)
        font = self.label.font()
        font.setPointSize(8)
        self.label.setFont(font)
        self.label.setDefaultTextColor(QColor(accent))
        self.label.setPos(8, 4)
        self.setRect(
            0,
            0,
            self.label.boundingRect().width() + 16,
            self.label.boundingRect().height() + 8,
        )
        self.setBrush(QColor(NEAR_BLACK))
        self.setPen(QPen(QColor(accent), 1))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Show or hide this subsystem's devices on the canvas")


class DeviceAlertBadge(QGraphicsEllipseItem):
    """A small red dot marking a device with an allocation-conflict finding.

    Clicking it selects the *other* device(s) named in the finding rather than this
    one, so a duplicate CAN ID can be chased to its twin in one click.
    """

    RADIUS = 4.0

    def __init__(self, owner: DeviceBlock, findings: tuple[AllocationFinding, ...]) -> None:
        super().__init__(-self.RADIUS, -self.RADIUS, self.RADIUS * 2, self.RADIUS * 2, owner)
        self.owner = owner
        self.findings = findings
        self.setBrush(QColor(ALERT_RED))
        self.setPen(QPen(QColor(PANEL_BLACK), 1))
        self.setZValue(6)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("\n".join(finding.message for finding in findings))


class ArchitectureBlock(CanvasBlock):
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
        device_count: int | None = None,
        devices_expanded: bool = False,
    ) -> None:
        super().__init__(
            element_id,
            kind,
            BLOCK_WIDTH,
            BLOCK_HEIGHT,
            imported,
            comparison_state,
            search_text,
        )
        self.source_anchor = source_anchor
        self.code_summary = code_summary
        default_accent = VOLTAGE_YELLOW if kind == "command" else VOLTAGE_BLUE
        accent = STATUS_ACCENTS.get(comparison_state, default_accent)
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
        self.title = QGraphicsTextItem(label, self)
        self.title.setDefaultTextColor(QColor(OFF_WHITE))
        self.title.setTextWidth(BLOCK_WIDTH - 24)
        self.title.setPos(12, 12)
        title_bottom = self.title.pos().y() + self.title.boundingRect().height()

        self.summary = QGraphicsTextItem(self)
        self.summary.setDefaultTextColor(QColor(MUTED_TEXT))
        self.summary.setTextWidth(BLOCK_WIDTH - 24)
        filtered_lines = [line for line in (detail_lines or []) if line]
        compact_lines = filtered_lines[:3]
        if len(filtered_lines) > 3:
            compact_lines.append(f"+{len(filtered_lines) - 3} more")
        self.summary.setPlainText("\n".join(compact_lines))
        self.summary.setPos(12, title_bottom + 4)
        summary_bottom = (
            self.summary.pos().y() + self.summary.boundingRect().height()
            if compact_lines
            else title_bottom
        )

        caption = STATUS_LABELS.get(comparison_state, "IMPORTED" if imported else "")
        self.caption = QGraphicsTextItem(caption, self)
        self.caption.setDefaultTextColor(QColor(accent))
        caption_y = summary_bottom + 8
        self.caption.setPos(12, caption_y)
        content_bottom = caption_y + self.caption.boundingRect().height()

        # A subsystem in the grouped device view carries its device count as a chip
        # instead of the device blocks themselves; every other view leaves it out.
        self.device_chip: DeviceCountChip | None = None
        if device_count:
            self.device_chip = DeviceCountChip(self, device_count, devices_expanded)
            self.device_chip.setPos(12, content_bottom + 6)
            content_bottom += 6 + self.device_chip.rect().height()

        # Size the block to fully contain wrapped title/summary/caption text
        # instead of relying on a fixed height that mechanism text can overflow.
        self.expanded_height = max(BLOCK_HEIGHT, content_bottom + 12)
        self.setRect(0, 0, BLOCK_WIDTH, self.expanded_height)

        # Imported code facts are read-only evidence, not valid relationship endpoints.
        self.connector_handle: ConnectorHandle | None = None
        if not imported:
            self.connector_handle = ConnectorHandle(self)
            self.connector_handle.reposition()

    def set_minimized(self, minimized: bool) -> None:
        """Collapse optional detail while retaining an identifiable canvas block."""
        self.minimized = minimized
        self.setRect(0, 0, BLOCK_WIDTH, 42 if minimized else self.expanded_height)
        self.caption.setVisible(not minimized)
        self.summary.setVisible(not minimized)
        if self.device_chip is not None:
            self.device_chip.setVisible(not minimized)
        if self.connector_handle is not None:
            self.connector_handle.reposition()


class DeviceBlock(CanvasBlock):
    """One hardware device, about a third the height of an ``ArchitectureBlock``.

    Selectable and movable like any block, but deliberately not a relationship drag
    source: a device's only structural edge is the filled-diamond composition line back
    to the subsystem that owns it, so it carries no connector handle.
    """

    def __init__(
        self,
        device_id: UUID,
        owner_subsystem_id: UUID,
        name: str,
        device_type: str,
        badge: str = "",
        comparison_state: ComparisonState | None = None,
        search_text: str = "",
        findings: tuple[AllocationFinding, ...] = (),
    ) -> None:
        super().__init__(
            device_id,
            "device",
            DEVICE_BLOCK_WIDTH,
            DEVICE_BLOCK_HEIGHT,
            comparison_state=comparison_state,
            search_text=search_text,
        )
        self.owner_subsystem_id = owner_subsystem_id
        # A device inherits its owner's comparison status, so filtering by status keeps
        # a subsystem and the hardware hanging off it on screen together.
        accent = STATUS_ACCENTS.get(comparison_state, MUTED_TEXT)
        self.setBrush(QColor(PANEL_BLACK))
        self.setPen(
            QPen(
                QColor(accent),
                1,
                Qt.PenStyle.DashLine
                if comparison_state == ComparisonState.DESIGN_ONLY
                else Qt.PenStyle.SolidLine,
            )
        )
        self.title = self._text(name, OFF_WHITE, 8, bold=True)
        self.title.setTextWidth(DEVICE_BLOCK_WIDTH - 14)
        self.title.setPos(7, 2)
        self.caption = self._text(device_type, MUTED_TEXT, 7)
        self.caption.setPos(7, 21)
        self.badge = self._text(badge, VOLTAGE_YELLOW, 7, mono=True)
        self.badge.setPos(DEVICE_BLOCK_WIDTH - 7 - self.badge.boundingRect().width(), 21)
        self.badge.setVisible(bool(badge))
        self.alert_findings = findings
        self.alert_badge: DeviceAlertBadge | None = None
        if findings:
            self.alert_badge = DeviceAlertBadge(self, findings)
            self.alert_badge.setPos(DEVICE_BLOCK_WIDTH - 6, 6)

    def _text(
        self,
        value: str,
        color: str,
        point_size: int,
        bold: bool = False,
        mono: bool = False,
    ) -> QGraphicsTextItem:
        """One tightly-margined line of block text; a device has 40px for three of them."""
        item = QGraphicsTextItem(value, self)
        item.setDefaultTextColor(QColor(color))
        item.document().setDocumentMargin(0)
        if mono:
            font = QFont("Consolas")
            font.setStyleHint(QFont.StyleHint.Monospace)
        else:
            font = item.font()
        font.setPointSize(point_size)
        font.setBold(bold)
        item.setFont(font)
        return item


class ArchitectureScene(QGraphicsScene):
    """Render design elements in semantic command and subsystem regions."""

    layout_changed = Signal()
    layout_move_completed = Signal(object, object)
    block_double_clicked = Signal()
    delete_requested = Signal()
    connection_requested = Signal(object, object, QPointF)
    device_view_changed = Signal()

    def __init__(self, parent: object | None = None) -> None:
        super().__init__(parent)
        self._drag_start_positions: dict[UUID, QPointF] = {}
        self._edges: list[QGraphicsPathItem] = []
        self.show_command_forms = False
        self.device_view_state = DEVICE_VIEW_STATES[0]
        self.expanded_device_subsystems: set[UUID] = set()
        self._search_query = ""
        self._visible_states = set(ComparisonState)
        self._connection_source: ArchitectureBlock | None = None
        self._connection_line: QGraphicsPathItem | None = None
        self._context_menu: QMenu | None = None
        self.selectionChanged.connect(self._update_edge_visibility)

    def mousePressEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if event.button() == Qt.MouseButton.LeftButton and self.views():
            hit = self.itemAt(event.scenePos(), self.views()[0].transform())
            if isinstance(hit, ConnectorHandle):
                self._begin_connection_drag(hit.owner, event.scenePos())
                event.accept()
                return
            if isinstance(hit, DeviceAlertBadge):
                self._select_other_devices(hit)
                event.accept()
                return
            chip = self._chip_at(hit)
            if chip is not None:
                self.toggle_subsystem_devices(chip.owner.element_id)
                event.accept()
                return
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_positions = {
                block.element_id: QPointF(block.pos())
                for block in self.selected_canvas_blocks()
            }
        super().mousePressEvent(event)

    @staticmethod
    def _chip_at(hit: object) -> DeviceCountChip | None:
        """Resolve a click on a chip or on the text drawn inside it, and nothing else."""
        while hit is not None and not isinstance(hit, (DeviceCountChip, CanvasBlock)):
            hit = hit.parentItem()  # type: ignore[attr-defined]
        return hit if isinstance(hit, DeviceCountChip) else None

    def _select_other_devices(self, badge: DeviceAlertBadge) -> None:
        """Jump from a device's alert badge to whichever device(s) it conflicts with.

        Only currently rendered blocks can be selected; a conflicting device hidden
        inside a collapsed subsystem group is silently skipped.
        """
        device_id = badge.owner.element_id
        target_ids = set(other_device_ids(device_id, badge.findings)) or {device_id}
        self.clearSelection()
        for item in self.items():
            if isinstance(item, DeviceBlock) and item.element_id in target_ids:
                item.setSelected(True)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if self._connection_source is not None:
            self._finish_connection_drag(event.scenePos())
            event.accept()
            return
        super().mouseReleaseEvent(event)
        self._update_edge_paths()
        moved_blocks = {
            block.element_id: QPointF(block.pos())
            for block in self.selected_canvas_blocks()
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
        if self._connection_source is not None:
            self._update_connection_drag(event.scenePos())
            event.accept()
            return
        super().mouseMoveEvent(event)
        if self._drag_start_positions:
            self._update_edge_paths()

    def _begin_connection_drag(self, source: ArchitectureBlock, scene_pos: QPointF) -> None:
        """Start a temporary rubber line from a connector handle, Visio-style."""
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
        """Emit a connection request only when dropped on a valid, distinct design block."""
        source = self._connection_source
        self._connection_source = None
        if self._connection_line is not None:
            self.removeItem(self._connection_line)
            self._connection_line = None
        if source is None:
            return
        target = self.itemAt(scene_pos, self.views()[0].transform()) if self.views() else None
        while target is not None and not isinstance(target, ArchitectureBlock):
            target = target.parentItem()
        if (
            isinstance(target, ArchitectureBlock)
            and target is not source
            and not source.imported
            and not target.imported
        ):
            self.connection_requested.emit(source, target, scene_pos)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Move selected blocks from the keyboard through the normal undoable layout path."""
        offsets = {
            Qt.Key.Key_Left: QPointF(-1, 0),
            Qt.Key.Key_Right: QPointF(1, 0),
            Qt.Key.Key_Up: QPointF(0, -1),
            Qt.Key.Key_Down: QPointF(0, 1),
        }
        direction = offsets.get(event.key())
        blocks = self.selected_canvas_blocks()
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
            if isinstance(item, CanvasBlock) and item.element_id in positions:
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
        super().contextMenuEvent(event)

    def render_project(
        self,
        project: ArchitectureProject | None,
        layout: dict[str, dict[str, Any]] | None = None,
        scan: ScanResult | None = None,
        statuses: dict[UUID, ComparisonState] | None = None,
        code_only_symbols: set[str] | None = None,
        allocation_findings: dict[UUID, list[AllocationFinding]] | None = None,
    ) -> None:
        """Replace scene contents with a deterministic initial model layout."""
        # Reset the edge cache before clear() destroys the items it points to: deleting a
        # selected item can fire selectionChanged synchronously, and a handler reacting to
        # that mid-clear() must not walk stale entries pointing at deleted C++ objects.
        self._edges = []
        self.clear()
        if project is None:
            if scan is not None:
                self._add_imported_code(scan, 0, 0)
                self.setSceneRect(self.itemsBoundingRect().adjusted(-80, -80, 80, 80))
            return

        layout = layout or {}
        self._restore_device_view(layout)
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
        subsystem_row_y = self._subsystem_row_y(list(blocks.values()))
        for index, subsystem in enumerate(project.subsystems):
            device_count = sum(
                1 for device in project.devices if device.owner_subsystem_id == subsystem.id
            )
            block = self._add_block(
                subsystem,
                "subsystem",
                index,
                subsystem_row_y,
                layout,
                statuses,
                # Hardware lives on its own tier now, so it never crowds this block's text.
                None,
                device_count if self.device_view_state == "grouped" else None,
                subsystem.id in self.expanded_device_subsystems,
            )
            blocks[subsystem.id] = block
        self._add_device_tier(project, blocks, layout, statuses, allocation_findings or {})
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
                scan,
                len(project.commands),
                len(project.subsystems),
                code_only_symbols,
                subsystem_row_y,
            )
        self.setSceneRect(self.itemsBoundingRect().adjusted(-80, -80, 80, 80))
        self._apply_filters()

    @staticmethod
    def _subsystem_row_y(command_blocks: list[ArchitectureBlock]) -> float:
        """Push the subsystem row down when command blocks grow taller than usual."""
        if not command_blocks:
            return SUBSYSTEM_Y
        tallest_bottom = max(block.pos().y() + block.rect().height() for block in command_blocks)
        return max(SUBSYSTEM_Y, tallest_bottom + VERTICAL_GAP)

    def _add_block(
        self,
        element: Command | Subsystem,
        kind: str,
        index: int,
        y_position: int,
        layout: dict[str, dict[str, Any]],
        statuses: dict[UUID, ComparisonState],
        design_detail_lines: list[str] | None = None,
        device_count: int | None = None,
        devices_expanded: bool = False,
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
            device_count=device_count,
            devices_expanded=devices_expanded,
        )
        item_layout = layout.get(str(element.id), {})
        block.setPos(
            float(item_layout.get("x", index * (BLOCK_WIDTH + HORIZONTAL_GAP))),
            float(item_layout.get("y", y_position)),
        )
        block.set_minimized(bool(item_layout.get("minimized", False)))
        self.addItem(block)
        return block

    def _restore_device_view(self, layout: dict[str, dict[str, Any]]) -> None:
        """Adopt a saved device view, leaving the current one alone when none was saved.

        Auto Layout re-renders without a layout dict on purpose; the device view is a
        view toggle rather than a position, so it must survive that.
        """
        saved = layout.get(DEVICE_VIEW_LAYOUT_KEY)
        if not isinstance(saved, dict):
            return
        state = saved.get("state")
        if state in DEVICE_VIEW_STATES:
            self.device_view_state = state
        expanded = saved.get("expandedSubsystems")
        if isinstance(expanded, list):
            self.expanded_device_subsystems = {
                parsed
                for value in expanded
                if (parsed := self._parsed_uuid(value)) is not None
            }

    @staticmethod
    def _parsed_uuid(value: object) -> UUID | None:
        """Ignore a layout entry that is no longer a usable id rather than failing to open."""
        try:
            return UUID(str(value))
        except ValueError:
            return None

    def _devices_expanded_for(self, subsystem_id: UUID) -> bool:
        """Whether this subsystem's device blocks are drawn under the current view."""
        if self.device_view_state == "expanded":
            return True
        return (
            self.device_view_state == "grouped"
            and subsystem_id in self.expanded_device_subsystems
        )

    def toggle_subsystem_devices(self, subsystem_id: UUID) -> None:
        """Expand or collapse one subsystem's devices from its count chip."""
        if subsystem_id in self.expanded_device_subsystems:
            self.expanded_device_subsystems.discard(subsystem_id)
        else:
            self.expanded_device_subsystems.add(subsystem_id)
        self.device_view_changed.emit()

    def cycle_device_view(self) -> str:
        """Advance grouped -> expanded -> hidden, returning the newly active state."""
        index = DEVICE_VIEW_STATES.index(self.device_view_state)
        self.device_view_state = DEVICE_VIEW_STATES[(index + 1) % len(DEVICE_VIEW_STATES)]
        return self.device_view_state

    def _add_device_tier(
        self,
        project: ArchitectureProject,
        blocks: dict[UUID, ArchitectureBlock],
        layout: dict[str, dict[str, Any]],
        statuses: dict[UUID, ComparisonState],
        allocation_findings: dict[UUID, list[AllocationFinding]],
    ) -> None:
        """Lay visible devices out on a third row, grouped under the subsystem owning them.

        Groups are placed left to right in subsystem order and never overlap, so a
        forty-five device robot still reads as one band of hardware per subsystem.
        """
        subsystem_blocks = [
            blocks[subsystem.id] for subsystem in project.subsystems if subsystem.id in blocks
        ]
        row_y = self._device_row_y(subsystem_blocks)
        cursor_x = 0.0
        for subsystem in project.subsystems:
            owner_block = blocks.get(subsystem.id)
            devices = [
                device
                for device in project.devices
                if device.owner_subsystem_id == subsystem.id
            ]
            if owner_block is None or not devices:
                continue
            if not self._devices_expanded_for(subsystem.id):
                continue
            group_x = max(cursor_x, owner_block.pos().x())
            for index, device in enumerate(devices):
                block = self._add_device_block(device, subsystem, statuses, allocation_findings)
                item_layout = layout.get(str(device.id), {})
                block.setPos(
                    float(
                        item_layout.get(
                            "x", group_x + index * (DEVICE_BLOCK_WIDTH + DEVICE_HORIZONTAL_GAP)
                        )
                    ),
                    float(item_layout.get("y", row_y)),
                )
                self._add_design_relationship_edge(
                    owner_block,
                    block,
                    "owns_device",
                    tooltip=(
                        f"{subsystem.name.effective or 'Subsystem'} owns "
                        f"{device.name.effective or 'device'}"
                    ),
                )
            cursor_x = (
                group_x
                + len(devices) * (DEVICE_BLOCK_WIDTH + DEVICE_HORIZONTAL_GAP)
                + DEVICE_GROUP_GAP
            )

    @staticmethod
    def _device_row_y(subsystem_blocks: list[ArchitectureBlock]) -> float:
        """Open the device tier below the tallest subsystem, leaving both rows where they are."""
        if not subsystem_blocks:
            return SUBSYSTEM_Y + BLOCK_HEIGHT + DEVICE_TIER_GAP
        lowest = max(
            block.pos().y() + block.rect().height() for block in subsystem_blocks
        )
        return lowest + DEVICE_TIER_GAP

    def _add_device_block(
        self,
        device: Device,
        owner: Subsystem,
        statuses: dict[UUID, ComparisonState],
        allocation_findings: dict[UUID, list[AllocationFinding]],
    ) -> DeviceBlock:
        badge = " ".join(
            part for part in (device.bus.effective, device.address.effective) if part
        )
        block = DeviceBlock(
            device.id,
            owner.id,
            device.name.effective or "Unnamed",
            device.device_type.effective or "Device",
            badge,
            comparison_state=statuses.get(device.id, statuses.get(owner.id)),
            search_text=" ".join(
                filter(
                    None,
                    [
                        device.name.effective,
                        device.device_type.effective,
                        device.mode.effective,
                        device.bus.effective,
                        device.address.effective,
                        device.notes.effective,
                        owner.name.effective,
                    ],
                )
            ),
            findings=tuple(allocation_findings.get(device.id, [])),
        )
        self.addItem(block)
        return block

    def _add_imported_code(
        self,
        scan: ScanResult,
        command_offset: int,
        subsystem_offset: int,
        code_only_symbols: set[str] | None = None,
        subsystem_row_y: float = SUBSYSTEM_Y,
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
        imported_command_blocks: list[ArchitectureBlock] = []
        for kind, symbols, offset, y_position in (
            ("command", imported_commands, command_offset, COMMAND_Y),
            ("subsystem", subsystem_symbols, subsystem_offset, subsystem_row_y),
        ):
            if kind == "subsystem":
                y_position = max(y_position, self._subsystem_row_y(imported_command_blocks))
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
                else:
                    imported_command_blocks.append(block)
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
        state: dict[str, dict[str, Any]] = {
            str(item.element_id): {
                "x": item.pos().x(),
                "y": item.pos().y(),
                "minimized": item.minimized,
            }
            for item in self.items()
            if isinstance(item, CanvasBlock) and not item.imported
        }
        state[DEVICE_VIEW_LAYOUT_KEY] = {
            "state": self.device_view_state,
            "expandedSubsystems": sorted(
                str(subsystem_id) for subsystem_id in self.expanded_device_subsystems
            ),
        }
        return state

    def selected_blocks(self) -> list[ArchitectureBlock]:
        return [item for item in self.selectedItems() if isinstance(item, ArchitectureBlock)]

    def selected_device_blocks(self) -> list[DeviceBlock]:
        return [item for item in self.selectedItems() if isinstance(item, DeviceBlock)]

    def selected_canvas_blocks(self) -> list[CanvasBlock]:
        """Every selected block on any tier, for the drag, nudge and undo paths."""
        return [item for item in self.selectedItems() if isinstance(item, CanvasBlock)]

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
            if isinstance(item, CanvasBlock):
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
            visible = endpoint_ids <= visible_ids
            edge.setVisible(visible)
            marker = edge.data(4)
            if marker is not None:
                marker.setVisible(visible)

    @staticmethod
    def _block_state(block: CanvasBlock) -> ComparisonState:
        """An unscanned or purely imported block filters as UNRESOLVED, as it always has."""
        return block.comparison_state or ComparisonState.UNRESOLVED

    def _update_edge_visibility(self) -> None:
        selected_ids = {block.element_id for block in self.selected_canvas_blocks()}
        for edge in self._edges:
            endpoint_ids = edge.data(0)
            is_connected = bool(selected_ids & endpoint_ids)
            opacity = 1.0 if not selected_ids or is_connected else 0.16
            edge.setOpacity(opacity)
            edge.setPen(edge.data(1))
            if selected_ids and is_connected:
                active_pen = QPen(edge.data(1))
                active_pen.setStyle(Qt.PenStyle.SolidLine)
                active_pen.setWidthF(2.5)
                edge.setPen(active_pen)
            marker = edge.data(4)
            if marker is not None:
                marker.setOpacity(opacity)

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
        self,
        source: CanvasBlock,
        target: CanvasBlock,
        relationship_type: str,
        tooltip: str | None = None,
    ) -> None:
        """Render an explicit authored relationship with UML-flavored typed notation."""
        edge = QGraphicsPathItem(self._design_relationship_path(source, target))
        pen = QPen(QColor(MUTED_TEXT), 1.25, Qt.PenStyle.DotLine)
        edge.setPen(pen)
        edge.setData(0, {source.element_id, target.element_id})
        edge.setData(1, pen)
        edge.setData(2, "design_relationship")
        edge.setData(3, (source.element_id, target.element_id))
        edge.setData(5, relationship_type)
        edge.setToolTip(
            tooltip or f"Designed {relationship_type.replace('_', ' ')} relationship"
        )
        edge.setZValue(-1)
        self.addItem(edge)
        self._edges.append(edge)
        marker = self._create_relationship_marker(relationship_type)
        edge.setData(4, marker)
        if marker is not None:
            marker.setZValue(2)
            self.addItem(marker)
            self._position_relationship_marker(edge, source, target)

    @staticmethod
    def _create_relationship_marker(relationship_type: str) -> QGraphicsPolygonItem | None:
        """Give calls/triggers/contains/owns-device edges distinct arrow or diamond notation."""
        notation = RELATIONSHIP_MARKERS.get(relationship_type)
        if notation is None:
            return None
        _, filled = notation
        marker = QGraphicsPolygonItem()
        marker.setPen(QPen(QColor(MUTED_TEXT), 1.25))
        if filled:
            marker.setBrush(QColor(MUTED_TEXT))
        return marker

    def _position_relationship_marker(
        self, edge: QGraphicsPathItem, source: CanvasBlock, target: CanvasBlock
    ) -> None:
        marker = edge.data(4)
        if marker is None:
            return
        shape, _ = RELATIONSHIP_MARKERS[edge.data(5)]
        source_rect = source.sceneBoundingRect()
        target_rect = target.sceneBoundingRect()
        if shape == "arrow":
            # Read the tip/direction off the edge's actual (possibly routed-around-an-
            # obstacle) path rather than the straight line between centers, so the
            # arrowhead still points the way the line actually approaches the target.
            before, tip = edge_routing.last_segment_endpoints(edge.path())
            marker.setPolygon(self._arrow_polygon(tip, tip - before))
        else:
            base = self._clip_to_rect(source_rect, target_rect.center())
            marker.setPolygon(self._diamond_polygon(base))

    @staticmethod
    def _clip_to_rect(rect: QRectF, towards: QPointF) -> QPointF:
        """Find where a ray from a rect's center toward a point exits the rect's border.

        This is what makes connectors leave from whichever side actually faces the
        other endpoint, instead of a side fixed at creation time that looks wrong
        once a block is dragged elsewhere.
        """
        center = rect.center()
        dx = towards.x() - center.x()
        dy = towards.y() - center.y()
        if dx == 0 and dy == 0:
            return center
        half_width = rect.width() / 2
        half_height = rect.height() / 2
        scale_x = half_width / abs(dx) if dx != 0 else float("inf")
        scale_y = half_height / abs(dy) if dy != 0 else float("inf")
        scale = min(scale_x, scale_y)
        return QPointF(center.x() + dx * scale, center.y() + dy * scale)

    @staticmethod
    def _arrow_polygon(tip: QPointF, direction: QPointF, size: float = 8.0) -> QPolygonF:
        """Build a triangle pointing along `direction`, so it reads correctly at any angle."""
        length = (direction.x() ** 2 + direction.y() ** 2) ** 0.5 or 1.0
        unit_x, unit_y = direction.x() / length, direction.y() / length
        perp_x, perp_y = -unit_y, unit_x
        back_x, back_y = tip.x() - unit_x * size, tip.y() - unit_y * size
        return QPolygonF(
            [
                tip,
                QPointF(back_x + perp_x * size * 0.6, back_y + perp_y * size * 0.6),
                QPointF(back_x - perp_x * size * 0.6, back_y - perp_y * size * 0.6),
            ]
        )

    @staticmethod
    def _diamond_polygon(center: QPointF, size: float = 7.0) -> QPolygonF:
        return QPolygonF(
            [
                QPointF(center.x() - size, center.y()),
                QPointF(center.x(), center.y() - size * 0.6),
                QPointF(center.x() + size, center.y()),
                QPointF(center.x(), center.y() + size * 0.6),
            ]
        )

    def _obstacle_rects(self, exclude: set[ArchitectureBlock]) -> list[QRectF]:
        """Bounding rects of every other visible block, for routing lines around them."""
        return [
            item.sceneBoundingRect()
            for item in self.items()
            if isinstance(item, ArchitectureBlock) and item not in exclude and item.isVisible()
        ]

    def _requirement_path(
        self, command: ArchitectureBlock, subsystem: ArchitectureBlock
    ) -> QPainterPath:
        return self._anchored_line(
            command.sceneBoundingRect(),
            subsystem.sceneBoundingRect(),
            self._obstacle_rects({command, subsystem}),
        )

    def _design_relationship_path(
        self, source: CanvasBlock, target: CanvasBlock
    ) -> QPainterPath:
        return self._anchored_line(
            source.sceneBoundingRect(),
            target.sceneBoundingRect(),
            self._obstacle_rects({source, target}),
        )

    @classmethod
    def _anchored_line(
        cls, source_rect: QRectF, target_rect: QRectF, obstacles: list[QRectF] | None = None
    ) -> QPainterPath:
        """Straight between the two near-side points, routed around other blocks if in the way."""
        start = cls._clip_to_rect(source_rect, target_rect.center())
        end = cls._clip_to_rect(target_rect, source_rect.center())
        return edge_routing.route_edge(start, end, obstacles or [])

    def _update_edge_paths(self) -> None:
        """Rebuild curves from their endpoints after a block position changes."""
        blocks = {
            item.element_id: item
            for item in self.items()
            if isinstance(item, CanvasBlock)
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
                self._position_relationship_marker(edge, source, target)
