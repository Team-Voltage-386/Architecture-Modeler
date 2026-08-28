from PySide6.QtWidgets import QGraphicsPathItem

from frc_arch_modeler.domain.model import ArchitectureProject, Command, FieldValue, Subsystem
from frc_arch_modeler.ui.architecture_scene import SUBSYSTEM_Y, ArchitectureBlock, ArchitectureScene


def test_scene_places_commands_and_subsystems_and_draws_requirements(qapp) -> None:
    drive = Subsystem(name=FieldValue(design="Drive"))
    command = Command(name=FieldValue(design="Teleop Drive"), requirement_ids=[drive.id])
    scene = ArchitectureScene()

    scene.render_project(ArchitectureProject(name="Robot", commands=[command], subsystems=[drive]))

    blocks = [item for item in scene.items() if isinstance(item, ArchitectureBlock)]
    assert len(blocks) == 2
    assert next(block for block in blocks if block.kind == "subsystem").pos().y() == SUBSYSTEM_Y
    assert len([item for item in scene.items() if isinstance(item, QGraphicsPathItem)]) == 1
