"""
cpu1 placement and routing.

Read by hw/tools/layout.py. Coordinates are millimetres in the board's own frame:
x runs right, y runs down, origin at the centre, where the MCU sits.

Most of this is computed, not written. The MCU's supply pins are found in
design.json by the nets they are on, and every one of them gets the same
treatment from the pin's own geometry:

- **Its plane via goes inward.** An LQFP-144 has an 18 mm square of empty board
  inside its pad ring, where no signal will ever escape. Supply pins sit next to
  each other at 0.5 mm pitch, so outside the ring their vias would collide; inside
  they stagger in rings - ground at 9.3 mm from the centre, 3V3 at 8.5 mm, and a
  second 3V3 ring at 7.7 mm for a 3V3 pin beside another.
- **Its capacitor goes outward**, turned so its first pad faces the pin, with a
  straight track to it and its ground via beyond.

Everything else - the crystals, the analog supply's filter, debug, indicators -
is placed by hand where the pins it serves come out, and routed where routing is
what the check depends on. The rest waits, and board.mk says so.

The board size is provisional until the blocks and the headers to the power
board are placed.
"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tools"))

import layout_lib  # noqa: E402
from layout_lib import qfp_pins  # noqa: E402
from mcu_pins import load_source  # noqa: E402

# --- the board itself --------------------------------------------------------
#
# PCBWay's published "regular" 4-layer build, from
# pcbway.com/multi-layer-laminated-structure.html, read 2026-09-17: 0.5 oz outer
# base copper plated to 1 oz, 7628 prepreg at 0.1855 mm after lamination
# (Dk 4.74), 1 oz inner copper, and a 1.03 mm core (Dk 4.6). 1.51 mm ±10 %
# finished.

BOARD = {
    # 130 x 110 rather than the 100 x 80 this started at. The RJ45 is 19 by
    # 22 mm with its magnetics inside it and has to sit on an edge, and there
    # was no square that size left. Growing the board is the cheap side of that
    # trade: a larger panel costs a few cents, and the alternative is a jack
    # crowding the analog front end.
    "size": (130.0, 110.0),      # provisional
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

F, B = "F.Cu", "B.Cu"
VIA = (0.5, 0.2)          # PCBWay: 0.15 mm drill, 0.15 mm annular ring, minimum
STUB = 0.2                # between 0.5 mm-pitch pads
SUPPLY = 0.25             # pin to its capacitor

MCU = "mcu"
PINS = qfp_pins(HERE / "parts" / "LQFP144" / "LQFP-144_20x20mm_P0.5mm.kicad_mod")


def _design() -> dict:
    path = HERE / "build" / "design.json"
    return json.loads(path.read_text()) if path.is_file() else {"parts": {}, "nets": {}}


DESIGN = _design()
NET_AT = {
    (address, pad): net
    for net, nodes in _design()["nets"].items()
    for address, pad in nodes
}
NET_OF_PIN = {
    pad: net
    for net, nodes in DESIGN["nets"].items()
    for address, pad in nodes
    if address == MCU
}

PLACEMENT: dict = {MCU: (0.0, 0.0)}
LABELS: dict = {"*": (0.0, -1.2), MCU: (0.0, -6.0)}
LABEL_FONT = {"size": 0.8, "thickness": 0.15}   # fab minimum
ROUTES: list = []
VIAS: list = []


# --- supply pins: plane vias inward ----------------------------------------------

GROUND_RING, SUPPLY_RING, SUPPLY_RING_2 = 9.3, 8.5, 7.7


def _supply_vias() -> None:
    rings: dict[int, float] = {}
    for number in sorted((int(n) for n, net in NET_OF_PIN.items() if net in ("3V3", "GND"))):
        net = NET_OF_PIN[str(number)]
        if net == "GND":
            ring = GROUND_RING
        else:
            beside = [rings.get(number - 1), rings.get(number + 1)]
            ring = SUPPLY_RING_2 if SUPPLY_RING in beside else SUPPLY_RING
        rings[number] = ring
        pin = PINS[str(number)]
        VIAS.append((f"{MCU}:{number}", pin.at(ring), net, *VIA, STUB))


# --- decoupling: capacitors outward ------------------------------------------------

CAP_CENTRE, CAP_VIA = 12.9, 14.2
# An 0402 is 0.62 mm across and the pins are 0.5 mm apart, so two capacitors on
# neighbouring pins cannot both sit on their pin's line. Each moves this far
# away from the other, and its track jogs out to it once clear of the pads.
SPREAD, JOG = 0.5, 11.9


def _decoupling() -> None:
    served = {
        address.rsplit("p", 1)[1]: address
        for address in DESIGN["parts"]
        if address.startswith(("core.dec.p", "core.vcap.p"))
    }
    taken: dict[tuple[float, float], list[float]] = {}
    for number, address in sorted(served.items(), key=lambda kv: int(kv[0])):
        pin = PINS[number]
        lines = taken.setdefault(pin.normal, [])
        # The first line far enough from every capacitor already on this side.
        # Two pins apart is enough room; one is not, whether the pin between
        # them carries a capacitor or - as at VREF+, between VSSA and VDDA -
        # nothing at all.
        for across in (0.0, SPREAD, -SPREAD, 2 * SPREAD, -2 * SPREAD):
            if all(abs(pin.centre_along + across - line) >= 2 * SPREAD for line in lines):
                break
        else:
            raise ValueError(f"no room for a capacitor on pin {number}")
        lines.append(pin.centre_along + across)
        PLACEMENT[address] = (*pin.at(CAP_CENTRE, across), pin.facing())
        LABELS[address] = _label_beside(pin)
        path = [f"{MCU}:{number}"]
        if across:
            path += [pin.at(JOG), pin.at(JOG + abs(across), across)]
        ROUTES.append((NET_OF_PIN[number], SUPPLY, F, path + [f"{address}:1"]))
        VIAS.append((f"{address}:2", pin.at(CAP_VIA, across), "GND", *VIA, SUPPLY))


def _label_beside(pin) -> tuple[float, float]:
    """Silkscreen for a part on a pin's line: pushed further out, clear of the ring."""
    nx, ny = pin.normal
    return (round(nx * 2.4, 3), round(ny * 2.4, 3))


# --- the analog supply ---------------------------------------------------------------
#
# VDDA's 100 nF sits on its pin's line like every other supply pin's. The rest of
# its filter - 1 uF and the ferrite from 3V3 - has no room there: the pins either
# side carry capacitors or future escapes. So VDDA also leaves its pin inward,
# through a via to the bottom layer, and meets the filter in the free corner
# below-left of the package.

VDDA_PIN = "33"


def _analog_supply() -> None:
    pin = PINS[VDDA_PIN]
    inward = pin.at(SUPPLY_RING)
    VIAS.append((f"{MCU}:{VDDA_PIN}", inward, "VDDA", *VIA, STUB))
    corner_via = (-11.5, 12.5)
    ROUTES.append(("VDDA", SUPPLY, B, [inward, (-12.0, inward[1]), (-12.0, 11.5), (-11.5, 12.0), corner_via]))
    VIAS.append((None, corner_via, "VDDA", *VIA))

    PLACEMENT["core.vdda.c1u"] = (-13.0, 12.5, 180)
    PLACEMENT["core.vdda.bead"] = (-13.0, 14.0, 0)      # pad 2, VDDA, towards the via
    LABELS["core.vdda.c1u"] = (-2.0, 0.0)
    LABELS["core.vdda.bead"] = (-2.0, 0.0)
    ROUTES.append(("VDDA", SUPPLY, F, [corner_via, "core.vdda.c1u:1"]))
    ROUTES.append(("VDDA", SUPPLY, F, [corner_via, (-11.5, 14.0), "core.vdda.bead:2"]))
    VIAS.append(("core.vdda.c1u:2", (-14.4, 12.5), "GND", *VIA, SUPPLY))
    VIAS.append(("core.vdda.bead:1", (-14.4, 14.0), "3V3", *VIA, SUPPLY))


# --- clocks ------------------------------------------------------------------------------

def _crystals() -> None:
    # 8 MHz, left of pins 23 and 24. Turned so pad 1 is the upper one and the two
    # tracks from the pins never cross.
    hse_in, hse_out = PINS["23"], PINS["24"]
    PLACEMENT["core.hse.crystal"] = (-16.0, 2.5, 270)
    PLACEMENT["core.hse.c_in"] = (-19.2, 0.65, 180)
    PLACEMENT["core.hse.c_out"] = (-19.2, 4.35, 180)
    LABELS["core.hse.crystal"] = (-3.4, 0.0)
    LABELS["core.hse.c_in"] = (0.0, -1.0)
    LABELS["core.hse.c_out"] = (0.0, 1.0)
    ROUTES.append(("HSE_IN", 0.2, F, [f"{MCU}:23", (-13.8, hse_in.at(0)[1]), (-13.8, 0.65), "core.hse.crystal:1"]))
    ROUTES.append(("HSE_OUT", 0.2, F, [f"{MCU}:24", (-12.8, hse_out.at(0)[1]), (-12.8, 4.35), "core.hse.crystal:2"]))
    ROUTES.append(("HSE_IN", 0.2, F, ["core.hse.crystal:1", "core.hse.c_in:1"]))
    ROUTES.append(("HSE_OUT", 0.2, F, ["core.hse.crystal:2", "core.hse.c_out:1"]))
    VIAS.append(("core.hse.c_in:2", (-20.6, 0.65), "GND", *VIA, SUPPLY))
    VIAS.append(("core.hse.c_out:2", (-20.6, 4.35), "GND", *VIA, SUPPLY))

    # 32.768 kHz, left of pins 8 and 9. Its crystal terminals are pads 1 and 4,
    # both on one end; turned to face the MCU.
    lse_in, lse_out = PINS["8"], PINS["9"]
    PLACEMENT["core.lse.crystal"] = (-19.0, -5.5, 180)
    PLACEMENT["core.lse.c_in"] = (-16.25, -9.6, 90)
    PLACEMENT["core.lse.c_out"] = (-16.25, -1.7, 270)
    LABELS["core.lse.crystal"] = (0.0, 0.0)
    LABELS["core.lse.c_in"] = (-1.3, 0.0)
    LABELS["core.lse.c_out"] = (-1.3, 0.0)
    ROUTES.append(("LSE_IN", 0.2, F, [f"{MCU}:8", (-15.0, lse_in.at(0)[1]), (-15.0, -7.1), "core.lse.crystal:1"]))
    ROUTES.append(("LSE_OUT", 0.2, F, [f"{MCU}:9", (-14.4, lse_out.at(0)[1]), (-14.4, -3.9), "core.lse.crystal:4"]))
    ROUTES.append(("LSE_IN", 0.2, F, ["core.lse.crystal:1", "core.lse.c_in:1"]))
    ROUTES.append(("LSE_OUT", 0.2, F, ["core.lse.crystal:4", "core.lse.c_out:1"]))
    VIAS.append(("core.lse.c_in:2", (-16.25, -10.6), "GND", *VIA, SUPPLY))
    VIAS.append(("core.lse.c_out:2", (-17.3, -1.22), "GND", *VIA, SUPPLY))


def path(net: str, width: float, legs: list) -> None:
    """
    One route that changes layer, with a via at each change.

    `legs` is [(layer, [points...]), ...]; consecutive legs must share their
    meeting point, and that point becomes a through via on the net.
    """
    for layer, points in legs:
        ROUTES.append((net, width, layer, points))
    for (_, before), (_, after) in zip(legs, legs[1:]):
        assert before[-1] == after[0], f"{net}: legs do not meet at {before[-1]} / {after[0]}"
        VIAS.append((None, before[-1], net, *VIA))


# --- everything else -------------------------------------------------------------------
#
# Debug, indicators, the button, reset and boot. Each sits where the pin it
# serves comes out. The three debug signals leave the package on three different
# sides, so they cross on the bottom layer, under the ring of supply vias, and
# surface beside the Tag-Connect pads.

SIGNAL = 0.15
DEBUG_LEFT, DEBUG_RIGHT = 18.2, 21.8   # via columns either side of the SWD pads


def _placed() -> None:
    # Bulk capacitance in the two top corners, where no pin escapes.
    PLACEMENT["core.bulk"] = (-13.5, -13.5, 0)
    VIAS.append(("core.bulk:1", (-15.0, -13.5), "3V3", *VIA, SUPPLY))
    VIAS.append(("core.bulk:2", (-12.0, -13.5), "GND", *VIA, SUPPLY))
    PLACEMENT["core.usb_bulk"] = (13.5, -13.5, 0)
    VIAS.append(("core.usb_bulk:1", (12.5, -13.5), "3V3", *VIA, SUPPLY))
    VIAS.append(("core.usb_bulk:2", (14.5, -13.5), "GND", *VIA, SUPPLY))
    _debug()
    _indicators()
    _button()
    _boot_and_console()


def _debug() -> None:
    """
    SWD on a Tag-Connect footprint, turned so its pads run in two columns.

    Its own keepout forbids vias under the pads, so each pad reaches its net
    through a via in the column beside it. 3V3 and ground need no route at all:
    their vias land on the planes.
    """
    PLACEMENT["core.swd"] = (20.0, -20.0, 90)
    LABELS["core.swd"] = (0.0, 3.2)
    for pad, x, y, net in (
        ("2", DEBUG_LEFT, -18.73, "SWDIO"), ("4", DEBUG_LEFT, -20.0, "SWCLK"),
        ("6", DEBUG_LEFT, -21.27, "SWO"), ("1", DEBUG_RIGHT, -18.73, "3V3"),
        ("3", DEBUG_RIGHT, -20.0, "NRST"), ("5", DEBUG_RIGHT, -21.27, "GND"),
    ):
        VIAS.append((f"core.swd:{pad}", (x, y), net, *VIA, SUPPLY if net in ("3V3", "GND") else SIGNAL))

    # Out of the package, down to the bottom layer, across, and up to the pads.
    for pin, net, pad_y in (("105", "SWDIO", -18.73), ("109", "SWCLK", -20.0), ("133", "SWO", -21.27)):
        p = PINS[pin]
        # SWDIO's pin is next to VCAP2, whose capacitor and ground via fill its
        # line out to 14.4 mm; it steps onto the neighbouring line and surfaces
        # beyond them.
        legs = [f"{MCU}:{pin}"]
        if pin == "105":
            legs += [p.at(11.9), p.at(12.4, 0.65)]
            out = p.at(15.6, 0.65)
        else:
            out = p.at(12.3)
        path(net, SIGNAL, [
            (F, legs + [out]),
            (B, [out, (out[0], pad_y) if pin != "105" else (out[0], pad_y), (DEBUG_LEFT, pad_y)]),
        ])

    # NRST leaves inward - the 8 MHz crystal fills the outward side of its pin -
    # crosses beneath the package, and picks up its capacitor on the way.
    inward = PINS["25"].at(SUPPLY_RING_2)
    VIAS.append((f"{MCU}:25", inward, "NRST", *VIA, STUB))
    # Along the middle of the package and out to the right, clear of the three
    # debug tracks running down to the pads.
    PLACEMENT["core.nrst.cap"] = (24.6, -2.0, 0)
    LABELS["core.nrst.cap"] = (0.0, -1.3)
    VIAS.append(("core.nrst.cap:2", (26.2, -2.0), "GND", *VIA, SUPPLY))
    cap_via = (23.2, -2.0)
    path("NRST", SIGNAL, [
        (B, [inward, (-6.5, 0.5), (23.2, 0.5), cap_via]),
        (F, [cap_via, "core.nrst.cap:1"]),
    ])
    ROUTES.append(("NRST", SIGNAL, B, [cap_via, (23.2, -20.0), (DEBUG_RIGHT, -20.0)]))


def _indicators() -> None:
    """Each LED and its resistor on the line of the pin that drives it."""
    apart = {"91": "92", "92": "91"}
    for key, pin in (("status", "142"), ("fault", "91"), ("comms", "92")):
        p = PINS[pin]
        spread = 0.0
        if pin in apart:
            spread = 0.5 if PINS[apart[pin]].centre_along < p.centre_along else -0.5
        resistor, led = f"core.led.{key}.resistor", f"core.led.{key}.led"
        PLACEMENT[resistor] = (*p.at(13.6, spread), p.facing())
        PLACEMENT[led] = (*p.at(16.8, spread * 3), p.facing(towards_package=False))
        LABELS[resistor] = _label_beside(p)
        LABELS[led] = _label_beside(p)
        route = [f"{MCU}:{pin}"]
        if spread:
            route += [p.at(12.2), p.at(12.6, spread)]
        ROUTES.append((f"LED_{key.upper()}", SIGNAL, F, route + [f"{resistor}:1"]))
        ROUTES.append((f"LED_{key.upper()}_A", SIGNAL, F, [
            f"{resistor}:2", p.at(15.0, spread), p.at(15.0, spread * 3), f"{led}:2",
        ]))
        VIAS.append((f"{led}:1", p.at(18.8, spread * 3), "GND", *VIA, SUPPLY))


def _button() -> None:
    """
    The button sits clear of the crystals, which fill the package's left side.

    Its leads are through holes, so the bottom-layer track reaches one pole
    directly, and the pole tied to 3V3 meets that plane through its own holes.
    """
    PLACEMENT["core.button.switch"] = (-30.0, 14.0)
    PLACEMENT["core.button.pulldown"] = (-26.5, 20.5, 0)
    LABELS["core.button.switch"] = (3.2, -2.4)
    LABELS["core.button.pulldown"] = (0.0, -1.3)
    inward = PINS["7"].at(SUPPLY_RING_2)
    VIAS.append((f"{MCU}:7", inward, "BUTTON", *VIA, STUB))
    ROUTES.append(("BUTTON", SIGNAL, B, [
        inward, (0.5, -7.0), (0.5, -11.5), (-12.6, -11.5), (-12.6, 12.0),
        (-14.0, 16.0), "core.button.switch:2",
    ]))
    ROUTES.append(("BUTTON", SIGNAL, F, ["core.button.switch:2", "core.button.pulldown:1"]))
    VIAS.append(("core.button.pulldown:2", (-25.0, 20.5), "GND", *VIA, SUPPLY))


def _boot_and_console() -> None:
    """BOOT0's pull-down and pad, and the console's pads, beside their pins."""
    boot = PINS["138"]
    PLACEMENT["core.boot0.pulldown"] = (*boot.at(15.5), boot.facing())
    PLACEMENT["tp_boot0"] = boot.at(19.5)
    LABELS["core.boot0.pulldown"] = _label_beside(boot)
    LABELS["tp_boot0"] = (-2.6, 0.0)
    ROUTES.append(("BOOT0", SIGNAL, F, [f"{MCU}:138", "core.boot0.pulldown:1"]))
    ROUTES.append(("BOOT0", SIGNAL, F, [
        "tp_boot0:1", (-7.0, -19.5), (-7.0, -15.02), "core.boot0.pulldown:1",
    ]))
    VIAS.append(("core.boot0.pulldown:2", boot.at(17.2), "GND", *VIA, SUPPLY))

    # The console's pads follow its pins' order, so the tracks never cross.
    PLACEMENT["tp_console_tx"] = (22.0, 6.75)
    PLACEMENT["tp_console_rx"] = (22.0, 4.0)
    PLACEMENT["tp_gnd"] = (22.0, 9.5)
    PLACEMENT["tp_3v3"] = (22.0, 12.25)
    for address in ("tp_console_tx", "tp_console_rx", "tp_gnd", "tp_3v3"):
        LABELS[address] = (2.6, 0.0)
    ROUTES.append(("CONSOLE_TX", SIGNAL, F, [f"{MCU}:77", "tp_console_tx:1"]))
    ROUTES.append(("CONSOLE_RX", SIGNAL, F, [
        f"{MCU}:78", (19.0, 6.25), (19.0, 4.0), "tp_console_rx:1",
    ]))
    VIAS.append(("tp_gnd:1", (23.6, 9.5), "GND", *VIA, SUPPLY))
    VIAS.append(("tp_3v3:1", (23.6, 12.25), "3V3", *VIA, SUPPLY))



# --- the power block ---------------------------------------------------------
#
# Along the bottom edge, left to right, in the order the current flows: terminal,
# fuse, reverse-polarity FET, TVS, input capacitance, the 100 V buck, then the
# 3V3 buck in the bottom-right corner.
#
# Everything on the input hangs off one horizontal track at BUS - the y of the
# buck's own VIN pin - with its ground via straight below. Everything on 5 V
# connects through a via instead: the second inner layer carries a 5 V island
# inside the 3V3 plane, at a higher priority, so the two pours keep clear of
# each other without either outline being drawn around the other.

BUS = 29.36                        # the input rail, at the 100 V buck's VIN pin
POWER = 0.4                        # the input rail, before any regulator
RAIL = 0.3                         # 5 V and the switch nodes
# The island stops short of the bottom edge: the power-good pull-up sits below
# it, and a 3V3 via inside the island would reach nothing but a gap.
ISLAND = (-9.0, 24.5, 33.0, 36.5)  # the 5 V island on In2.Cu: x0, y0, x1, y1


def _power() -> None:
    _input_stage()
    _buck_5v()
    _buck_3v3()
    _reference()


def _input_stage() -> None:
    """Terminal, fuse, FET and TVS, in a line, with the gate network below."""
    PLACEMENT["power.terminal"] = (-41.5, BUS, 180)
    PLACEMENT["power.fuse"] = (-35.5, BUS, 0)
    PLACEMENT["power.q_rpp"] = (-29.0, BUS - 3.15, 90)
    PLACEMENT["power.r_gate"] = (-32.5, 33.0, 180)
    PLACEMENT["power.d_gate_clamp"] = (-28.5, 33.0, 180)
    PLACEMENT["buck5.c_in1"] = (-22.0, BUS - 1.48, 90)
    PLACEMENT["buck5.c_in2"] = (-18.0, BUS - 1.48, 90)
    PLACEMENT["power.tvs"] = (-14.0, BUS - 2.15, 90)
    PLACEMENT["buck5.c_in_hf"] = (-10.5, BUS - 0.78, 90)
    PLACEMENT["tp_vin"] = (-22.0, 36.0)
    for address in ("power.terminal", "power.fuse", "power.q_rpp", "power.tvs",
                    "power.r_gate", "power.d_gate_clamp", "buck5.c_in1",
                    "buck5.c_in2", "buck5.c_in_hf", "tp_vin"):
        LABELS[address] = (0.0, -2.6)

    ROUTES.append(("VIN_RAW", POWER, F, ["power.terminal:1", "power.fuse:1"]))
    # Around the FET rather than into it: its three leads are in a row on the
    # line the rail runs along, and the gate comes first. So the fused rail
    # goes under the package to the tab, and down the middle of the pads, which
    # is the drain lead. KiCad numbers lead and tab alike and the netlist puts
    # them on one net, but each is a pad of its own and each has to be reached.
    ROUTES.append(("VIN_FUSED", POWER, F, [
        "power.fuse:2", (-34.1, 25.0), (-29.0, 25.0),
    ]))
    ROUTES.append(("VIN_FUSED", POWER, F, [(-29.0, BUS), (-29.0, BUS - 6.3)]))

    # The gate: to ground through R6, clamped to the source by D4.
    ROUTES.append(("RPP_GATE", SIGNAL, F, [(-31.3, BUS), (-31.3, 33.0), "power.r_gate:1"]))
    ROUTES.append(("RPP_GATE", SIGNAL, F, ["power.d_gate_clamp:2", "power.r_gate:1"]))
    VIAS.append(("power.r_gate:2", (-34.2, 33.0), "GND", *VIA, SUPPLY))
    ROUTES.append(("VIN", POWER, F, ["power.d_gate_clamp:1", (-26.85, 30.0)]))

    # The rail behind the FET, out to the buck. Each part on it hangs below the
    # line on its own pad and drops to the ground plane beyond.
    ROUTES.append(("VIN", POWER, F, [(-26.7, BUS), "buck5.ic:2"]))
    ROUTES.append(("VIN", POWER, F, ["tp_vin:1", (-22.0, BUS)]))
    for address, via_y in (("buck5.c_in1", 25.1), ("buck5.c_in2", 25.1),
                           ("power.tvs", 23.8), ("buck5.c_in_hf", 26.6)):
        x = PLACEMENT[address][0]
        VIAS.append((f"{address}:2", (x, via_y), "GND", *VIA, POWER))


def _buck_5v() -> None:
    """
    The 100 V buck: on-time resistor, lockout divider, ripple network, feedback.

    Its exposed pad is the part's only heat path, and it is a ground pad: four
    vias under it reach the ground plane on the first inner layer.
    """
    PLACEMENT["buck5.ic"] = (-5.0, BUS + 0.64, 0)
    PLACEMENT["buck5.r_uvlo_top"] = (-10.5, 32.0, 270)
    PLACEMENT["buck5.r_uvlo_bottom"] = (-10.5, 34.5, 270)
    PLACEMENT["buck5.r_on"] = (-7.64, 36.0, 270)
    PLACEMENT["buck5.c_bst"] = (-0.5, 28.6, 270)
    PLACEMENT["buck5.inductor"] = (5.5, 28.09, 0)
    PLACEMENT["buck5.r_ramp"] = (2.0, 32.5, 0)
    PLACEMENT["buck5.c_ramp"] = (5.0, 32.5, 0)
    PLACEMENT["buck5.c_couple"] = (0.0, 34.5, 0)
    PLACEMENT["buck5.r_fb_top"] = (-5.0, 33.6, 0)
    PLACEMENT["buck5.r_fb_bottom"] = (-2.36, 34.4, 270)
    PLACEMENT["buck5.r_pgood"] = (5.5, 37.5, 0)
    PLACEMENT["tp_pgood"] = (2.0, 37.5)
    PLACEMENT["buck5.c_out1"] = (11.5, 29.04, 90)
    PLACEMENT["buck5.c_out2"] = (14.0, 29.04, 90)
    PLACEMENT["tp_5v"] = (16.0, 26.0)
    for address in ("buck5.ic", "buck5.r_uvlo_top", "buck5.r_uvlo_bottom", "buck5.r_on",
                    "buck5.c_bst", "buck5.inductor", "buck5.r_ramp", "buck5.c_ramp",
                    "buck5.c_couple", "buck5.r_fb_top", "buck5.r_fb_bottom",
                    "buck5.r_pgood", "tp_pgood", "buck5.c_out1", "buck5.c_out2", "tp_5v"):
        LABELS[address] = (0.0, -2.6)

    for dx, dy in ((-0.6, -0.9), (0.6, -0.9), (-0.6, 0.9), (0.6, 0.9)):
        VIAS.append((None, (-5.0 + dx, BUS + 0.64 + dy), "GND", *VIA))
    # The ground lead is a pad of its own; it reaches the plane through the
    # exposed pad beside it, which is where the vias are.
    ROUTES.append(("GND", SUPPLY, F, ["buck5.ic:1", (-6.0, 28.6)]))

    # Undervoltage lockout, straight down from the input's own high-frequency
    # capacitor, and back up to EN clear of the on-time pin beside it.
    ROUTES.append(("VIN", POWER, F, [(-10.5, BUS), "buck5.r_uvlo_top:1"]))
    ROUTES.append(("UVLO", SIGNAL, F, ["buck5.r_uvlo_top:2", "buck5.r_uvlo_bottom:1"]))
    ROUTES.append(("UVLO", SIGNAL, F, [
        (-10.5, 33.2), (-9.0, 33.2), (-9.0, 30.64), "buck5.ic:3",
    ]))
    VIAS.append(("buck5.r_uvlo_bottom:2", (-10.5, 36.2), "GND", *VIA, SUPPLY))

    # The on-time resistor, as short a trace as the datasheet asks for: straight
    # down out of the pin.
    ROUTES.append(("RON", SIGNAL, F, ["buck5.ic:4", "buck5.r_on:1"]))
    VIAS.append(("buck5.r_on:2", (-7.64, 37.7), "GND", *VIA, SUPPLY))

    # The switch node: bootstrap capacitor, then the inductor.
    ROUTES.append(("SW_5V", POWER, F, ["buck5.ic:8", "buck5.c_bst:1"]))
    ROUTES.append(("SW_5V", POWER, F, ["buck5.c_bst:1", "buck5.inductor:1"]))
    ROUTES.append(("BST_5V", SIGNAL, F, ["buck5.ic:7", "buck5.c_bst:2"]))

    # The ripple network: a ramp off the switch node into the feedback pin.
    ROUTES.append(("SW_5V", RAIL, F, ["buck5.r_ramp:1", (1.49, 28.09)]))
    ROUTES.append(("RAMP", SIGNAL, F, ["buck5.r_ramp:2", "buck5.c_ramp:1"]))
    ROUTES.append(("RAMP", SIGNAL, F, ["buck5.c_couple:2", (2.51, 34.5), (2.51, 32.5)]))
    ROUTES.append(("FB_5V", SIGNAL, F, ["buck5.ic:5", (-2.36, 33.2)]))
    ROUTES.append(("FB_5V", SIGNAL, F, [(-2.36, 33.2), "buck5.r_fb_bottom:1"]))
    ROUTES.append(("FB_5V", SIGNAL, F, ["buck5.r_fb_top:2", (-2.36, 33.2)]))
    ROUTES.append(("FB_5V", SIGNAL, F, [
        "buck5.c_couple:1", (-1.5, 34.5), (-1.5, 33.2), (-2.36, 33.2),
    ]))
    VIAS.append(("buck5.r_fb_bottom:2", (-2.36, 36.1), "GND", *VIA, SUPPLY))

    # Everything on 5 V reaches the island underneath rather than each other.
    for pad, at in (("buck5.inductor:2", (8.52, 28.09)), ("buck5.c_ramp:2", (6.2, 32.5)),
                    ("buck5.r_fb_top:1", (-6.7, 33.6)), ("buck5.c_out1:1", (11.5, 31.2)),
                    ("buck5.c_out2:1", (14.0, 31.2)), ("tp_5v:1", (17.2, 26.0))):
        VIAS.append((pad, at, "5V", *VIA, POWER))
    for pad, at in (("buck5.c_out1:2", (11.5, 26.9)), ("buck5.c_out2:2", (14.0, 26.9))):
        VIAS.append((pad, at, "GND", *VIA, POWER))

    # Power good: out from between two pins, under the switch node on the bottom
    # layer, and up again where there is room for the pull-up and its pad.
    out = (-0.9, 30.64)
    path("PGOOD", SIGNAL, [
        (F, ["buck5.ic:6", out]),
        (B, [out, (-0.9, 39.0), (4.0, 39.0)]),
        (F, [(4.0, 39.0), (4.0, 37.5), "buck5.r_pgood:1"]),
    ])
    ROUTES.append(("PGOOD", SIGNAL, F, ["tp_pgood:1", (4.0, 37.5)]))
    VIAS.append(("buck5.r_pgood:2", (7.2, 37.5), "3V3", *VIA, SUPPLY))


def _buck_3v3() -> None:
    """
    The 3V3 buck, in the corner, straddling the edge of the 5 V island.

    Turned so its supply pins face the island and its switch node faces away:
    everything on 5 V reaches the island through a via of its own, and the rail
    it makes leaves to the right, past where the island ends, into the 3V3
    plane that covers the rest of the board.
    """
    PLACEMENT["buck3v3.ic"] = (31.0, 29.0, 180)
    PLACEMENT["buck3v3.c_bst"] = (31.0, 32.5, 180)
    PLACEMENT["buck3v3.c_in"] = (26.0, 26.5, 90)
    PLACEMENT["buck3v3.c_in_hf"] = (28.0, 26.5, 90)
    PLACEMENT["buck3v3.inductor"] = (36.0, 29.0, 0)
    PLACEMENT["buck3v3.c_out1"] = (38.0, 33.0, 270)
    PLACEMENT["buck3v3.c_out2"] = (40.5, 33.0, 270)
    PLACEMENT["buck3v3.r_fb_top"] = (36.0, 23.0, 180)
    PLACEMENT["buck3v3.r_fb_bottom"] = (36.0, 25.0, 0)
    for address in ("buck3v3.ic", "buck3v3.c_bst", "buck3v3.c_in", "buck3v3.c_in_hf",
                    "buck3v3.inductor", "buck3v3.c_out1", "buck3v3.c_out2",
                    "buck3v3.r_fb_top", "buck3v3.r_fb_bottom"):
        LABELS[address] = (0.0, -2.6)

    # 5 V in and the enable tied to it, each straight into the island.
    ROUTES.append(("5V", RAIL, F, ["buck3v3.ic:3", (32.14, 26.5)]))
    VIAS.append((None, (32.14, 26.5), "5V", *VIA))
    ROUTES.append(("5V", RAIL, F, ["buck3v3.ic:5", (28.5, 29.0)]))
    VIAS.append((None, (28.5, 29.0), "5V", *VIA))
    for address, at in (("buck3v3.c_in", (26.0, 28.6)), ("buck3v3.c_in_hf", (28.0, 28.0))):
        VIAS.append((f"{address}:1", at, "5V", *VIA, POWER))
    for address, at in (("buck3v3.c_in", (26.0, 24.4)), ("buck3v3.c_in_hf", (28.0, 24.9))):
        VIAS.append((f"{address}:2", at, "GND", *VIA, POWER))
    VIAS.append(("buck3v3.ic:1", (32.14, 31.5), "GND", *VIA, SUPPLY))

    # Switch node out to the right, with the bootstrap capacitor below.
    ROUTES.append(("SW_3V3", RAIL, F, ["buck3v3.ic:2", "buck3v3.inductor:1"]))
    ROUTES.append(("SW_3V3", RAIL, F, [
        (33.6, 29.0), (33.6, 32.5), "buck3v3.c_bst:1",
    ]))
    ROUTES.append(("BST_3V3", SIGNAL, F, [
        "buck3v3.ic:6", (29.86, 32.5), "buck3v3.c_bst:2",
    ]))

    # The rail out to its capacitors, and into the plane beyond the island.
    ROUTES.append(("3V3", POWER, F, [
        "buck3v3.inductor:2", (38.0, 29.0), "buck3v3.c_out1:1", "buck3v3.c_out2:1",
    ]))
    VIAS.append((None, (42.0, 32.05), "3V3", *VIA))
    ROUTES.append(("3V3", POWER, F, ["buck3v3.c_out2:1", (42.0, 32.05)]))
    VIAS.append(("buck3v3.c_out1:2", (38.0, 35.2), "GND", *VIA, POWER))
    VIAS.append(("buck3v3.c_out2:2", (40.5, 35.2), "GND", *VIA, POWER))

    # Feedback, above the package where nothing else runs, sensed at the plane.
    ROUTES.append(("FB_3V3", SIGNAL, F, [
        "buck3v3.ic:4", (29.86, 23.0), "buck3v3.r_fb_top:2",
    ]))
    ROUTES.append(("FB_3V3", SIGNAL, F, ["buck3v3.r_fb_top:2", "buck3v3.r_fb_bottom:1"]))
    VIAS.append(("buck3v3.r_fb_top:1", (37.7, 23.0), "3V3", *VIA, SUPPLY))
    VIAS.append(("buck3v3.r_fb_bottom:2", (37.7, 25.0), "GND", *VIA, SUPPLY))


def _reference() -> None:
    """
    The 3.0 V reference, below the package's bottom-left corner.

    VREF+ leaves its pin inward, like VDDA does, and crosses to the reference on
    the bottom layer through the empty corner of the pad ring - the one place
    where neither the plane vias inside the ring nor the capacitors outside it
    leave anything in the way.
    """
    PLACEMENT["vref.ic"] = (-13.5, 19.0, 180)
    PLACEMENT["vref.c_in"] = (-12.56, 22.0, 270)
    PLACEMENT["core.vref.c1u"] = (-16.5, 19.0, 180)
    PLACEMENT["tp_vref"] = (-7.5, 18.05)
    for address in ("vref.ic", "vref.c_in", "core.vref.c1u", "tp_vref"):
        LABELS[address] = (0.0, -2.6)

    pin = PINS[VREF_PIN]
    inward = pin.at(SUPPLY_RING_2)
    VIAS.append((f"{MCU}:{VREF_PIN}", inward, "VREF+", *VIA, STUB))
    surfaced = (-10.0, 18.05)
    # Out through the corner well inside the ring, then down the one lane past
    # the package's bottom-left corner that no via of any kind reaches: the
    # inner vias stop at the last pin on each side, and the outer ones are
    # further out still.
    path("VREF+", SUPPLY, [
        (B, [inward, (-6.5, 8.0), (-6.5, 10.5), (-10.0, 13.5), surfaced]),
        (F, [surfaced, "vref.ic:2"]),
    ])
    ROUTES.append(("VREF+", SUPPLY, F, ["tp_vref:1", surfaced]))
    ROUTES.append(("VREF+", SUPPLY, F, [
        "vref.ic:2", (-12.56, 16.0), (-15.99, 16.0), "core.vref.c1u:1",
    ]))
    VIAS.append(("core.vref.c1u:2", (-18.2, 19.0), "GND", *VIA, SUPPLY))

    # The reference's own supply, up from the island on the 5 V side.
    ROUTES.append(("5V", RAIL, F, [(-6.0, 25.0), (-6.0, 21.49), "vref.c_in:1"]))
    VIAS.append((None, (-6.0, 25.0), "5V", *VIA))
    ROUTES.append(("5V", RAIL, F, ["vref.c_in:1", "vref.ic:1"]))
    VIAS.append(("vref.c_in:2", (-12.56, 23.7), "GND", *VIA, SUPPLY))
    VIAS.append(("vref.ic:3", (-14.44, 17.0), "GND", *VIA, SUPPLY))


VREF_PIN = "32"



# Where the RJ45 sits, and how far the planes stay out from under it. The
# jack's own pads keep their copper - they have to reach the plane - and what
# is cleared is the half of it the cable goes into, where the contacts and the
# cable's screen are and where a plane under them is one more path for
# everything arriving on eighty metres of twisted pair.
JACK = (-50.0, -37.2)
JACK_KEEPOUT = (-64.5, -54.5, -44.4, -42.0)   # x0, y0, x1, y1


def _pour_outline() -> list[tuple[float, float]]:
    """The board, less the corner the jack's cable end sits in."""
    width, height = BOARD["size"]
    x, y = width / 2 - BOARD["pour_inset"], height / 2 - BOARD["pour_inset"]
    _, _, notch_x, notch_y = JACK_KEEPOUT
    return [(notch_x, -y), (x, -y), (x, y), (-x, y), (-x, notch_y), (notch_x, notch_y)]


def _island_outline() -> list[tuple[float, float]]:
    x0, y0, x1, y1 = ISLAND
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


# Ground on the first inner layer, and the supplies on the second: 3V3 over the
# whole board, with the 5 V island cut out of it by priority rather than by
# outline. KiCad fills the higher priority first and the 3V3 pour keeps clear.
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
    {
        "net": "3V3",
        "layer": "In2.Cu",
        "outline": _pour_outline(),
        "pad_clearance": 0.3,
        "min_thickness": 0.25,
        "thermal_gap": 0.3,
        "thermal_bridge": 0.4,
    },
    {
        "net": "5V",
        "layer": "In2.Cu",
        "outline": _island_outline(),
        "priority": 1,
        "pad_clearance": 0.3,
        "min_thickness": 0.25,
        "thermal_gap": 0.3,
        "thermal_bridge": 0.4,
    },
]


# --- the safety chain --------------------------------------------------------
#
# The right-hand third of the board, in the order a PWM edge travels: out of the
# package, into an octal buffer, through a series resistor past a pull-down, and
# onto the connector. The latch that can take all of it away sits between the
# two buffers, where both enables are short.
#
# **Placed, not yet routed.** The connections are in design.json and the checks
# in `checks/test_safety.py` read them from there; what is here is where every
# part sits. Routing this block on its own turned into a fight with the escapes
# of a package whose other three sides are already full, which is an argument
# for doing it with the whole board in view - M8, which the plan already sets
# aside for the full route. `board.mk` says `ROUTING := incomplete` until then,
# so DRC still refuses anything drawn wrongly but does not demand what is not
# drawn at all.
#
# Almost none of the placement is written as coordinates. The header's pin
# numbers come from the same table the netlist is built from, each buffer
# channel's position from the package's own pin geometry, and the thirty output
# slots are a loop.

HEADER_ORIGIN = (44.0, -24.0)    # pin 1; row 2 is 2.54 mm to the right
HEADER_PITCH = 2.54
# One column of series resistors and one of pull-downs, not two of each. The
# slots used to sit level with the header pin they feed, which put two of them
# at the same height whenever both header rows carried a signal, and meant the
# outer one's feed ran through the inner one's resistor. Evenly spaced instead:
# every slot gets its own height, the feeds never collide, and what it costs is
# a short diagonal from each pull-down to its pin.
SERIES_X, PULLDOWN_X = 38.5, 40.5
SLOT_LOW, SLOT_PITCH = -4.3, 1.87
# The buffers sit 1.5 mm further left than they first did, to open the lane
# field between them and the slot columns: four tracks need room to pass, and a
# track half a millimetre from a package pin merges its solder mask with it.
BUFFER1, BUFFER2, LATCH = (28.5, 18.27), (28.5, 2.2), (26.0, 9.0)

_TSSOP = 0.65                    # lead pitch of both buffers
PINMAP = load_source(HERE / "pinmap.py", "cpu1_pinmap")
HEADER_NET = PINMAP.header_pins(PINMAP.HEADER_DIGITAL, PINMAP.HEADER_GROUND, 40)
HEADER_PIN = {net: number for number, net in HEADER_NET.items()}


def _header_at(number: int) -> tuple[float, float]:
    """Where pin `number` of a 2x20 odd/even header sits, with pin 1 at the origin."""
    x, y = HEADER_ORIGIN
    position = (number + 1) // 2 - 1
    return (x + (0.0 if number % 2 else HEADER_PITCH), round(y + position * HEADER_PITCH, 4))


def _lane_of(name: str) -> float:
    """Where a static signal's parts sit, by its place in the header table."""
    # 2.0 mm apart, not 1.4. At the tighter pitch there was nowhere to put a
    # via beside two of these resistors' supply pads, which the plane stitching
    # generator refused to guess at rather than placing one on a neighbour.
    statics = [n for n in PINMAP.HEADER_DIGITAL[:11] if n != "3V3"]
    return round(-38.6 + 2.0 * statics.index(name), 4)


def _safety() -> None:
    PLACEMENT["header.digital"] = (*HEADER_ORIGIN, 0)
    LABELS["header.digital"] = (-3.0, -2.0)
    PLACEMENT["safety.buffer1"] = (*BUFFER1, 0)
    PLACEMENT["safety.buffer2"] = (*BUFFER2, 0)
    PLACEMENT["safety.latch"] = (*LATCH, 0)
    LABELS["safety.buffer1"] = (0.0, -4.4)
    LABELS["safety.buffer2"] = (0.0, -4.4)
    LABELS["safety.latch"] = (0.0, -2.4)
    for address, at in (("safety.buffer1", (BUFFER1[0], BUFFER1[1] - 5.6)),
                        ("safety.buffer2", (BUFFER2[0], BUFFER2[1] - 5.6)),
                        ("safety.latch", (19.0, LATCH[1]))):
        PLACEMENT[f"{address}.decoupling"] = (*at, 0)
        LABELS[f"{address}.decoupling"] = (0.0, -1.3)

    # The trip chain: both diodes where the two fault lanes will run, and the
    # pull-up that holds the bus high beside them.
    PLACEMENT["safety.d_faults"] = (22.0, -28.0, 0)
    PLACEMENT["safety.d_reset"] = (20.5, -32.0, 0)
    PLACEMENT["safety.r_trip_pullup"] = (22.0, -24.0, 180)
    PLACEMENT["safety.r_clear_pullup"] = (23.0, 17.0, 0)
    PLACEMENT["safety.r_enable_pullup"] = (23.0, 15.0, 0)
    for address in ("safety.d_faults", "safety.d_reset", "safety.r_trip_pullup",
                    "safety.r_clear_pullup", "safety.r_enable_pullup"):
        LABELS[address] = (2.6, 0.0)

    _output_slots()
    _static_pulls()
    _output_routes()
    _buffer_fanout()


def _rule_widths() -> list[tuple[str, float]]:
    """
    (net pattern, minimum width) from the board's own design rules.

    The rules file already says how wide each net has to be, and DRC holds the
    board to it. A generator that picked its own widths would be a second
    opinion on the same question, and the two would drift: the first thing this
    was needed for was GATE_ENABLE_OUT, which the rules make wider than a
    signal and which four generated tracks had drawn at signal width.
    """
    import re

    text = (HERE / "rules.kicad_dru").read_text()
    out = []
    for block in re.findall(r"\(rule\b.*?\(severity", text, re.S):
        width = re.search(r"\(constraint track_width \(min ([\d.]+)mm\)\)", block)
        if not width:
            continue
        for name in re.findall(r"A\.NetName == '([^']+)'", block):
            out.append((name, float(width.group(1))))
    return out


RULE_WIDTHS = _rule_widths()


def _width_for(net: str, floor: float = 0.0) -> float:
    """How wide the rules say this net has to be, at least."""
    import fnmatch

    widths = [w for pattern, w in RULE_WIDTHS if fnmatch.fnmatchcase(net, pattern)]
    return max([floor] + widths)


def _buffered() -> list[tuple[str, str]]:
    """(buffer, signal name) for all fifteen buffered outputs, in header order."""
    out = []
    for address, names in (("safety.buffer2", PINMAP.HEADER_DIGITAL[11:18]),
                           ("safety.buffer1", PINMAP.HEADER_DIGITAL[18:])):
        out.extend((address, name) for name in names)
    return sorted(out, key=lambda pair: HEADER_PIN[pair[1]])


def _slot_of(name: str) -> float:
    """Where a buffered output's own two parts sit."""
    order = [n for _, n in _buffered()]
    return round(SLOT_LOW + order.index(name) * SLOT_PITCH, 4)


def _output_slots() -> None:
    """
    Fifteen identical slots, one per buffered output, in the header's order.

    Each is a series resistor and the pull-down that holds the connector low
    when the buffer is not driving it. They are evenly spaced rather than lined
    up with their header pins, which is what lets all fifteen feeds arrive from
    the same side without crossing each other.
    """
    for _, name in _buffered():
        signal = name[: -len("_OUT")].lower()
        slot = _slot_of(name)
        PLACEMENT[f"safety.series.{signal}"] = (SERIES_X, slot, 0)
        PLACEMENT[f"safety.pulldown.{name.lower()}"] = (PULLDOWN_X, slot, 270)
        LABELS[f"safety.series.{signal}"] = (0.0, -1.3)
        LABELS[f"safety.pulldown.{name.lower()}"] = (-1.6, 0.0)


def _output_routes() -> None:
    """
    Each buffered output from its series resistor to the pin it leaves on.

    Fifteen copies of one short route: through the series resistor, past the
    pull-down that holds the pin low when nothing is driving it, and into the
    connector. The slots no longer sit level with their pins, so the last leg
    is a diagonal - they stay in the header's own order, so the diagonals fan
    without crossing.

    The second row goes underneath. A straight line to it passes through the
    first row's pin, and those pins are through-hole: they are on the back
    layer too.
    """
    for _, name in _buffered():
        number = HEADER_PIN[name]
        signal = name[: -len("_OUT")].lower()
        series = f"safety.series.{signal}"
        pulldown = f"safety.pulldown.{name.lower()}"
        pin = f"header.digital:{number}"
        width = _width_for(name, SIGNAL)
        if number % 2:                    # the header's first row, in the clear
            ROUTES.append((name, width, F, [f"{series}:2", f"{pulldown}:1", pin]))
        else:
            # Under the first row, crossing it midway between two positions.
            between = _header_at(number)[1] + HEADER_PITCH / 2
            path(name, width, [
                (F, [f"{series}:2", f"{pulldown}:1"]),
                (B, [f"{pulldown}:1", (PULLDOWN_X + 1.0, _slot_of(name)),
                     (PULLDOWN_X + 1.0, between),
                     (HEADER_ORIGIN[0] + HEADER_PITCH, between), pin]),
            ])


# The lane field between each buffer and the slot column.
LANE_ONE, LANE_PITCH = 33.2, 0.6


def _buffer_fanout() -> None:
    """
    Each buffer's outputs out to the slot that carries them.

    The two buffers feed two blocks of slots that do not overlap in height, so
    each gets its own eight lanes and both use the same strip of board.

    Lane order is what keeps the fan from crossing itself, and it depends on
    which way the track is going. An output whose slot is *below* its pin takes
    an inner lane the further down it goes; one whose slot is above takes an
    inner lane the further *up* it goes. Either way a track's own escape, which
    runs at the height of its pin, passes only over lanes whose verticals have
    not reached that height yet.
    """
    for address, names in (("safety.buffer1", PINMAP.HEADER_DIGITAL[18:]),
                           ("safety.buffer2", PINMAP.HEADER_DIGITAL[11:18])):
        pin_y = {
            name: round(PLACEMENT[address][1] + (channel - 2.5) * _TSSOP, 4)
            for channel, name in enumerate(names)
        }
        going_down = [n for n in names if _slot_of(n) < pin_y[n]]
        going_up = [n for n in names if _slot_of(n) >= pin_y[n]][::-1]
        lanes = {name: lane for lane, name in enumerate(going_down)}
        lanes.update({name: lane for lane, name in enumerate(going_up)})

        for channel, name in enumerate(names):
            signal = name[: -len("_OUT")]
            net = f"{signal}_B"           # the buffer's side of the resistor
            x = LANE_ONE + lanes[name] * LANE_PITCH
            ROUTES.append((net, _width_for(net, SIGNAL), F, [
                f"{address}:{18 - channel}",
                (x, pin_y[name]),
                (x, _slot_of(name)),
                f"safety.series.{signal.lower()}:1",
            ]))


def _static_pulls() -> None:
    """
    The ten signals that are not PWM, each with its pull-up or pull-down.

    They sit in a column at the end of the lane each will take across the board,
    in the order the header table puts them - which is the order they leave the
    package, furthest first.
    """
    pulls = {
        "RELAY_PRECHARGE": "down", "RELAY_MAIN": "down",
        "ID_STRAP0": "up", "ID_STRAP1": "up", "ID_STRAP2": "up", "ID_STRAP3": "up",
        "FAULT1_N": "up", "FAULT2_N": "up",
        "STO1_FEEDBACK": "down", "STO2_FEEDBACK": "down",
    }
    named = {"FAULT1_N": "safety.r_fault1_pullup", "FAULT2_N": "safety.r_fault2_pullup"}
    for name, direction in pulls.items():
        address = named.get(name, f"safety.{'pullup' if direction == 'up' else 'pulldown'}.{name.lower()}")
        PLACEMENT[address] = (34.5, _lane_of(name), 0 if direction == "up" else 180)
        LABELS[address] = (0.0, -1.3)



# --- the trip comparators and the analog connector ---------------------------
#
# The left-hand third, which the analog signals reach first. Seven comparators
# in a column beside the connector they watch, their threshold DAC below them,
# and the four dual Schottkys that carry seven outputs onto one trip bus.
#
# Placed, not routed, for the same reason the safety chain is: M8.

ANALOG_HEADER = (-46.0, -18.0)


# The comparators, in the order the analog header presents them, so the two
# that watch one phase sit together. Named once: the placement and the supply
# spine both walk it.
TRIP_ORDER = (
    "ia_high", "ia_low", "ib_high", "ib_low", "ic_high", "ic_low", "vdc_high",
)

# The 5 V spine down that column, and where it leaves the island.
TRIP_SPINE_X = -33.0
ISLAND_TAP = (-8.5, 25.5)


def _trip_supply() -> None:
    """
    5 V from the regulator's island to the comparators, thirty millimetres away.

    The island on the inner layer stops beside the buck; the comparators do not
    reach it, so their supply pads have no plane under them and stitching them
    gave four vias connected to nothing. The supply is routed instead - on the
    back layer, which is empty here - and tapped up to each comparator in turn.

    Each tap goes to the comparator's own supply pin first and to its
    decoupling capacitor second, so the capacitor is on the pin's side of the
    inductance rather than the spine's.
    """
    spine = [
        ISLAND_TAP,
        (ISLAND_TAP[0], 21.0),
        (TRIP_SPINE_X, 21.0),
        (TRIP_SPINE_X, -19.0 + 0.95),
    ]
    VIAS.append((None, ISLAND_TAP, "5V", *VIA))
    ROUTES.append(("5V", _width_for("5V", RAIL), B, spine))

    for index, key in enumerate(TRIP_ORDER):
        y = round(-19.0 + 4.6 * index, 4)
        tap = (TRIP_SPINE_X, y + 0.95)
        VIAS.append((None, tap, "5V", *VIA))
        ROUTES.append(("5V", _width_for("5V", SUPPLY), F, [
            tap, f"trip.{key}:4", f"trip.{key}.decoupling:1",
        ]))


def _trip() -> None:
    PLACEMENT["header.analog"] = (*ANALOG_HEADER, 0)
    LABELS["header.analog"] = (3.0, -2.0)

    # One comparator per trip point, in the order the header presents them, so
    # the two that watch one phase sit together.
    for index, key in enumerate(TRIP_ORDER):
        y = round(-19.0 + 4.6 * index, 4)
        PLACEMENT[f"trip.{key}"] = (-36.0, y, 0)
        LABELS[f"trip.{key}"] = (0.0, -2.4)
        # Turned round so its supply pad faces the comparator's: both 5 V
        # points then sit on the same side and the spine taps them in one run.
        PLACEMENT[f"trip.{key}.decoupling"] = (-36.0, y + 2.2, 180)
        LABELS[f"trip.{key}.decoupling"] = (0.0, -1.3)

    _trip_supply()

    # The threshold DAC, below the comparators it feeds, with its own supply
    # decoupling and the two pull-ups its bus needs.
    PLACEMENT["trip.dac"] = (-38.0, -26.0, 0)
    LABELS["trip.dac"] = (0.0, -3.0)
    PLACEMENT["trip.dac.decoupling"] = (-38.0, -22.0, 0)
    PLACEMENT["trip.dac.bulk"] = (-38.0, -30.0, 0)
    PLACEMENT["trip.r_scl_pullup"] = (-32.0, -26.0, 0)
    PLACEMENT["trip.r_sda_pullup"] = (-32.0, -28.0, 0)
    PLACEMENT["tp_dac_spare"] = (-32.0, -22.0)
    for address in ("trip.dac.decoupling", "trip.dac.bulk", "trip.r_scl_pullup",
                    "trip.r_sda_pullup", "tp_dac_spare"):
        LABELS[address] = (0.0, -1.6)

    # The four dual Schottkys, in a column between the comparators and the bus.
    for index in range(4):
        PLACEMENT[f"trip.d_outputs{index + 1}"] = (-29.0, round(-17.0 + 4.0 * index, 4), 0)
        LABELS[f"trip.d_outputs{index + 1}"] = (2.6, 0.0)

    # The analog supply for the power board's own sensors: the 5 V rail through
    # a bead, which is what VDDA gets and for the same reason.
    PLACEMENT["analog.bead"] = (-40.5, 10.0, 0)
    PLACEMENT["analog.bulk"] = (-40.5, 12.0, 0)
    PLACEMENT["analog.decoupling"] = (-40.5, 14.0, 0)
    for address in ("analog.bead", "analog.bulk", "analog.decoupling"):
        LABELS[address] = (0.0, -1.6)


# --- the ADC input networks --------------------------------------------------
#
# Fifteen identical RC pairs in a grid above the package, between the connector
# the signals arrive on and the pins that measure them. Nothing here is
# hand-placed: the order is the order `cpu1.py` builds them in, which is the
# order the pin map lists the channels.

ADC_GRID = (-24.0, -37.0)        # first cell
ADC_STEP = (5.0, 2.4)            # between columns, between rows
ADC_ROWS = 5


def _adc_inputs() -> None:
    cells = sorted(
        address.rsplit(".", 1)[0]
        for address in DESIGN["parts"]
        if address.startswith("adc.") and address.endswith(".shunt")
    )
    for index, cell in enumerate(cells):
        column, row = divmod(index, ADC_ROWS)
        x = round(ADC_GRID[0] + ADC_STEP[0] * column, 4)
        y = round(ADC_GRID[1] + ADC_STEP[1] * row, 4)
        PLACEMENT[f"{cell}.series"] = (x, y, 0)
        PLACEMENT[f"{cell}.shunt"] = (round(x + 2.2, 4), y, 90)
        LABELS[f"{cell}.series"] = (0.0, -1.3)
        LABELS[f"{cell}.shunt"] = (-1.6, 0.0)

    PLACEMENT["adc.dac_test.series"] = (-8.0, -31.0, 0)
    PLACEMENT["tp_dac_test"] = (-8.0, -34.0)
    LABELS["adc.dac_test.series"] = (0.0, -1.3)
    LABELS["tp_dac_test"] = (0.0, -2.0)


# --- the field buses ---------------------------------------------------------
#
# CAN and RS-485 side by side above the package, each with its transceiver, its
# termination on a jumper, and three pins out to the field.

def _field_buses() -> None:
    # Four rows above the package: each transceiver, its decoupling, its
    # termination on a jumper, and the three pins that leave the board.
    PLACEMENT["can.transceiver"] = (2.0, -25.0, 0)
    PLACEMENT["can.decoupling_vcc"] = (8.0, -25.0, 0)
    PLACEMENT["can.decoupling_vio"] = (11.0, -25.0, 0)
    PLACEMENT["can.termination_jumper"] = (2.0, -29.0, 0)
    PLACEMENT["can.termination_upper"] = (6.0, -29.0, 0)
    PLACEMENT["can.termination_lower"] = (10.0, -29.0, 0)
    PLACEMENT["can.termination_split"] = (14.0, -29.0, 0)
    PLACEMENT["rs485.transceiver"] = (2.0, -33.0, 0)
    PLACEMENT["rs485.decoupling"] = (8.0, -33.0, 0)
    PLACEMENT["rs485.termination_jumper"] = (11.5, -33.0, 0)
    PLACEMENT["rs485.termination"] = (15.0, -33.0, 0)
    PLACEMENT["can.header"] = (2.0, -37.5, 90)
    PLACEMENT["rs485.header"] = (12.0, -37.5, 90)
    for address in ("can.transceiver", "rs485.transceiver"):
        LABELS[address] = (0.0, -3.4)
    for address in ("can.header", "rs485.header"):
        LABELS[address] = (2.6, 2.6)
    for address in ("can.decoupling_vcc", "can.decoupling_vio", "can.termination_jumper",
                    "can.termination_upper", "can.termination_lower", "can.termination_split",
                    "rs485.decoupling", "rs485.termination_jumper", "rs485.termination"):
        LABELS[address] = (0.0, -1.6)


# --- USB ---------------------------------------------------------------------
#
# The one differential pair on this board. Its width and gap are not written
# down: `pair_geometry` solves the stackup in BOARD for the width that makes
# 90 ohm at the gap chosen, so a change to the fab's build changes the trace
# rather than leaving a number behind that used to be right.

USB_GAP = 0.2
USB_STACK = layout_lib.Microstrip(
    height=BOARD["stack"][0]["thickness"],
    epsilon_r=BOARD["stack"][0]["epsilon_r"],
)
USB_WIDTH = layout_lib.pair_geometry(90.0, USB_STACK, gap=USB_GAP)

# The Ethernet pairs run on the same layer over the same prepreg, so the only
# thing that differs is what they have to present: 100 ohm, not 90.
ETH_GAP = 0.2
ETH_WIDTH = layout_lib.pair_geometry(100.0, USB_STACK, gap=ETH_GAP)


def _usb() -> None:
    # The receptacle faces out of the top edge, in the corridor between the
    # safety chain's reset diode and its column of strap resistors, with the
    # array immediately behind it: a protection device further from the
    # connector than the thing it protects is protecting the wrong end.
    PLACEMENT["usb.receptacle"] = (28.0, -37.0, 180)
    PLACEMENT["usb.protection"] = (28.0, -26.0, 270)
    PLACEMENT["usb.cc1_pulldown"] = (24.0, -30.5, 0)
    PLACEMENT["usb.cc2_pulldown"] = (32.0, -30.5, 0)
    LABELS["usb.receptacle"] = (0.0, 4.2)
    LABELS["usb.protection"] = (-2.4, 0.0)
    for address in ("usb.cc1_pulldown", "usb.cc2_pulldown"):
        LABELS[address] = (0.0, -1.3)

    # The pair runs south from the array, down the empty corridor east of the
    # package. Written as one line down the middle of it; the two tracks are
    # that line offset, so they are the same length by construction and the
    # only difference between them is what the corners add.
    #
    # **It stops short of the package.** Pads 103 and 104 sit in the middle of
    # the debug escapes - SWDIO steps onto pin 104's line to get past VCAP2's
    # capacitor - and untangling that is the same job as the rest of the
    # escapes, which M8 does with the whole board in view. What is drawn here
    # is the length that decides the pair's impedance; what is missing is the
    # two millimetres at the end of it.
    centre = [(28.0, -22.0), (28.0, -13.0), (25.0, -10.0)]
    west, east = layout_lib.diff_pair(centre, USB_WIDTH, USB_GAP)
    if west[0][0] > east[0][0]:
        west, east = east, west

    # D+ leaves the array on its western pad and D- on its eastern one, so each
    # takes the line on its own side and the pair never crosses itself.
    #
    # The two halves step wide before they come together. VBUS sits on the pad
    # between them on this part, so a pair that left at its final spacing would
    # run one track along each side of a pad it has nothing to do with. The
    # fan-out is deliberately not at the pair's spacing, and the impedance it
    # is drawn to starts where the fan-out ends.
    for net, line, pad, clear in (("USB_DP", west, "4", 26.8),
                                  ("USB_DM", east, "6", 29.2)):
        ROUTES.append((net, USB_WIDTH, F, [
            f"usb.protection:{pad}", (clear, -23.4), line[0]]))
        ROUTES.append((net, USB_WIDTH, F, list(line)))


# --- Ethernet ----------------------------------------------------------------
#
# The PHY and its clock, in the corner left of the threshold DAC. The jack is
# not here: see cpu1.py's ethernet(), and M7d.

def _ethernet() -> None:
    # The jack in the corner the board grew to hold it, opening out of the top
    # edge; the PHY on the column below it, far enough away that the pairs
    # between them have room to be pairs.
    PLACEMENT["eth.jack"] = (*JACK, 180)
    LABELS["eth.jack"] = (-9.5, 5.0)

    PLACEMENT["eth.phy"] = (-54.0, -17.0, 0)
    LABELS["eth.phy"] = (0.0, 3.6)

    # Each supply pin routes to its own capacitor and the capacitor carries the
    # via down to the plane, rather than the pin being stitched and the
    # capacitor stitched separately beside it. That is the order the current
    # actually takes, and it is what leaves the pins either side a lane to
    # escape along.
    PLACEMENT["eth.dec_vdd2a"] = (-58.5, -19.5, 180)
    PLACEMENT["eth.dec_vdd1a"] = (-51.5, -22.5, 90)
    PLACEMENT["eth.dec_vddio"] = (-54.25, -12.5, 270)
    PLACEMENT["eth.r_refclk_strap"] = (-58.7, -17.75, 180)

    # The package's left side carries both crystal pins, so the crystal gets
    # that side to itself. A four-pad crystal has its two terminals diagonally
    # opposite, with the can's pads on the other diagonal, and the two pins
    # driving it are adjacent: there is no angle that makes both tracks
    # straight, so one of them gets past a can pad underneath.
    PLACEMENT["eth.xtal.crystal"] = (-62.0, -13.0, 0)
    PLACEMENT["eth.xtal.c_in"] = (-63.0, -8.5, 0)
    PLACEMENT["eth.xtal.c_out"] = (-59.0, -16.0, 180)

    # The core rail's pair: one bypass split across two decades, not two
    # separate jobs.
    PLACEMENT["eth.core_bulk"] = (-57.5, -11.0, 0)
    PLACEMENT["eth.core_hf"] = (-57.5, -8.5, 0)

    PLACEMENT["eth.bias"] = (-56.5, -22.5, 90)
    PLACEMENT["eth.r_mdio_pullup"] = (-51.0, -8.5, 0)
    PLACEMENT["eth.r_reset_pullup"] = (-51.0, -6.0, 0)

    for address, x in (("eth.tap_bypass1", -47.0), ("eth.tap_bypass2", -44.5)):
        PLACEMENT[address] = (x, -31.0, 0)

    for address in ("eth.dec_vdd2a", "eth.dec_vdd1a", "eth.dec_vddio",
                    "eth.r_refclk_strap", "eth.xtal.c_in", "eth.xtal.c_out",
                    "eth.core_bulk", "eth.core_hf", "eth.bias",
                    "eth.r_mdio_pullup", "eth.r_reset_pullup",
                    "eth.tap_bypass1", "eth.tap_bypass2"):
        LABELS[address] = (0.0, -1.3)
    LABELS["eth.xtal.crystal"] = (0.0, -3.0)

    _ethernet_pairs()
    _ethernet_local()


def _ethernet_local() -> None:
    """
    Everything on the PHY that goes to a part rather than to the MCU.

    The crystal and its two load capacitors, the bias resistor, the core rail's
    bypass pair and the one strap that has to be fought. All of them sit beside
    the pin they belong to, so each is a straight run from a package pin to a
    pad and there is nothing to arrange.
    """
    for net, points in (
        # Both leave the package straight out and turn once they are clear of
        # the pins either side of them - a diagonal from the pad crosses the
        # escape of whichever supply pin is next along.
        ("ETH_XTAL2", ["eth.phy:4", (-57.6, -16.75), "eth.xtal.c_out:1",
                       "eth.xtal.crystal:3"]),
        ("ETH_RBIAS", ["eth.phy:24", "eth.bias:1"]),
        ("ETH_VDDCR", ["eth.phy:6", "eth.core_bulk:1", "eth.core_hf:1"]),
        ("ETH_NINTSEL", ["eth.phy:2", "eth.r_refclk_strap:1"]),
        ("3V3", ["eth.phy:1", "eth.dec_vdd2a:1"]),
    ):
        ROUTES.append((net, _width_for(net, SIGNAL), F, points))

    # XTAL1 goes to the terminal on the far corner, which means past the can
    # pad sitting between it and the package. Under the crystal rather than
    # around it: around is three millimetres further on the one net where
    # length is the thing being controlled.
    width = _width_for("ETH_XTAL1", SIGNAL)
    path("ETH_XTAL1", width, [
        (F, ["eth.phy:5", (-57.0, -16.25), (-57.3, -15.2)]),
        (B, [(-57.3, -15.2), (-62.0, -9.8)]),
        (F, [(-62.0, -9.8), "eth.xtal.c_in:1", "eth.xtal.crystal:1"]),
    ])


# Where each pair's two halves have to end up, and the fact that forces the
# only vias on this board that sit inside a controlled-impedance run.
#
# The PHY's line pins go TXP, TXN, RXP, RXN from left to right. The jack's go
# RD-, RD+, TD-, TD+. The pairs are in the same order - transmit outside,
# receive inside - but each pair is the other way round inside itself, so each
# one has to cross once between the package and the connector. That is
# topology, not layout: no arrangement of two tracks on one layer swaps them.
#
# The alternative is to wire P to N deliberately and rely on the PHY correcting
# the polarity. It very likely would; 10BASE-T detects inverted link pulses and
# most PHYs carry the same correction into 100BASE-TX. But "most PHYs" and "a
# feature firmware can switch off" are not what a physical layer should rest
# on, so the crossing is drawn instead - on the back layer, above the point
# where the pair starts running parallel, where it costs two vias and a
# millimetre and a half of copper facing the wrong plane.

def _ethernet_pairs() -> None:
    phy_x, phy_y = PLACEMENT["eth.phy"][0], PLACEMENT["eth.phy"][1]
    finish = phy_y - 1.95 - 8.0     # where the parallel run ends
    jack_x, jack_y = JACK

    # Per pair: the P and N pins, the centre line's x, the pads at the far end,
    # and the crossing - where P steps aside to dive, at what height it runs
    # under N, and where it comes back up. The two crossings are at different
    # heights so their four vias are not neighbours.
    for pair, pins, centre, pads, detour, hop, target in (
        # Both lines sit inboard of the pins that feed them, which leaves
        # VDD1A - the pin outboard of the transmit pair - a lane of its own to
        # escape along. Put either line outside its pins and that lane closes.
        ("ETH_TD", ("21", "20"), phy_x + 0.55, ("1", "2"), -53.2, -30.2, jack_x),
        ("ETH_RD", ("23", "22"), phy_x - 0.55, ("3", "6"), -57.5, -32.5, jack_x - 2.54),
    ):
        line = [(centre, phy_y - 1.95 - 3.0), (centre, finish)]
        left, right = layout_lib.diff_pair(line, ETH_WIDTH, ETH_GAP)
        if left[0][0] > right[0][0]:
            left, right = right, left

        # Out of the package and into the pair. P takes the left line because
        # it is the left pin, so neither half crosses the other here.
        for net, side, pin in ((f"{pair}_P", left, pins[0]),
                               (f"{pair}_N", right, pins[1])):
            ROUTES.append((net, ETH_WIDTH, F, [f"eth.phy:{pin}", side[0]]))
            ROUTES.append((net, ETH_WIDTH, F, list(side)))

        # N goes on to its pad in the connector's near row, moving away from P.
        ROUTES.append((f"{pair}_N", ETH_WIDTH, F,
                       [right[-1], f"eth.jack:{pads[1]}"]))

        # P has to reach the far row, on the other side of N. It steps further
        # away first - a via needs more room than the pair's own spacing gives
        # it - then goes under on the back layer and comes up beyond N.
        path(f"{pair}_P", ETH_WIDTH, [
            (F, [left[-1], (detour, hop)]),
            (B, [(detour, hop), (target, hop)]),
            (F, [(target, hop), (target, jack_y), f"eth.jack:{pads[0]}"]),
        ])



# --- everything the planes have to reach -------------------------------------
#
# Ninety-six ground pads, and fifty more on the two supply islands, each of
# them a surface pad that has to find a plane two layers down. Written as a
# generator rather than as a hundred and fifty coordinates, for the same reason
# the decoupling is: a via list that long is a list nobody reads, and one wrong
# entry in it looks exactly like the rest.
#
# A pad is given a via beyond it, on the line out from the part's own centre,
# so the stub runs along the part's axis rather than across its neighbour. Pads
# something else already reaches - the decoupling capacitors, the MCU's supply
# ring, anything routed by hand - are left alone, and through-hole pads need
# nothing: they are already in every layer.

# The stub width each plane net's own design rule asks for. 5 V is wider than
# the logic rails because `rules.kicad_dru` says so, and a stub is a track.
PLANE_NETS = {"GND": 0.25, "3V3": 0.25, "5V": 0.3}
STITCH_REACH = 0.85       # how far beyond a pad its via sits
VIA_TO_PAD = 0.45         # via edge to pad edge, with clearance to spare
VIA_TO_VIA = 0.95         # centre to centre, which hole-to-hole decides
SHARE_REACH = 1.8         # how far a pad will reach to use a via already there


def _pads_of(address: str) -> dict[str, list]:
    library, _, name = DESIGN["parts"][address]["footprint"].partition(":")
    return layout_lib.footprint_pads(HERE / "parts" / library / f"{name}.kicad_mod")


def _absolute(address: str, x: float, y: float) -> tuple[float, float]:
    """A point in a footprint's frame, placed on the board."""
    import math

    ox, oy, *rest = PLACEMENT[address]
    angle = math.radians(rest[0] if rest else 0.0)
    return (round(ox + x * math.cos(angle) + y * math.sin(angle), 4),
            round(oy - x * math.sin(angle) + y * math.cos(angle), 4))


def _already_reached() -> set[str]:
    """Every `address:pad` some route or via already touches."""
    out = set()
    for _, _, _, points in ROUTES:
        out |= {p for p in points if isinstance(p, str)}
    for entry in VIAS:
        if entry[0] is not None:
            out.add(entry[0])
    return out


def _obstacles() -> tuple[list, list]:
    """
    Every pad on the board as an upright rectangle, and every via already there.

    Rectangles rather than circles: a via wants to pass *along* a row of
    0.6 by 1.3 mm pads, and measuring them by their diagonal says there is no
    room anywhere on an SOIC. Every part on this board is placed at a right
    angle, so the rectangles stay upright and the arithmetic stays simple.
    """
    pads = []
    for address in PLACEMENT:
        turned = round((PLACEMENT[address][2] if len(PLACEMENT[address]) > 2 else 0)) % 180 == 90
        for copies in _pads_of(address).values():
            for pad in copies:
                x, y = _absolute(address, pad.x, pad.y)
                half_w, half_h = pad.width / 2, pad.height / 2
                if turned:
                    half_w, half_h = half_h, half_w
                pads.append((x, y, half_w, half_h))
    return pads, [_point(entry[1]) for entry in VIAS]


def _track_points() -> list[tuple[float, float, float, str]]:
    """
    Every route already drawn, sampled as (x, y, half width, layer).

    A via goes through every layer, so it has to clear copper on all of them -
    and the first thing the stitching generator did once the safety chain was
    routed was drop three ground vias onto tracks running underneath. Sampled
    rather than solved: the arithmetic for a point against a fat line segment
    is more than this needs, and the points go into the same grid as the pads.
    """
    import math

    out = []
    for net, width, layer, points in ROUTES:
        resolved = [_point(p) for p in points]
        for a, b in zip(resolved, resolved[1:]):
            steps = max(1, int(math.dist(a, b) / 0.3))
            out.extend(
                (a[0] + (b[0] - a[0]) * i / steps, a[1] + (b[1] - a[1]) * i / steps,
                 width / 2, layer)
                for i in range(steps + 1)
            )
    return out


def _point(where) -> tuple[float, float]:
    """A via's place, whether it was given as coordinates or as a pad."""
    if isinstance(where, str):
        address, _, number = where.partition(":")
        pad = next(p for p in _pads_of(address)[number])
        return _absolute(address, pad.x, pad.y)
    return tuple(where)


def _inside(polygon: list[tuple[float, float]], point: tuple[float, float]) -> bool:
    """Ray casting: how many sides a ray from the point crosses going right."""
    x, y = point
    crossings = 0
    for (x1, y1), (x2, y2) in zip(polygon, polygon[1:] + polygon[:1]):
        if (y1 > y) != (y2 > y) and x1 + (y - y1) * (x2 - x1) / (y2 - y1) > x:
            crossings += 1
    return crossings % 2 == 1


def _plane_stitches() -> None:
    """
    A via for every surface pad that belongs to a plane and has no other way
    down.

    Where the via goes is searched for rather than assumed. The first choice is
    straight out from the part's centre, past the pad, which keeps the stub
    along the part's own axis; if something is already there the direction
    turns in steps until it finds room. A generator that always used its first
    choice would put fifty of these on top of their neighbours, and finding
    that out one DRC violation at a time is not a design method.
    """
    import math

    reached = _already_reached()
    pads, vias = _obstacles()

    # Where each plane actually is. A via only reaches a plane if the plane is
    # underneath it: 5V is an island beside the regulator, and the comparators
    # that run from it are thirty millimetres away, over ground and 3V3. Four
    # vias were placed there that connected to nothing, and DRC counted the
    # pads as unrouted while the board looked stitched.
    covered = {plane["net"]: plane["outline"] for plane in PLANES}

    # A search that asks every pad on the board about every candidate position
    # takes half a minute; the same search asking only the pads nearby takes
    # under a second. Bucketed on a four-millimetre grid, which is wider than
    # anything this generator reaches.
    grid: dict[tuple[int, int], list] = {}
    for rect in pads:
        grid.setdefault((int(rect[0] // 4), int(rect[1] // 4)), []).append(rect)

    copper: dict[tuple[int, int], list] = {}
    for x, y, half, layer in _track_points():
        copper.setdefault((int(x // 4), int(y // 4)), []).append((x, y, half, layer))

    def near_copper(point):
        cx, cy = int(point[0] // 4), int(point[1] // 4)
        return [
            spot
            for dx in (-1, 0, 1) for dy in (-1, 0, 1)
            for spot in copper.get((cx + dx, cy + dy), ())
        ]

    def near_pads(point):
        cx, cy = int(point[0] // 4), int(point[1] // 4)
        return [
            rect
            for dx in (-1, 0, 1) for dy in (-1, 0, 1)
            for rect in grid.get((cx + dx, cy + dy), ())
        ]

    # net -> where that net already goes through to the plane, so a second pad
    # on the same net can reach an existing via instead of asking for its own.
    placed: dict[str, list] = {}
    for entry in VIAS:
        placed.setdefault(entry[2], []).append(tuple(entry[1]))

    def _outside(rect, point, margin) -> bool:
        x, y, half_w, half_h = rect
        return (abs(point[0] - x) > half_w + margin
                or abs(point[1] - y) > half_h + margin)

    def clear(at: tuple[float, float], own: tuple[float, float],
              width: float, margin: float, existing: bool = False) -> bool:
        """
        Room for the via *and* for the stub that reaches it.

        The first version of this checked only where the via landed, and left
        six stubs lying across their neighbours' pads - a via can have all the
        room in the world at the end of a track that crosses something on the
        way there. The stub is walked in small steps rather than solved for,
        because a rectangle and a segment is more arithmetic than this needs.

        `margin` is tried generously first and then tightened. Copper clearance
        is 0.15 mm, but a track threading between two pads also merges their
        solder mask openings, and that rule wants more room than this one does.
        Pads at 0.5 mm pitch cannot give it, so the tight figure exists for
        them and is used only where the roomy one finds nothing.
        """
        steps = max(2, int(math.dist(own, at) / 0.1))
        walk = [(own[0] + (at[0] - own[0]) * i / steps,
                 own[1] + (at[1] - own[1]) * i / steps) for i in range(1, steps + 1)]
        looking = {id(rect): rect for point in walk + [at] for rect in near_pads(point)}
        for rect in looking.values():
            if abs(rect[0] - own[0]) < 1e-6 and abs(rect[1] - own[1]) < 1e-6:
                continue                  # the pad this via belongs to
            if not _outside(rect, at, 0.25 + 0.2):
                return False
            if any(not _outside(rect, point, width / 2 + margin) for point in walk):
                return False
        # Copper already drawn. The via meets every layer; the stub only meets
        # the front one.
        for x, y, half, layer in near_copper(at):
            if math.dist((x, y), at) < half + 0.25 + 0.2:
                return False
        for point in walk:
            for x, y, half, layer in near_copper(point):
                if layer == F and math.dist((x, y), point) < half + width / 2 + margin:
                    return False
        if existing:
            return True                   # the via is already there and legal
        return all(math.dist(other, at) >= VIA_TO_VIA for other in vias)

    stranded = []
    for address in sorted(PLACEMENT):
        if address == MCU:
            continue                      # its ring is drawn by _supply_vias()
        for number, copies in sorted(_pads_of(address).items()):
            net = NET_AT.get((address, number))
            if net not in PLANE_NETS or f"{address}:{number}" in reached:
                continue
            pad = next((p for p in copies if p.kind == "smd"), None)
            if pad is None:
                continue                  # through-hole: already in every layer
            here = _absolute(address, pad.x, pad.y)
            if net in covered and not _inside(covered[net], here):
                continue                  # the plane is somewhere else; route it

            # Two pads of one net, side by side, do not need two ways down -
            # but only if the track between them has somewhere to run. The
            # first version of this shared a via whenever one was near enough
            # and put five stubs straight across a comparator's input pad.
            near = sorted((v for v in placed.get(net, []) if math.dist(v, here) <= SHARE_REACH),
                          key=lambda v: math.dist(v, here))
            shared = next(
                (v for v in near
                 if clear(v, here, PLANE_NETS[net], 0.3, existing=True)),
                None,
            )
            if shared is not None:
                ROUTES.append((net, PLANE_NETS[net], F, [f"{address}:{number}", shared]))
                continue

            # Straight out along the pad's own long axis, away from the part.
            # That is where a pin escapes: for the middle pin of a 0.5 mm-pitch
            # package it is the only line with room on both sides, and a
            # bearing taken from the part's centre misses it by the few degrees
            # that put the stub into a neighbour.
            if abs(pad.width - pad.height) < 1e-6:
                bearing = math.atan2(pad.y, pad.x)
            elif pad.width > pad.height:
                bearing = 0.0 if pad.x >= 0 else math.pi
            else:
                bearing = math.pi / 2 if pad.y >= 0 else -math.pi / 2
            candidates = (
                (margin, turn, STITCH_REACH + step * 0.3)
                for margin in (0.3, 0.22, 0.17)
                for turn in (0, 10, -10, 20, -20, 30, -30, 40, -40, 55, -55,
                             70, -70, 90, -90, 120, -120, 150, -150, 180)
                for step in range(9)
            )
            for margin, turn, reach in candidates:
                angle = bearing + math.radians(turn)
                at = _absolute(address,
                               pad.x + math.cos(angle) * reach,
                               pad.y + math.sin(angle) * reach)
                if net in covered and not _inside(covered[net], at):
                    continue              # the plane does not reach here
                if clear(at, here, PLANE_NETS[net], margin):
                    VIAS.append((f"{address}:{number}", at, net, *VIA, PLANE_NETS[net]))
                    vias.append(at)
                    placed.setdefault(net, []).append(at)
                    break
            else:
                stranded.append(f"{address}:{number} ({net})")
    if stranded:
        sys.exit("no room for a plane via beside: " + ", ".join(stranded))



_supply_vias()
_decoupling()
_analog_supply()
_crystals()
_placed()
_power()
_safety()
_trip()
_adc_inputs()
_field_buses()
_usb()
_ethernet()
_plane_stitches()
