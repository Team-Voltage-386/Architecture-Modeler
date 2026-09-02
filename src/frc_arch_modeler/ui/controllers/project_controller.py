"""Model lifecycle: new/open/save, dirty state, draft autosave and close protection."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QFileDialog, QInputDialog, QLabel, QMessageBox

from frc_arch_modeler.domain.model import ArchitectureProject
from frc_arch_modeler.persistence.draft_store import DraftStore
from frc_arch_modeler.persistence.layout_store import LayoutStore

if TYPE_CHECKING:
    from frc_arch_modeler.ui.main_window import MainWindow


class ProjectController:
    """Own where the model lives on disk and whether it has unsaved changes."""

    def __init__(self, window: MainWindow) -> None:
        self.window = window

    def new_project(self, name: str) -> ArchitectureProject:
        """Create and display an unsaved design-only project."""
        window = self.window
        project = window.project_service.create(name)
        window.model_root = None
        window.set_project(project)
        window.is_dirty = True
        window.statusBar().showMessage(f"Unsaved design model: {project.name}")
        return project

    def open_project(self, root: Path) -> ArchitectureProject:
        """Load a saved model sidecar directory into the canvas."""
        window = self.window
        project = window.project_service.open(root)
        window.model_root = Path(root)
        draft = DraftStore(window.model_root).load()
        recovered = False
        if draft is not None and draft.to_dict() != project.to_dict():
            choice = QMessageBox.question(
                window,
                "Recover unsaved draft",
                "An autosaved draft differs from the saved model. Restore it?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if choice == QMessageBox.StandardButton.Yes:
                project = draft
                recovered = True
        window.set_project(project)
        layout_store = LayoutStore(window.model_root)
        loaded_layout = layout_store.load()
        window.scene.render_project(project, loaded_layout, window.last_scan)
        window.behavior_scene.render_diagram(window._active_behavior_diagram(), loaded_layout)
        self.restore_ui_preferences(layout_store.load_ui())
        window.recent_model_store.save(window.model_root)
        self.refresh_recent_model_action()
        if recovered:
            window.is_dirty = True
            window.statusBar().showMessage(f"Recovered unsaved draft: {project.name}")
        else:
            window.statusBar().showMessage(f"Opened design model: {project.name}")
        return project

    def save_project(self, root: Path | None = None) -> Path:
        """Persist the current design model and clear its dirty state."""
        window = self.window
        if window.project is None:
            raise RuntimeError("Create or open a model before saving.")
        if root is not None:
            window.model_root = Path(root)
        if window.model_root is None:
            raise RuntimeError("Choose a folder for the model before saving.")
        saved_path = window.project_service.save(window.model_root, window.project)
        combined_layout = {**window.scene.layout_state(), **window.behavior_scene.layout_state()}
        LayoutStore(window.model_root).save(combined_layout, self.ui_preferences())
        DraftStore(window.model_root).discard()
        window.is_dirty = False
        window.undo_stack.setClean()
        window.recent_model_store.save(window.model_root)
        self.refresh_recent_model_action()
        window.statusBar().showMessage(f"Saved design model: {saved_path}")
        self.update_status_indicators()
        return saved_path

    def mark_dirty(self, message: str) -> None:
        """Record an unsaved edit, autosaving a draft whenever the model has a home."""
        window = self.window
        window.is_dirty = True
        if window.project is not None and window.model_root is not None:
            DraftStore(window.model_root).save(window.project)
        window.statusBar().showMessage(message)
        self.update_status_indicators()

    def prompt_new_project(self) -> None:
        name, accepted = QInputDialog.getText(self.window, "New model", "Model name:")
        if accepted and name.strip():
            self.window.new_project(name.strip())

    def prompt_open_project(self) -> None:
        root = QFileDialog.getExistingDirectory(self.window, "Open architecture model")
        if root:
            try:
                self.window.open_project(Path(root))
            except ValueError as error:
                QMessageBox.critical(self.window, "Could not open model", str(error))

    def open_recent_model(self) -> None:
        recent_path = self.window.recent_model_store.load()
        if recent_path is None:
            return
        try:
            self.window.open_project(recent_path)
        except ValueError as error:
            QMessageBox.critical(self.window, "Could not open model", str(error))

    def refresh_recent_model_action(self) -> None:
        """Reflect the last-opened model (if any) on the Model menu's Recent entry."""
        recent_path = self.window.recent_model_store.load()
        action = self.window.open_recent_model_action
        action.setVisible(recent_path is not None)
        if recent_path is not None:
            action.setText(f"Recent: {recent_path.name}")
            action.setToolTip(str(recent_path))

    def prompt_save_project(self) -> None:
        if self.window.model_root is None:
            root = QFileDialog.getExistingDirectory(self.window, "Save architecture model")
            if not root:
                return
            self.window.save_project(Path(root))
        else:
            self.window.save_project()

    def handle_close_event(self, event: QCloseEvent) -> None:
        """Protect unsaved design and canvas edits when the main window closes."""
        window = self.window
        if not window.is_dirty or not window.isVisible():
            self._accept_or_wait(event)
            return
        choice = QMessageBox.warning(
            window,
            "Unsaved architecture model",
            "Save changes before closing?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if choice == QMessageBox.StandardButton.Discard:
            self._accept_or_wait(event)
            return
        if choice == QMessageBox.StandardButton.Save:
            try:
                self.prompt_save_project()
            except OSError as error:
                QMessageBox.critical(window, "Could not save model", str(error))
            if not window.is_dirty:
                self._accept_or_wait(event)
                return
        event.ignore()

    def _accept_or_wait(self, event: QCloseEvent) -> None:
        """Close only once the background scanner has released its Qt owner."""
        if self.window._stop_background_scan_for_close():
            event.accept()
        else:
            event.ignore()

    def ui_preferences(self) -> dict[str, int]:
        """Persist bounded presentation values separately from semantic design data."""
        return {
            "windowWidth": self.window.width(),
            "windowHeight": self.window.height(),
            "detailsWidth": self.window.details_dock.width(),
        }

    def restore_ui_preferences(self, preferences: dict[str, object]) -> None:
        """Restore only reasonable dimensions so changed monitor setups remain usable."""
        window = self.window
        width = preferences.get("windowWidth")
        height = preferences.get("windowHeight")
        if isinstance(width, int) and isinstance(height, int):
            window.resize(min(max(width, 800), 2560), min(max(height, 600), 1600))
        details_width = preferences.get("detailsWidth")
        if isinstance(details_width, int) and 180 <= details_width <= 900:
            window.resizeDocks(
                [window.details_dock], [details_width], Qt.Orientation.Horizontal
            )
        window._update_details_presentation()

    def build_status_bar(self) -> None:
        """Reserve the plan's persistent status fields alongside transient action messages."""
        window = self.window
        bar = window.statusBar()
        window.status_project_label = QLabel("No model", window)
        window.status_scan_label = QLabel("No robot project connected", window)
        window.status_warnings_label = QLabel("", window)
        window.status_dirty_label = QLabel("", window)
        for label in (
            window.status_project_label,
            window.status_scan_label,
            window.status_warnings_label,
            window.status_dirty_label,
        ):
            label.setContentsMargins(8, 0, 8, 0)
            bar.addPermanentWidget(label)
        self.update_status_indicators()

    def update_status_indicators(self) -> None:
        """Keep the persistent status fields current without disturbing action messages."""
        window = self.window
        window.status_project_label.setText(
            f"Model: {window.project.name}" if window.project is not None else "No model"
        )
        if window.robot_project_root is not None:
            scan_time = window._last_scan_time or "not scanned yet"
            revision = f" @ {window._git_revision_text}" if window._git_revision_text else ""
            window.status_scan_label.setText(
                f"Robot: {window.robot_project_root.name}{revision} · scanned {scan_time}"
            )
        else:
            window.status_scan_label.setText("No robot project connected")
        warning_count = len(window.last_scan.diagnostics) if window.last_scan is not None else 0
        window.status_warnings_label.setText(
            f"{warning_count} parse warning(s)" if window.last_scan is not None else ""
        )
        window.status_dirty_label.setText("● Unsaved" if window.is_dirty else "Saved")

    @staticmethod
    def git_revision(root: Path) -> str | None:
        """Best-effort short revision when Git is available; never blocks on a scan."""
        try:
            result = subprocess.run(
                ["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
                capture_output=True,
                text=True,
                timeout=2,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if result.returncode != 0:
            return None
        return result.stdout.strip() or None
