"""Read-only source inspection for code-derived architecture evidence."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QDialog, QPlainTextEdit, QVBoxLayout

from frc_arch_modeler.domain.model import SourceAnchor


class SourceViewerDialog(QDialog):
    """Display the source file identified by a portable source anchor."""

    def __init__(self, root: Path, anchor: SourceAnchor, parent: object | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Source: {anchor.qualified_symbol}")
        self.resize(900, 650)
        self.editor = QPlainTextEdit(self)
        self.editor.setObjectName("sourceViewer")
        self.editor.setReadOnly(True)
        self.editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        layout = QVBoxLayout(self)
        layout.addWidget(self.editor)
        self._load_source(root, anchor)

    def _load_source(self, root: Path, anchor: SourceAnchor) -> None:
        source_path = Path(root) / anchor.relative_path
        try:
            source = source_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            self.editor.setPlainText(f"Could not open {anchor.relative_path}:\n{error}")
            return
        self.editor.setPlainText(source)
        cursor = self.editor.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        cursor.movePosition(QTextCursor.MoveOperation.Down, n=max(anchor.start_line - 1, 0))
        self.editor.setTextCursor(cursor)
        self.editor.centerCursor()
        self.editor.setFocus(Qt.FocusReason.OtherFocusReason)
