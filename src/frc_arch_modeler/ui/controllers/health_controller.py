"""Model Health: recomputing findings off the paint path, revealing them, fixing them.

The rules themselves live in `services.health_service`; this controller only decides
*when* to ask for them, where the offending element lives, and how a fix reaches the
undo stack.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QDockWidget, QLabel

from frc_arch_modeler.services.health_service import (
    FIX_ASSIGN_NEXT_FREE_ADDRESS,
    FIX_REMOVE_ORPHANED_RELATIONSHIP,
    HealthFinding,
    HealthService,
)
from frc_arch_modeler.ui.architecture_scene import CanvasBlock
from frc_arch_modeler.ui.behavior_scene import StateBlock
from frc_arch_modeler.ui.details_panel import EditEntityFieldsCommand
from frc_arch_modeler.ui.health_panel import HealthPanel, summary_text
from frc_arch_modeler.ui.undo_commands import RemoveDesignEntityCommand

if TYPE_CHECKING:
    from frc_arch_modeler.ui.main_window import MainWindow

#: Milliseconds of quiet before findings are recomputed. Long enough that a burst of
#: edits (a drag, a cascading delete, a template insertion) recomputes once, short
#: enough that the panel still feels live.
RECOMPUTE_DELAY_MS = 250


class HealthController:
    """Own the Model Health dock, its debounce timer and its status-bar count."""

    def __init__(self, window: MainWindow) -> None:
        self.window = window
        self.service = HealthService()
        self.findings: list[HealthFinding] = []

    # -- construction -----------------------------------------------------

    def build_health_dock(self) -> None:
        window = self.window
        dock = QDockWidget("Model Health", window)
        dock.setObjectName("healthDock")
        window.health_panel = HealthPanel(dock)
        # Both connections target bound methods of the window: Qt only auto-disconnects
        # a slot whose receiver is a QObject it can watch.
        window.health_panel.finding_activated.connect(window._reveal_health_finding)
        window.health_panel.fix_requested.connect(window._apply_health_fix)
        dock.setWidget(window.health_panel)
        window.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
        dock.setVisible(False)
        window.health_dock = dock
        window.toggle_health_action = dock.toggleViewAction()
        window.toggle_health_action.setText("Model Health")
        window._set_action_help(
            window.toggle_health_action,
            "Show or hide the Model Health panel, which lists what is incomplete or "
            "wrong in the model and takes you straight to the element it is about.",
        )
        # Recomputation is queued on a single-shot timer owned by the window, so a burst
        # of edits costs one pass and none of it happens while a canvas is painting.
        window._health_timer = QTimer(window)
        window._health_timer.setSingleShot(True)
        window._health_timer.setInterval(RECOMPUTE_DELAY_MS)
        window._health_timer.timeout.connect(window._refresh_model_health)

    def build_status_badge(self) -> None:
        window = self.window
        window.status_health_label = QLabel("", window)
        window.status_health_label.setObjectName("statusHealthLabel")
        window.status_health_label.setContentsMargins(8, 0, 8, 0)
        window.statusBar().addPermanentWidget(window.status_health_label)

    # -- recomputation ----------------------------------------------------

    def schedule_refresh(self) -> None:
        """Coalesce every edit in this burst into one later recomputation."""
        self.window._health_timer.start()

    def refresh(self) -> None:
        """Recompute now and repaint the panel and the status-bar count."""
        window = self.window
        self.findings = self.service.check(window.project)
        window.health_panel.set_findings(self.findings, has_project=window.project is not None)
        self._update_status_badge()

    def _update_status_badge(self) -> None:
        window = self.window
        if window.project is None:
            window.status_health_label.setText("")
            return
        count = len(self.findings)
        window.status_health_label.setText(
            "Health: OK" if not count else f"Health: {count} ({summary_text(self.findings)})"
        )
        window.status_health_label.setToolTip(
            "Model Health findings. Open the Model Health panel to work through them."
        )

    # -- reveal -----------------------------------------------------------

    def reveal(self, finding: HealthFinding) -> bool:
        """Select the element a finding is about, on whichever canvas owns it."""
        if not finding.entity_ids:
            return False
        entity_id = finding.entity_ids[0]
        if finding.diagram_id is not None:
            return self._reveal_in_behavior(finding.diagram_id, entity_id)
        return self._reveal_in_structure(entity_id)

    def _reveal_in_structure(self, entity_id: UUID) -> bool:
        window = self.window
        window.diagram_tabs.setCurrentIndex(0)
        if self._select_structure_block(entity_id):
            return True
        # A device can be hidden inside a collapsed subsystem group; expand only the
        # group that owns it rather than changing the whole device view.
        devices = window.project.devices if window.project is not None else []
        device = next((item for item in devices if item.id == entity_id), None)
        if device is None:
            return False
        window.scene.expanded_device_subsystems.add(device.owner_subsystem_id)
        window.canvas_controller.render_with_current_scan()
        return self._select_structure_block(entity_id)

    def _select_structure_block(self, entity_id: UUID) -> bool:
        window = self.window
        window.scene.clearSelection()
        for item in window.scene.items():
            if isinstance(item, CanvasBlock) and item.element_id == entity_id:
                item.setSelected(True)
                window.canvas.centerOn(item)
                return True
        return False

    def _reveal_in_behavior(self, diagram_id: UUID, entity_id: UUID) -> bool:
        window = self.window
        window.diagram_tabs.setCurrentIndex(1)
        if window._selected_behavior_diagram_id != diagram_id:
            window._select_behavior_diagram(diagram_id)
        window.behavior_scene.clearSelection()
        if entity_id == diagram_id:
            return True
        for item in window.behavior_scene.items():
            if isinstance(item, StateBlock) and item.state_id == entity_id:
                item.setSelected(True)
                window.behavior_canvas.centerOn(item)
                return True
        edge = window.behavior_scene.edge_for_transition(entity_id)
        if edge is not None:
            edge.setSelected(True)
            window.behavior_canvas.centerOn(edge)
            return True
        return False

    # -- fixes ------------------------------------------------------------

    def apply_fix(self, finding: HealthFinding) -> bool:
        """Apply an unambiguous fix as one undoable command. Never called automatically."""
        window = self.window
        if window.project is None or finding.fix_action is None or not finding.entity_ids:
            return False
        entity_id = finding.entity_ids[0]
        if finding.fix_action == FIX_ASSIGN_NEXT_FREE_ADDRESS and finding.fix_value:
            device = next(
                (item for item in window.project.devices if item.id == entity_id), None
            )
            if device is None:
                return False
            window.undo_stack.push(
                EditEntityFieldsCommand(
                    device,
                    {"address": finding.fix_value},
                    "device address",
                    window._refresh_after_hardware_edit,
                )
            )
            window._mark_dirty(f"Assigned address {finding.fix_value} to {_device_name(device)}")
            return True
        if finding.fix_action == FIX_REMOVE_ORPHANED_RELATIONSHIP:
            relationship = next(
                (item for item in window.project.relationships if item.id == entity_id), None
            )
            if relationship is None:
                return False
            window.undo_stack.push(
                RemoveDesignEntityCommand(
                    window.project.relationships,
                    relationship,
                    "orphaned relationship",
                    window._refresh_after_edit,
                )
            )
            window._mark_dirty("Removed an orphaned relationship")
            return True
        return False


def _device_name(device) -> str:  # type: ignore[no-untyped-def]
    return device.name.effective or "Unnamed"
