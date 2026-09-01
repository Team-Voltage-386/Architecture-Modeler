import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtWidgets import QGraphicsTextItem, QGraphicsView

from frc_arch_modeler.domain.model import (
    BehaviorDiagram,
    BehaviorState,
    BehaviorTransition,
    FieldValue,
)
from frc_arch_modeler.ui.architecture_scene import ArchitectureScene
from frc_arch_modeler.ui.behavior_scene import (
    DECISION_SIZE,
    JOIN_DIAMETER,
    PSEUDOSTATE_DIAMETER,
    SYNC_HEIGHT,
    SYNC_WIDTH,
    BehaviorScene,
    StateBlock,
    TransitionEndpointHandle,
)


def _linear_diagram() -> tuple[BehaviorDiagram, BehaviorState, BehaviorState, BehaviorState]:
    disabled = BehaviorState(name=FieldValue(design="Disabled"))
    autonomous = BehaviorState(name=FieldValue(design="Autonomous"))
    teleop = BehaviorState(name=FieldValue(design="Teleop"))
    diagram = BehaviorDiagram(
        name="Robot Modes",
        states=[disabled, autonomous, teleop],
        transitions=[BehaviorTransition(disabled.id, autonomous.id, "Go")],
    )
    return diagram, disabled, autonomous, teleop


def test_render_diagram_gives_each_pseudostate_kind_its_own_shape_and_size(qapp) -> None:
    start = BehaviorState(name=FieldValue(design="Start"), kind="start")
    decision = BehaviorState(name=FieldValue(design="Ball Detected?"), kind="decision")
    sync = BehaviorState(name=FieldValue(design="Sync"), kind="synchronization")
    end = BehaviorState(name=FieldValue(design="End"), kind="end")
    join = BehaviorState(name=FieldValue(design="Join"), kind="join")
    plain = BehaviorState(name=FieldValue(design="Disabled"))
    diagram = BehaviorDiagram(
        name="Robot Modes", states=[start, decision, sync, end, join, plain]
    )
    scene = BehaviorScene()

    scene.render_diagram(diagram)

    blocks = {
        block.state_id: block for block in scene.items() if isinstance(block, StateBlock)
    }
    assert blocks[start.id].kind == "start"
    assert (blocks[start.id].rect().width(), blocks[start.id].rect().height()) == (
        PSEUDOSTATE_DIAMETER,
        PSEUDOSTATE_DIAMETER,
    )
    assert blocks[decision.id].kind == "decision"
    assert (blocks[decision.id].rect().width(), blocks[decision.id].rect().height()) == (
        DECISION_SIZE,
        DECISION_SIZE,
    )
    assert blocks[sync.id].kind == "synchronization"
    assert (blocks[sync.id].rect().width(), blocks[sync.id].rect().height()) == (
        SYNC_WIDTH,
        SYNC_HEIGHT,
    )
    assert blocks[end.id].kind == "end"
    assert blocks[join.id].kind == "join"
    assert (blocks[join.id].rect().width(), blocks[join.id].rect().height()) == (
        JOIN_DIAMETER,
        JOIN_DIAMETER,
    )
    assert JOIN_DIAMETER < PSEUDOSTATE_DIAMETER
    assert blocks[join.id].title is None
    assert blocks[plain.id].kind == "state"


def test_render_diagram_shows_the_diagram_name_above_its_states(qapp) -> None:
    disabled = BehaviorState(name=FieldValue(design="Disabled"))
    diagram = BehaviorDiagram(name="Robot Modes", states=[disabled])
    scene = BehaviorScene()

    scene.render_diagram(diagram)

    title_items = [
        item
        for item in scene.items()
        if isinstance(item, QGraphicsTextItem) and item.toPlainText() == "Robot Modes"
    ]
    assert len(title_items) == 1
    block = next(item for item in scene.items() if isinstance(item, StateBlock))
    assert title_items[0].pos().y() < block.sceneBoundingRect().top()


def test_clip_ellipse_lands_exactly_on_the_circle_boundary() -> None:
    rect = QRectF(0, 0, 30, 30)
    point = BehaviorScene._clip_ellipse(rect, QPointF(200, 140))

    center = rect.center()
    normalized = ((point.x() - center.x()) / (rect.width() / 2)) ** 2 + (
        (point.y() - center.y()) / (rect.height() / 2)
    ) ** 2
    assert math.isclose(normalized, 1.0, rel_tol=1e-9)


def test_clip_diamond_lands_exactly_on_the_diamond_boundary() -> None:
    rect = QRectF(0, 0, 56, 56)
    point = BehaviorScene._clip_diamond(rect, QPointF(300, 40))

    center = rect.center()
    manhattan = abs(point.x() - center.x()) / (rect.width() / 2) + abs(
        point.y() - center.y()
    ) / (rect.height() / 2)
    assert math.isclose(manhattan, 1.0, rel_tol=1e-9)


def test_clip_diamond_snaps_to_the_nearest_of_its_four_points() -> None:
    rect = QRectF(0, 0, 56, 56)
    center = rect.center()

    top = BehaviorScene._clip_diamond(rect, QPointF(center.x() + 5, -1000))
    right = BehaviorScene._clip_diamond(rect, QPointF(1000, center.y() - 5))
    bottom = BehaviorScene._clip_diamond(rect, QPointF(center.x() - 5, 1000))
    left = BehaviorScene._clip_diamond(rect, QPointF(-1000, center.y() + 5))

    assert top == QPointF(center.x(), rect.top())
    assert right == QPointF(rect.right(), center.y())
    assert bottom == QPointF(center.x(), rect.bottom())
    assert left == QPointF(rect.left(), center.y())


def test_clip_diamond_shares_one_point_for_lines_from_similar_directions() -> None:
    """Two lines converging from roughly the same direction should land on the same
    point, the way Cameo treats a decision node's points as its only real targets."""
    rect = QRectF(0, 0, 56, 56)

    first = BehaviorScene._clip_diamond(rect, QPointF(200, 500))
    second = BehaviorScene._clip_diamond(rect, QPointF(260, 620))

    assert first == second


def test_clip_diamond_differs_from_a_plain_rectangle_clip_on_a_diagonal() -> None:
    """A rectangle clip would land past the diamond's slanted edge, outside the shape."""
    rect = QRectF(0, 0, 56, 56)
    towards = QPointF(300, 300)

    diamond_point = BehaviorScene._clip_diamond(rect, towards)
    rect_point = ArchitectureScene._clip_to_rect(rect, towards)

    assert diamond_point != rect_point


def test_transition_path_between_states_and_a_decision_node_touches_the_diamond(qapp) -> None:
    start_state = BehaviorState(name=FieldValue(design="Autonomous"))
    decision = BehaviorState(name=FieldValue(design="Ball Detected?"), kind="decision")
    diagram = BehaviorDiagram(
        name="Robot Modes",
        states=[start_state, decision],
        transitions=[BehaviorTransition(start_state.id, decision.id, "")],
    )
    scene = BehaviorScene()
    scene.render_diagram(diagram)

    blocks = {block.state_id: block for block in scene.items() if isinstance(block, StateBlock)}
    decision_block = blocks[decision.id]
    decision_block.setPos(decision_block.pos().x() + 400, decision_block.pos().y() + 400)
    scene._update_edge_paths()

    edge = next(item for item in scene._edges)
    end_point = edge.path().currentPosition()
    rect = decision_block.sceneBoundingRect()
    center = rect.center()
    manhattan = abs(end_point.x() - center.x()) / (rect.width() / 2) + abs(
        end_point.y() - center.y()
    ) / (rect.height() / 2)
    assert math.isclose(manhattan, 1.0, rel_tol=1e-6)


def test_transition_routes_around_a_state_placed_between_source_and_target(qapp) -> None:
    disabled = BehaviorState(name=FieldValue(design="Disabled"))
    teleop = BehaviorState(name=FieldValue(design="Teleop"))
    blocker = BehaviorState(name=FieldValue(design="Blocker"))
    diagram = BehaviorDiagram(
        name="Robot Modes",
        states=[disabled, teleop, blocker],
        transitions=[BehaviorTransition(disabled.id, teleop.id, "Go")],
    )
    scene = BehaviorScene()
    scene.render_diagram(diagram)
    blocks = {block.state_id: block for block in scene.items() if isinstance(block, StateBlock)}

    # Disabled, blocker, and teleop in a single horizontal row: the blocker sits
    # squarely on the straight line the transition would otherwise take.
    blocks[disabled.id].setPos(0, 0)
    blocks[blocker.id].setPos(200, 0)
    blocks[teleop.id].setPos(400, 0)
    scene._update_edge_paths()

    edge = scene._edges[0]
    path = edge.path()
    assert path.elementCount() > 2
    blocker_rect = blocks[blocker.id].sceneBoundingRect()
    points = [
        QPointF(path.elementAt(i).x, path.elementAt(i).y) for i in range(path.elementCount())
    ]
    for p1, p2 in zip(points, points[1:]):
        midpoint = QPointF((p1.x() + p2.x()) / 2, (p1.y() + p2.y()) / 2)
        assert not blocker_rect.contains(midpoint)


def test_sync_bar_keeps_incoming_and_outgoing_transitions_on_opposite_sides(qapp) -> None:
    """Fan-in and fan-out wires on a split/merge bar must not land on the same edge,
    or the diagram reads as a tangle instead of a clean fork/join."""
    upstream = BehaviorState(name=FieldValue(design="Upstream"))
    sync = BehaviorState(name=FieldValue(design="Sync"), kind="synchronization")
    downstream = BehaviorState(name=FieldValue(design="Downstream"))
    diagram = BehaviorDiagram(
        name="Robot Modes",
        states=[upstream, sync, downstream],
        transitions=[
            BehaviorTransition(upstream.id, sync.id, ""),
            BehaviorTransition(sync.id, downstream.id, ""),
        ],
    )
    scene = BehaviorScene()
    scene.render_diagram(diagram)
    blocks = {block.state_id: block for block in scene.items() if isinstance(block, StateBlock)}
    sync_rect = blocks[sync.id].sceneBoundingRect()

    incoming_edge, outgoing_edge = scene._edges
    incoming_end = incoming_edge.path().currentPosition()
    outgoing_start = QPointF(
        outgoing_edge.path().elementAt(0).x, outgoing_edge.path().elementAt(0).y
    )

    assert math.isclose(incoming_end.y(), sync_rect.top(), rel_tol=1e-9)
    assert math.isclose(outgoing_start.y(), sync_rect.bottom(), rel_tol=1e-9)


def test_transition_endpoint_handles_are_hidden_until_the_line_is_selected(qapp) -> None:
    diagram, _disabled, _autonomous, _teleop = _linear_diagram()
    scene = BehaviorScene()
    scene.render_diagram(diagram)
    edge = scene._edges[0]
    source_handle = edge.source_handle
    target_handle = edge.target_handle
    assert isinstance(source_handle, TransitionEndpointHandle)
    assert isinstance(target_handle, TransitionEndpointHandle)
    assert not source_handle.isVisible()
    assert not target_handle.isVisible()

    edge.setSelected(True)

    assert source_handle.isVisible()
    assert target_handle.isVisible()

    edge.setSelected(False)

    assert not source_handle.isVisible()
    assert not target_handle.isVisible()


def test_clicking_a_transitions_label_arrow_or_handle_resolves_to_that_transition(qapp) -> None:
    """A short transition's label sits on top of its line, so aiming for the line often
    hits the label instead. Every decoration must resolve back to the same transition."""
    diagram, _disabled, _autonomous, _teleop = _linear_diagram()
    scene = BehaviorScene()
    scene.render_diagram(diagram)
    edge = scene._edges[0]

    assert scene._edge_for(edge) is edge
    assert scene._edge_for(edge.label) is edge
    assert scene._edge_for(edge.marker) is edge
    assert scene._edge_for(edge.source_handle) is edge
    assert scene._edge_for(edge.target_handle) is edge
    assert scene._edge_for(None) is None


def test_transition_label_and_arrow_do_not_swallow_mouse_clicks(qapp) -> None:
    """Clicks must fall through the decorations to the selectable line underneath."""
    diagram, _disabled, _autonomous, _teleop = _linear_diagram()
    scene = BehaviorScene()
    scene.render_diagram(diagram)
    edge = scene._edges[0]

    assert edge.label.acceptedMouseButtons() == Qt.MouseButton.NoButton
    assert edge.marker.acceptedMouseButtons() == Qt.MouseButton.NoButton


def test_selected_transition_ids_reports_only_selected_edges(qapp) -> None:
    diagram, _disabled, _autonomous, _teleop = _linear_diagram()
    scene = BehaviorScene()
    scene.render_diagram(diagram)
    edge = scene._edges[0]

    assert scene.selected_transition_ids() == []

    edge.setSelected(True)

    assert scene.selected_transition_ids() == [diagram.transitions[0].id]


def test_dragging_an_endpoint_handle_onto_a_new_state_requests_reattach(qapp) -> None:
    diagram, _disabled, _autonomous, teleop = _linear_diagram()
    scene = BehaviorScene()
    view = QGraphicsView(scene)
    assert view.scene() is scene
    scene.render_diagram(diagram)
    edge = scene._edges[0]
    target_handle = edge.target_handle
    blocks = {block.state_id: block for block in scene.items() if isinstance(block, StateBlock)}
    teleop_block = blocks[teleop.id]

    requests = []
    scene.transition_reattach_requested.connect(lambda *args: requests.append(args))

    scene._begin_reattach_drag(target_handle, target_handle.scenePos())
    scene._finish_reattach_drag(teleop_block.sceneBoundingRect().center())

    assert requests == [(diagram.transitions[0].id, "target", teleop.id)]


def test_dragging_an_endpoint_onto_its_own_fixed_end_is_a_no_op(qapp) -> None:
    """Dropping a dragged endpoint back onto the state at the line's other end would make a
    degenerate self-loop, so it should be silently ignored rather than requested."""
    diagram, disabled, _autonomous, _teleop = _linear_diagram()
    scene = BehaviorScene()
    view = QGraphicsView(scene)
    assert view.scene() is scene
    scene.render_diagram(diagram)
    edge = scene._edges[0]
    target_handle = edge.target_handle
    blocks = {block.state_id: block for block in scene.items() if isinstance(block, StateBlock)}
    disabled_block = blocks[disabled.id]

    requests = []
    scene.transition_reattach_requested.connect(lambda *args: requests.append(args))

    scene._begin_reattach_drag(target_handle, target_handle.scenePos())
    scene._finish_reattach_drag(disabled_block.sceneBoundingRect().center())

    assert requests == []


def test_dragging_an_endpoint_onto_empty_space_is_a_no_op(qapp) -> None:
    diagram, _disabled, _autonomous, _teleop = _linear_diagram()
    scene = BehaviorScene()
    view = QGraphicsView(scene)
    assert view.scene() is scene
    scene.render_diagram(diagram)
    edge = scene._edges[0]
    target_handle = edge.target_handle

    requests = []
    scene.transition_reattach_requested.connect(lambda *args: requests.append(args))

    scene._begin_reattach_drag(target_handle, target_handle.scenePos())
    scene._finish_reattach_drag(QPointF(-9000, -9000))

    assert requests == []
    assert scene._reattach_handle is None


def test_dragging_an_endpoint_onto_a_decision_diamond_sets_a_sticky_anchor(qapp) -> None:
    """Dropping an endpoint on a specific corner should fix the line there, not to
    whatever point the automatic direction-based rule would otherwise pick."""
    disabled = BehaviorState(name=FieldValue(design="Disabled"))
    decision = BehaviorState(name=FieldValue(design="Ball Detected?"), kind="decision")
    autonomous = BehaviorState(name=FieldValue(design="Autonomous"))
    diagram = BehaviorDiagram(
        name="Robot Modes",
        states=[disabled, decision, autonomous],
        transitions=[BehaviorTransition(disabled.id, autonomous.id, "Go")],
    )
    scene = BehaviorScene()
    view = QGraphicsView(scene)
    assert view.scene() is scene
    scene.render_diagram(diagram)
    blocks = {block.state_id: block for block in scene.items() if isinstance(block, StateBlock)}
    decision_block = blocks[decision.id]
    decision_block.setPos(400, 400)
    rect = decision_block.sceneBoundingRect()
    left_point = QPointF(rect.left(), rect.center().y())

    edge = scene._edges[0]
    requests = []
    scene.transition_reattach_requested.connect(lambda *args: requests.append(args))

    scene._begin_reattach_drag(edge.target_handle, edge.target_handle.scenePos())
    scene._finish_reattach_drag(left_point)

    assert requests == [(diagram.transitions[0].id, "target", decision.id)]
    assert edge.target_anchor == "left"


def test_dropping_back_on_the_same_diamond_repositions_the_anchor_without_reattaching(
    qapp,
) -> None:
    """Picking a different corner of the diamond the line already connects to is a
    presentation tweak, not a rewire -- it shouldn't request reattachment."""
    disabled = BehaviorState(name=FieldValue(design="Disabled"))
    decision = BehaviorState(name=FieldValue(design="Ball Detected?"), kind="decision")
    diagram = BehaviorDiagram(
        name="Robot Modes",
        states=[disabled, decision],
        transitions=[BehaviorTransition(disabled.id, decision.id, "")],
    )
    scene = BehaviorScene()
    view = QGraphicsView(scene)
    assert view.scene() is scene
    scene.render_diagram(diagram)
    blocks = {block.state_id: block for block in scene.items() if isinstance(block, StateBlock)}
    decision_block = blocks[decision.id]
    decision_block.setPos(400, 0)
    scene._update_edge_paths()
    rect = decision_block.sceneBoundingRect()
    # A hair inside the boundary -- a point exactly on the rect's edge is unreliable for
    # itemAt() hit-testing, but still nearest to the bottom vertex either way.
    drop_point = QPointF(rect.center().x(), rect.bottom() - 2)

    edge = scene._edges[0]
    reattach_requests = []
    anchor_changes = []
    scene.transition_reattach_requested.connect(lambda *args: reattach_requests.append(args))
    scene.transition_anchor_changed.connect(lambda: anchor_changes.append(True))

    scene._begin_reattach_drag(edge.target_handle, edge.target_handle.scenePos())
    scene._finish_reattach_drag(drop_point)

    assert reattach_requests == []
    assert len(anchor_changes) == 1
    assert edge.target_anchor == "bottom"
    assert edge.path().currentPosition() == QPointF(rect.center().x(), rect.bottom())


def test_manual_diamond_anchor_survives_a_render_diagram_round_trip(qapp) -> None:
    """A sticky anchor is presentation state, so it must ride along in the layout dict
    through a render_diagram() rebuild and keep overriding automatic placement."""
    disabled = BehaviorState(name=FieldValue(design="Disabled"))
    decision = BehaviorState(name=FieldValue(design="Ball Detected?"), kind="decision")
    diagram = BehaviorDiagram(
        name="Robot Modes",
        states=[disabled, decision],
        transitions=[BehaviorTransition(disabled.id, decision.id, "")],
    )
    scene = BehaviorScene()
    scene.render_diagram(diagram)
    scene._edges[0].target_anchor = "right"
    scene._update_edge_paths()

    layout = scene.layout_state()
    transition_id = diagram.transitions[0].id
    assert layout[str(transition_id)] == {"source_anchor": None, "target_anchor": "right"}

    scene.render_diagram(diagram, layout)

    rebuilt_edge = scene._edges[0]
    assert rebuilt_edge.target_anchor == "right"

    blocks = {block.state_id: block for block in scene.items() if isinstance(block, StateBlock)}
    decision_block = blocks[decision.id]
    disabled_block = blocks[disabled.id]
    # Directly above the diamond -- the automatic rule would pick "top" here, but the
    # sticky "right" anchor must still win.
    disabled_block.setPos(decision_block.pos().x(), decision_block.pos().y() - 400)
    scene._update_edge_paths()

    rect = decision_block.sceneBoundingRect()
    assert rebuilt_edge.path().currentPosition() == QPointF(rect.right(), rect.center().y())
