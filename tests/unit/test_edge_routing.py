from PySide6.QtCore import QPointF, QRectF

from frc_arch_modeler.ui.edge_routing import (
    last_segment_endpoints,
    route_edge,
    route_points,
)


def test_route_points_with_no_obstacles_returns_the_straight_line() -> None:
    start = QPointF(0, 0)
    end = QPointF(100, 100)

    assert route_points(start, end, []) == [start, end]


def test_route_points_with_an_obstacle_clear_of_the_line_stays_straight() -> None:
    start = QPointF(0, 0)
    end = QPointF(100, 0)
    far_away_obstacle = QRectF(0, 500, 40, 40)

    assert route_points(start, end, [far_away_obstacle]) == [start, end]


def test_route_points_detours_around_a_blocking_obstacle() -> None:
    start = QPointF(0, 0)
    end = QPointF(100, 0)
    blocker = QRectF(40, -10, 20, 20)  # squarely on the straight line

    points = route_points(start, end, [blocker])

    assert points[0] == start
    assert points[-1] == end
    assert len(points) > 2
    inflated = blocker.adjusted(-14.0, -14.0, 14.0, 14.0)
    for p1, p2 in zip(points, points[1:]):
        midpoint = QPointF((p1.x() + p2.x()) / 2, (p1.y() + p2.y()) / 2)
        assert not inflated.contains(midpoint)


def test_route_points_falls_back_to_the_straight_line_when_no_detour_clears_everything() -> None:
    start = QPointF(0, 0)
    end = QPointF(100, 0)
    # A single obstacle so large that every L/U-shaped candidate still clips it.
    engulfing_obstacle = QRectF(-1000, -1000, 2000, 2000)

    assert route_points(start, end, [engulfing_obstacle]) == [start, end]


def test_route_edge_builds_a_qpainterpath_through_the_routed_points() -> None:
    start = QPointF(0, 0)
    end = QPointF(100, 0)
    blocker = QRectF(40, -10, 20, 20)

    path = route_edge(start, end, [blocker])

    assert path.elementCount() > 2
    assert QPointF(path.elementAt(0).x, path.elementAt(0).y) == start
    last = path.elementAt(path.elementCount() - 1)
    assert QPointF(last.x, last.y) == end


def test_last_segment_endpoints_reads_the_final_two_points() -> None:
    path = route_edge(QPointF(0, 0), QPointF(100, 0), [QRectF(40, -10, 20, 20)])

    before, tip = last_segment_endpoints(path)

    last_element = path.elementAt(path.elementCount() - 1)
    second_last_element = path.elementAt(path.elementCount() - 2)
    assert tip == QPointF(last_element.x, last_element.y)
    assert before == QPointF(second_last_element.x, second_last_element.y)


def test_last_segment_endpoints_on_a_plain_two_point_line() -> None:
    path = route_edge(QPointF(0, 0), QPointF(100, 0), [])

    before, tip = last_segment_endpoints(path)

    assert before == QPointF(0, 0)
    assert tip == QPointF(100, 0)
