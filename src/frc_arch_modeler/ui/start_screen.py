"""The page shown in the main window in place of the canvas until a project is open."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget


class StartScreen(QWidget):
    """New Model, Open Model, Open Recent, Open the Sample Robot and Take the Tour.

    Lives inside the main window as a stacked-widget page rather than a modal dialog,
    so it disappears the moment a project opens and reappears if the last one closes.
    """

    def __init__(
        self,
        on_new: Callable[[], None],
        on_open: Callable[[], None],
        on_open_recent: Callable[[], None],
        on_open_sample: Callable[[], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("startScreen")
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title = QLabel("FRC Architecture Modeler", self)
        title.setObjectName("startScreenTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle = QLabel(
            "Model your robot's commands, subsystems and hardware before — or "
            "alongside — writing a line of code.",
            self,
        )
        subtitle.setObjectName("startScreenSubtitle")
        subtitle.setWordWrap(True)
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(16)

        def add_button(text: str, handler: Callable[[], None], object_name: str) -> QPushButton:
            button = QPushButton(text, self)
            button.setObjectName(object_name)
            button.setMinimumWidth(260)
            button.clicked.connect(handler)
            layout.addWidget(button, alignment=Qt.AlignmentFlag.AlignHCenter)
            return button

        add_button("New Model", on_new, "startNewModelButton")
        add_button("Open Model", on_open, "startOpenModelButton")
        self.open_recent_button = add_button(
            "Open Recent", on_open_recent, "startOpenRecentButton"
        )
        add_button("Open the Sample Robot", on_open_sample, "startOpenSampleButton")
        self.tour_button = add_button("Take the Tour", lambda: None, "startTourButton")
        self.tour_button.setEnabled(False)
        self.tour_button.setToolTip("Coming soon.")
        self.tour_button.setStatusTip("An interactive tour of the tool. Coming soon.")

    def set_recent_visible(self, visible: bool, label: str | None = None) -> None:
        """Reflect the last-opened model (if any), matching the Model menu's Recent entry."""
        self.open_recent_button.setVisible(visible)
        if visible and label:
            self.open_recent_button.setText(f"Open Recent: {label}")
        else:
            self.open_recent_button.setText("Open Recent")
