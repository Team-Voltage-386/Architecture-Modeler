"""Code-scan lifecycle: connect, refresh, cancel, compare, accept and bind."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QThread
from PySide6.QtWidgets import QFileDialog, QTreeWidgetItem

from frc_arch_modeler.domain.model import SourceAnchor
from frc_arch_modeler.importers.base import ScanResult
from frc_arch_modeler.importers.java.scanner import JavaProjectScanner
from frc_arch_modeler.services.reconcile_service import ReconciliationResult, ReconciliationService
from frc_arch_modeler.ui.controllers.project_controller import ProjectController
from frc_arch_modeler.ui.scan_worker import JavaScanWorker

if TYPE_CHECKING:
    from frc_arch_modeler.ui.main_window import MainWindow


class ScanController:
    """Own the background scanner thread and everything derived from a scan."""

    def __init__(self, window: MainWindow) -> None:
        self.window = window
        self.scan_thread: QThread | None = None
        self.scan_worker: JavaScanWorker | None = None
        self.pending_scan_root: Path | None = None
        self.pending_scan_action = "Connected"
        self.inventory_symbols: dict[str, object] = {}

    # -- scanning ---------------------------------------------------------

    def connect_robot_project(self, root: Path) -> ScanResult:
        """Scan a Java/WPILib project without altering the user-authored design."""
        root = Path(root)
        scan = JavaProjectScanner().scan(root)
        self.apply_scan(root, scan, "Connected")
        return scan

    def refresh_robot_project(self) -> ScanResult | None:
        """Refresh the current code-derived inventory while retaining design edits."""
        window = self.window
        if window.robot_project_root is None:
            return None
        scan = JavaProjectScanner().scan(window.robot_project_root)
        self.apply_scan(window.robot_project_root, scan, "Refreshed")
        return scan

    def refresh_robot_project_async(self) -> None:
        if self.window.robot_project_root is not None:
            self.start_scan(self.window.robot_project_root, "Refreshed")

    def apply_scan(self, root: Path, scan: ScanResult, action: str) -> None:
        """Apply a completed scan atomically to the visible, regenerable code layer."""
        window = self.window
        window.robot_project_root = root
        window.last_scan = scan
        window.reconciliation = None
        window._last_scan_time = datetime.now().strftime("%H:%M:%S")
        window._git_revision_text = ProjectController.git_revision(root)
        window.refresh_code_action.setEnabled(True)
        window.compare_action.setEnabled(window.project is not None)
        window.export_change_request_action.setEnabled(window.project is not None)
        window._render_with_current_scan()
        self._show_scan_inventory()
        self._show_scan_status(action)
        window._update_status_indicators()

    def start_scan(self, root: Path, action: str) -> None:
        """Run a toolbar-initiated scan off the UI thread, preserving the old view on failure."""
        window = self.window
        if self.scan_thread is not None:
            return
        self.pending_scan_root = Path(root)
        self.pending_scan_action = action
        thread = QThread(window)
        worker = JavaScanWorker(self.pending_scan_root)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        # The worker lives on another thread, so these must connect to bound methods of
        # the window: Qt queues a cross-thread signal onto the receiver QObject's thread
        # and drops it once that object dies. A plain controller receiver has neither
        # affinity nor lifetime, and would run these handlers on the worker thread.
        worker.completed.connect(window._scan_completed)
        worker.failed.connect(window._scan_failed)
        worker.cancelled.connect(window._scan_cancelled)
        worker.progress.connect(window._scan_progress)
        self.scan_thread = thread
        self.scan_worker = worker
        window.connect_robot_action.setEnabled(False)
        window.refresh_code_action.setEnabled(False)
        window.cancel_scan_action.setEnabled(True)
        window.statusBar().showMessage(f"{action} Java project in background…")
        thread.start()

    def cancel_scan(self) -> None:
        if self.scan_worker is not None:
            self.scan_worker.request_cancel()
            self.window.statusBar().showMessage("Cancelling Java project scan…")

    def stop_background_scan_for_close(self) -> bool:
        """Cancel a live worker before destroying its Qt owner during window shutdown."""
        if self.scan_thread is None:
            return True
        self.cancel_scan()
        if not self.scan_thread.wait(1500):
            self.window.statusBar().showMessage(
                "Waiting for the code scan to cancel before closing."
            )
            return False
        self.scan_thread = None
        self.scan_worker = None
        self.pending_scan_root = None
        return True

    def scan_progress(self, completed: int, total: int) -> None:
        self.window.statusBar().showMessage(
            f"{self.pending_scan_action} Java project in background… {completed}/{total} files"
        )

    def scan_completed(self, scan: ScanResult) -> None:
        assert self.pending_scan_root is not None
        self.apply_scan(self.pending_scan_root, scan, self.pending_scan_action)
        self._finish_background_scan()

    def scan_failed(self, message: str) -> None:
        self.window.statusBar().showMessage(f"Code scan failed: {message}")
        self._finish_background_scan()

    def scan_cancelled(self) -> None:
        self.window.statusBar().showMessage(
            "Code scan cancelled; prior code view was retained."
        )
        self._finish_background_scan()

    def _finish_background_scan(self) -> None:
        window = self.window
        if self.scan_thread is not None:
            self.scan_thread.quit()
            self.scan_thread.wait()
            self.scan_thread.deleteLater()
        if self.scan_worker is not None:
            self.scan_worker.deleteLater()
        self.scan_thread = None
        self.scan_worker = None
        self.pending_scan_root = None
        window.connect_robot_action.setEnabled(True)
        window.refresh_code_action.setEnabled(window.robot_project_root is not None)
        window.cancel_scan_action.setEnabled(False)

    def prompt_connect_robot_project(self) -> None:
        root = QFileDialog.getExistingDirectory(
            self.window, "Connect Java/WPILib robot project"
        )
        if root:
            self.start_scan(Path(root), "Connected")

    # -- scan presentation ------------------------------------------------

    def _show_scan_status(self, action: str) -> None:
        window = self.window
        assert window.robot_project_root is not None
        assert window.last_scan is not None
        subsystem_count = len(window.last_scan.symbols_of_kind("subsystem"))
        command_count = len(window.last_scan.symbols_of_kind("command"))
        factory_count = len(window.last_scan.symbols_of_kind("command_factory"))
        form_count = len(window.last_scan.symbols_of_kind("command_composition"))
        trigger_count = len(window.last_scan.triggers)
        device_count = len(window.last_scan.devices)
        diagnostic_count = len(window.last_scan.diagnostics)
        window.statusBar().showMessage(
            f"{action} {window.robot_project_root.name}: {subsystem_count} subsystems, "
            f"{command_count} commands, {factory_count} factories, {form_count} forms, "
            f"{trigger_count} triggers, {device_count} devices, {diagnostic_count} warnings"
        )

    def _show_scan_inventory(self) -> None:
        window = self.window
        assert window.last_scan is not None
        window.inventory_tree.clear()
        self.inventory_symbols = {}
        labels = {
            "subsystem": "Subsystems",
            "command": "Commands",
            "command_factory": "Command factories",
            "command_composition": "Command forms and groups",
            "command_registration": "Default and autonomous commands",
            "lifecycle_method": "Lifecycle methods",
        }
        groups: dict[str, QTreeWidgetItem] = {}
        for kind, label in labels.items():
            symbols = window.last_scan.symbols_of_kind(kind)
            if symbols:
                group = QTreeWidgetItem([label, ""])
                window.inventory_tree.addTopLevelItem(group)
                groups[kind] = group
        for symbol in window.last_scan.symbols:
            group = groups.get(symbol.kind)
            if group is not None:
                item = QTreeWidgetItem(
                    [symbol.name, f"{symbol.anchor.relative_path}:{symbol.anchor.start_line}"]
                )
                item.setData(0, Qt.ItemDataRole.UserRole, symbol.anchor.qualified_symbol)
                self.inventory_symbols[symbol.anchor.qualified_symbol] = symbol
                group.addChild(item)
        if window.last_scan.triggers:
            trigger_group = QTreeWidgetItem(["Trigger bindings", ""])
            window.inventory_tree.addTopLevelItem(trigger_group)
            for index, trigger in enumerate(window.last_scan.triggers):
                key = f"trigger:{index}"
                item = QTreeWidgetItem(
                    [
                        f"{trigger.controller_expression} · {trigger.activation}",
                        f"{trigger.anchor.relative_path}:{trigger.anchor.start_line}",
                    ]
                )
                item.setData(0, Qt.ItemDataRole.UserRole, key)
                self.inventory_symbols[key] = trigger
                trigger_group.addChild(item)
        if window.last_scan.devices:
            device_group = QTreeWidgetItem(["Devices", ""])
            window.inventory_tree.addTopLevelItem(device_group)
            for index, device in enumerate(window.last_scan.devices):
                key = f"device:{index}"
                item = QTreeWidgetItem(
                    [
                        self._device_inventory_label(device),
                        f"{device.anchor.relative_path}:{device.anchor.start_line}",
                    ]
                )
                item.setData(0, Qt.ItemDataRole.UserRole, key)
                self.inventory_symbols[key] = device
                device_group.addChild(item)
        if window.last_scan.diagnostics:
            diagnostic_group = QTreeWidgetItem(["Scan diagnostics", ""])
            window.inventory_tree.addTopLevelItem(diagnostic_group)
            for diagnostic in window.last_scan.diagnostics:
                diagnostic_group.addChild(
                    QTreeWidgetItem([diagnostic.message, diagnostic.relative_path or ""])
                )
        window.inventory_tree.expandAll()

    @staticmethod
    def _device_inventory_label(device) -> str:  # type: ignore[no-untyped-def]
        resolved = (
            f" → {device.resolved_arguments}" if device.resolved_arguments is not None else ""
        )
        return f"{device.device_type} ({device.constructor_arguments}{resolved})"

    def open_inventory_source(self, item: QTreeWidgetItem, column: int) -> None:
        symbol_name = item.data(0, Qt.ItemDataRole.UserRole)
        symbol = self.inventory_symbols.get(symbol_name)
        if symbol is None or self.window.robot_project_root is None:
            return
        self.window._open_source_anchor(symbol.anchor)

    # -- reconciliation ---------------------------------------------------

    def compare_changes(self) -> ReconciliationResult | None:
        """Display a non-destructive design/code comparison on the canvas."""
        window = self.window
        if window.project is None or window.last_scan is None:
            return None
        reconciliation_service = ReconciliationService()
        window.reconciliation = reconciliation_service.reconcile(window.project, window.last_scan)
        reconciliation_service.populate_scanned_fields(window.project, window.reconciliation)
        window._render_with_current_scan()
        window.accept_matches_action.setEnabled(bool(window.reconciliation.matches))
        matched = len(window.reconciliation.matches)
        design_only = sum(
            state.value == "design_only" for state in window.reconciliation.statuses.values()
        )
        window.statusBar().showMessage(
            f"Comparison: {matched} matched, {design_only} design-only"
        )
        return window.reconciliation

    def accept_matches(self) -> int:
        """Persist the currently suggested unambiguous bindings after user confirmation."""
        window = self.window
        if window.project is None or window.reconciliation is None:
            return 0
        accepted = ReconciliationService.accept_matches(window.project, window.reconciliation)
        if accepted:
            window._mark_dirty(f"Accepted {accepted} code binding(s)")
        window.accept_matches_action.setEnabled(False)
        return accepted

    def bind_selected(self) -> bool:
        """Persist an explicit design-to-code binding selected by the user."""
        window = self.window
        if window.project is None or window.last_scan is None:
            return False
        blocks = window.scene.selected_blocks()
        if len(blocks) != 2:
            return False
        design_block = next((block for block in blocks if not block.imported), None)
        code_block = next((block for block in blocks if block.imported), None)
        if design_block is None or code_block is None or design_block.kind != code_block.kind:
            return False
        if not isinstance(code_block.source_anchor, SourceAnchor):
            return False
        element = next(
            (
                item
                for item in [*window.project.commands, *window.project.subsystems]
                if item.id == design_block.element_id
            ),
            None,
        )
        if element is None:
            return False
        element.code_binding = code_block.source_anchor
        code_name = code_block.title.toPlainText()
        reconciliation_service = ReconciliationService()
        window.reconciliation = reconciliation_service.reconcile(window.project, window.last_scan)
        reconciliation_service.populate_scanned_fields(window.project, window.reconciliation)
        window._render_with_current_scan()
        window._mark_dirty(f"Bound {element.name.effective} to {code_name}")
        return True

    def comparison_statuses(self) -> dict:
        window = self.window
        return window.reconciliation.statuses if window.reconciliation is not None else {}

    def code_only_symbols(self) -> set[str]:
        if self.window.reconciliation is None:
            return set()
        return {
            symbol.anchor.qualified_symbol for symbol in self.window.reconciliation.code_only
        }
