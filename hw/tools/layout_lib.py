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


def footprint_holes(path: Path) -> list[Pad]:
    """
    The unplated holes in a `.kicad_mod` - mounting holes and connector posts.

    They carry no net and `footprint_pads` leaves them out for that reason, but
    a via cannot sit in one: the drill goes through whatever copper is there.
    Anything placing copper by searching for room has to see them.
    """
    return [
        Pad("", float(x), float(y), float(w), float(h), "npth")
        for x, y, w, h in re.findall(
            r'\(pad "[^"]*" np_thru_hole \w+\s*\(at ([-\d.]+) ([-\d.]+)(?: [-\d.]+)?\)\s*'
            r"\(size ([\d.]+) ([\d.]+)\)",
            path.read_text(),
        )
    ]


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


def point_to_segment(point, a, b) -> float:
    """
    How close a point comes to a line segment, not to either of its endpoints.

    Here rather than in a check because three of them wanted it and each had
    written its own - a mounting hole asking whether a track passes through
    it, a via asking how far it is from foreign copper, and a pair asking how
    much of one half runs beside the other.
    """
    (px, py), (ax, ay), (bx, by) = point, a, b
    dx, dy = bx - ax, by - ay
    if dx == 0.0 and dy == 0.0:
        return math.dist(point, a)
    along = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.dist(point, (ax + along * dx, ay + along * dy))


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


# The two constants the capacitance below needs, in SI: everything else in this
# module is millimetres, and the conversions are written out where they happen.
LIGHT = 2.99792458e8            # m/s
PERMITTIVITY = 8.854187817e-12  # F/m


def _effective_permittivity(width: float, stack: Microstrip) -> float:
    """Hammerstad's e_eff for a microstrip, which depends on how wide it is."""
    er = stack.epsilon_r
    return (er + 1) / 2 + ((er - 1) / 2) / math.sqrt(1 + 12.0 * stack.height / width)


def microstrip_impedance(width: float, stack: Microstrip) -> float:
    """
    Hammerstad's microstrip Z0, in ohms, valid either side of w = h.

    A second impedance model in this file, deliberately. `single_ended_impedance`
    above is IPC-2141's, and the pair widths and the DRU floors are solved with
    it, so it stays exactly as it is - changing it would move copper that is
    already drawn. But its logarithm goes negative once `0.8 w + t` exceeds
    `5.98 h`, which on this stackup is **1.343 mm**, and capacitance derived
    from it then comes out negative. A pad is several times wider than that.

    Hammerstad has a branch for each side of w = h and neither misbehaves, so
    it is what anything asking about wide copper uses.
    """
    effective = _effective_permittivity(width, stack)
    ratio = width / stack.height
    if ratio <= 1.0:
        return (60.0 / math.sqrt(effective)) * math.log(8.0 / ratio + ratio / 4.0)
    return (120.0 * math.pi / math.sqrt(effective)) / (
        ratio + 1.393 + 0.667 * math.log(ratio + 1.444))


def microstrip_capacitance(width: float, stack: Microstrip) -> float:
    """
    Farads per millimetre between copper of this width and the plane under it.

    A lossless line's capacitance per unit length is sqrt(e_eff) / (c * Z0), so
    this is the impedance read the other way round and the two cannot drift
    apart.

    It is what a crystal's load capacitors are sized against. Copper that runs
    to a crystal terminal is in parallel with that terminal's capacitor, and a
    few millimetres of it is a few tenths of a picofarad against capacitors of
    tens - small, and not small enough to leave out when the whole link has
    fifty parts per million to spend.
    """
    if width <= 0.0:
        raise ValueError(f"a track cannot be {width:g} mm wide")
    return math.sqrt(_effective_permittivity(width, stack)) / (
        LIGHT * microstrip_impedance(width, stack)) * 1e-3


def pad_capacitance(area: float, width: float, stack: Microstrip) -> float:
    """
    Farads between a pad and that same plane, fringing included.

    A pad is a very wide, very short microstrip, so it is one: capacitance per
    millimetre at the pad's width, times its length.

    **It used to be parallel plate**, and the reason recorded for replacing it
    was wrong. That reason said fringing is "half again to two and a half
    times the plate term, not a correction". Evaluated against every pad on
    cpu1's board file at this stackup, the fringing term is between 7 % and
    86 % of the plate term with a median of 23 % - a correction, which is what
    the argument it replaced had said. It reaches half again only on pads
    around a quarter of a millimetre across, of which this board has none.

    What does justify the change is the other half: one model instead of two.
    The parallel-plate pad sat beside a trace model that returned *negative*
    capacitance above 1.343 mm, and a file computing one physical quantity two
    incompatible ways will eventually be asked which answer it meant. The
    numbers moved by a quarter, not by an order of magnitude, and the crystal
    load capacitors this feeds were chosen with this model, not the old one.
    """
    if width <= 0.0:
        raise ValueError(f"a pad cannot be {width:g} mm wide")
    return microstrip_capacitance(width, stack) * (area / width)


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


# --- what the routed copper is worth as capacitance --------------------------
#
# **One implementation, two readers.** These used to live inside
# `cpu1/checks/conftest.py` as a fixture, which made them reachable from a
# check and from nothing else. The simulation decks need the same numbers - the
# trip bus is 137 pF of which sixteen is copper, and a deck that typed that
# figure would be the second copy of the design this repository exists to
# avoid - so the layout computes them once, writes them beside `lengths.json`,
# and both the checks and the decks read the file.


def reference_stack(board: dict, planes: list[dict]) -> dict:
    """
    Copper layer -> the dielectric between it and the nearest plane.

    Derived from the stackup and from which layers the design pours on, rather
    than written out: a layer's neighbour changes the moment the layer roles
    do, and the number that changes with it is a capacitance nobody would
    think to re-derive.

    **The nearest plane, not the nearest ground.** A microstrip's field stops
    at the first plane it meets whatever net that plane carries - a supply
    plane is an equipotential at these frequencies too. Only outer pours are
    excluded, because a pour on a signal layer is local copper rather than a
    reference.
    """
    grounds = {p["layer"] for p in planes} - {"F.Cu", "B.Cu"}
    copper = (["F.Cu"]
              + [f"In{n}.Cu" for n in range(1, board["copper_layers"] - 1)]
              + ["B.Cu"])
    dielectrics = board["stack"]
    if len(dielectrics) != len(copper) - 1:
        raise ValueError("a dielectric between every pair of copper layers")

    out: dict[str, Microstrip] = {}
    for index, layer in enumerate(copper):
        if layer in grounds:
            continue
        best = None
        for other, name in enumerate(copper):
            if name not in grounds:
                continue
            low, high = sorted((index, other))
            spanned = dielectrics[low:high]
            height = sum(d["thickness"] for d in spanned)
            # Thickness-weighted, because a stack of two dielectrics behaves as
            # one of the total thickness only if they share a permittivity.
            epsilon = sum(d["thickness"] * d["epsilon_r"] for d in spanned) / height
            if best is None or height < best.height:
                best = Microstrip(height=height, epsilon_r=epsilon)
        if best is None:
            raise ValueError(f"{layer} has no plane anywhere in the stack")
        out[layer] = best
    return out


def net_capacitance(pcb_text: str, stack: dict) -> dict[str, float]:
    """
    net -> farads of copper against the planes, tracks and pads together.

    The board's own stray capacitance, measured off the board file instead of
    declared. It is what the crystal load capacitors are sized against, what
    the trip bus's loading term is computed from, and what the trip deck drives
    its comparator output into - and a declared figure for any of those is a
    belief about copper that the copper can answer for itself.

    Vias are left out. A via on a signal net passes through an antipad in every
    plane it crosses, so what it adds is a fraction of what the same area of
    pad would, and counting it as though it were a pad would be worse than
    leaving it out.
    """
    names = dict(re.findall(r'\(net (\d+) "([^"]*)"\)', pcb_text))
    totals: dict[str, float] = {}

    for block in re.findall(r"\n\t\(segment\n(?:\t\t[^\n]*\n)+\t\)", pcb_text):
        start = re.search(r"\(start ([-\d.]+) ([-\d.]+)\)", block)
        end = re.search(r"\(end ([-\d.]+) ([-\d.]+)\)", block)
        width = re.search(r"\(width ([\d.]+)\)", block)
        layer = re.search(r'\(layer "([^"]+)"\)', block)
        number = re.search(r"\(net (\d+)\)", block)
        if not (start and end and width and layer and number):
            continue
        net = names.get(number.group(1), "")
        length = math.dist(
            (float(start.group(1)), float(start.group(2))),
            (float(end.group(1)), float(end.group(2))),
        )
        per_mm = microstrip_capacitance(float(width.group(1)), stack[layer.group(1)])
        totals[net] = totals.get(net, 0.0) + length * per_mm

    for block in re.findall(r'\t\t\(pad "[^"]*" \w+ \w+\n(?:\t\t\t[^\n]*\n)+?\t\t\)', pcb_text):
        number = re.search(r'\(net \d+ "([^"]*)"\)', block)
        size = re.search(r"\(size ([\d.]+) ([\d.]+)\)", block)
        layers = re.search(r"\(layers ([^\n]*)\)", block)
        if not (number and size and layers):
            continue
        # A through-hole pad is on both outer layers; a surface pad on one. It
        # is the copper facing a plane that matters, so each face counts.
        faces = [name for name in ("F.Cu", "B.Cu")
                 if f'"{name}"' in layers.group(1) or '"*.Cu"' in layers.group(1)]
        # The wider side is the one the microstrip model is asked about: a pad
        # is a very wide, very short line, and it is the width across the field
        # that sets the capacitance per unit of the other direction.
        across = max(float(size.group(1)), float(size.group(2)))
        area = float(size.group(1)) * float(size.group(2))
        for face in faces:
            totals[number.group(1)] = totals.get(number.group(1), 0.0) + pad_capacitance(
                area, across, stack[face])

    return totals
