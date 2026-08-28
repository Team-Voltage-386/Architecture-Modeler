from PySide6.QtWidgets import QDockWidget

from frc_arch_modeler.app import create_application
from frc_arch_modeler.ui.architecture_scene import ArchitectureBlock
from frc_arch_modeler.ui.main_window import MainWindow


def test_main_window_has_planned_regions(qtbot) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)

    assert window.windowTitle() == "FRC Architecture Modeler"
    assert window.findChild(QDockWidget, "detailsDock") is not None
    assert window.statusBar().currentMessage() == "No robot project connected"


def test_new_model_and_design_elements_update_the_canvas(qtbot) -> None:
    create_application([])
    window = MainWindow()
    qtbot.addWidget(window)

    window.new_project("Competition Robot")
    window.add_subsystem("Drive")
    window.add_command("Teleop Drive")

    assert window.is_dirty
    assert window.new_command_action.isEnabled()
    assert window.project is not None
    assert len(window.project.commands) == 1
    assert len(window.project.subsystems) == 1
    assert len([item for item in window.scene.items() if isinstance(item, ArchitectureBlock)]) == 2
