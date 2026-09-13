"""The six-step guided tour: step definitions and the overlay/card widgets that show them.

Completion is read from the model, never from a click: each step records how many of
some countable thing (subsystems, devices, scoped commands, ...) existed when it became
current, and considers itself done once that count goes up. This works whether the tour
starts on an empty model or on an already-populated one (the sample robot, say), and it
means a GUI test can drive a step by calling the same `window.add_*` methods a user's
click would reach, with no need to simulate the click itself.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from PySide6.QtCore import QPoint, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QVBoxLayout, QWidget

if TYPE_CHECKING:
    from frc_arch_modeler.ui.main_window import MainWindow


@dataclass(frozen=True)
class TourStep:
    """One tour step: where to point, what to say, and how to tell it is done."""

    key: str
    title: str
    instruction: str
    target: Callable[[MainWindow], QWidget | None]
    counter: Callable[[MainWindow], int]


def _new_group_button(window: MainWindow) -> QWidget | None:
    return window._toolbar_group_buttons.get("New")


def _behavior_tab(window: MainWindow) -> QWidget | None:
    return window.diagram_tabs


def _subsystem_count(window: MainWindow) -> int:
    return len(window.project.subsystems) if window.project else 0


def _device_count(window: MainWindow) -> int:
    return len(window.project.devices) if window.project else 0


def _scoped_command_count(window: MainWindow) -> int:
    if window.project is None:
        return 0
    return sum(1 for command in window.project.commands if command.requirement_ids)


def _scoped_trigger_count(window: MainWindow) -> int:
    if window.project is None:
        return 0
    scoped_command_ids = {
        command.id for command in window.project.commands if command.requirement_ids
    }
    return sum(
        1 for trigger in window.project.triggers if trigger.command_id in scoped_command_ids
    )


def _transition_count(window: MainWindow) -> int:
    if window.project is None:
        return 0
    return sum(len(diagram.transitions) for diagram in window.project.behavior_diagrams)


TOUR_STEPS: list[TourStep] = [
    TourStep(
        key="create_subsystem",
        title="Create a subsystem",
        instruction=(
            "Create a subsystem — or add one from a template — to start modeling your "
            "robot's hardware groups."
        ),
        target=_new_group_button,
        counter=_subsystem_count,
    ),
    TourStep(
        key="add_device",
        title="Give it a device",
        instruction=(
            "Give that subsystem a device, and notice the address the tool proposed."
        ),
        target=_new_group_button,
        counter=_device_count,
    ),
    TourStep(
        key="create_command",
        title="Create a command",
        instruction="Create a command and set its required subsystem.",
        target=_new_group_button,
        counter=_scoped_command_count,
    ),
    TourStep(
        key="bind_trigger",
        title="Bind a trigger",
        instruction="Bind a controller trigger to that command.",
        target=_new_group_button,
        counter=_scoped_trigger_count,
    ),
    TourStep(
        key="add_transition",
        title="Add a behavior transition",
        instruction="Open the Behavior tab and add a transition between two states.",
        target=_behavior_tab,
        counter=_transition_count,
    ),
]

# Step 6 — "Link that transition to the command from step 3, then export the
# Architecture Markdown and look at what came out" — depends on plan step 6.1
# (transition-to-command linking from the details panel). That linking exists in the
# file format (`BehaviorTransition.command_id`) but not yet in any UI, so this tour
# stops at step 5 and GuidedTourController._finish() reports the hook instead.
#
# Once step 6.1 ships, append a TourStep here (target: the details panel; counter:
# transitions whose `command_id` is set) and change GuidedTourController._finish to
# advance into it instead of ending the tour.


class GuidedTourOverlay(QWidget):
    """A translucent, click-through dimmer with a cut-out around the current target."""

    def __init__(self, window: MainWindow) -> None:
        super().__init__(window)
        self.setObjectName("guidedTourOverlay")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self._window = window
        self._target: QWidget | None = None
        self.hide()

    def set_target(self, target: QWidget | None) -> None:
        self._target = target
        self.update()

    def reposition(self) -> None:
        self.setGeometry(self._window.rect())
        self.update()

    def _target_rect(self) -> QRect | None:
        target = self._target
        if target is None or not target.isVisible() or target.width() <= 0:
            return None
        top_left = target.mapTo(self._window, QPoint(0, 0))
        return QRect(top_left, target.size())

    def paintEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        cutout = self._target_rect()
        path = QPainterPath()
        path.setFillRule(Qt.FillRule.OddEvenFill)
        path.addRect(QRectF(self.rect()))
        if cutout is not None:
            path.addRoundedRect(QRectF(cutout).adjusted(-6, -6, 6, 6), 8, 8)
        painter.fillPath(path, QColor(0, 0, 0, 150))
        if cutout is not None:
            painter.setPen(QPen(QColor(255, 196, 0), 3))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(QRectF(cutout).adjusted(-6, -6, 6, 6), 8, 8)


class TourStepCard(QFrame):
    """A small, always-interactive card carrying the current step's instruction."""

    exit_requested = Signal()

    def __init__(self, window: MainWindow) -> None:
        super().__init__(window)
        self.setObjectName("guidedTourCard")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setAutoFillBackground(True)
        self.setFixedWidth(320)
        layout = QVBoxLayout(self)
        self.counter_label = QLabel(self)
        self.counter_label.setObjectName("guidedTourCounter")
        self.instruction_label = QLabel(self)
        self.instruction_label.setObjectName("guidedTourInstruction")
        self.instruction_label.setWordWrap(True)
        self._exit_button = QPushButton("Exit Tour", self)
        self._exit_button.setObjectName("guidedTourExitButton")
        self._exit_button.clicked.connect(self.exit_requested)
        layout.addWidget(self.counter_label)
        layout.addWidget(self.instruction_label)
        layout.addWidget(self._exit_button, alignment=Qt.AlignmentFlag.AlignRight)
        self.hide()

    def show_step(self, index: int, total: int, title: str, instruction: str) -> None:
        self._exit_button.setText("Exit Tour")
        self.counter_label.setText(f"Step {index + 1} of {total}: {title}")
        self.instruction_label.setText(instruction)
        self.adjustSize()
        self.show()

    def show_finished(self, message: str) -> None:
        self._exit_button.setText("Close")
        self.counter_label.setText("Tour complete")
        self.instruction_label.setText(message)
        self.adjustSize()
        self.show()

    def reposition(self, window_rect: QRect) -> None:
        margin = 24
        x = window_rect.right() - self.width() - margin
        y = window_rect.bottom() - self.height() - margin
        self.move(max(window_rect.left() + margin, x), max(window_rect.top() + margin, y))
