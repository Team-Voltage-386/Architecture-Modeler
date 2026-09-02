"""Both canvases: scene wiring, selection routing, layout moves, zoom and minimize."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QGraphicsView, QTabWidget, QVBoxLayout, QWidget

from frc_arch_modeler.ui.architecture_scene import ArchitectureBlock
from frc_arch_modeler.ui.undo_commands import MoveBlocksCommand

if TYPE_CHECKING:
    from frc_arch_modeler.ui.main_window import MainWindow


class CanvasController:
    """Keep the two graphics views, their selection state and their layout in step."""

    def __init__(self, window: MainWindow) -> None:
        self.window = window

    # -- construction -----------------------------------------------------

    def connect_scenes(self) -> None:
        """Route both scenes' edit signals to the controllers that handle them.

        Called before the views exist, so it must only touch the scenes themselves.
        """
        window = self.window
        window.scene.layout_changed.connect(window._layout_changed)
        window.scene.layout_move_completed.connect(window._record_layout_move)
        window.scene.block_double_clicked.connect(window._open_compact_details)
        window.scene.delete_requested.connect(window._confirm_delete_selected)
        window.scene.connection_requested.connect(window._handle_connection_requested)
        window.behavior_scene.layout_move_completed.connect(window._record_behavior_layout_move)
        window.behavior_scene.delete_requested.connect(window._confirm_delete_selected)
        window.behavior_scene.connection_requested.connect(
            window._handle_behavior_connection_requested
        )
        window.behavior_scene.state_double_clicked.connect(window._prompt_rename_behavior_state)
        window.behavior_scene.transition_delete_requested.connect(
            window._delete_behavior_transition
        )
        window.behavior_scene.transition_reattach_requested.connect(
            window._reattach_behavior_transition
        )
        window.behavior_scene.transition_anchor_changed.connect(window._behavior_layout_changed)

    def build_canvas(self) -> None:
        """Create both views and the tab widget that switches between them."""
        window = self.window
        window.canvas = QGraphicsView(window.scene, window)
        window.canvas.setAccessibleName("Architecture canvas")
        window.canvas.setRenderHint(QPainter.RenderHint.Antialiasing)
        window.canvas.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        window.canvas.setBackgroundBrush(Qt.GlobalColor.black)
        # Every connection below targets a bound method of the window, never of this
        # controller: Qt only auto-disconnects a slot when its receiver is a QObject it
        # can watch, and a plain controller left these firing against a deleted scene.
        window.scene.selectionChanged.connect(window._update_selected_element)
        window.scene.selectionChanged.connect(window._update_bind_selected_action)
        window.scene.selectionChanged.connect(window._update_delete_selected_action)
        window.scene.selectionChanged.connect(window._update_link_selected_action)

        window.behavior_canvas = QGraphicsView(window.behavior_scene, window)
        window.behavior_canvas.setAccessibleName("Behavior canvas")
        window.behavior_canvas.setRenderHint(QPainter.RenderHint.Antialiasing)
        window.behavior_canvas.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        window.behavior_canvas.setBackgroundBrush(Qt.GlobalColor.black)
        window._build_behavior_toolbar()

        window._behavior_tab = QWidget(window)
        behavior_layout = QVBoxLayout(window._behavior_tab)
        behavior_layout.setContentsMargins(0, 0, 0, 0)
        behavior_layout.setSpacing(0)
        behavior_layout.addWidget(window.behavior_toolbar)
        behavior_layout.addWidget(window.behavior_canvas)

        window.diagram_tabs = QTabWidget(window)
        window.diagram_tabs.addTab(window.canvas, "Structure")
        window.diagram_tabs.addTab(window._behavior_tab, "Behavior")
        window.diagram_tabs.currentChanged.connect(window._update_delete_selected_action)
        window.behavior_scene.selectionChanged.connect(window._update_delete_selected_action)
        window.setCentralWidget(window.diagram_tabs)

    # -- rendering --------------------------------------------------------

    def render_with_current_scan(self) -> None:
        window = self.window
        window.scene.render_project(
            window.project,
            layout=window.scene.layout_state(),
            scan=window.last_scan,
            statuses=window._comparison_statuses(),
            code_only_symbols=window._code_only_symbols(),
        )

    def render_preserving_selection(self) -> None:
        """Refresh block text without disrupting the active details context."""
        window = self.window
        selected_ids = {block.element_id for block in window.scene.selected_blocks()}
        self.render_with_current_scan()
        for item in window.scene.items():
            if isinstance(item, ArchitectureBlock) and item.element_id in selected_ids:
                item.setSelected(True)

    def toggle_command_forms(self, visible: bool) -> None:
        """Keep inline forms in the inventory unless the user explicitly expands the canvas."""
        self.window.scene.show_command_forms = visible
        self.render_with_current_scan()

    def auto_layout(self) -> None:
        """Restore the deterministic layout without changing design intent."""
        window = self.window
        if window.project is None:
            return
        window.scene.render_project(window.project, scan=window.last_scan)
        window._mark_dirty("Auto-layout applied")

    # -- action enablement ------------------------------------------------

    def apply_status_filters(self) -> None:
        window = self.window
        window.scene.set_status_filter(
            {
                state
                for state, action in window._status_filter_actions.items()
                if action.isChecked()
            }
        )

    def update_bind_selected_action(self) -> None:
        window = self.window
        blocks = window.scene.selected_blocks()
        window.bind_selected_action.setEnabled(
            len(blocks) == 2
            and {block.imported for block in blocks} == {False, True}
            and blocks[0].kind == blocks[1].kind
            and window.project is not None
            and window.last_scan is not None
        )

    def update_delete_selected_action(self) -> None:
        """Route the single Delete action/shortcut to whichever diagram tab is active."""
        window = self.window
        if window.diagram_tabs.currentWidget() is window._behavior_tab:
            blocks = window.behavior_scene.selected_blocks()
            transitions = window.behavior_scene.selected_transition_ids()
            window.delete_selected_action.setEnabled(
                window._active_behavior_diagram() is not None
                and ((len(blocks) == 1) != (len(transitions) == 1))
            )
            return
        blocks = window.scene.selected_blocks()
        window.delete_selected_action.setEnabled(
            window.project is not None and len(blocks) == 1 and not blocks[0].imported
        )

    def update_link_selected_action(self) -> None:
        """Enable the direct drafting shortcut for a command/subsystem pair."""
        window = self.window
        blocks = window.scene.selected_blocks()
        window.link_selected_action.setEnabled(
            window.project is not None
            and len(blocks) == 2
            and not any(block.imported for block in blocks)
            and {block.kind for block in blocks} == {"command", "subsystem"}
        )

    # -- view state -------------------------------------------------------

    def zoom_to_fit(self) -> None:
        """Fit the current design into the visible canvas without changing it."""
        self._fit_view_to_items(self.window.canvas, self.window.scene)

    def behavior_zoom_to_fit(self) -> None:
        """Fit the current behavior diagram into the visible canvas without changing it."""
        self._fit_view_to_items(self.window.behavior_canvas, self.window.behavior_scene)

    @staticmethod
    def _fit_view_to_items(view: QGraphicsView, scene) -> None:  # type: ignore[no-untyped-def]
        """Fit the view to the actual item bounds, not the padded sceneRect, so
        content fills the canvas instead of appearing small and off-centre."""
        bounds = scene.itemsBoundingRect()
        if bounds.isEmpty():
            return
        margin = 20
        bounds = bounds.adjusted(-margin, -margin, margin, margin)
        view.fitInView(bounds, Qt.AspectRatioMode.KeepAspectRatio)

    def minimize_selected(self) -> None:
        if self.window.scene.set_selected_minimized(True):
            self.window._mark_dirty("Selected items minimized")

    def restore_selected(self) -> None:
        if self.window.scene.set_selected_minimized(False):
            self.window._mark_dirty("Selected items restored")

    # -- layout moves -----------------------------------------------------

    def layout_changed(self) -> None:
        self.window._mark_dirty("Canvas layout updated")

    def record_layout_move(self, before, after) -> None:  # type: ignore[no-untyped-def]
        """Place completed drags on the normal undo stack after Qt releases the mouse."""
        self.window.undo_stack.push(
            MoveBlocksCommand(self.window.scene, before, after, self.layout_changed)
        )

    def sync_left_dock_to_active_tab(self, index: int) -> None:
        """Show the behavior model browser only while the Behavior tab is active."""
        window = self.window
        on_behavior = window.diagram_tabs.currentWidget() is window._behavior_tab
        window._left_dock_stack.setCurrentWidget(
            window.behavior_model_browser if on_behavior else window.inventory_tree
        )
        window._left_dock.setWindowTitle(
            "Behavior Diagrams" if on_behavior else "Code Inventory"
        )
        window.help_panel.set_active_context("behavior" if on_behavior else "structure")
