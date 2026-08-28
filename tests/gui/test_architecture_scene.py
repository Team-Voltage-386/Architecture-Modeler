from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGraphicsPathItem

from frc_arch_modeler.domain.model import (
    ArchitectureProject,
    Command,
    ComparisonState,
    FieldValue,
    Subsystem,
)
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
    edges = [item for item in scene.items() if isinstance(item, QGraphicsPathItem)]
    assert len(edges) == 1
    assert edges[0].toolTip() == "Designed requirement"


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
        ("command", "stopDrive"),
    }
    imported_command = next(
        item
        for item in imported
        if item.kind == "command" and item.title.toPlainText() == "DriveCommand"
    )
    imported_subsystem = next(item for item in imported if item.kind == "subsystem")
    assert imported_command.pen().color().name() == VOLTAGE_YELLOW.lower()
    assert imported_subsystem.pen().color().name() == VOLTAGE_BLUE.lower()
    assert imported_command.caption.toPlainText() == "Imported COMMAND"
    assert imported_subsystem.caption.toPlainText() == "Imported SUBSYSTEM"
    assert "driver.a() · onTrue" in imported_command.summary.toPlainText()
    assert "SparkMax: 4, MotorType.kBrushless" in imported_subsystem.summary.toPlainText()
    edges = [item for item in scene.items() if isinstance(item, QGraphicsPathItem)]
    assert len(edges) == 1
    assert edges[0].toolTip() == "addRequirements(drive)"


def test_selection_emphasizes_only_connected_requirement_edges(qapp) -> None:
    drive = Subsystem(name=FieldValue(design="Drive"))
    intake = Subsystem(name=FieldValue(design="Intake"))
    drive_command = Command(name=FieldValue(design="Drive Command"), requirement_ids=[drive.id])
    intake_command = Command(name=FieldValue(design="Intake Command"), requirement_ids=[intake.id])
    scene = ArchitectureScene()
    scene.render_project(
        ArchitectureProject(
            name="Robot",
            commands=[drive_command, intake_command],
            subsystems=[drive, intake],
        )
    )

    drive_block = next(
        item
        for item in scene.items()
        if isinstance(item, ArchitectureBlock) and item.element_id == drive_command.id
    )
    drive_block.setSelected(True)
    edges = [item for item in scene.items() if isinstance(item, QGraphicsPathItem)]

    assert sorted(edge.opacity() for edge in edges) == [0.16, 1.0]
    selected_edge = next(edge for edge in edges if edge.opacity() == 1.0)
    assert selected_edge.pen().style() == Qt.PenStyle.SolidLine


def test_filter_hides_nonmatching_blocks_and_relationships(qapp) -> None:
    drive = Subsystem(name=FieldValue(design="Drive"))
    intake = Subsystem(name=FieldValue(design="Intake"))
    command = Command(name=FieldValue(design="Teleop Drive"), requirement_ids=[drive.id])
    scene = ArchitectureScene()
    project = ArchitectureProject(
        name="Robot", commands=[command], subsystems=[drive, intake]
    )
    scene.render_project(project)

    scene.filter_blocks("drive")

    blocks = [item for item in scene.items() if isinstance(item, ArchitectureBlock)]
    assert {block.title.toPlainText() for block in blocks if block.isVisible()} == {
        "Drive",
        "Teleop Drive",
    }
    assert all(edge.isVisible() for edge in scene._edges)


def test_filter_matches_design_description_and_imported_device_evidence(qapp) -> None:
    design = Command(
        name=FieldValue(design="Teleop"), description=FieldValue(design="Drive using joysticks")
    )
    scene = ArchitectureScene()
    scan = JavaProjectScanner().scan(Path(__file__).parents[1] / "fixtures" / "java_basic")
    scene.render_project(ArchitectureProject(name="Robot", commands=[design]), scan=scan)

    scene.filter_blocks("joysticks")

    assert [
        block.title.toPlainText()
        for block in scene.items()
        if isinstance(block, ArchitectureBlock) and block.isVisible()
    ] == ["Teleop"]
    scene.filter_blocks("SparkMax")
    assert [
        block.title.toPlainText()
        for block in scene.items()
        if isinstance(block, ArchitectureBlock) and block.isVisible()
    ] == ["Drive"]


def test_modified_status_has_non_color_caption_and_border_style(qapp) -> None:
    command = Command(name=FieldValue(design="Teleop Drive"))
    scene = ArchitectureScene()
    scene.render_project(
        ArchitectureProject(name="Robot", commands=[command]),
        statuses={command.id: ComparisonState.MODIFIED},
    )

    block = next(item for item in scene.items() if isinstance(item, ArchitectureBlock))

    assert block.caption.toPlainText() == "Δ MODIFIED"
    assert block.pen().style() == Qt.PenStyle.DashDotLine


def test_status_filter_hides_blocks_outside_the_selected_state(qapp) -> None:
    matched = Command(name=FieldValue(design="Matched"))
    modified = Command(name=FieldValue(design="Modified"))
    scene = ArchitectureScene()
    scene.render_project(
        ArchitectureProject(name="Robot", commands=[matched, modified]),
        statuses={
            matched.id: ComparisonState.MATCHED,
            modified.id: ComparisonState.MODIFIED,
        },
    )

    scene.set_status_filter({ComparisonState.MODIFIED})

    assert [
        block.title.toPlainText()
        for block in scene.items()
        if isinstance(block, ArchitectureBlock) and block.isVisible()
    ] == ["Modified"]
