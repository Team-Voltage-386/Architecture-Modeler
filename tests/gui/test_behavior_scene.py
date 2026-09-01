import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtWidgets import QGraphicsView

from frc_arch_modeler.domain.model import (
    BehaviorDiagram,
    BehaviorState,
    BehaviorTransition,
    FieldValue,
)
from frc_arch_modeler.ui.architecture_scene import ArchitectureScene
from frc_arch_modeler.ui.behavior_scene import (
    DECISION_SIZE,
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
    plain = BehaviorState(name=FieldValue(design="Disabled"))
    diagram = BehaviorDiagram(name="Robot Modes", states=[start, decision, sync, end, plain])
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
    assert blocks[plain.id].kind == "state"


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
