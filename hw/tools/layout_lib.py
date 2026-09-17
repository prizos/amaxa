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


def footprint_pads(path: Path) -> dict[str, list[Pad]]:
    """Every copper pad in a `.kicad_mod`, by number, in the footprint's own frame."""
    text = path.read_text()
    pads: dict[str, list[Pad]] = {}
    for match in re.finditer(
        r'\(pad "([^"]+)" (?!np_thru_hole)\w+ \w+\s*\(at ([-\d.]+) ([-\d.]+)(?: [-\d.]+)?\)\s*'
        r"\(size ([\d.]+) ([\d.]+)\)",
        text,
    ):
        number, x, y, w, h = match.groups()
        pads.setdefault(number, []).append(Pad(number, float(x), float(y), float(w), float(h)))
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
