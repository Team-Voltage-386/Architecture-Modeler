"""Qt worker wrapper for cancellable Java project scans."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from frc_arch_modeler.importers.java.scanner import JavaProjectScanner, ScanCancelled


class JavaScanWorker(QObject):
    """Run tolerant file scanning outside the event loop and publish one outcome."""

    completed = Signal(object)
    failed = Signal(str)
    cancelled = Signal()
    progress = Signal(int, int)

    def __init__(self, root: Path) -> None:
        super().__init__()
        self.root = Path(root)
        self._cancel_requested = False

    def request_cancel(self) -> None:
        self._cancel_requested = True

    @Slot()
    def run(self) -> None:
        try:
            result = JavaProjectScanner().scan(
                self.root,
                lambda: self._cancel_requested,
                self.progress.emit,
            )
        except ScanCancelled:
            self.cancelled.emit()
        except (OSError, ValueError) as error:
            self.failed.emit(str(error))
        else:
            self.completed.emit(result)
