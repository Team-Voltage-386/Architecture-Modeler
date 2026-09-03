"""A reusable placeholder for a region that can be empty: one explanatory sentence
and, when there's an action that fills the region, the button that does it."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget


class EmptyStateWidget(QWidget):
    """One sentence describing what belongs here, plus an optional creation button."""

    def __init__(
        self,
        object_name: str,
        message: str,
        button_text: str | None = None,
        on_click: Callable[[], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName(object_name)
        layout = QVBoxLayout(self)
        layout.addStretch()
        self.label = QLabel(message, self)
        self.label.setObjectName(f"{object_name}Message")
        self.label.setWordWrap(True)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.label)
        self.button: QPushButton | None = None
        if button_text is not None and on_click is not None:
            button = QPushButton(button_text, self)
            button.setObjectName(f"{object_name}Button")
            button.clicked.connect(on_click)
            layout.addWidget(button, alignment=Qt.AlignmentFlag.AlignHCenter)
            self.button = button
        layout.addStretch()

    def set_message(self, message: str) -> None:
        self.label.setText(message)
