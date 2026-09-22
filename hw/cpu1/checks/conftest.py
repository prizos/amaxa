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
def net_voltages(spec):
    """
    (named net -> the volts it sits at, the default for everything else).

    **One copy.** This table was written out twice - once in `test_power.py`
    for what a resistor dissipates and once in `test_core.py` for what a
    capacitor has to stand off - and the two had already drifted apart: one
    knew about `3V3A` and the other did not, one listed `UVLO` and the other
    stopped. `cpu1.py` says of `trip.budget` and of `layout.decoupling_reach`
    that two copies of a number is the defect this repository does not
    accept, and this was two copies of ten of them.

    The default is the logic rail. Every signal net on this board is driven
    from it - the MCU, the buffers, the latch, the comparators through their
    pull-ups - and the two that break it, the field buses, are checked against
    their transceivers' own declared fault voltage instead.

    `UVLO` is deliberately *not* here. It is a divider tap, not the input
    voltage, and naming it at V_IN is what once left the lockout divider's top
    leg with zero volts across it and no bound at all. Unnamed, the walk finds
    the other leg and derives both.
    """
    _, input_high = spec("input", "voltage")
    _, v5 = spec("rail.5v", "voltage")
    _, v3v3 = spec("rail.3v3", "voltage")
    return {
        "GND": 0.0,
        "VIN": input_high, "VIN_RAW": input_high, "VIN_FUSED": input_high,
        "RPP_GATE": input_high, "SW_5V": input_high,
        "5V": v5, "SW_3V3": v5,
        "3V3": v3v3, "3V3A": v3v3,
    }, v3v3


@pytest.fixture(scope="session")
def effective_capacitance(spec):
    """
    `effective_capacitance(address, bias)` -> the low end of what that
    capacitor is worth at that DC bias, in farads.

    Nominal, less its tolerance, less `capacitors.bias_derating` times the
    fraction of its rated voltage the bias represents.

    **Not every datasheet figure is held against it**, and this used to claim
    they all were. A figure that is a *minimum* is - the converters' input
    capacitance, the 3V3 output window's floor, the LM5164's bootstrap range,
    the analog regulator's, ST's CEXT. A figure that specifies a part to fit
    rather than a floor to clear is not, because no part can deliver its own
    nominal once tolerance is taken off and reading it as a floor would
    reject every part that satisfies it: TI's "connect a 0.1 uF capacitor"
    for the TPS562200's bootstrap is the example, and the check there says so
    beside the one that does apply the model.
    """
    _, coefficient = spec("capacitors", "bias_derating")

    def lookup(address: str, bias: float) -> float:
        low, _ = spec(address, "capacitance")
        rated, _ = spec(address, "max_voltage")
        return max(0.0, low * (1.0 - coefficient * min(1.0, bias / rated)))

    return lookup


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
    Copper layer -> the dielectric between it and the nearest plane.

    Derived from the stackup and from which layers the design pours on, rather
    than written out: a layer's neighbour changes the moment the layer roles
    do, and the number that changes with it is a capacitance nobody would
    think to re-derive.

    **The nearest plane, not the nearest ground.** A microstrip's field stops
    at the first plane it meets whatever net that plane carries - a supply
    plane is an equipotential at these frequencies too - and this said ground
    while `plane_layers` in test_routing.py said plane, so two fixtures gave
    In3.Cu two different heights, 0.43 mm and 0.175. Only outer pours are
    excluded, because a pour on a signal layer is local copper rather than a
    reference: the same distinction `plane_layers` draws.
    """
    module = _layout(board_dir)
    from layout_lib import Microstrip

    board = module.BOARD
    grounds = {p["layer"] for p in module.PLANES} - {"F.Cu", "B.Cu"}

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
    from layout_lib import microstrip_capacitance, pad_capacitance

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
        per_mm = microstrip_capacitance(float(width.group(1)), layer_stack[layer.group(1)])
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
        # The wider side is the one the microstrip model is asked about: a pad
        # is a very wide, very short line, and it is the width across the
        # field that sets the capacitance per unit of the other direction.
        across = max(float(size.group(1)), float(size.group(2)))
        area = float(size.group(1)) * float(size.group(2))
        for face in faces:
            totals[number.group(1)] = totals.get(number.group(1), 0.0) + pad_capacitance(
                area, across, layer_stack[face])

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


@pytest.fixture(scope="session")
def forward_voltage(spec):
    """
    A Schottky's forward drop at the current and temperature it is used at.

    The datasheet gives three points - 0.1, 1 and 10 mA - and a family of
    curves against temperature. One figure was being used for all of it, the
    0.1 mA row, on a bus that runs these at nearly three times that and on a
    board declared down to 0 degC. Log-linear between the rows, then the
    tempco off FIG.1.
    """
    import math

    def at(address: str, current: float, ambient: float) -> float:
        curve = sorted(
            (amps, spec(address, f"forward_voltage_at_{name}")[1])
            for amps, name in ((100e-6, "100ua"), (1e-3, "1ma"), (10e-3, "10ma"))
        )
        tempco, _ = spec(address, "forward_voltage_tempco")
        current = min(max(current, curve[0][0]), curve[-1][0])
        drop = curve[-1][1]
        for (i0, v0), (i1, v1) in zip(curve, curve[1:]):
            if current <= i1:
                drop = v0 + (v1 - v0) * math.log10(current / i0) / math.log10(i1 / i0)
                break
        return drop + tempco * (ambient - 25.0)

    return at
