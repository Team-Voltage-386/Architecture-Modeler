"""Orchestration for the guided tour: which step is current and whether it is done.

The overlay and card only draw; this controller decides progression by comparing each
step's model-derived counter against the value it had when that step became current
(see `guided_tour.TOUR_STEPS`), so it works the same whether the tour starts on an
empty model or an already-populated one.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QTimer

from frc_arch_modeler.ui.guided_tour import TOUR_STEPS, GuidedTourOverlay, TourStepCard

if TYPE_CHECKING:
    from frc_arch_modeler.ui.main_window import MainWindow

_REPOSITION_INTERVAL_MS = 200


class GuidedTourController:
    """Own tour progress and the lazily-built overlay/card that display it."""

    def __init__(self, window: MainWindow) -> None:
        self.window = window
        self.step_index = 0
        self.completed = False
        self.active = False
        self._baseline = 0
        self._overlay: GuidedTourOverlay | None = None
        self._card: TourStepCard | None = None
        self._timer: QTimer | None = None

    # -- lifecycle ----------------------------------------------------------

    def start(self) -> None:
        """Launch the tour, creating an empty model first if none is open yet."""
        window = self.window
        if window.project is None:
            window.new_project("Untitled Model")
        if self.completed:
            self.step_index = 0
            self.completed = False
        self.step_index = min(self.step_index, len(TOUR_STEPS) - 1)
        self._ensure_widgets()
        self.active = True
        self._timer.start()
        self._show_current_step()

    def exit_tour(self) -> None:
        """Hide the tour without losing progress, so it can resume from this step."""
        self.active = False
        if self._timer is not None:
            self._timer.stop()
        if self._overlay is not None:
            self._overlay.hide()
        if self._card is not None:
            self._card.hide()

    def reposition(self) -> None:
        if not self.active or self._overlay is None or self._card is None:
            return
        self._overlay.reposition()
        self._card.reposition(self.window.rect())

    def check_progress(self) -> None:
        """Re-derive whether the current step is done; called after every model edit."""
        if not self.active or self.completed:
            return
        step = TOUR_STEPS[self.step_index]
        if step.counter(self.window) > self._baseline:
            self._advance()

    # -- internals ------------------------------------------------------

    def _ensure_widgets(self) -> None:
        window = self.window
        if self._overlay is None:
            self._overlay = GuidedTourOverlay(window)
        if self._card is None:
            self._card = TourStepCard(window)
            self._card.exit_requested.connect(window._exit_guided_tour)
        if self._timer is None:
            self._timer = QTimer(window)
            self._timer.setInterval(_REPOSITION_INTERVAL_MS)
            self._timer.timeout.connect(window._reposition_guided_tour)

    def _advance(self) -> None:
        self.step_index += 1
        if self.step_index >= len(TOUR_STEPS):
            self._finish()
        else:
            self._show_current_step()

    def _finish(self) -> None:
        self.completed = True
        self.active = False
        assert self._overlay is not None and self._card is not None and self._timer is not None
        self._timer.stop()
        self._overlay.set_target(None)
        self._overlay.hide()
        self._card.show_finished(
            "Nice work — that's the tour for now. Linking this transition to its "
            "command and exporting the Architecture Markdown (step 6) will join the "
            "tour once behavior-to-command linking ships."
        )
        self._card.reposition(self.window.rect())

    def _show_current_step(self) -> None:
        assert self._overlay is not None and self._card is not None
        step = TOUR_STEPS[self.step_index]
        self._baseline = step.counter(self.window)
        target = step.target(self.window)
        self._overlay.set_target(target)
        self._overlay.reposition()
        self._overlay.show()
        self._overlay.raise_()
        self._card.show_step(self.step_index, len(TOUR_STEPS), step.title, step.instruction)
        self._card.reposition(self.window.rect())
        self._card.raise_()

    # -- persistence (mirrors ProjectController.ui_preferences) --------------

    def preferences(self) -> dict[str, object]:
        return {"tourStep": self.step_index, "tourCompleted": self.completed}

    def restore_preferences(self, preferences: dict[str, object]) -> None:
        step = preferences.get("tourStep")
        completed = preferences.get("tourCompleted")
        if isinstance(step, int) and 0 <= step < len(TOUR_STEPS):
            self.step_index = step
        if isinstance(completed, bool):
            self.completed = completed
