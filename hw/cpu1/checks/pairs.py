"""
Measuring a differential pair off the board, for the checks that care.

Shared by `test_usb.py` and `test_ethernet.py`, which ask the same three
questions of different pairs: what impedance does the copper actually present,
how far apart in time do the two halves arrive, and how much copper did each
of them get.

Everything here reads the finished board file. None of it asks the layout what
it intended - that is the whole point of checking the geometry, and a pair
drawn at one width and spaced for another is exactly the case where the two
disagree.
"""

import math
import re

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / "tools"))
from layout_lib import point_to_segment  # noqa: E402

LIGHT = 299.792458e9      # mm per second


def tracks_of(pcb_text: str, nets: tuple[str, ...], layer: str | None = None
              ) -> dict[str, list]:
    """
    net -> [((x1, y1), (x2, y2), width, layer), ...] for its segments.

    Every layer by default. It used to default to F.Cu, which is where these
    pairs mostly are - and "mostly" is the problem: each Ethernet pair sends
    one half under the other on the back layer to swap them over, and a
    measurement that cannot see those segments is measuring most of a pair and
    reporting it as all of one.
    """
    numbers = {name: number for number, name in
               re.findall(r"\n\t\(net (\d+) \"([^\"]*)\"\)", pcb_text)}
    wanted = {numbers[name]: name for name in nets if name in numbers}

    out: dict[str, list] = {}
    for block in re.findall(r"\n\t\(segment\n(?:\t\t[^\n]*\n)+\t\)", pcb_text):
        found = {
            key: re.search(pattern, block)
            for key, pattern in (
                ("start", r"\(start ([-\d.]+) ([-\d.]+)\)"),
                ("end", r"\(end ([-\d.]+) ([-\d.]+)\)"),
                ("width", r"\(width ([\d.]+)\)"),
                ("layer", r'\(layer "([^"]+)"\)'),
                ("net", r"\(net (\d+)\)"),
            )
        }
        if not all(found.values()):
            continue
        if layer is not None and found["layer"].group(1) != layer:
            continue
        if found["net"].group(1) not in wanted:
            continue
        out.setdefault(wanted[found["net"].group(1)], []).append((
            (float(found["start"].group(1)), float(found["start"].group(2))),
            (float(found["end"].group(1)), float(found["end"].group(2))),
            float(found["width"].group(1)),
            found["layer"].group(1),
        ))
    return out


def controlled_width(tracks: dict[str, list]) -> float:
    """The width the pair's parallel run is drawn at: the widest it ever is."""
    return max(round(segment[2], 4) for segments in tracks.values() for segment in segments)


def separation(one: list, other: list) -> float:
    """
    How far apart the pair's parallel run is, centre to centre.

    Not "the distance between the two longest segments": a half that fans out,
    crosses under its partner and comes back has a long segment that is not
    part of the run at all, and on the Ethernet pairs that segment is the
    longest one either net has.

    So this looks for the two segments that actually run together - parallel,
    overlapping along their own direction - and takes the distance between the
    pair that overlap for the greatest length. That is the geometry the
    impedance comes from, and it is the only part of the route that has one.
    """
    best = None
    for (a1, a2, _, a_layer) in one:
        ax, ay = a2[0] - a1[0], a2[1] - a1[1]
        length = math.hypot(ax, ay)
        if not length:
            continue
        ux, uy = ax / length, ay / length
        for (b1, b2, _, b_layer) in other:
            if b_layer != a_layer:
                continue          # two halves on different layers are not a pair
            bx, by = b2[0] - b1[0], b2[1] - b1[1]
            if math.hypot(bx, by) < 1e-9:
                continue
            # Parallel, either way round.
            if abs(ux * by - uy * bx) > 1e-6 * math.hypot(bx, by):
                continue
            # How far the two overlap, projected onto the first's direction.
            span = sorted((ux * (b1[0] - a1[0]) + uy * (b1[1] - a1[1]),
                           ux * (b2[0] - a1[0]) + uy * (b2[1] - a1[1])))
            overlap = min(span[1], length) - max(span[0], 0.0)
            if overlap <= 0:
                continue
            distance = abs(-uy * (b1[0] - a1[0]) + ux * (b1[1] - a1[1]))
            if best is None or overlap > best[0]:
                best = (overlap, distance)
    if best is None:
        raise AssertionError("the pair's two halves never run parallel")
    return best[1]


def delay_per_mm(stack, width: float) -> float:
    """
    Seconds per millimetre along a microstrip, through its effective
    permittivity.

    A microstrip's field is half in the laminate and half in the air above it,
    so it propagates faster than the laminate alone would suggest and slower
    than air. Hammerstad's expression for that effective value; on this stackup
    it lands near 6 ps/mm, which is the number every layout rule of thumb is
    quoted in.
    """
    er = stack.epsilon_r
    effective = (er + 1) / 2 + ((er - 1) / 2) / math.sqrt(1 + 12.0 * stack.height / width)
    return math.sqrt(effective) / LIGHT


def coupled_length(one: list, other: list, width: float, gap: float
                   ) -> tuple[float, float, float]:
    """
    (how much of `one` runs beside `other`, how long `one` is altogether, and
    the longest unbroken stretch of it that runs alone).

    That third number is the one the physics is about. An uncoupled stretch is
    an impedance discontinuity, and what decides whether a discontinuity
    matters is its own extent against the rising edge - not the sum of every
    discontinuity on the route. A pair fans out at the package, crosses over
    in the middle and spreads again at the connector: three separate
    discontinuities, and adding them up and comparing the total against one
    edge length is both wrong and unfailable, because the total is bounded by
    the route length while the edge is far longer than the board.

    "Beside" means on the same layer with no more than `gap` between their
    copper **edges**. The caller passes that distance rather than this file
    inventing one: it is the same three dielectric heights the comparator
    separation is derived from, past which coupling between two microstrips
    has largely gone.

    It used to be three track widths, measured centre to centre - a number
    from nowhere, in the units nothing else on this board states pair geometry
    in. Everything else - the fan out of the package, the spread to the
    connector's pads, the excursion to the other layer to cross over - is two
    single tracks that happen to carry a differential signal.

    Sampled rather than solved, so it does not care about orientation and
    counts a converging pair for the part that is actually close.
    """
    limit = gap + width
    total = coupled = 0.0
    run = longest = 0.0
    for start, end, _, layer in one:
        length = math.dist(start, end)
        total += length
        if not length:
            continue
        steps = max(1, int(length / 0.05))
        for i in range(steps):
            fraction = (i + 0.5) / steps
            point = (start[0] + (end[0] - start[0]) * fraction,
                     start[1] + (end[1] - start[1]) * fraction)
            nearest = min(
                (point_to_segment(point, b_start, b_end)
                 for b_start, b_end, _, b_layer in other if b_layer == layer),
                default=float("inf"))
            if nearest <= limit:
                coupled += length / steps
                run = 0.0
            else:
                # Segments arrive in the order the router laid them, so a
                # stretch that spans two of them accumulates across the join.
                run += length / steps
                longest = max(longest, run)
    return coupled, total, longest


