from pathlib import Path

from PySide6.QtWidgets import QGraphicsPathItem

from frc_arch_modeler.domain.model import ArchitectureProject, Command, FieldValue, Subsystem
from frc_arch_modeler.importers.java.scanner import JavaProjectScanner
from frc_arch_modeler.ui.architecture_scene import SUBSYSTEM_Y, ArchitectureBlock, ArchitectureScene
from frc_arch_modeler.ui.theme import VOLTAGE_BLUE, VOLTAGE_YELLOW


def test_scene_places_commands_and_subsystems_and_draws_requirements(qapp) -> None:
    drive = Subsystem(name=FieldValue(design="Drive"))
    command = Command(name=FieldValue(design="Teleop Drive"), requirement_ids=[drive.id])
    scene = ArchitectureScene()

    scene.render_project(ArchitectureProject(name="Robot", commands=[command], subsystems=[drive]))

    blocks = [item for item in scene.items() if isinstance(item, ArchitectureBlock)]
    assert len(blocks) == 2
    subsystem_block = next(block for block in blocks if block.kind == "subsystem")
    command_block = next(block for block in blocks if block.kind == "command")
    assert subsystem_block.pos().y() == SUBSYSTEM_Y
    assert subsystem_block.pen().color().name() == VOLTAGE_BLUE.lower()
    assert command_block.pen().color().name() == VOLTAGE_YELLOW.lower()
    assert len([item for item in scene.items() if isinstance(item, QGraphicsPathItem)]) == 1


def test_scene_round_trips_block_layout_and_minimized_state(qapp) -> None:
    command = Command(name=FieldValue(design="Score"))
    project = ArchitectureProject(name="Competition Robot", commands=[command])
    scene = ArchitectureScene()
    scene.render_project(project)
    block = next(item for item in scene.items() if isinstance(item, ArchitectureBlock))
    block.setPos(73, 29)
    block.setSelected(True)
    assert scene.set_selected_minimized(True)

    restored_scene = ArchitectureScene()
    restored_scene.render_project(project, scene.layout_state())
    restored_block = next(
        item for item in restored_scene.items() if isinstance(item, ArchitectureBlock)
    )

    assert restored_block.pos() == block.pos()
    assert restored_block.minimized


def test_scene_renders_code_import_as_separate_architecture_layer(qapp) -> None:
    fixture_root = Path(__file__).parents[1] / "fixtures" / "java_basic"
    scene = ArchitectureScene()

    scan = JavaProjectScanner().scan(fixture_root)
    scene.render_project(ArchitectureProject(name="Robot"), scan=scan)

    imported = [
        item for item in scene.items() if isinstance(item, ArchitectureBlock) and item.imported
    ]
    assert {(item.kind, item.title.toPlainText()) for item in imported} == {
        ("subsystem", "Drive"),
        ("command", "DriveCommand"),
    }
    imported_command = next(item for item in imported if item.kind == "command")
    imported_subsystem = next(item for item in imported if item.kind == "subsystem")
    assert imported_command.pen().color().name() == VOLTAGE_YELLOW.lower()
    assert imported_subsystem.pen().color().name() == VOLTAGE_BLUE.lower()
    assert imported_command.caption.toPlainText() == "Imported COMMAND"
    assert imported_subsystem.caption.toPlainText() == "Imported SUBSYSTEM"
    assert len([item for item in scene.items() if isinstance(item, QGraphicsPathItem)]) == 1
