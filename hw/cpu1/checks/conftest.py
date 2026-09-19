"""
Fixtures shared by cpu1's own checks.

All of them are about the board as built rather than as designed: the stackup
the layout computes its impedances from, what each net's copper actually
measured once it was routed, and what that copper is worth as capacitance
against the planes it runs over.
"""

import json
import math
import re
import sys

import pytest


def _layout(board_dir):
    """The board's own layout module, for the stackup and the plane list."""
    sys.path.insert(0, str(board_dir.parent / "tools"))
    from mcu_pins import load_source

    return load_source(board_dir / "layout.py", "cpu1_layout_stack")


@pytest.fixture(scope="session")
def stack(board_dir):
    """The dielectric between the outer layers and the plane beside them."""
    board = _layout(board_dir).BOARD
    from layout_lib import Microstrip

    first = board["stack"][0]
    return Microstrip(height=first["thickness"], epsilon_r=first["epsilon_r"])


@pytest.fixture(scope="session")
def layer_stack(board_dir):
    """
    Copper layer -> the dielectric between it and the nearest ground plane.

    Derived from the stackup and from which layers the design pours ground on,
    rather than written out: a layer's neighbour changes the moment the layer
    roles do, and the number that changes with it is a capacitance nobody would
    think to re-derive.
    """
    module = _layout(board_dir)
    from layout_lib import Microstrip

    board = module.BOARD
    grounds = {p["layer"] for p in module.PLANES if p["net"] == "GND"}

    copper = ["F.Cu"] + [f"In{n}.Cu" for n in range(1, board["copper_layers"] - 1)] + ["B.Cu"]
    dielectrics = board["stack"]
    assert len(dielectrics) == len(copper) - 1, "a dielectric between every pair of layers"

    out = {}
    for index, layer in enumerate(copper):
        if layer in grounds:
            continue
        # Walk outward from this layer until a ground plane turns up, adding
        # the dielectric crossed at each step. The nearer side wins.
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
        assert best is not None, f"{layer} has no ground plane anywhere in the stack"
        out[layer] = best
    return out


@pytest.fixture(scope="session")
def board_capacitance(pcb_text, layer_stack):
    """
    net -> farads of copper against the ground planes, tracks and pads together.

    The board's own stray capacitance, measured off the board file instead of
    declared. It is what the crystal load capacitors are sized against, and a
    declared figure there is a belief about copper that the copper can answer
    for itself.

    Vias are left out. A via on a signal net passes through an antipad in every
    plane it crosses, so what it adds is a fraction of what the same area of
    pad would, and counting it as though it were a pad would be worse than
    leaving it out.
    """
    from layout_lib import pad_capacitance, trace_capacitance

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
        per_mm = trace_capacitance(float(width.group(1)), layer_stack[layer.group(1)])
        totals[net] = totals.get(net, 0.0) + length * per_mm

    for block in re.findall(r'\t\t\(pad "[^"]*" \w+ \w+\n(?:\t\t\t[^\n]*\n)+?\t\t\)', pcb_text):
        number = re.search(r'\(net \d+ "([^"]*)"\)', block)
        size = re.search(r"\(size ([\d.]+) ([\d.]+)\)", block)
        layers = re.search(r'\(layers ([^\n]*)\)', block)
        if not (number and size and layers):
            continue
        # A through-hole pad is on both outer layers; a surface pad on one. It
        # is the copper facing a plane that matters, so each face counts.
        faces = [name for name in ("F.Cu", "B.Cu") if f'"{name}"' in layers.group(1)
                 or '"*.Cu"' in layers.group(1)]
        area = float(size.group(1)) * float(size.group(2))
        for face in faces:
            totals[number.group(1)] = totals.get(number.group(1), 0.0) + pad_capacitance(
                area, layer_stack[face])

    def lookup(net: str) -> float:
        assert net in totals, f"no copper on {net}"
        return totals[net]

    return lookup


@pytest.fixture(scope="session")
def lengths(build_dir):
    """net -> millimetres of copper, written by the layout as it routed."""
    report = build_dir / "lengths.json"
    assert report.is_file(), "no lengths.json; run `make layout` first"
    return json.loads(report.read_text())
