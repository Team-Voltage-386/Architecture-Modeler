from pathlib import Path

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QGraphicsPathItem,
    QGraphicsPolygonItem,
    QGraphicsSceneMouseEvent,
    QGraphicsView,
)

from frc_arch_modeler.domain.model import (
    ArchitectureProject,
    Command,
    ComparisonState,
    Device,
    FieldValue,
    Relationship,
    SourceAnchor,
    Subsystem,
    TriggerBinding,
)
from frc_arch_modeler.importers.base import ScannedDevice, ScannedSymbol, ScanResult
from frc_arch_modeler.importers.java.scanner import JavaProjectScanner
from frc_arch_modeler.ui.architecture_scene import (
    SUBSYSTEM_Y,
    ArchitectureBlock,
    ArchitectureScene,
    ConnectorHandle,
    DeviceBlock,
    DeviceCountChip,
)
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


def test_command_block_shows_a_more_line_when_triggers_are_dropped_past_the_cap(qapp) -> None:
    command = Command(name=FieldValue(design="Score"))
    triggers = [
        TriggerBinding(
            expression=FieldValue(design=f"Driver {index}"),
            activation=FieldValue(design="onTrue"),
            command_id=command.id,
        )
        for index in range(5)
    ]
    project = ArchitectureProject(name="Robot", commands=[command], triggers=triggers)
    scene = ArchitectureScene()

    scene.render_project(project)

    block = next(item for item in scene.items() if isinstance(item, ArchitectureBlock))
    summary_lines = block.summary.toPlainText().splitlines()
    assert len(summary_lines) == 4
    assert summary_lines[-1] == "+2 more"


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


def test_requirement_edge_runs_horizontally_when_blocks_are_arranged_side_by_side(qapp) -> None:
    drive = Subsystem(name=FieldValue(design="Drive"))
    command = Command(name=FieldValue(design="Teleop Drive"), requirement_ids=[drive.id])
    scene = ArchitectureScene()
    scene.render_project(ArchitectureProject(name="Robot", commands=[command], subsystems=[drive]))
    command_block = next(
        item
        for item in scene.items()
        if isinstance(item, ArchitectureBlock) and item.kind == "command"
    )

    # Move the subsystem beside the command instead of the default row-below layout.
    scene.apply_block_positions(
        {drive.id: QPointF(command_block.pos().x() + 400, command_block.pos().y())}
    )

    edge = next(item for item in scene.items() if isinstance(item, QGraphicsPathItem))
    start = edge.path().pointAtPercent(0)
    end = edge.path().currentPosition()
    assert abs(end.x() - start.x()) > abs(end.y() - start.y())


def test_requirement_edge_routes_around_a_block_placed_between_endpoints(qapp) -> None:
    drive = Subsystem(name=FieldValue(design="Drive"))
    command = Command(name=FieldValue(design="Teleop Drive"), requirement_ids=[drive.id])
    blocker = Subsystem(name=FieldValue(design="Blocker"))
    scene = ArchitectureScene()
    scene.render_project(
        ArchitectureProject(name="Robot", commands=[command], subsystems=[drive, blocker])
    )
    blocker_block = next(
        item
        for item in scene.items()
        if isinstance(item, ArchitectureBlock) and item.element_id == blocker.id
    )

    # Command, blocker, and subsystem in a single horizontal row: the blocker sits
    # squarely on the straight line the requirement edge would otherwise take.
    scene.apply_block_positions(
        {command.id: QPointF(0, 0), blocker.id: QPointF(300, 0), drive.id: QPointF(600, 0)}
    )

    edge = next(
        item
        for item in scene.items()
        if isinstance(item, QGraphicsPathItem) and item.toolTip() == "Designed requirement"
    )
    path = edge.path()
    assert path.elementCount() > 2
    blocker_rect = blocker_block.sceneBoundingRect()
    points = [
        QPointF(path.elementAt(i).x, path.elementAt(i).y) for i in range(path.elementCount())
    ]
    for p1, p2 in zip(points, points[1:]):
        midpoint = QPointF((p1.x() + p2.x()) / 2, (p1.y() + p2.y()) / 2)
        assert not blocker_rect.contains(midpoint)


def test_requirement_edge_follows_block_positions(qapp) -> None:
    drive = Subsystem(name=FieldValue(design="Drive"))
    command = Command(name=FieldValue(design="Teleop Drive"), requirement_ids=[drive.id])
    scene = ArchitectureScene()
    scene.render_project(ArchitectureProject(name="Robot", commands=[command], subsystems=[drive]))
    edge = next(item for item in scene.items() if isinstance(item, QGraphicsPathItem))
    before = edge.path().currentPosition()

    scene.apply_block_positions({drive.id: QPointF(400, 480)})

    assert edge.path().currentPosition() != before
    drive_block = next(
        item
        for item in scene.items()
        if isinstance(item, ArchitectureBlock) and item.element_id == drive.id
    )
    command_block = next(
        item
        for item in scene.items()
        if isinstance(item, ArchitectureBlock) and item.element_id == command.id
    )
    # The edge should now leave from whichever side of the moved block faces the command,
    # not a side fixed at creation time.
    expected_end = ArchitectureScene._clip_to_rect(
        drive_block.sceneBoundingRect(), command_block.sceneBoundingRect().center()
    )
    assert edge.path().currentPosition() == expected_end


def test_selected_blocks_can_move_by_keyboard_and_emit_layout_change(qapp) -> None:
    command = Command(name=FieldValue(design="Score"))
    scene = ArchitectureScene()
    scene.render_project(ArchitectureProject(name="Robot", commands=[command]))
    block = next(item for item in scene.items() if isinstance(item, ArchitectureBlock))
    block.setSelected(True)
    changes = []
    scene.layout_move_completed.connect(lambda before, after: changes.append((before, after)))

    scene.keyPressEvent(QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Right, Qt.NoModifier))

    assert block.flags() & block.GraphicsItemFlag.ItemIsFocusable
    assert block.pos() == QPointF(10, 0)
    assert changes[0][0][command.id] == QPointF(0, 0)
    assert changes[0][1][command.id] == QPointF(10, 0)


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
    assert imported_command.caption.toPlainText() == "IMPORTED"
    assert imported_subsystem.caption.toPlainText() == "IMPORTED"
    assert "driver.a() · onTrue" in imported_command.summary.toPlainText()
    assert "SparkMax: 4, MotorType.kBrushless" in imported_subsystem.summary.toPlainText()
    edges = [item for item in scene.items() if isinstance(item, QGraphicsPathItem)]
    assert len(edges) == 1
    assert edges[0].toolTip() == "addRequirements(drive)"


def test_scene_keeps_inline_command_forms_out_of_canvas_until_requested(qapp, tmp_path) -> None:
    scan = ScanResult(
        tmp_path,
        symbols=[
            ScannedSymbol(
                "command_composition",
                "runOnce (line 1)",
                SourceAnchor("A.java", "runOnce@1", 1, 1),
            )
        ],
    )
    scene = ArchitectureScene()
    scene.render_project(ArchitectureProject(name="Robot"), scan=scan)

    assert not any(isinstance(item, ArchitectureBlock) for item in scene.items())
    scene.show_command_forms = True
    scene.render_project(ArchitectureProject(name="Robot"), scan=scan)
    assert any(isinstance(item, ArchitectureBlock) for item in scene.items())


def test_scene_groups_io_variant_devices_under_logical_subsystem(qapp, tmp_path) -> None:
    drive = ScannedSymbol(
        kind="subsystem",
        name="Drive",
        anchor=SourceAnchor("src/Drive.java", "frc.robot.Drive", 1, 1),
    )
    io_device = ScannedDevice(
        device_type="SparkMax",
        constructor_arguments="4, MotorType.kBrushless",
        owner_symbol="frc.robot.DriveIOSim",
        anchor=SourceAnchor("src/DriveIOSim.java", "frc.robot.DriveIOSim", 3, 3),
        mode="SIM",
    )
    scene = ArchitectureScene()

    scene.render_project(
        ArchitectureProject(name="Robot"), scan=ScanResult(tmp_path, [drive], devices=[io_device])
    )

    subsystem = next(
        item
        for item in scene.items()
        if isinstance(item, ArchitectureBlock) and item.title.toPlainText() == "Drive"
    )
    assert "SparkMax [SIM]: 4, MotorType.kBrushless" in subsystem.summary.toPlainText()


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


def test_connector_handle_drag_emits_connection_requested_for_valid_drop(qapp) -> None:
    drive = Subsystem(name=FieldValue(design="Drive"))
    command = Command(name=FieldValue(design="Teleop Drive"))
    scene = ArchitectureScene()
    view = QGraphicsView(scene)
    scene.render_project(ArchitectureProject(name="Robot", commands=[command], subsystems=[drive]))
    command_block = next(
        item
        for item in scene.items()
        if isinstance(item, ArchitectureBlock) and item.kind == "command"
    )
    subsystem_block = next(
        item
        for item in scene.items()
        if isinstance(item, ArchitectureBlock) and item.kind == "subsystem"
    )
    assert view.scene() is scene
    assert command_block.connector_handle is not None
    received = []
    scene.connection_requested.connect(
        lambda source, target, pos: received.append((source, target))
    )

    scene._begin_connection_drag(command_block, command_block.sceneBoundingRect().center())
    assert scene._connection_line is not None
    scene._finish_connection_drag(subsystem_block.sceneBoundingRect().center())

    assert scene._connection_line is None
    assert received == [(command_block, subsystem_block)]


def test_connector_handle_drag_ignores_same_block_and_imported_targets(qapp, tmp_path) -> None:
    command = Command(name=FieldValue(design="Teleop Drive"))
    scene = ArchitectureScene()
    view = QGraphicsView(scene)
    scan = ScanResult(
        tmp_path,
        symbols=[
            ScannedSymbol(
                "subsystem", "Drive", SourceAnchor("Drive.java", "frc.robot.Drive", 1, 1)
            )
        ],
    )
    scene.render_project(ArchitectureProject(name="Robot", commands=[command]), scan=scan)
    command_block = next(
        item
        for item in scene.items()
        if isinstance(item, ArchitectureBlock) and item.kind == "command"
    )
    imported_block = next(
        item for item in scene.items() if isinstance(item, ArchitectureBlock) and item.imported
    )
    assert view.scene() is scene
    assert imported_block.connector_handle is None
    received = []
    scene.connection_requested.connect(lambda *args: received.append(args))

    scene._begin_connection_drag(command_block, command_block.sceneBoundingRect().center())
    scene._finish_connection_drag(command_block.sceneBoundingRect().center())
    assert received == []

    scene._begin_connection_drag(command_block, command_block.sceneBoundingRect().center())
    scene._finish_connection_drag(imported_block.sceneBoundingRect().center())
    assert received == []


def test_relationship_types_render_distinct_arrow_or_diamond_markers(qapp) -> None:
    drive = Subsystem(name=FieldValue(design="Drive"))
    intake = Subsystem(name=FieldValue(design="Intake"))
    scene = ArchitectureScene()
    scene.render_project(
        ArchitectureProject(
            name="Robot",
            subsystems=[drive, intake],
            relationships=[Relationship("contains", drive.id, intake.id)],
        )
    )
    edge = next(item for item in scene.items() if isinstance(item, QGraphicsPathItem))
    marker = edge.data(4)
    assert isinstance(marker, QGraphicsPolygonItem)
    assert marker.polygon().count() == 4
    assert marker.brush().style() == Qt.BrushStyle.NoBrush


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


def _robot_with_devices() -> tuple[ArchitectureProject, Subsystem, Subsystem]:
    """Two subsystems, three devices: enough to tell "just this one" from "all of them"."""
    drive = Subsystem(name=FieldValue(design="Drive"))
    arm = Subsystem(name=FieldValue(design="Arm"))
    devices = [
        Device(
            name=FieldValue(design="Left motor"),
            device_type=FieldValue(design="SparkMax"),
            owner_subsystem_id=drive.id,
            bus=FieldValue(design="canivore"),
            address=FieldValue(design="3"),
        ),
        Device(
            name=FieldValue(design="Right motor"),
            device_type=FieldValue(design="SparkMax"),
            owner_subsystem_id=drive.id,
        ),
        Device(
            name=FieldValue(design="Elbow"),
            device_type=FieldValue(design="TalonFX"),
            owner_subsystem_id=arm.id,
        ),
    ]
    project = ArchitectureProject(name="Robot", subsystems=[drive, arm], devices=devices)
    return project, drive, arm


def _device_titles(scene: ArchitectureScene) -> set[str]:
    return {
        item.title.toPlainText()
        for item in scene.items()
        if isinstance(item, DeviceBlock)
    }


def _click_scene(scene: ArchitectureScene, point: QPointF) -> None:
    event = QGraphicsSceneMouseEvent(QEvent.Type.GraphicsSceneMousePress)
    event.setScenePos(point)
    event.setButton(Qt.MouseButton.LeftButton)
    scene.mousePressEvent(event)


def test_the_grouped_default_draws_count_chips_and_no_device_blocks(qapp) -> None:
    project, _, _ = _robot_with_devices()
    scene = ArchitectureScene()
    assert scene.device_view_state == "grouped"

    scene.render_project(project)

    assert _device_titles(scene) == set()
    chips = {
        chip.owner.title.toPlainText(): chip.label.toPlainText()
        for chip in scene.items()
        if isinstance(chip, DeviceCountChip)
    }
    assert chips.keys() == {"Drive", "Arm"}
    assert chips["Drive"].endswith("2 devices")
    assert chips["Arm"].endswith("1 device")


def test_expanding_one_subsystem_shows_only_its_devices_with_filled_diamond_edges(
    qapp,
) -> None:
    project, drive, _ = _robot_with_devices()
    scene = ArchitectureScene()
    scene.render_project(project)

    scene.toggle_subsystem_devices(drive.id)
    scene.render_project(project, scene.layout_state())

    assert _device_titles(scene) == {"Left motor", "Right motor"}
    ownership_edges = [edge for edge in scene._edges if edge.data(5) == "owns_device"]
    assert len(ownership_edges) == 2
    drive_block = next(
        item
        for item in scene.items()
        if isinstance(item, ArchitectureBlock) and item.element_id == drive.id
    )
    for edge in ownership_edges:
        marker = edge.data(4)
        assert isinstance(marker, QGraphicsPolygonItem)
        assert marker.polygon().count() == 4
        assert marker.brush().style() == Qt.BrushStyle.SolidPattern
        # A composition diamond belongs at the owner's end of the line.
        assert drive_block.sceneBoundingRect().adjusted(-8, -8, 8, 8).contains(
            marker.polygon().boundingRect().center()
        )


def test_expanded_device_view_shows_every_device_and_hidden_shows_none(qapp) -> None:
    project, _, _ = _robot_with_devices()
    scene = ArchitectureScene()

    assert scene.cycle_device_view() == "expanded"
    scene.render_project(project, scene.layout_state())
    assert _device_titles(scene) == {"Left motor", "Right motor", "Elbow"}
    assert not [item for item in scene.items() if isinstance(item, DeviceCountChip)]

    assert scene.cycle_device_view() == "hidden"
    scene.render_project(project, scene.layout_state())
    assert _device_titles(scene) == set()
    assert not [item for item in scene.items() if isinstance(item, DeviceCountChip)]
    subsystem = next(
        item
        for item in scene.items()
        if isinstance(item, ArchitectureBlock) and item.title.toPlainText() == "Drive"
    )
    assert "SparkMax" not in subsystem.summary.toPlainText()

    assert scene.cycle_device_view() == "grouped"


def test_devices_open_a_third_tier_below_the_two_existing_rows(qapp) -> None:
    project, drive, arm = _robot_with_devices()
    scene = ArchitectureScene()
    scene.device_view_state = "expanded"

    scene.render_project(project)

    subsystems = [
        item
        for item in scene.items()
        if isinstance(item, ArchitectureBlock) and item.kind == "subsystem"
    ]
    assert {block.pos().y() for block in subsystems} == {SUBSYSTEM_Y}
    devices = {
        item.title.toPlainText(): item
        for item in scene.items()
        if isinstance(item, DeviceBlock)
    }
    lowest_subsystem = max(
        block.pos().y() + block.rect().height() for block in subsystems
    )
    assert all(block.pos().y() > lowest_subsystem for block in devices.values())
    assert {block.owner_subsystem_id for block in devices.values()} == {drive.id, arm.id}
    # Devices are grouped: both of Drive's sit left of the group belonging to Arm.
    assert devices["Elbow"].pos().x() > devices["Right motor"].pos().x()


def test_device_view_state_and_per_subsystem_expansion_round_trip_through_layout(
    qapp,
) -> None:
    project, _, arm = _robot_with_devices()
    scene = ArchitectureScene()
    scene.render_project(project)
    scene.toggle_subsystem_devices(arm.id)

    restored = ArchitectureScene()
    restored.render_project(project, scene.layout_state())

    assert restored.device_view_state == "grouped"
    assert restored.expanded_device_subsystems == {arm.id}
    assert _device_titles(restored) == {"Elbow"}


def test_devices_take_part_in_search_and_in_the_status_filters(qapp) -> None:
    project, drive, arm = _robot_with_devices()
    scene = ArchitectureScene()
    scene.device_view_state = "expanded"
    scene.render_project(
        project,
        statuses={drive.id: ComparisonState.MATCHED, arm.id: ComparisonState.DESIGN_ONLY},
    )

    scene.filter_blocks("elbow")
    assert {
        item.title.toPlainText()
        for item in scene.items()
        if isinstance(item, DeviceBlock) and item.isVisible()
    } == {"Elbow"}

    scene.filter_blocks("")
    scene.set_status_filter({ComparisonState.MATCHED})
    assert {
        item.title.toPlainText()
        for item in scene.items()
        if isinstance(item, DeviceBlock) and item.isVisible()
    } == {"Left motor", "Right motor"}


def test_a_device_block_is_a_short_badge_block_and_not_a_relationship_drag_source(
    qapp,
) -> None:
    project, _, _ = _robot_with_devices()
    scene = ArchitectureScene()
    scene.device_view_state = "expanded"
    scene.render_project(project)
    blocks = {
        item.title.toPlainText(): item
        for item in scene.items()
        if isinstance(item, DeviceBlock)
    }
    subsystem = next(
        item
        for item in scene.items()
        if isinstance(item, ArchitectureBlock) and item.kind == "subsystem"
    )

    left = blocks["Left motor"]
    assert left.caption.toPlainText() == "SparkMax"
    assert left.badge.toPlainText() == "canivore 3"
    assert left.badge.isVisible()
    assert not blocks["Right motor"].badge.isVisible()
    assert left.rect().height() <= subsystem.rect().height() / 2
    assert not [
        child for child in left.childItems() if isinstance(child, ConnectorHandle)
    ]


def test_clicking_a_count_chip_toggles_only_that_subsystems_devices(qapp) -> None:
    project, drive, _ = _robot_with_devices()
    scene = ArchitectureScene()
    view = QGraphicsView(scene)
    scene.render_project(project)
    assert view.scene() is scene
    toggles: list[bool] = []
    scene.device_view_changed.connect(lambda: toggles.append(True))
    chip = next(
        item
        for item in scene.items()
        if isinstance(item, DeviceCountChip) and item.owner.element_id == drive.id
    )

    _click_scene(scene, chip.sceneBoundingRect().center())
    assert toggles == [True]
    assert scene.expanded_device_subsystems == {drive.id}

    _click_scene(scene, chip.sceneBoundingRect().center())
    assert toggles == [True, True]
    assert scene.expanded_device_subsystems == set()
