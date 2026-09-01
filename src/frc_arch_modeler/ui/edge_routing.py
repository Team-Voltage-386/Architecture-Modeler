"""Pure-geometry orthogonal detour routing shared by both diagram scenes.

Every connector starts life as a straight line between two clipped boundary points. When
that line is clear of every other block, it stays exactly that -- a plain two-point path,
identical to the pre-routing behavior. Only when it actually crosses another block does
this module compute a right-angle detour around it. Diagrams here are FRC-project scale
(well under 20 blocks), so a small set of candidate detours, tried and the best one kept,
is simpler and just as effective as a general shortest-path router.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QPainterPath

OBSTACLE_MARGIN = 14.0


def route_points(
    start: QPointF, end: QPointF, obstacles: list[QRectF], margin: float = OBSTACLE_MARGIN
) -> list[QPointF]:
    """Bend points (including start/end) detouring around obstacles where possible.

    Returns ``[start, end]`` unchanged whenever the straight line is already clear of
    every (margin-inflated) obstacle, or when no candidate detour clears them all.
    """
    if not obstacles:
        return [start, end]
    inflated = [rect.adjusted(-margin, -margin, margin, margin) for rect in obstacles]
    blocking = sorted(
        (rect for rect in inflated if _segment_crosses_rect(start, end, rect)),
        key=lambda rect: (rect.left(), rect.top()),
    )
    if not blocking:
        return [start, end]
    candidates = _candidate_routes(start, end, blocking)
    valid = [points for points in candidates if _path_is_clear(points, inflated)]
    if not valid:
        return [start, end]
    return min(valid, key=lambda points: (_path_length(points), len(points)))


def route_edge(
    start: QPointF, end: QPointF, obstacles: list[QRectF], margin: float = OBSTACLE_MARGIN
) -> QPainterPath:
    """``route_points(...)`` rendered as a QPainterPath of straight lineTo segments."""
    points = _dedupe(route_points(start, end, obstacles, margin))
    path = QPainterPath(points[0])
    for point in points[1:]:
        path.lineTo(point)
    return path


def last_segment_endpoints(path: QPainterPath) -> tuple[QPointF, QPointF]:
    """(second-to-last, last) point of a path -- for orienting an arrowhead at its tip."""
    count = path.elementCount()
    if count < 2:
        current = path.currentPosition()
        return QPointF(current), QPointF(current)
    before = path.elementAt(count - 2)
    last = path.elementAt(count - 1)
    return QPointF(before.x, before.y), QPointF(last.x, last.y)


_CANDIDATE_CLEARANCE = 1.0


def _candidate_routes(
    start: QPointF, end: QPointF, blocking: list[QRectF]
) -> list[list[QPointF]]:
    candidates = [
        [start, QPointF(end.x(), start.y()), end],
        [start, QPointF(start.x(), end.y()), end],
    ]
    for rect in blocking:
        # Nudged a hair past the (already-inflated) obstacle so the detour's own hop
        # doesn't sit exactly on the boundary it's meant to be checked as clearing.
        top = rect.top() - _CANDIDATE_CLEARANCE
        bottom = rect.bottom() + _CANDIDATE_CLEARANCE
        left = rect.left() - _CANDIDATE_CLEARANCE
        right = rect.right() + _CANDIDATE_CLEARANCE
        candidates.append([start, QPointF(start.x(), top), QPointF(end.x(), top), end])
        candidates.append([start, QPointF(start.x(), bottom), QPointF(end.x(), bottom), end])
        candidates.append([start, QPointF(left, start.y()), QPointF(left, end.y()), end])
        candidates.append([start, QPointF(right, start.y()), QPointF(right, end.y()), end])
    return candidates


def _path_is_clear(points: list[QPointF], obstacles: list[QRectF]) -> bool:
    points = _dedupe(points)
    for p1, p2 in zip(points, points[1:]):
        if any(_segment_crosses_rect(p1, p2, rect) for rect in obstacles):
            return False
    return True


def _path_length(points: list[QPointF]) -> float:
    points = _dedupe(points)
    total = 0.0
    for p1, p2 in zip(points, points[1:]):
        total += ((p2.x() - p1.x()) ** 2 + (p2.y() - p1.y()) ** 2) ** 0.5
    return total


def _dedupe(points: list[QPointF]) -> list[QPointF]:
    result = [points[0]]
    for point in points[1:]:
        if point != result[-1]:
            result.append(point)
    if len(result) == 1:
        result.append(points[-1])
    return result


def _segment_crosses_rect(p1: QPointF, p2: QPointF, rect: QRectF) -> bool:
    if rect.contains(p1) or rect.contains(p2):
        return True
    corners = [rect.topLeft(), rect.topRight(), rect.bottomRight(), rect.bottomLeft()]
    return any(
        _segments_intersect(p1, p2, corners[i], corners[(i + 1) % 4]) for i in range(4)
    )


def _orientation(a: QPointF, b: QPointF, c: QPointF) -> float:
    return (b.x() - a.x()) * (c.y() - a.y()) - (b.y() - a.y()) * (c.x() - a.x())


def _on_segment(a: QPointF, b: QPointF, c: QPointF) -> bool:
    """True if c (already known collinear with a-b) lies within the a-b segment's span."""
    return min(a.x(), b.x()) <= c.x() <= max(a.x(), b.x()) and min(a.y(), b.y()) <= c.y() <= max(
        a.y(), b.y()
    )


def _segments_intersect(p1: QPointF, p2: QPointF, p3: QPointF, p4: QPointF) -> bool:
    d1 = _orientation(p3, p4, p1)
    d2 = _orientation(p3, p4, p2)
    d3 = _orientation(p1, p2, p3)
    d4 = _orientation(p1, p2, p4)
    if ((d1 > 0) != (d2 > 0)) and ((d1 < 0) != (d2 < 0)) and ((d3 > 0) != (d4 > 0)) and (
        (d3 < 0) != (d4 < 0)
    ):
        return True
    if d1 == 0 and _on_segment(p3, p4, p1):
        return True
    if d2 == 0 and _on_segment(p3, p4, p2):
        return True
    if d3 == 0 and _on_segment(p1, p2, p3):
        return True
    if d4 == 0 and _on_segment(p1, p2, p4):
        return True
    return False
