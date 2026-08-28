from PySide6.QtWidgets import QDockWidget

from frc_arch_modeler.app import create_application
from frc_arch_modeler.ui.main_window import MainWindow


def test_main_window_has_planned_regions(qtbot) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)

    assert window.windowTitle() == "FRC Architecture Modeler"
    assert window.findChild(QDockWidget, "detailsDock") is not None
    assert window.statusBar().currentMessage() == "No robot project connected"
