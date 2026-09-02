"""Both export paths: the Architecture document and the AI change request."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QFileDialog

from frc_arch_modeler.services.change_request_export import ChangeRequestExportService
from frc_arch_modeler.services.export_service import ArchitectureExportService
from frc_arch_modeler.services.reconcile_service import ReconciliationService

if TYPE_CHECKING:
    from frc_arch_modeler.ui.main_window import MainWindow


class ExportController:
    """Turn the current design, scan and comparison into Markdown on disk."""

    def __init__(self, window: MainWindow) -> None:
        self.window = window
        self.export_service = ArchitectureExportService()
        self.change_request_export_service = ChangeRequestExportService()

    def export_architecture(self, root: Path | None = None) -> Path:
        """Write a deterministic Architecture Markdown document for the current design."""
        window = self.window
        if window.project is None:
            raise RuntimeError("Create or open a model before exporting.")
        export_root = Path(root) if root is not None else window.model_root
        if export_root is None:
            raise RuntimeError("Choose a folder for the architecture export.")
        destination = self.export_service.export(
            export_root, window.project, window.last_scan, window.reconciliation
        )
        window.statusBar().showMessage(f"Exported architecture: {destination}")
        return destination

    def export_change_request(self, root: Path | None = None) -> Path:
        """Export the current design/code delta as an implementation-ready Markdown brief."""
        window = self.window
        if window.project is None or window.last_scan is None:
            raise RuntimeError(
                "Create a model and connect a robot project before exporting changes."
            )
        export_root = Path(root) if root is not None else window.model_root
        if export_root is None:
            raise RuntimeError("Choose a folder for the change-request export.")
        comparison = window.reconciliation or ReconciliationService().reconcile(
            window.project, window.last_scan
        )
        destination = self.change_request_export_service.export(
            export_root, window.project, window.last_scan, comparison
        )
        window.statusBar().showMessage(f"Exported AI change request: {destination}")
        return destination

    def prompt_export_architecture(self) -> None:
        root = self.window.model_root
        if root is None:
            selected_root = QFileDialog.getExistingDirectory(self.window, "Export architecture")
            if not selected_root:
                return
            root = Path(selected_root)
        self.window.export_architecture(root)

    def prompt_export_change_request(self) -> None:
        root = self.window.model_root
        if root is None:
            selected_root = QFileDialog.getExistingDirectory(
                self.window, "Export AI change request"
            )
            if not selected_root:
                return
            root = Path(selected_root)
        self.window.export_change_request(root)
