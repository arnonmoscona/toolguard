"""
Round the corners of Graphviz orthogonal edges in an SVG.

``splines=ortho`` gives short, readable right-angle runs but hard 90-degree
corners. Graphviz has no rounded-ortho mode, so this rounds them afterwards:
each edge path is reduced to its polyline, and every interior corner is
replaced by a quadratic arc that starts and ends *radius* along the two
adjoining segments.

Only paths inside ``<g class="edge">`` are touched. Node shapes, cluster
rectangles and arrowheads are left exactly as Graphviz drew them.

Usage:
    round_svg_corners.py in.svg out.svg [--radius 6]
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import List, Tuple

Point = Tuple[float, float]

#: An edge group and the path inside it. Graphviz emits one path per edge.
_EDGE_PATH = re.compile(
    r'(<g id="edge\d+" class="edge">.*?<path[^>]*?\sd=")([^"]+)(")', re.DOTALL
)

_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")


def path_points(d: str) -> List[Point]:
    """
    The polyline behind an orthogonal edge path.

    Graphviz writes ortho segments as cubic Béziers whose control points lie on
    the segment, so every coordinate in the path is on the polyline. Taking all
    of them and dropping duplicates and collinear midpoints recovers the corners
    exactly, without having to interpret the command letters.
    """
    values = [float(v) for v in _NUMBER.findall(d)]
    raw = list(zip(values[0::2], values[1::2]))

    points: List[Point] = []
    for point in raw:
        if (
            not points
            or abs(point[0] - points[-1][0]) > 1e-9
            or abs(point[1] - points[-1][1]) > 1e-9
        ):
            points.append(point)

    simplified: List[Point] = []
    for point in points:
        if len(simplified) >= 2:
            (x0, y0), (x1, y1) = simplified[-2], simplified[-1]
            cross = (x1 - x0) * (point[1] - y0) - (y1 - y0) * (point[0] - x0)
            if abs(cross) < 1e-6:
                simplified[-1] = point  # collinear: extend rather than turn
                continue
        simplified.append(point)
    return simplified


def _shift(origin: Point, towards: Point, distance: float) -> Point:
    """A point *distance* from *origin* along the line to *towards*."""
    dx, dy = towards[0] - origin[0], towards[1] - origin[1]
    length = (dx * dx + dy * dy) ** 0.5
    if length == 0:
        return origin
    ratio = min(distance, length / 2) / length
    return (origin[0] + dx * ratio, origin[1] + dy * ratio)


def rounded_path(points: List[Point], radius: float) -> str:
    """An SVG path over *points* with each interior corner arced."""
    if len(points) < 3:
        return "M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in points)

    parts = [f"M{points[0][0]:.2f},{points[0][1]:.2f}"]
    for index in range(1, len(points) - 1):
        corner = points[index]
        entry = _shift(corner, points[index - 1], radius)
        exit_ = _shift(corner, points[index + 1], radius)
        parts.append(f"L{entry[0]:.2f},{entry[1]:.2f}")
        parts.append(f"Q{corner[0]:.2f},{corner[1]:.2f} {exit_[0]:.2f},{exit_[1]:.2f}")
    parts.append(f"L{points[-1][0]:.2f},{points[-1][1]:.2f}")
    return "".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path)
    parser.add_argument("--radius", type=float, default=6.0)
    args = parser.parse_args()

    text = args.source.read_text()
    rounded = 0
    corners = 0

    def replace(match: re.Match) -> str:
        nonlocal rounded, corners
        points = path_points(match.group(2))
        if len(points) < 3:
            return match.group(0)
        rounded += 1
        corners += len(points) - 2
        return match.group(1) + rounded_path(points, args.radius) + match.group(3)

    args.target.write_text(_EDGE_PATH.sub(replace, text))
    print(f"rounded {corners} corner(s) across {rounded} edge(s) -> {args.target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
