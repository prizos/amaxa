"""
cpu1 placement and routing.

Read by hw/tools/layout.py. Coordinates are millimetres in the board's own frame:
x runs right, y runs down, origin at the centre.

So far this places the MCU and stitches its ground pads down to the In1 ground
plane. Everything else is added block by block, and routes will increasingly be
computed from pad geometry rather than written as coordinates — which is why the
ground stitching below is generated from the footprint file, not listed.

The board size is provisional: it gets decided once the blocks and the headers
to the power board are placed.
"""

import math
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tools"))

from stm32 import Silicon  # noqa: E402

# --- the board itself --------------------------------------------------------
#
# PCBWay's published "regular" 4-layer build, from
# pcbway.com/multi-layer-laminated-structure.html, read 2026-09-17: 0.5 oz outer
# base copper plated to 1 oz, 7628 prepreg at 0.1855 mm after lamination
# (Dk 4.74), 1 oz inner copper, and a 1.03 mm core (Dk 4.6). 1.51 mm ±10 %
# finished.

BOARD = {
    "size": (100.0, 80.0),       # provisional
    "corner_radius": 3.0,
    "thickness": 1.51,
    "copper_layers": 4,
    "copper_thickness": 0.035,
    "inner_copper_thickness": 0.035,
    "stack": [
        {"type": "prepreg", "thickness": 0.1855, "epsilon_r": 4.74},
        {"type": "core", "thickness": 1.03, "epsilon_r": 4.6},
        {"type": "prepreg", "thickness": 0.1855, "epsilon_r": 4.74},
    ],
    "core_thickness": 1.03,
    "finish": "ENIG",
    "mask_colour": "Black",
    "pour_inset": 0.5,
}

MCU_AT = (0.0, 0.0)

PLACEMENT = {
    "mcu": MCU_AT,
}

LABELS = {
    "*": (0.0, -1.7),
    "mcu": (0.0, -12.5),
}

LABEL_FONT = {"size": 1.0, "thickness": 0.15}

ROUTES: list = []

# --- ground stitching ----------------------------------------------------------
#
# Every MCU ground pad gets its own via to the In1 plane, straight out from the
# package. The pads are 0.3 mm wide at 0.5 mm pitch, so the stub is 0.2 mm - the
# 0.5 mm default suits an 0805 and would short a QFP pad to both neighbours. The
# via sits 1 mm beyond the pad's outer end, clear of the neighbours' pads.

VIA = (0.6, 0.3)
STUB = 0.2
_FOOTPRINT = HERE / "parts" / "LQFP144" / "LQFP-144_20x20mm_P0.5mm.kicad_mod"


def _pads() -> dict[str, tuple[float, float, float, float]]:
    """Pad number -> (x, y, width, height) in the footprint's own frame."""
    text = _FOOTPRINT.read_text()
    return {
        number: (float(x), float(y), float(w), float(h))
        for number, x, y, w, h in re.findall(
            r'\(pad "(\d+)" smd \w+\s*\(at ([-\d.]+) ([-\d.]+)\)\s*\(size ([\d.]+) ([\d.]+)\)',
            text,
        )
    }


def _escape(x: float, y: float, w: float, h: float, gap: float = 1.0) -> tuple[float, float]:
    """A point `gap` beyond a peripheral pad's outer end, straight out from the package."""
    if abs(x) > abs(y):
        reach = abs(x) + w / 2 + gap
        return (math.copysign(reach, x), y)
    reach = abs(y) + h / 2 + gap
    return (x, math.copysign(reach, y))


def _ground_vias() -> list:
    silicon = Silicon("STM32H743ZITx")
    pads = _pads()
    vias = []
    for name in ("VSS", "VSSA"):
        for number in silicon.pins[name].positions:
            x, y, w, h = pads[number]
            ex, ey = _escape(x, y, w, h)
            vias.append((f"mcu:{number}", (MCU_AT[0] + ex, MCU_AT[1] + ey), "GND", *VIA, STUB))
    return vias


VIAS = _ground_vias()


def _pour_outline() -> list[tuple[float, float]]:
    width, height = BOARD["size"]
    x, y = width / 2 - BOARD["pour_inset"], height / 2 - BOARD["pour_inset"]
    return [(-x, -y), (x, -y), (x, y), (-x, y)]


# One solid ground plane on the first inner layer. The second inner layer gets
# the supply islands once the power block exists.
PLANES = [
    {
        "net": "GND",
        "layer": "In1.Cu",
        "outline": _pour_outline(),
        "pad_clearance": 0.3,
        "min_thickness": 0.25,
        "thermal_gap": 0.3,
        "thermal_bridge": 0.4,
    },
]
