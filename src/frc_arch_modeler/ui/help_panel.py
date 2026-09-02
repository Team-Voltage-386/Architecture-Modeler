"""A collapsible, searchable notation help panel for the main window's docks."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QLineEdit, QScrollArea, QVBoxLayout, QWidget

from frc_arch_modeler.ui.help_content import build_help_sections


class HelpPanel(QWidget):
    """Searchable notation reference, hidden by default behind a dock toggle."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("helpPanel")
        self._active_context: str | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        self.search_field = QLineEdit(self)
        self.search_field.setObjectName("helpSearch")
        self.search_field.setAccessibleName("Search notation help")
        self.search_field.setPlaceholderText("Search help")
        self.search_field.setClearButtonEnabled(True)
        self.search_field.textChanged.connect(self._apply_filter)
        layout.addWidget(self.search_field)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        container = QWidget(scroll)
        sections_layout = QVBoxLayout(container)
        sections_layout.setSpacing(10)
        self._sections: list[tuple[str, str, str, QLabel]] = []
        for title, html, context in build_help_sections():
            label = QLabel(container)
            label.setTextFormat(Qt.TextFormat.RichText)
            label.setWordWrap(True)
            label.setText(f"<b style='font-size:14px'>{title}</b><br>{html}")
            sections_layout.addWidget(label)
            self._sections.append((title, html, context, label))
        sections_layout.addStretch(1)
        scroll.setWidget(container)
        layout.addWidget(scroll)

        self.setMinimumWidth(340)
        self.setMaximumWidth(560)

    def set_active_context(self, context: str | None) -> None:
        """Restrict the visible sections to those relevant to the given diagram tab.

        `context` is "structure" or "behavior" to match the active canvas, or None to
        show every section regardless of tab.
        """
        self._active_context = context
        self._apply_filter(self.search_field.text())

    def _apply_filter(self, text: str) -> None:
        """Show sections matching both the search text and the active diagram tab."""
        needle = text.strip().lower()
        for title, html, context, label in self._sections:
            matches_search = not needle or needle in f"{title} {html}".lower()
            matches_context = self._active_context is None or context == self._active_context
            label.setVisible(matches_search and matches_context)
