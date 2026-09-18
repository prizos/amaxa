"""
Geometry for generating a layout rather than writing one out.

A board's `layout.py` is plain data - placement, routes, vias, planes - which is
fine for thirty parts and hopeless for a 144-pin MCU. These helpers let it be
computed instead: where a quad-flat package's pin points, what lies a given
distance along that line, and which way to turn a two-pad part so its first pad
faces the package.

Coordinates follow KiCad's board frame, as tools/layout.py does: x right, y down,
millimetres, and a footprint's rotation turns it anticlockwise on screen.

Dependency-free, so it runs under the system Python like the layout engine.
"""

import math
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Pad:
    number: str
    x: float
    y: float
    width: float
    height: float
    # "smd" or "thru_hole". A through-hole pad is already in every layer, so it
    # meets an inner plane without needing a via; a surface pad does not, and
    # anything that stitches pads to planes has to tell them apart.
    kind: str = "smd"


def footprint_pads(path: Path) -> dict[str, list[Pad]]:
    """Every copper pad in a `.kicad_mod`, by number, in the footprint's own frame."""
    text = path.read_text()
    pads: dict[str, list[Pad]] = {}
    for match in re.finditer(
        r'\(pad "([^"]+)" (?!np_thru_hole)(\w+) \w+\s*\(at ([-\d.]+) ([-\d.]+)(?: [-\d.]+)?\)\s*'
        r"\(size ([\d.]+) ([\d.]+)\)",
        text,
    ):
        number, kind, x, y, w, h = match.groups()
        pads.setdefault(number, []).append(
            Pad(number, float(x), float(y), float(w), float(h), kind)
        )
    return pads


@dataclass(frozen=True)
class QfpPin:
    """
    One pin of a quad-flat package placed unrotated at `origin`.

    `normal` points out of the package, away from its centre; `tangent` runs
    along the side. Distances along the pin's line are measured from the
    package centre, so `outer` is where the pad ends on the outside and `inner`
    where it ends on the inside.
    """

    number: str
    origin: tuple[float, float]
    centre: tuple[float, float]
    normal: tuple[float, float]
    radius: float
    inner: float
    outer: float

    @property
    def tangent(self) -> tuple[float, float]:
        nx, ny = self.normal
        return (-ny, nx)

    def at(self, distance: float, across: float = 0.0) -> tuple[float, float]:
        """The point `distance` from the package centre along this pin's line, shifted `across`."""
        ox, oy = self.origin
        nx, ny = self.normal
        tx, ty = self.tangent
        along = self.centre_along
        return (
            round(ox + nx * distance + tx * (along + across), 4),
            round(oy + ny * distance + ty * (along + across), 4),
        )

    @property
    def centre_along(self) -> float:
        """Where along its side the pin sits, in the tangent's direction."""
        tx, ty = self.tangent
        return self.centre[0] * tx + self.centre[1] * ty

    def facing(self, towards_package: bool = True) -> int:
        """
        The rotation that points a two-pad part's pad 1 along this pin's line.

        Pad 1 of a stock two-pad footprint is at negative x. Turned by this, it
        is the pad nearer the package, so the pin reaches it first.
        """
        nx, ny = self.normal
        angle = {(1, 0): 0, (0, -1): 90, (-1, 0): 180, (0, 1): 270}[(round(nx), round(ny))]
        return angle if towards_package else (angle + 180) % 360


def qfp_pins(path: Path, origin: tuple[float, float] = (0.0, 0.0)) -> dict[str, QfpPin]:
    """Every peripheral pad of an unrotated quad-flat footprint, as a `QfpPin`."""
    out = {}
    for number, pads in footprint_pads(path).items():
        pad = pads[0]
        if abs(pad.x) > abs(pad.y):
            normal = (math.copysign(1, pad.x), 0.0)
            radius, half = abs(pad.x), pad.width / 2
        else:
            normal = (0.0, math.copysign(1, pad.y))
            radius, half = abs(pad.y), pad.height / 2
        out[number] = QfpPin(
            number=number,
            origin=origin,
            centre=(pad.x, pad.y),
            normal=normal,
            radius=radius,
            inner=radius - half,
            outer=radius + half,
        )
    return out


def offset(point: tuple[float, float], dx: float = 0.0, dy: float = 0.0) -> tuple[float, float]:
    return (round(point[0] + dx, 4), round(point[1] + dy, 4))


# --- controlled impedance ----------------------------------------------------
#
# A differential pair's width and gap are not a style choice, and they are not
# properties of the pair: they follow from the stackup the fab builds. Writing
# 0.25 mm and 0.2 mm into a layout file records the answer to a calculation
# nobody can see, and leaves it unchanged when the stackup does.
#
# The formulas are IPC-2141's, for edge-coupled microstrip over one reference
# plane. They are approximations - a few per cent against a field solver, and
# worse as the trace gets much wider or narrower than the dielectric is thick -
# which is why what they produce is checked against a band rather than a number.


@dataclass(frozen=True)
class Microstrip:
    """The layer a pair runs on, and the dielectric under it."""

    height: float       # to the nearest reference plane, mm
    epsilon_r: float
    copper: float = 0.035   # finished thickness, mm; 1 oz


def single_ended_impedance(width: float, stack: Microstrip) -> float:
    """IPC-2141 equation 1: one microstrip trace over a plane, in ohms."""
    return (87.0 / math.sqrt(stack.epsilon_r + 1.41)) * math.log(
        5.98 * stack.height / (0.8 * width + stack.copper)
    )


def differential_impedance(width: float, gap: float, stack: Microstrip) -> float:
    """
    IPC-2141's edge-coupled pair: two of those, coupled by the gap between them.

    The coupling term falls away as the gap grows, so a pair spread far apart
    tends to twice the single-ended impedance - which is the sanity check on
    this formula, and the reason a pair that wanders apart is a pair whose
    impedance rises.
    """
    return 2.0 * single_ended_impedance(width, stack) * (
        1.0 - 0.48 * math.exp(-0.96 * gap / stack.height)
    )


def pair_geometry(target: float, stack: Microstrip, gap: float,
                  minimum: float = 0.1, maximum: float = 1.0) -> float:
    """
    The trace width that hits `target` ohms differential at a given gap.

    Solved rather than tabulated: impedance falls monotonically with width, so
    a bisection converges on the one width that fits this stackup. If the fab's
    minimum width cannot reach the target, that is a real answer and it raises
    rather than returning the nearest miss.
    """
    low, high = minimum, maximum
    if differential_impedance(low, gap, stack) < target:
        raise ValueError(
            f"{target:g} ohm needs a trace narrower than {minimum:g} mm on this "
            f"stackup: {differential_impedance(low, gap, stack):.1f} ohm at the minimum"
        )
    if differential_impedance(high, gap, stack) > target:
        raise ValueError(f"{target:g} ohm needs a trace wider than {maximum:g} mm")
    for _ in range(60):
        middle = (low + high) / 2
        if differential_impedance(middle, gap, stack) > target:
            low = middle
        else:
            high = middle
    return round((low + high) / 2, 3)


# --- routing a pair ----------------------------------------------------------


def _offset_polyline(points: list[tuple[float, float]], distance: float
                     ) -> list[tuple[float, float]]:
    """
    One side of a polyline, `distance` away, measured perpendicular to it.

    Each vertex moves to where its two neighbouring offset segments meet, so
    the two sides of a pair stay the same distance apart through a corner
    instead of pinching on the inside of it and opening on the outside.
    """
    def unit(a, b):
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = math.hypot(dx, dy)
        if not length:
            raise ValueError(f"a zero-length segment at {a}")
        return dx / length, dy / length

    out = []
    for index, point in enumerate(points):
        before = unit(points[index - 1], point) if index else None
        after = unit(point, points[index + 1]) if index + 1 < len(points) else None
        if before is None:
            direction = after
        elif after is None:
            direction = before
        else:
            # The miter: where the two offset segments actually meet. The
            # offset distance is perpendicular to each segment, so at a corner
            # the vertex has to move further than `distance` to keep both sides
            # that far from their own segment - otherwise the pair pinches on
            # the inside of every turn and opens on the outside.
            left_before = (-before[1], before[0])
            left_after = (-after[1], after[0])
            mx, my = left_before[0] + left_after[0], left_before[1] + left_after[1]
            length = math.hypot(mx, my)
            if length < 1e-9:        # a reversal; nothing sensible to offset to
                raise ValueError(f"the path doubles back at {point}")
            mx, my = mx / length, my / length
            reach = distance / (mx * left_before[0] + my * left_before[1])
            out.append((round(point[0] + mx * reach, 4),
                        round(point[1] + my * reach, 4)))
            continue
        out.append((round(point[0] - direction[1] * distance, 4),
                    round(point[1] + direction[0] * distance, 4)))
    return out


def diff_pair(centre: list[tuple[float, float]], width: float, gap: float
              ) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
    """
    Two polylines either side of a centre line, `gap` apart edge to edge.

    Written as one line and offset, rather than as two lines that happen to run
    near each other, because "the same path, mirrored" is the property that
    makes a pair a pair - equal length, constant separation - and two
    hand-written lists of points do not have it.
    """
    half = (gap + width) / 2
    return _offset_polyline(centre, -half), _offset_polyline(centre, half)


def path_length(points: list[tuple[float, float]]) -> float:
    """Millimetres along a polyline."""
    return round(sum(math.dist(a, b) for a, b in zip(points, points[1:])), 4)
