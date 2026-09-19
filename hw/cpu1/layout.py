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
import math
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
    # Six layers, not four. Four was chosen before this board had an Ethernet
    # jack, a 144-pin package and 191 nets on it, and it cost: the RMII took
    # two attempts and ended up crossing under the die, and eight reserved
    # signals could not be routed at all - four usable via positions where
    # eight were needed. With one signal layer on top and one underneath,
    # every crossing is a via, and a via wants 0.65 mm of hole-to-hole room
    # this board does not have. PCBWay builds 1 to 14 layers on the same
    # standard process, with the same 0.15 mm drill and 0.1 mm track and
    # spacing, so nothing in fab/pcbway.kicad_dru changes.
    #
    # F.Cu / In1 ground / In2 supply islands / In3 signal / In4 ground / B.Cu.
    #
    # The supply plane goes next to the *least* used signal layer. B.Cu
    # carries 294 track segments and In3 carries 24, so putting the islands
    # under B - which is what this board did first, on the reasoning that it
    # kept the four-layer arrangement - left the busiest signal layer with no
    # ground to return to and gave the quietest one a plane on both sides.
    # Swapping the two assignments costs nothing: the lamination is symmetric,
    # no track moves, and no fab file changes.
    #
    # What it buys is measured rather than argued. Every through-hole via is a
    # layer change from F to B; with ground under both, the return crosses on
    # any ground via, and there are 176 of them. The worst return detour on
    # this board is 8.0 mm and the median is 2.7 mm. With the islands under B
    # the return had to cross on a GND-to-supply capacitor instead, and the
    # worst detour was 14.2 mm - past the board's own 10 mm limit, which the
    # check missed because nine of the thirteen candidate capacitors tie
    # ground to a 5 V *track* rather than to the island.
    #
    # In3 keeps a solid ground immediately under it, so its return is
    # continuous even where the islands above it are not. That is the
    # distinction `test_every_signal_layer_has_a_ground_plane_beside_it` draws,
    # and it is the one four layers could not satisfy for B.Cu at all.
    #
    # This is PCBWay's own published 6-layer build, from their standard
    # stackup table (`multi-layer-laminated-structure.html`), the 1.6 mm
    # 1 oz-inner entry:
    #
    #     L1-CU  outer base copper 0.5 oz, plated to 1 oz
    #     PP     7628 RC46%  DK 4.74   0.1960 pressed to 0.1855
    #     L2-CU  inner copper 1 oz
    #     CORE   DK 4.6      0.4300
    #     L3-CU  inner copper 1 oz
    #     PP     7628 RC46%  DK 4.74   0.1960 pressed to 0.1750
    #     L4-CU  inner copper 1 oz
    #     CORE   DK 4.6      0.4300
    #     L5-CU  inner copper 1 oz
    #     PP     7628 RC46%  DK 4.74   0.1960 pressed to 0.1855
    #     L6-CU  outer base copper 0.5 oz, plated to 1 oz
    #
    # The outer prepreg is the same 7628 at the same 0.1855 as the 4-layer
    # board, which is the whole reason this build was picked out of their
    # table rather than the first 6-layer entry in it. Every
    # impedance-controlled track on this board is on F.Cu over In1, so that
    # one dielectric being identical keeps the USB and Ethernet pair geometry
    # exactly as it was, and `pair_geometry` solves it from these numbers
    # rather than from a width someone remembered. PCBWay's own default
    # 6-layer 1.6 mm build uses 2116 at 0.1195 for the outer prepreg, which
    # would have moved every pair on the board.
    "thickness": 1.6,
    "copper_layers": 6,
    "copper_thickness": 0.035,
    "inner_copper_thickness": 0.035,
    "stack": [
        {"type": "prepreg", "thickness": 0.1855, "epsilon_r": 4.74},   # F  - In1
        {"type": "core", "thickness": 0.43, "epsilon_r": 4.6},         # In1 - In2
        {"type": "prepreg", "thickness": 0.175, "epsilon_r": 4.74},    # In2 - In3
        {"type": "core", "thickness": 0.43, "epsilon_r": 4.6},         # In3 - In4
        {"type": "prepreg", "thickness": 0.1855, "epsilon_r": 4.74},   # In4 - B
    ],
    "core_thickness": 0.43,
    "finish": "ENIG",
    "mask_colour": "Black",
    "pour_inset": 0.5,
}

F, B, MID = "F.Cu", "B.Cu", "In3.Cu"
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


# The two supply pins in the north-west corner, whose rings fall where the five
# static signals on the west edge have to escape inward.
#
# Those five pins are half a millimetre apart, and a via on the ring is a
# quarter of a millimetre from two of their lines: with these where the rest
# are, three of the five have no way out of the package at all. Moved outward
# instead of the signals being moved, because a supply via has one job - reach
# the plane - and it does that from anywhere its stub is short.
CORNER_RINGS = {"143": 9.6, "144": None}
CORNER_144 = (-9.6, -9.3)        # diagonally out, which is the only side free


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
        if str(number) in CORNER_RINGS:
            moved = CORNER_RINGS[str(number)]
            where = CORNER_144 if moved is None else pin.at(moved)
        else:
            where = pin.at(ring)
        VIAS.append((f"{MCU}:{number}", where, net, *VIA, STUB))


# --- decoupling: capacitors outward ------------------------------------------------

CAP_CENTRE, CAP_VIA = 12.9, 14.2

# The south side's row sits half a millimetre further out. Six analog channels
# come off that edge and their input networks are on the other side of the
# board, so the gap between the pads and this row is the only way west for
# them; everywhere else the row is where it wants to be. `test_core.py` allows
# three millimetres and this is 2.7.
CAP_CENTRE_SOUTH, CAP_VIA_SOUTH = 13.4, 14.7
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
        south = pin.normal[1] > 0
        centre = CAP_CENTRE_SOUTH if south else CAP_CENTRE
        PLACEMENT[address] = (*pin.at(centre, across), pin.facing())
        LABELS[address] = _label_beside(pin)
        path = [f"{MCU}:{number}"]
        if across:
            path += [pin.at(JOG), pin.at(JOG + abs(across), across)]
        ROUTES.append((NET_OF_PIN[number], SUPPLY, F, path + [f"{address}:1"]))
        VIAS.append((f"{address}:2",
                     pin.at(CAP_VIA_SOUTH if south else CAP_VIA, across),
                     "GND", *VIA, SUPPLY))


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
    corner_via = (-10.5, 10.9)
    ROUTES.append(("VDDA", SUPPLY, B, [inward, (-10.5, inward[1]), corner_via]))
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
    # The capacitors sit clear of the crystal's own two tracks rather than in
    # line with them: the fifteen analog lines cross this strip on the back
    # layer, and a ground via in line with a track is a via in a lane.
    PLACEMENT["core.hse.c_in"] = (-17.5, -1.6, 180)
    PLACEMENT["core.hse.c_out"] = (-17.5, 6.4, 180)
    LABELS["core.hse.crystal"] = (-3.4, 0.0)
    LABELS["core.hse.c_in"] = (0.0, -1.0)
    LABELS["core.hse.c_out"] = (0.0, 1.0)
    # Both turn well clear of the package: the strip between the pads and these
    # two columns is where the analog pins drop to the back layer, and it needs
    # room for three vias abreast.
    ROUTES.append(("HSE_IN", 0.2, F, [f"{MCU}:23", (-15.0, hse_in.at(0)[1]), (-15.0, 0.65), "core.hse.crystal:1"]))
    ROUTES.append(("HSE_OUT", 0.2, F, [f"{MCU}:24", (-13.8, hse_out.at(0)[1]), (-13.8, 4.35), "core.hse.crystal:2"]))
    ROUTES.append(("HSE_IN", 0.2, F, ["core.hse.crystal:1", "core.hse.c_in:1"]))
    ROUTES.append(("HSE_OUT", 0.2, F, ["core.hse.crystal:2", "core.hse.c_out:1"]))
    VIAS.append(("core.hse.c_in:2", (-18.9, -0.75), "GND", *VIA, SUPPLY))
    VIAS.append(("core.hse.c_out:2", (-18.9, 6.4), "GND", *VIA, SUPPLY))

    # 32.768 kHz, left of pins 8 and 9. Its crystal terminals are pads 1 and 4,
    # both on one end; turned to face the MCU.
    # North-west of the package rather than beside it. Where it used to sit is
    # the only strip on this side of the board wide enough for the fifteen
    # analog lines to change layer in, and a watch crystal is the one thing
    # here that does not mind being a few millimetres further away.
    lse_in, lse_out = PINS["8"], PINS["9"]
    PLACEMENT["core.lse.crystal"] = (-19.0, -12.0, 180)
    PLACEMENT["core.lse.c_in"] = (-16.25, -16.1, 90)
    PLACEMENT["core.lse.c_out"] = (-16.25, -8.2, 270)
    LABELS["core.lse.crystal"] = (0.0, 0.0)
    LABELS["core.lse.c_in"] = (-1.3, 0.0)
    LABELS["core.lse.c_out"] = (-1.3, 0.0)
    ROUTES.append(("LSE_IN", 0.2, F, [f"{MCU}:8", (-15.0, lse_in.at(0)[1]), (-15.0, -13.6), "core.lse.crystal:1"]))
    ROUTES.append(("LSE_OUT", 0.2, F, [f"{MCU}:9", (-15.6, lse_out.at(0)[1]), (-15.6, -10.4), "core.lse.crystal:4"]))
    ROUTES.append(("LSE_IN", 0.2, F, ["core.lse.crystal:1", "core.lse.c_in:1"]))
    ROUTES.append(("LSE_OUT", 0.2, F, ["core.lse.crystal:4", "core.lse.c_out:1"]))
    VIAS.append(("core.lse.c_in:2", (-16.25, -17.5), "GND", *VIA, SUPPLY))
    # North along the pad's own line, not west of it: west of it is the one
    # column on this side of the board with room for a signal to pass.
    VIAS.append(("core.lse.c_out:2", (-16.25, -6.6), "GND", *VIA, SUPPLY))


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
    PLACEMENT["core.bulk"] = (-13.5, -16.5, 0)
    VIAS.append(("core.bulk:1", (-15.0, -16.5), "3V3", *VIA, SUPPLY))
    VIAS.append(("core.bulk:2", (-12.0, -16.5), "GND", *VIA, SUPPLY))
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
            # It used to step onto the line between the two USB data pins to
            # get past VCAP2's capacitor. That line is a quarter of a
            # millimetre from one of them, and both of them need it now, so it
            # goes down where it is instead.
            out = p.at(11.9)
        elif pin == "133":
            # SWO stays on the front until it is clear of the band the four
            # field-bus signals cross in. Where it used to go down, at 12.3 mm,
            # its back-layer run cut that band to two lines and there are four
            # of them.
            out = p.at(16.5)
        else:
            out = p.at(12.3)
        path(net, SIGNAL, [
            (F, legs + [out]),
            (B, [out, (out[0], pad_y), (DEBUG_LEFT, pad_y)]),
        ])

    # NRST leaves inward - the 8 MHz crystal fills the outward side of its pin -
    # crosses beneath the package, and picks up its capacitor on the way.
    inward = PINS["25"].at(SUPPLY_RING_2)
    VIAS.append((f"{MCU}:25", inward, "NRST", *VIA, STUB))
    # Along the middle of the package and out to the right, clear of the three
    # debug tracks running down to the pads.
    PLACEMENT["core.nrst.cap"] = (19.4, -6.0, 0)
    LABELS["core.nrst.cap"] = (0.0, -1.3)
    VIAS.append(("core.nrst.cap:2", (21.0, -6.0), "GND", *VIA, SUPPLY))
    cap_via = (17.9, -6.0)
    path("NRST", SIGNAL, [
        # North of the buffer fan, not through it: fourteen PWM lines turn
        # south in the strip this used to cross. It runs at 3.27, the last
        # line in the band the ten static signals leave the package through,
        # and turns north at 17.5 - east of every one of their turns, so by
        # the time it gets there none of them is still running.
        (B, [inward, (-6.5, 0.5), (-6.5, -3.27), (17.9, -3.27), cap_via]),
        (F, [cap_via, "core.nrst.cap:1"]),
    ])
    # And down to the debug pad on the front, because the static lanes all
    # cross that column on the back.
    path("NRST", SIGNAL, [
        (B, [cap_via, (17.9, -7.5), (29.0, -7.5), (29.0, -9.9)]),
        # The static lanes cross this column on the back, so it crosses them
        # on the front; east of the USB pair, which crosses it the other way.
        (F, [(29.0, -9.9), (29.0, -20.0)]),
        (B, [(29.0, -20.0), (DEBUG_RIGHT, -20.0)]),
    ])


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
    PLACEMENT["core.button.switch"] = (-36.5, 5.25)
    # West of the switch rather than east: east of it is the strip the analog
    # lines change layer in, and this resistor's ground via was in it.
    PLACEMENT["core.button.pulldown"] = (-35.0, 12.0, 0)
    LABELS["core.button.switch"] = (3.2, -2.4)
    LABELS["core.button.pulldown"] = (0.0, -1.3)
    inward = PINS["7"].at(SUPPLY_RING_2)
    VIAS.append((f"{MCU}:7", inward, "BUTTON", *VIA, STUB))
    # It used to cross the package eastward and come back round the north-west
    # corner. The band it crossed in is now the one the ten static signals use
    # to get out of the package, and a button is the net here that can afford
    # to move: it turns south inside the package instead and leaves on the
    # south-west side, which is the side its switch is on anyway.
    ROUTES.append(("BUTTON", SIGNAL, B, [
        inward, (-12.0, -5.75), (-39.5, -5.75), (-40.3, -5.49), (-46.5, -5.49),
        (-46.5, 9.75), "core.button.switch:2",
    ]))
    ROUTES.append(("BUTTON", SIGNAL, F, ["core.button.switch:2", "core.button.pulldown:1"]))
    # A tactile switch has two legs on each pole, and they are separate pads:
    # the netlist calls them one node and the fabricator does not.
    legs = [_absolute("core.button.switch", pad.x, pad.y)
            for pad in _pads_of("core.button.switch")["2"]]
    if len(legs) > 1:
        ROUTES.append(("BUTTON", SIGNAL, F, legs))


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
    PLACEMENT["tp_console_tx"] = (22.0, 8.2)
    PLACEMENT["tp_console_rx"] = (22.0, 5.45)
    # The two rail pads go north-east, out of the strip the latch's signals
    # cross. They carry no signal - a plane via each is the whole net - so
    # anywhere the planes reach will do.
    PLACEMENT["tp_gnd"] = (52.0, 28.0)
    PLACEMENT["tp_3v3"] = (52.0, 31.0)
    for address in ("tp_console_tx", "tp_console_rx", "tp_gnd", "tp_3v3"):
        LABELS[address] = (2.6, 0.0)
    ROUTES.append(("CONSOLE_TX", SIGNAL, F, [f"{MCU}:77", (20.5, 6.75), "tp_console_tx:1"]))
    ROUTES.append(("CONSOLE_RX", SIGNAL, F, [
        # The dip happens east of the buffer fan, not through it.
        f"{MCU}:78", (21.5, 6.25), (21.5, 5.45), "tp_console_rx:1",
    ]))
    VIAS.append(("tp_gnd:1", (53.5, 28.0), "GND", *VIA, SUPPLY))
    VIAS.append(("tp_3v3:1", (53.5, 31.0), "3V3", *VIA, SUPPLY))



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
    # Its ground pin sits between the package and the on-time resistor, with
    # no room on its own line; the via goes west of it.
    VIAS.append(("buck5.ic:1", (-8.9, 28.1), "GND", *VIA, SUPPLY))

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
    # It surfaces inside the 5 V island rather than beyond it. The back layer
    # is referenced to whatever inner copper is under it, and that changes at
    # the island's edge: a track that crosses it hands its return current from
    # one plane to another halfway along.
    out = (-0.9, 30.64)
    path("PGOOD", SIGNAL, [
        (F, ["buck5.ic:6", out]),
        (B, [out, (-0.9, 35.5), (4.0, 35.5)]),
        (F, [(4.0, 35.5), "buck5.r_pgood:1"]),
    ])
    ROUTES.append(("PGOOD", SIGNAL, F, ["tp_pgood:1", "buck5.r_pgood:1"]))
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
    ROUTES.append(("5V", RAIL, F, ["buck3v3.ic:3", (32.14, 27.3)]))
    VIAS.append((None, (32.14, 27.3), "5V", *VIA))
    ROUTES.append(("5V", RAIL, F, ["buck3v3.ic:5", (28.5, 28.5)]))
    VIAS.append((None, (28.5, 28.5), "5V", *VIA))
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
    # The decoupling capacitor for pin 39 steps west: the reference's riser
    # runs down this column now, and there is no room for both.
    PLACEMENT["core.dec.p39"] = (-8.0, 13.4, 270)
    for address in ("vref.ic", "vref.c_in", "core.vref.c1u", "tp_vref"):
        LABELS[address] = (0.0, -2.6)

    pin = PINS[VREF_PIN]
    inward = pin.at(SUPPLY_RING_2)
    VIAS.append((f"{MCU}:{VREF_PIN}", inward, "VREF+", *VIA, STUB))
    surfaced = (-7.25, 12.2)
    # Out through the corner well inside the ring, then up to the front as soon
    # as it is clear of the package: south of here is the channel the six
    # analog pins on this edge cross on the back, and this is the one net that
    # would otherwise have to cross all six of them.
    path("VREF+", SUPPLY, [
        (B, [inward, (-6.5, 8.0), (-6.5, 10.5), surfaced]),
        (F, [surfaced, (-7.25, 18.05), "tp_vref:1"]),
    ])
    ROUTES.append(("VREF+", SUPPLY, F, ["tp_vref:1", "vref.ic:2"]))
    ROUTES.append(("VREF+", SUPPLY, F, [
        "vref.ic:2", (-12.56, 16.0), (-15.99, 16.0), "core.vref.c1u:1",
    ]))
    VIAS.append(("core.vref.c1u:2", (-16.98, 17.8), "GND", *VIA, SUPPLY))

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


# Ground on the first and third inner layers, and the supplies on the fourth:
# 3V3 over the whole board, with the 5 V island cut out of it by priority
# rather than by outline. KiCad fills the higher priority first and the 3V3
# pour keeps clear.
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
    # The second ground plane, under In2.Cu. This is the layer six buys: the
    # middle signal layer is referenced to ground on both sides, so its return
    # current never has to find its way around an island's edge.
    {
        "net": "GND",
        "layer": "In4.Cu",
        "outline": _pour_outline(),
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
HEADER_NET = PINMAP.header_pins(PINMAP.HEADER_DIGITAL, PINMAP.HEADER_GROUND, 52)
HEADER_PIN = {net: number for number, net in HEADER_NET.items()}


def _header_at(number: int) -> tuple[float, float]:
    """Where pin `number` of a 2x26 odd/even header sits, with pin 1 at the origin."""
    x, y = HEADER_ORIGIN
    position = (number + 1) // 2 - 1
    return (x + (0.0 if number % 2 else HEADER_PITCH), round(y + position * HEADER_PITCH, 4))


def _lane_of(name: str) -> float:
    """Where a static signal's parts sit, by its place in the header table."""
    # 2.0 mm apart, not 1.4. At the tighter pitch there was nowhere to put a
    # via beside two of these resistors' supply pads, which the plane stitching
    # generator refused to guess at rather than placing one on a neighbour.
    statics = [n for n in PINMAP.HEADER_STATIC if n != "3V3"]
    return round(-26.6 + 2.0 * statics.index(name), 4)


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
    # On the lane each one holds up, in the strip between the package and the
    # latch. South of the buffer put their ground vias across the only way the
    # four signals from the package have of getting here.
    PLACEMENT["safety.r_clear_pullup"] = (21.0, 13.6, 0)
    PLACEMENT["safety.r_enable_pullup"] = (18.0, 11.3, 0)
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
    for address, names in (("safety.buffer2", PINMAP.HEADER_BUFFER2),
                           ("safety.buffer1", PINMAP.HEADER_BUFFER1)):
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
            # Under the first row, crossing midway between two of its pins.
            # Threading between them on the front is 0.42 mm from each pad -
            # enough copper clearance, not enough to keep their solder mask
            # apertures apart - so it goes underneath, and the capacitors that
            # give its return current a way across sit beyond the connector.
            between = _header_at(number)[1] + HEADER_PITCH / 2
            path(name, width, [
                (F, [f"{series}:2", f"{pulldown}:1"]),
                (B, [f"{pulldown}:1", (PULLDOWN_X + 1.0, _slot_of(name)),
                     (PULLDOWN_X + 1.0, between),
                     (HEADER_ORIGIN[0] + HEADER_PITCH, between), pin]),
            ])


# Each static signal from its pull resistor to the pin it leaves on.
#
# The resistors are already in the header's order, so the ten runs fan without
# crossing. What decides the rest is which row the pin is in. A first-row pin
# is reached on the front: out along the signal's own lane, then a turn north
# in a column of its own, then a step east into the pin. The columns go west as
# the lanes go south, which is what stops a lane meeting a column.
#
# A second-row pin is behind the first row, and the first row is through-hole -
# there is no going past it on either layer except between two of its pins. So
# those five drop to the back at their own lane, before the first row's columns
# start, and come up at the pin.
STATIC_TURN = {
    "RELAY1": 42.7, "ID_STRAP1": 42.4, "ID_STRAP2": 42.1,
    "STO1_FEEDBACK": 41.8, "STO2_FEEDBACK": 41.5,
}
# East of the 5 V spine, which runs the length of the board on the back here.
STATIC_UNDER = {
    "FAULT2_N": 37.0, "FAULT1_N": 37.7, "ID_STRAP3": 38.4,
    "ID_STRAP0": 39.1, "RELAY2": 39.8,
}


def _static_routes() -> None:
    for name, address in sorted(STATIC_PULL.items()):
        number = HEADER_PIN[name]
        lane, width = _lane_of(name), _width_for(name, SIGNAL)
        pin = f"header.digital:{number}"
        # A pull-up holds the signal on its second pad and a pull-down on its
        # first; which it is comes from the netlist, not from the name.
        pad = next(p for a, p in DESIGN["nets"][name] if a == address)
        if number % 2:
            turn = STATIC_TURN[name]
            ROUTES.append((name, width, F, [
                f"{address}:{pad}", (turn, lane), (turn, _header_at(number)[1]), pin]))
        else:
            # Under the first row, crossing midway between two of its pins.
            drop = (STATIC_UNDER[name], lane)
            between = _header_at(number)[1] + HEADER_PITCH / 2
            path(name, width, [
                (F, [f"{address}:{pad}", drop]),
                (B, [drop, (drop[0], between),
                     (HEADER_ORIGIN[0] + HEADER_PITCH, between), pin]),
            ])


# --- the ten static signals, from the package to their pulls -----------------
#
# The last signals off the package and the only ones that cross the whole
# board. Their pins are on four different edges and the resistors they meet are
# in one column on the far side, so a bundle sorted by pin would have to be
# unsorted at the other end. They are sorted once instead, on the way out:
# ordered the way the resistor column is ordered rather than the way the pins
# are, each turning north on its own column and running east on its own lane.
# Nothing crosses anything, which is what the ordering buys.
#
# Seven of them leave through the band between the supply ring and the PWM
# lines that drop behind the package - three and a half millimetres, which is
# eight lines at the pitch a via needs, and reset crosses in it too. The other
# three take routes their own pins make easy: two off the north edge go over
# the top, and the one off the east edge is pointing the right way already.
STATIC_BAND = (
    # net, its line through the band, the column it turns north on
    ("RELAY1", -6.70, 13.0),
    ("RELAY2", -6.21, 13.7),
    ("ID_STRAP0", -5.72, 15.0),
    ("ID_STRAP1", -5.23, 15.7),
    ("ID_STRAP2", -4.74, 16.4),
    ("ID_STRAP3", -4.25, 16.9),
    ("FAULT1_N", -3.76, 17.2),
)

# The five on the west edge run inward on the front at their own pin's height,
# climb together in one window, and drop through in a staggered row - staggered
# because the pins are half a millimetre apart and a via is not.
STATIC_WEST = {"ID_STRAP0": -1.0, "ID_STRAP1": -0.2, "ID_STRAP2": 0.6,
               "ID_STRAP3": 1.4, "FAULT1_N": 2.2}
STATIC_CLIMB = (-7.5, -2.5)

# The two off the south edge cross the package on the front, where the band's
# own tracks cannot be in their way, and drop into the two lines nearest them.
STATIC_SOUTH = {"RELAY1": (4.0, 0.75), "RELAY2": (4.6, 1.25)}

# The two off the north edge never enter the band. They go out on the front at
# their own pin's height, cross the field-bus escapes on the back, and come
# back to the front for the strip the lanes fill. The one that ends further
# south goes out further north, so neither crosses the other.
STATIC_OVER = {"STO1_FEEDBACK": (-12.0, 22.4, -15.9, 4.4, 11.0),
               "STO2_FEEDBACK": (-14.0, 23.5, -16.9, 3.8, 11.0)}
STATIC_OVER_STEP = (8.2, 21.5)
STATIC_OVER_HOP = (23.0, 24.0)

# The one off the east edge is south of the band and has to get north of it, so
# it goes east first, past every column, and turns up the far side.
FAULT2_OUT = ((11.6, 1.25), (12.4, 1.6))
FAULT2_DROP, FAULT2_LANE, FAULT2_COLUMN = (15.0, 1.9), -1.4, 33.0
FAULT2_LEGS = ((15.0, -1.4),)
# It crosses the four PWM lines turning south to the buffers; three
# millimetres on the front is the whole of that crossing.
FAULT2_STEP = (19.2, 32.4)

# Where each lane surfaces onto the track its resistor already has: east of the
# pad, so the track runs under the resistor rather than into its supply pad.
STATIC_RISE = 35.9

# The debug port's three back-layer runs cross the lanes that go furthest
# north. They step onto the front for as far as they have to, which for one of
# them is only as far as its own lane.
DEBUG_CROSSING = -18.73
DEBUG_STEP = (-17.6, -21.8)

# The Tag-Connect's pads and unplated holes sit on two lanes. Each goes round
# on the side its neighbours leave free.
SWD_DODGE = {"ID_STRAP0": (33.0, -23.7), "ID_STRAP2": (22.4, -19.37)}


def _static_lane(net: str, lane: float) -> tuple:
    """How far north the column goes, and the lane from there to where it rises."""
    if net in SWD_DODGE:
        after, over = SWD_DODGE[net]
        return over, [(after, over), (after, lane), (STATIC_RISE, lane)]
    return lane, [(STATIC_RISE, lane)]


def _static_mcu() -> None:
    """Each static signal from its package pin to the track its resistor has."""
    start, finish = STATIC_CLIMB
    for net, slot, column in STATIC_BAND:
        width = _width_for(net, SIGNAL)
        pin = next(pad for address, pad in DESIGN["nets"][net] if address == MCU)
        lane = _lane_of(net)

        if net in STATIC_WEST:
            drop = (STATIC_WEST[net], slot)
            ROUTES.append((net, width, F, [
                f"{MCU}:{pin}", (start, _point(f"{MCU}:{pin}")[1]),
                (finish, slot), drop]))
        else:
            column_x, out = STATIC_SOUTH[net]
            drop = (column_x, slot)
            ROUTES.append((net, width, F, [
                f"{MCU}:{pin}", (out, 9.0), (column_x, 7.0), drop]))
        VIAS.append((None, drop, net, *VIA))

        deepest, tail = _static_lane(net, lane)
        legs = [drop, (column, slot)]
        if deepest < DEBUG_CROSSING:
            step = max(deepest, DEBUG_STEP[1])
            path(net, width, [
                (B, legs + [(column, DEBUG_STEP[0])]),
                (F, [(column, DEBUG_STEP[0]), (column, step)]),
                (B, [(column, step), (column, deepest), *tail]),
            ])
        else:
            ROUTES.append((net, width, B, legs + [(column, deepest), *tail]))
        VIAS.append((None, (STATIC_RISE, lane), net, *VIA))

    west, east = STATIC_OVER_STEP
    for net, (over, column, out, turn, along) in STATIC_OVER.items():
        width = _width_for(net, SIGNAL)
        pin = next(pad for address, pad in DESIGN["nets"][net] if address == MCU)
        lane = _lane_of(net)
        at = _point(f"{MCU}:{pin}")
        path(net, width, [
            (F, [f"{MCU}:{pin}", (at[0], out), (turn, out)]),
            (B, [(turn, out), (west, out)]),
            (F, [(west, out), (along, over), (east, over)]),
            (B, [(east, over), (column, over), (column, lane),
                 (STATIC_OVER_HOP[0], lane)]),
            # One of the two has to cross the other's column; a millimetre on
            # the front is the whole of it.
            (F, [(STATIC_OVER_HOP[0], lane), (STATIC_OVER_HOP[1], lane)]),
            (B, [(STATIC_OVER_HOP[1], lane), (STATIC_RISE, lane)]),
        ])
        for where in ((turn, out), (west, out), (east, over),
                      (STATIC_OVER_HOP[0], lane), (STATIC_OVER_HOP[1], lane),
                      (STATIC_RISE, lane)):
            VIAS.append((None, where, net, *VIA))

    net = "FAULT2_N"
    width = _width_for(net, SIGNAL)
    pin = next(pad for address, pad in DESIGN["nets"][net] if address == MCU)
    lane = _lane_of(net)
    ROUTES.append((net, width, F, [f"{MCU}:{pin}", *FAULT2_OUT, FAULT2_DROP]))
    VIAS.append((None, FAULT2_DROP, net, *VIA))
    path(net, width, [
        (B, [FAULT2_DROP, *FAULT2_LEGS, (FAULT2_STEP[0], FAULT2_LANE)]),
        (F, [(FAULT2_STEP[0], FAULT2_LANE), (FAULT2_STEP[1], FAULT2_LANE)]),
        (B, [(FAULT2_STEP[1], FAULT2_LANE), (FAULT2_COLUMN, FAULT2_LANE),
             (FAULT2_COLUMN, lane), (STATIC_RISE, lane)]),
    ])
    VIAS.append((None, (STATIC_RISE, lane), net, *VIA))


# --- the last few, each one local ---------------------------------------------

# The CAN transceiver's supply pin and the capacitor beside it: the capacitor's
# ground pad sits between them, so the track goes round it on the pin's own
# line rather than straight across.
CAN_SUPPLY = ((1.1, -21.9), (1.1, -22.8), (-3.3, -22.8), (-3.98, -21.4), (-3.98, -20.81))

# Both gate-driver faults meet the same dual diode north of the Tag-Connect.
# Each drops off its own lane and comes down its own column on the front,
# because the lanes between them and it are all on the back.
# The first drops off its lane and comes straight down. The second starts
# south of the band, north of the USB pair, so it goes down on the back until
# it is south of the pair and changes to the front for the lanes.
FAULT_DIODES = (
    # net, the column it comes down, the lane it leaves, its pad, the height
    # it crosses at and the height the pad is on
    ("FAULT1_N", 25.5, -14.6, "safety.d_faults:1", -28.7, -28.95),
    ("FAULT2_N", 32.8, -8.6, "safety.d_faults:2", -28.0, -27.05),
)
# Where the first crosses the VBUS leg coming up from the receptacle.
# Both of them reach the diode's own side on the back, because the trip bus's
# link between the two diodes runs across the front between them.
FAULT_WEST = {"FAULT1_N": 20.0, "FAULT2_N": 19.4}

# Reset reaches the diode that presets the latch from the leg that goes down to
# the debug pad, on the front for the same reason.
# Reset reaches the diode that presets the latch from the debug pad it already
# goes to, stepping west between the Tag-Connect's holes and the trip pull-up.
NRST_DIODE = ((DEBUG_RIGHT, -20.0), (22.3, -20.0), (22.3, -23.4),
              (18.6, -23.4), (18.6, -32.95))


def _last_few() -> None:
    # Its ground pad's way down, where the generator used to find it: the
    # supply track now runs close enough below to put it off.
    VIAS.append(("can.decoupling_vcc:2", (-3.02, -21.95), "GND", *VIA, SUPPLY))
    width = _width_for("5V", SIGNAL)
    # The CAN transceiver's 5 V does not reach the island beside the
    # regulator, so it goes north to the spine that carries 5 V out of the
    # island along the top of the board - east of the comparators' own lane,
    # which stops where the comparators do.
    ROUTES.append(("5V", _width_for("5V", SIGNAL), B,
                   [CAN_SUPPLY[1], (5.9, CAN_SUPPLY[1][1]),
                    (5.9, TRIP_SPINE_Y)]))
    out, down, west, up, pad = CAN_SUPPLY
    path("5V", width, [
        (F, ["can.transceiver:3", out]),
        (B, [out, down, west]),
        (F, [west, up, pad, "can.decoupling_vcc:1"]),
    ])
    VIAS.append((None, out, "5V", *VIA))
    VIAS.append((None, west, "5V", *VIA))

    for net, column, lane, target, across, height in FAULT_DIODES:
        width = _width_for(net, SIGNAL)
        # The second one's lane only starts east of the resistor column, so it
        # runs back west on the back layer first: the trip bus crosses this
        # corner on the front.
        if net == "FAULT2_N":
            ROUTES.append((net, width, B, [(33.0, lane), (column, lane)]))
        VIAS.append((None, (column, lane), net, *VIA))
        path(net, width, [
            (F, [(column, lane), (column, across)]),
            (B, [(column, across), (FAULT_WEST[net], across)]),
            (F, [(FAULT_WEST[net], across), (FAULT_WEST[net], height), target]),
        ])

    ROUTES.append(("NRST", SIGNAL, F, [*NRST_DIODE, "safety.d_reset:1"]))


# The threshold DAC's two I2C lines. They leave the west edge two pins apart
# and have to reach the DAC, which is north-west of the package behind the boot
# pad, the crystal, the bulk capacitor and two test networks. The back layer
# through there is nearly empty - only the button's long wire and the DC link's
# sense line cross it - but it is stitched with plane vias, and a via is what
# neither of these can put anywhere. So each one is written out: a column where
# there is room for one, a step onto the front where it has to pass a wire, and
# a jog where the next via would not have fitted.
I2C_PATHS = {
    # West on the back at the pin's own height, past everything the crystal
    # and the decoupling row put in the way, then north on the front in the
    # strip between the crystal and the analog fan's lanes - which is the one
    # column on this side with nothing on the front in it at all. The button's
    # wire and the DC link's sense line both cross it, and both are on the
    # back, so neither costs a via.
    "DAC_SCL": (
        (F, [(-12.0, -3.75)]),
        (B, [(-18.2, -3.75)]),
        (F, [(-18.2, -23.4)]),
        (B, [(-11.4, -23.4), (-11.4, -24.5)]),
        (F, ["trip.dac:2"]),
    ),
    "DAC_SDA": (
        (F, [(-12.7, -4.25)]),
        (B, [(-19.2, -4.25)]),
        (F, [(-19.2, -22.2)]),
        (B, [(-6.8, -22.2)]),
        (F, ["trip.r_sda_pullup:2"]),
    ),
}

# And from the DAC to the pull-up each one has, on the front, each on its own
# side of the other.
I2C_PULLUPS = {
    "DAC_SCL": ((-8.8, -24.5), (-8.8, -22.6), "trip.r_scl_pullup:2"),
    "DAC_SDA": ((-8.3, -25.0), "trip.dac:3"),
}


def _dac_i2c() -> None:
    """The two I2C lines from the package to the threshold DAC and its pulls."""
    # The DAC's ground pin used to reach the plane west of it; the data line
    # now runs there, so it goes south instead.
    VIAS.append(("trip.dac:4", (-7.5, -25.5), "GND", *VIA, SUPPLY))
    VIAS.append(("trip.dac:10", (-12.5, -24.0), "GND", *VIA, SUPPLY))

    for net, legs in I2C_PATHS.items():
        width = _width_for(net, SIGNAL)
        pin = next(pad for address, pad in DESIGN["nets"][net] if address == MCU)
        here: list = [f"{MCU}:{pin}"]
        steps = []
        for layer, points in legs:
            steps.append((layer, here + list(points)))
            here = [points[-1]]
        path(net, width, steps)
        for layer, points in legs[:-1]:
            VIAS.append((None, points[-1], net, *VIA))
        ROUTES.append((net, width, F, [legs[-1][1][-1], *I2C_PULLUPS[net]]))


# The reference out to the analog connector. It leaves the connector's east
# column like a sense line does - half a row out and half a row along - and
# then runs east under the input networks on the back, which is empty at that
# height, and south round the west end of the fan's own lanes.
VREF_OUT = ((-40.4, 3.4), (-39.0, 4.67))
VREF_LANE, VREF_COLUMN, VREF_ROW = 7.21, -39.0, 17.0
VREF_TURN, VREF_RISE = -28.0, -16.02


def _vref_out() -> None:
    net = "VREF+"
    width = _width_for(net, SIGNAL)
    path(net, width, [
        (F, ["header.analog:22", *VREF_OUT]),
        (B, [VREF_OUT[-1], (VREF_COLUMN, VREF_LANE), (VREF_TURN, VREF_LANE),
             (VREF_TURN, VREF_ROW), (VREF_RISE, VREF_ROW)]),
        (F, [(VREF_RISE, VREF_ROW), "core.vref.c1u:1"]),
    ])
    VIAS.append((None, VREF_OUT[-1], net, *VIA))
    VIAS.append((None, (VREF_RISE, VREF_ROW), net, *VIA))


# The spare DAC output's test network. Its pin is on the south edge in the
# middle of the analog fan's own escapes, so it goes inward and out again to
# the west, where the network now sits.
DAC_TEST_INWARD, GATE_ENABLE_INWARD = (-7.25, 10.0), (5.5, 7.7)
DAC_TEST_PATH = (
    (B, [(-10.0, 10.0)]),
    (F, [(-11.2, 10.0)]),                           # over VDDA's own corner
    (B, [(-14.5, 10.0), (-14.5, 9.6)]),
    (F, ["adc.dac_test.series:1"]),
)


def _across_the_package() -> None:
    for net, inward, legs in (("DAC_TEST", DAC_TEST_INWARD, DAC_TEST_PATH),):
        width = _width_for(net, SIGNAL)
        pin = next(pad for address, pad in DESIGN["nets"][net] if address == MCU)
        here: list = [f"{MCU}:{pin}", inward]
        steps = []
        if legs[0][0] is not F:
            steps.append((F, here))
            VIAS.append((None, inward, net, *VIA))
            here = [inward]
        for layer, points in legs:
            steps.append((layer, here + list(points)))
            here = [points[-1]]
        path(net, width, steps)
        for layer, points in legs[:-1]:
            VIAS.append((None, points[-1], net, *VIA))


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
    for address, names in (("safety.buffer1", PINMAP.HEADER_BUFFER1),
                           ("safety.buffer2", PINMAP.HEADER_BUFFER2)):
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


STATIC_PULL: dict[str, str] = {}


def _static_pulls() -> None:
    """
    The ten signals that are not PWM, each with its pull-up or pull-down.

    They sit in a column at the end of the lane each will take across the board,
    in the order the header table puts them - which is the order they leave the
    package, furthest first.
    """
    pulls = {
        "RELAY1": "down", "RELAY2": "down",
        "ID_STRAP0": "up", "ID_STRAP1": "up", "ID_STRAP2": "up", "ID_STRAP3": "up",
        "FAULT1_N": "up", "FAULT2_N": "up",
        "STO1_FEEDBACK": "down", "STO2_FEEDBACK": "down",
    }
    named = {"FAULT1_N": "safety.r_fault1_pullup", "FAULT2_N": "safety.r_fault2_pullup"}
    STATIC_PULL.update(
        {name: named.get(name,
                         f"safety.{'pullup' if direction == 'up' else 'pulldown'}.{name.lower()}")
         for name, direction in pulls.items()})
    for name, direction in pulls.items():
        address = STATIC_PULL[name]
        PLACEMENT[address] = (34.5, _lane_of(name), 0 if direction == "up" else 180)
        LABELS[address] = (0.0, -1.3)



# --- the trip comparators and the analog connector ---------------------------
#
# The left-hand third, which the analog signals reach first. Seven comparators
# in a column beside the connector they watch, their threshold DAC below them,
# and the four dual Schottkys that carry seven outputs onto one trip bus.
#
# Placed, not routed, for the same reason the safety chain is: M8.

# The connector stands on the west edge with its pins in a column, and
# everything it feeds stands east of it.
ANALOG_HEADER = (-44.0, -22.0)

# The comparator row along the north edge, turned so the inputs face south -
# towards the connector the signals arrive on - and the outputs north, towards
# the diodes. The pitch is what leaves each one room for its capacitor beside
# it; the two offsets are where that capacitor and the diode row go.
TRIP_ROW, TRIP_PITCH = (-40.0, -35.0), 5.0
TRIP_DECOUPLING = (2.2, -2.6)
TRIP_DIODES = -43.0

# 5 V arrives along a lane between the comparators and the diodes, and the
# outputs cross it on the front. That is the whole reason it is on the back:
# seven outputs cross this lane and none of them should have to change layer.
TRIP_SUPPLY_LANE = -39.0

# The threshold DAC, in the channel between the connector's column and the
# comparator row and east of every tap but one, so its three buses run the one
# way. Where it leaves the island the 5 V spine starts.
TRIP_DAC = (-12.0, -25.0)
ISLAND_TAP = (-8.5, 25.5)
TRIP_SPINE_X, TRIP_SPINE_Y = 36.5, -51.5


# The comparators, in the order the analog header presents them, so the two
# that watch one phase sit together. Named once: the placement and the supply
# spine both walk it.
TRIP_ORDER = (
    "fast1_high", "fast1_low", "fast2_high", "fast2_low", "fast3_high", "fast3_low", "fast4_high",
)

# The three threshold buses: the net, the DAC pad it leaves on, the lane it
# runs down, the comparator pin it lands on, and the comparators it feeds.
#
# They run on the back layer under the comparator row. The four sense lines
# share this channel and run on the front, and between the two sets there are
# seven crossings: putting one set on each layer is what makes those crossings
# cost nothing. Which set goes on the back is decided by the taps - a
# threshold tap surfaces beside the pin it feeds and goes nowhere else, while a
# sense line has to reach the input networks as well.
THRESHOLDS = (
    ("TRIP_LEVEL_HIGH", "6", -31.0, "3", ("fast1_high", "fast2_high", "fast3_high")),
    ("TRIP_LEVEL_LOW", "7", -31.8, "1", ("fast1_low", "fast2_low", "fast3_low")),
    ("TRIP_LEVEL_FAST4", "8", -32.6, "3", ("fast4_high",)),
)


def _trip_supply() -> None:
    """
    5 V from the regulator's island to the comparators, forty millimetres away.

    The island on the inner layer stops beside the buck; the comparators do not
    reach it, so their supply pads have no plane under them and stitching them
    gave four vias connected to nothing. The supply is routed instead.

    It goes the long way round, east of the package, because the short way is
    through the channel these comparators are fed from - and everything in that
    channel is already using both layers. A supply that has to thread between
    seven signals is a supply in the wrong place, not a harder routing problem.

    Each tap lands on the comparator's decoupling capacitor and reaches the
    supply pin from there, so the capacitor is on the pin's side of the
    inductance rather than the lane's.
    """
    taps = [_point(f"trip.{key}.decoupling:1")[0] for key in TRIP_ORDER]
    spine = [
        ISLAND_TAP,
        (ISLAND_TAP[0], 21.0),
        (TRIP_SPINE_X, 21.0),
        # North of the USB receptacle rather than through it, and along the
        # top of the board to the far end of the row, so the lane itself
        # starts where the comparators do.
        (TRIP_SPINE_X, TRIP_SPINE_Y),
        (min(taps), TRIP_SPINE_Y),
        (min(taps), TRIP_SUPPLY_LANE),
        (max(taps), TRIP_SUPPLY_LANE),
    ]
    VIAS.append((None, ISLAND_TAP, "5V", *VIA))
    ROUTES.append(("5V", _width_for("5V", RAIL), B, spine))

    for key in TRIP_ORDER:
        pad = _point(f"trip.{key}.decoupling:1")
        tap = (pad[0], TRIP_SUPPLY_LANE)
        VIAS.append((None, tap, "5V", *VIA))
        ROUTES.append(("5V", _width_for("5V", SUPPLY), F, [
            tap, f"trip.{key}.decoupling:1", f"trip.{key}:4",
        ]))


def _trip_routes() -> None:
    """
    The thresholds in, and the comparator outputs out.

    Each threshold drops to the back layer beside the DAC, runs its own lane
    west under the comparator row, and surfaces directly below the pin it
    feeds. Nothing it passes on the way is on the back, so the three lanes are
    parallel for their whole length and cross nothing at all.

    The outputs need no via: they leave the north side of the row, cross the
    supply lane - which is on the back for exactly this reason - and land on
    the diode above. Two comparators share a diode, and the two that share it
    approach from opposite sides, so no two outputs cross either.
    """
    for index, (net, dac_pad, lane, pin, keys) in enumerate(THRESHOLDS):
        width = _width_for(net, SIGNAL)
        pad_x, pad_y = _point(f"trip.dac:{dac_pad}")
        # Out of the package and straight down. The three pads are half a
        # millimetre apart and a via is half a millimetre across, so they step
        # away from the package as well as along it.
        # The deeper a bus's lane, the further east it drops: a lane that has
        # to get past another one's horizontal has to start east of where that
        # horizontal ends, and the DAC's pins come out in that order already.
        drop = (round(pad_x - 1.3 - (len(THRESHOLDS) - 1 - index) * 0.7, 4), pad_y)
        taps = sorted(_point(f"trip.{key}:{pin}")[0] for key in keys)
        # The lane has to reach the furthest tap either way. A bus whose first
        # tap is east of where it drops goes out along the pad's own line
        # first, then down, then back west past the rest - and the version
        # that stopped at that first tap left the other two comparators on
        # their own, which nothing but the unrouted count noticed.
        if taps[-1] < drop[0]:
            legs = [drop, (drop[0], lane), (taps[0], lane)]
        else:
            legs = [drop, (taps[-1], pad_y), (taps[-1], lane), (taps[0], lane)]
        path(net, width, [
            (F, [f"trip.dac:{dac_pad}", drop]),
            (B, legs),
        ])
        for x in taps:
            VIAS.append((None, (x, lane), net, *VIA))
            ROUTES.append((net, width, F, [(x, lane), f"trip.{key_at(keys, pin, x)}:{pin}"]))

    for index, key in enumerate(TRIP_ORDER):
        diode = f"trip.d_outputs{index // 2 + 1}"
        pad = "1" if index % 2 == 0 else "2"
        net = f"TRIP_{key.upper()}"
        ROUTES.append((net, _width_for(net, SIGNAL), F,
                       [f"trip.{key}:5", f"{diode}:{pad}"]))


def key_at(keys: tuple[str, ...], pin: str, x: float) -> str:
    """Which of a bus's comparators has its tap at this x."""
    return next(k for k in keys if abs(_point(f"trip.{k}:{pin}")[0] - x) < 1e-6)


def _trip() -> None:
    """
    The analog front end, laid out as the chain it is.

    The connector stands on the west edge with its pins in a column; the input
    networks stand beside it in two columns, one per column of pins, each cell
    level with the pin it belongs to; and the comparators sit in a row along
    the north edge, where the four signals they watch are the four nearest
    pins.

    It was a column of comparators between the connector and the cells before,
    with the threshold buses in the gap. Nothing could get past: fourteen sense
    lines had one two-millimetre corridor to share with three threshold lanes,
    and no arrangement of them fitted. The fix was not a cleverer route.
    """
    PLACEMENT["header.analog"] = (*ANALOG_HEADER, 0)
    LABELS["header.analog"] = (-3.0, -2.0)

    for index, key in enumerate(TRIP_ORDER):
        x = round(TRIP_ROW[0] + TRIP_PITCH * index, 4)
        PLACEMENT[f"trip.{key}"] = (x, TRIP_ROW[1], 90)
        LABELS[f"trip.{key}"] = (-2.4, 0.0)
        # North-east of the part, clear of both its courtyard and the output
        # leaving the pin beside it: a capacitor level with the supply pin sits
        # in the courtyard, and one directly north of it sits on the output.
        PLACEMENT[f"trip.{key}.decoupling"] = (
            round(x + TRIP_DECOUPLING[0], 4),
            round(TRIP_ROW[1] + TRIP_DECOUPLING[1], 4), 0)
        LABELS[f"trip.{key}.decoupling"] = (0.0, -1.3)

    # The four dual Schottkys north of the row, each between the pair it
    # serves - which is what lets both outputs reach it without crossing.
    for index in range(4):
        first = TRIP_ROW[0] + TRIP_PITCH * 2 * index
        PLACEMENT[f"trip.d_outputs{index + 1}"] = (
            round(first + (TRIP_PITCH / 2 if index < 3 else 0.0), 4),
            TRIP_DIODES, 90)
        LABELS[f"trip.d_outputs{index + 1}"] = (0.0, -2.2)

    # The threshold DAC, turned so the three outputs face the lanes they drop
    # into and the bus and supply pins face the package they come from.
    PLACEMENT["trip.dac"] = (*TRIP_DAC, 180)
    LABELS["trip.dac"] = (0.0, 3.0)
    PLACEMENT["trip.dac.decoupling"] = (-14.0, -21.5, 0)
    PLACEMENT["trip.dac.bulk"] = (-11.0, -21.5, 0)
    PLACEMENT["trip.r_scl_pullup"] = (-8.0, -21.5, 0)
    PLACEMENT["trip.r_sda_pullup"] = (-6.5, -23.5, 0)
    PLACEMENT["tp_dac_spare"] = (-11.0, -18.5)
    for address in ("trip.dac.decoupling", "trip.dac.bulk", "trip.r_scl_pullup",
                    "trip.r_sda_pullup", "tp_dac_spare"):
        LABELS[address] = (0.0, -1.6)

    _analog_header_supply()

    _trip_supply()
    _trip_routes()


# The analog supply for the power board's own sensors: the 5 V rail through a
# bead, which is what VDDA gets and for the same reason. It sits west of the
# connector and level with the two pins it leaves on, so the bead is at the
# load rather than at the rail - which is the only place a bead is worth
# fitting.
ANALOG_SUPPLY = 7.21                      # midway between pins 23 and 25
ANALOG_SUPPLY_LANE, ANALOG_SUPPLY_TAP = 22.0, (-7.0, 26.0)
ANALOG_SUPPLY_COLUMN = -53.0


def _analog_header_supply() -> None:
    PLACEMENT["analog.bead"] = (-51.5, ANALOG_SUPPLY, 0)
    PLACEMENT["analog.bulk"] = (-49.5, ANALOG_SUPPLY + 2.6, 270)
    PLACEMENT["analog.decoupling"] = (-47.5, ANALOG_SUPPLY + 2.6, 270)
    for address in ("analog.bead", "analog.bulk", "analog.decoupling"):
        LABELS[address] = (0.0, -1.6)

    # 5 V from the island, the long way round the west of the board: the
    # connector is as far from the regulator as anything on this board is.
    rail = _width_for("5V", RAIL)
    VIAS.append((None, ANALOG_SUPPLY_TAP, "5V", *VIA))
    ROUTES.append(("5V", rail, B, [
        ANALOG_SUPPLY_TAP,
        (ANALOG_SUPPLY_TAP[0], ANALOG_SUPPLY_LANE),
        (ANALOG_SUPPLY_COLUMN, ANALOG_SUPPLY_LANE),
        (ANALOG_SUPPLY_COLUMN, ANALOG_SUPPLY),
    ]))
    VIAS.append((None, (ANALOG_SUPPLY_COLUMN, ANALOG_SUPPLY), "5V", *VIA))
    ROUTES.append(("5V", rail, F,
                   [(ANALOG_SUPPLY_COLUMN, ANALOG_SUPPLY), "analog.bead:1"]))

    # And out the other side of the bead to the two pins and both capacitors.
    supply = _width_for("5VA", RAIL)
    ROUTES.append(("5VA", supply, F, [
        "analog.bead:2", (-45.5, ANALOG_SUPPLY), "header.analog:23"]))
    ROUTES.append(("5VA", supply, F, [(-45.5, ANALOG_SUPPLY), "header.analog:25"]))
    for address in ("analog.bulk", "analog.decoupling"):
        x = PLACEMENT[address][0]
        ROUTES.append(("5VA", supply, F, [(x, ANALOG_SUPPLY), f"{address}:1"]))


# --- the ADC input networks --------------------------------------------------
#
# One cell per connector pin, level with its pin, in two columns because the
# connector has two. A single column ordered alphabetically, which is what was
# here, had every one of the fourteen sense lines crossing every other.

ADC_COLUMNS = (-38.0, -31.0)     # the series resistor of each column's cells
ADC_SHUNT_OFFSET = 2.2

# One connector pin can feed more than one cell: the DC link's does, once for
# the measurement and once for the faster tap the over-voltage comparator
# watches. The second cell goes half a row from the first, on the side away
# from the other column, and is fed from the first cell's own input pad - which
# is the node it is meant to be tapping.

# The connector's two pin columns are 2.54 mm apart along the row and their
# cells would be level with each other. Half a row of stagger puts each east
# column cell in the gap between two west column cells, which is the gap the
# line reaching it has to pass through.
ADC_STAGGER = 1.27

HEADER_PITCH = 2.54


def _adc_pins() -> dict[str, int]:
    """Which connector pin each input network belongs to."""
    out = {}
    for net, nodes in DESIGN["nets"].items():
        pins = [int(pad) for address, pad in nodes if address == "header.analog"]
        if not pins:
            continue
        for address, _ in nodes:
            if address.startswith("adc.") and address.endswith(".series"):
                out[address[: -len(".series")]] = pins[0]
    return out


def _adc_inputs() -> None:
    spilled: dict[int, int] = {}
    for cell, pin in sorted(_adc_pins().items()):
        row, column = divmod(pin - 1, 2)
        seen = spilled.get(pin, 0)
        spilled[pin] = seen + 1
        x = ADC_COLUMNS[column]
        y = round(ANALOG_HEADER[1] + HEADER_PITCH * row + ADC_STAGGER * column
                  + ADC_STAGGER * seen * (1 if column == 0 else -1), 4)
        PLACEMENT[f"{cell}.series"] = (x, y, 0)
        PLACEMENT[f"{cell}.shunt"] = (round(x + ADC_SHUNT_OFFSET, 4), y, 0)
        LABELS[f"{cell}.series"] = (0.0, -1.3)
        LABELS[f"{cell}.shunt"] = (0.0, -1.3)

    # The spare DAC output's own network, beside the DAC it comes from.
    # Beside the pin that drives it, on the strip west of the package, rather
    # than beside the DAC it has nothing to do with. Its pin is on the south
    # edge in the middle of the analog fan's own escapes, and from there this
    # is the only direction that is not through them.
    PLACEMENT["adc.dac_test.series"] = (-13.0, 9.6, 0)
    PLACEMENT["tp_dac_test"] = (-15.5, 11.3)
    LABELS["adc.dac_test.series"] = (0.0, -1.3)
    LABELS["tp_dac_test"] = (0.0, -2.0)


# The connector's two pin columns are 2.54 mm apart and so are its rows, so a
# line leaving the west column runs straight into the east column's pin. It
# steps half a row north to get past it and back again; the east column's own
# lines step half a row south instead, into the gap the staggered cells leave.
SENSE_DODGE = 1.15
SENSE_WEST = (-42.8, -40.0, -38.8)      # step out, run along, step back
SENSE_EAST = (-40.4, -39.6)             # step out, and rise into the gap

# The four sense lines a comparator watches, and how each of them reaches the
# row. They go north on the back layer: the front of this channel is where they
# come back down, and a line that rose on the front would cross the ones that
# rose before it. The only other thing on the back here is the three threshold
# buses, and those are north of where these surface.
#
# Each entry is the net, the lane it surfaces on, the back-layer way there from
# its connector pin, and - where the column it would otherwise pick is taken -
# the x it rises on. The lanes go south as their taps go east, and each one
# ends before the next one's first tap, so no lane crosses another's riser.
SENSE_LANES = (
    ("FAST1_SENSE", -30.0, ((-44.0, -24.5),), None),
    ("FAST2_SENSE", -29.2, ((-41.46, -23.7),), None),
    # Two of the three rise west of the column they would have chosen, to
    # leave the Ethernet a set of columns between them and the threshold
    # buses: this strip is the only way from the package's west side to the
    # lane north of the input bank.
    ("FAST3_SENSE", -28.4, ((-39.0, -19.46), (-39.0, -22.9)), -22.2),
    # The DC link's line arrives from the east instead. Its tap is the last on
    # the row and its own threshold bus surfaces where it would have risen, so
    # it runs along the empty back layer under the input networks and comes up
    # beyond it - but only just beyond: it used to carry on to x -5.2, a
    # detour east that it then walked back on the front, and that back-layer
    # line was a wall across the whole north-west. It now rises as soon as it
    # is clear of the threshold buses, which is what leaves the Ethernet a
    # channel down the west side of the package.
    ("FAST4_SENSE", -27.6, ((-44.0, -15.65), (-21.6, -15.65)), -21.6),
)


def _sense_route(net: str) -> list[str]:
    """The comparator input pads on a sense net, west to east."""
    return sorted(
        (f"{address}:{pad}" for address, pad in DESIGN["nets"][net]
         if address.startswith("trip.")),
        key=lambda ref: _point(ref)[0],
    )


def _sense_routes() -> None:
    """
    The connector's analog inputs: to their cells, and to the comparators.

    Every line is a run east at its pin's own height, which is what placing one
    cell per pin bought. The two that are not - the dodge past the other
    column's pin, and the half-row rise into the gap between two cells - are
    both a millimetre long and happen before the line has left the connector.
    """
    pins = _adc_pins()
    order: dict[int, list[str]] = {}
    for cell, pin in sorted(pins.items()):
        order.setdefault(pin, []).append(cell)

    for pin, cells in sorted(order.items()):
        net = NET_AT[("header.analog", str(pin))]
        width = _width_for(net, SIGNAL)
        row, column = divmod(pin - 1, 2)
        y = round(ANALOG_HEADER[1] + HEADER_PITCH * row, 4)
        if column == 0:
            legs = [(SENSE_WEST[0], round(y - SENSE_DODGE, 4)),
                    (SENSE_WEST[1], round(y - SENSE_DODGE, 4)),
                    (SENSE_WEST[2], y)]
        else:
            legs = [(SENSE_EAST[0], y),
                    (SENSE_EAST[1], round(y + ADC_STAGGER, 4))]
        ROUTES.append((net, width, F,
                       [f"header.analog:{pin}", *legs, f"{cells[0]}.series:1"]))
        # A pin that feeds a second cell feeds it from the first one's input
        # pad, which is the node the second one is there to tap.
        for extra in cells[1:]:
            ROUTES.append((net, width, F,
                           [f"{cells[0]}.series:1", f"{extra}.series:1"]))

    for net, lane, waypoints, chosen in SENSE_LANES:
        width = _width_for(net, SIGNAL)
        pads = _sense_route(net)
        taps = [_point(ref)[0] for ref in pads]
        entry = waypoints[-1]
        riser = chosen if chosen is not None else (
            entry[0] if entry[0] > taps[-1] else taps[0])
        pin = next(pad for address, pad in DESIGN["nets"][net]
                   if address == "header.analog")
        back = [f"header.analog:{pin}", *waypoints,
                (riser, entry[1]), (riser, lane)]
        def along(ref: str, x: float) -> list:
            corner = [] if abs(x - riser) < 1e-6 else [(x, lane)]
            return [(riser, lane), *corner, ref]

        path(net, width, [(B, back), (F, along(pads[0], taps[0]))])
        for ref, x in zip(pads[1:], taps[1:]):
            ROUTES.append((net, width, F, along(ref, x)))


# The one wire the whole safety chain hangs off, along the top of the board
# where the only thing in its way is the RS-485 connector - and it passes north
# of that too, rather than crossing the pair on its way to it.
TRIP_BUS, TRIP_BUS_EAST = -49.5, 20.5

# From the pull-up to the latch is the length of the board, and the front of
# that column belongs to the package's own escapes. It goes on the back.
TRIP_LATCH_LANE = 31.9


def _trip_bus() -> None:
    """
    Seven comparator outputs, two gate-driver faults and reset, on one wire.

    The diodes are what puts them there: each pair's common cathode faces north
    and drops onto a lane that runs the length of the row, so no output has to
    reach past another one. The lane carries on east to the two diodes that
    also set the latch, and the pull-up that holds it clear when none of them
    do, and then to the latch itself.
    """
    net = "TRIP_SET_N"
    width = _width_for(net, SIGNAL)
    cathodes = sorted((f"trip.d_outputs{index + 1}:3" for index in range(4)),
                      key=lambda ref: _point(ref)[0])
    west = _point(cathodes[0])[0]
    ROUTES.append((net, width, F, [
        (west, TRIP_BUS), (TRIP_BUS_EAST, TRIP_BUS),
        (TRIP_BUS_EAST, -33.0), "safety.d_reset:3",
    ]))
    for ref in cathodes:
        ROUTES.append((net, width, F, [(_point(ref)[0], TRIP_BUS), ref]))
    for first, second in (("safety.d_reset:3", "safety.d_faults:3"),
                          ("safety.d_faults:3", "safety.r_trip_pullup:2")):
        ROUTES.append((net, width, F, [first, second]))

    # And up the east side of the board to the latch, on the back: the front
    # of that column is the package's own escapes for its whole length.
    drop, rise = (19.75, -25.4), (29.6, 8.75)
    path(net, width, [
        (F, ["safety.r_trip_pullup:2", drop]),
        (B, [drop, (drop[0], -26.0), (TRIP_LATCH_LANE, -26.0)]),
        # The ten static lanes cross this column on the back on their way to
        # the resistors. It steps onto the front for their whole depth rather
        # than ten of them stepping over it.
        (F, [(TRIP_LATCH_LANE, -26.0), (TRIP_LATCH_LANE, -2.0)]),
        (B, [(TRIP_LATCH_LANE, -2.0), (TRIP_LATCH_LANE, rise[1]), rise]),
        (F, [rise, "safety.latch:7"]),
    ])


# --- the input networks to the package -----------------------------------------
#
# Fifteen filtered analog lines from the cells beside the connector to the pins
# that sample them, and the order at the two ends has nothing in common: the
# cells are in connector order and the pins are in whatever order the silicon
# put them. A fan between two arbitrary orders crosses itself, and no clever
# lane assignment fixes that.
#
# So it is routed the way an arbitrary permutation has to be: every east-west
# run on the back layer, every north-south run on the front, and a via at each
# corner. Nothing crosses anything, by construction rather than by argument.
# The strip between the crystals and the input networks is empty on both
# layers, which is where the north-south runs go.
#
# Four vias a net is a lot of holes. These are the filtered side of a 1.5 MHz
# RC into an ADC pin, so the inductance does not matter; the alternative is
# thirty crossings, and each of those costs two vias anyway.

# Where each analog pin leaves the package, as (net, via). The vias step away
# from the package as well as along it, because three pins at 0.5 mm pitch
# cannot each have a via: the diagonal that gets there is what buys the room.
# Where each analog pin leaves the package, the way out to that point, and
# where beside its cell it comes back up.
#
# The nine on the west edge get a diagonal apiece: three pins at 0.5 mm pitch
# cannot each have a via below them, and the length of the diagonal that buys
# the room depends on which neighbour is in the way - a pad with no net on one
# side, a decoupling capacitor on the other. The six on the south edge leave
# through the gap between the pads and the decoupling row, which is a
# millimetre and a half wide and holds all six of them.
#
# The third figure is where the cell is approached from, relative to its
# capacitor's input pad. Half a row north is the gap the staggered columns
# leave; where that gap is already a sense line's lane, or where the cell has
# a neighbour on both sides, it says something else.
#
# The order is the order the lanes run in, west to east, which is the order of
# the approaches, southernmost first. Nothing depends on it - the fan crosses nothing whatever the
# order - but it keeps each lane's two vias away from its neighbours'.
ADC_ESCAPES = (
    ("BOARD_ID2", ((-14.1, -2.05),), (0.0, 1.0)),
    ("BOARD_ID1", ((-14.1, 1.75),), (0.0, -1.27)),
    ("SLOW3", ((-12.4, 3.75),), (0.0, -1.85)),
    ("SLOW4", ((-9.6, 11.7),), (-0.6375, -0.55)),
    ("SLOW2", ((-13.0, -2.75),), (0.0, -1.27)),
    ("SLOW1", ((-14.9, -1.45),), (0.0, -0.64)),
    ("FAST8", ((-11.9, 0.25),), (0.0, 0.75)),
    ("FAST7", ((-13.0, 0.8),), (0.0, -0.75)),
    ("FAST5", ((-3.75, 13.5),), (-0.6375, 0.65)),
    ("FAST6", ((-11.9, 5.1),), (0.0, -1.27)),
    ("COMP_FAST4", ((-3.25, 14.0), (-4.5, 15.9)), (0.0, -0.75)),
    ("FAST4", ((-6.25, 13.0),), (-0.6375, 0.65)),
    ("FAST3", ((-12.9, 4.3),), (0.0, -1.27)),
    ("FAST2", ((-0.75, 11.7), (0.3, 12.4), (0.3, 16.5)), (0.0, -1.27)),
    ("FAST1", ((-2.75, 15.3),), (-0.6375, 0.65)),
)

# The strip the north-south runs use, and how far apart they sit in it. It is
# bounded by the 8 MHz crystal's capacitors on one side and the input networks
# on the other.
ADC_LANE, ADC_LANE_PITCH = -19.7, -0.5


def _adc_cell_of(net: str) -> str:
    """The input network whose filtered side is this net."""
    return next(
        address[: -len(".shunt")]
        for address, _ in DESIGN["nets"][net]
        if address.endswith(".shunt")
    )


def _adc_to_package() -> None:
    for index, (net, leaving, offset) in enumerate(ADC_ESCAPES):
        escape = leaving[-1]
        width = _width_for(net, SIGNAL)
        cell = _adc_cell_of(net)
        pin = next(pad for address, pad in DESIGN["nets"][net] if address == MCU)
        shunt = _point(f"{cell}.shunt:1")
        approach = (round(shunt[0] + offset[0], 4), round(shunt[1] + offset[1], 4))
        lane = round(ADC_LANE + ADC_LANE_PITCH * index, 4)

        # The cell's own two pads, which are a millimetre apart.
        ROUTES.append((net, width, F, [f"{cell}.series:2", f"{cell}.shunt:1"]))
        path(net, width, [
            (F, [f"{MCU}:{pin}", *leaving]),
            (B, [escape, (lane, escape[1])]),
            (F, [(lane, escape[1]), (lane, approach[1])]),
            (B, [(lane, approach[1]), approach]),
            (F, [approach, f"{cell}.shunt:1"]),
        ])


# --- the PWM lines to the buffers -----------------------------------------------
#
# TIM1's seven leave the package's south edge in exactly the order the buffer
# wants them, because the pin map put them on one port in one order and the
# buffer's channels are in that order too. So each one is a drop to its own
# channel's height and a run east, and nothing crosses anything.
#
# TIM8's are not so lucky: the three CHN pins that had to move off TIM1's port
# are on a different edge, and one of them is on the far side of the south
# edge entirely. Each of those gets a turning column, ordered so that a line
# turning further north turns further east.
# TIM8's seven are not so lucky. The three CHN pins that had to move off TIM1's
# port are on the east edge, behind the two indicator LEDs, and one more is on
# the far west of the south edge. They go behind everything on the back layer:
# escape via, a lane east, a turn south, and back up beside the buffer. The
# turns are ordered so a line ending further south turns further west, which is
# what keeps the six of them from crossing.
#
# Each entry is the net, the via it drops through, the column it turns in, and
# the via it comes back up on.
PWM_BEHIND = (
    ("PWM2_C_LOW", (16.5, 7.25), 18.0, (20.0, 3.175)),
    ("PWM2_B_LOW", (17.5, 7.75), 19.0, (21.0, 3.825)),
    # Three of these four drop at eighteen millimetres and beyond rather than
    # just outside the package. They ran east on the back from wherever they
    # dropped, so it costs them nothing, and their four vias were what left
    # the band between here and the supply ring too shallow for the ten static
    # signals to leave the package through. The first one stays where it is:
    # its line runs behind the two indicator LEDs, and on the front it would
    # bridge the mask to their pads.
    ("PWM2_A_HIGH", (11.9, -2.75), 19.8, (23.0, 1.875)),
    ("PWM2_B_HIGH", (18.6, -3.25), 20.6, (24.0, 1.225)),
    ("PWM2_C_HIGH", (19.4, -3.75), 21.4, (23.0, 0.575)),
    ("PWM2_CH4", (20.2, -4.25), 22.2, (24.0, -0.075)),
)

PWM_STRAY, PWM_STRAY_TURN, PWM_STRAY_EXIT = 14.2, 24.0, 24.0


def _pwm_inputs() -> None:
    behind = {entry[0]: entry[1:] for entry in PWM_BEHIND}
    # Every net with a pin at one end and a buffer input at the other. Tested
    # that way round because the names do not divide cleanly: each timer's
    # fourth channel has one word where the others have two, and a filter
    # written on the names left both of them unrouted.
    for net in sorted(n for n in DESIGN["nets"] if n.startswith(("PWM1_", "PWM2_"))):
        nodes = {address: pad for address, pad in DESIGN["nets"][net]}
        buffered = next((a for a in nodes if a.startswith("safety.buffer")), None)
        if buffered is None or MCU not in nodes:
            continue
        source, target = f"{MCU}:{nodes[MCU]}", f"{buffered}:{nodes[buffered]}"
        width = _width_for(net, SIGNAL)
        here, there = _point(source), _point(target)
        if net in behind:
            drop, turn, rise = behind[net]
            path(net, width, [
                (F, [source, drop]),
                (B, [drop, (turn, drop[1]), (turn, rise[1]), rise]),
                (F, [rise, target]),
            ])
        elif here[0] < 0.0:
            rise = (PWM_STRAY_EXIT, there[1])
            path(net, width, [
                (F, [source, (here[0], PWM_STRAY)]),
                (B, [(here[0], PWM_STRAY), (PWM_STRAY_TURN, PWM_STRAY),
                     (PWM_STRAY_TURN, there[1]), rise]),
                (F, [rise, target]),
            ])
        else:
            ROUTES.append((net, width, F, [source, (here[0], there[1]), target]))


# --- the latch's two ends -------------------------------------------------------
#
# Both buffers' second enable comes from the latch, and both of those pins are
# on the far side of their package from it. Everything east of the buffers is
# the output fan-out, on the front; this goes underneath it.
TRIPPED_LANE = 32.6


def _tripped() -> None:
    """The latch's output to the enable pin of both buffers."""
    net = "TRIPPED"
    width = _width_for(net, SIGNAL)
    ends = sorted((f"safety.buffer{n}:19" for n in (1, 2)),
                  key=lambda ref: -_point(ref)[1])
    rises = [(TRIPPED_LANE, round(_point(ref)[1], 4)) for ref in ends]
    tap = (29.8, 10.6)
    path(net, width, [
        (F, [ends[0], rises[0]]),
        (B, [rises[0], rises[1]]),
        (F, [rises[1], ends[1]]),
    ])
    path(net, width, [
        (F, ["safety.latch:5", tap]),
        (B, [tap, (TRIPPED_LANE, tap[1])]),
    ])


# --- the safety signals the package drives ---------------------------------------
#
# Four pins on the package's east edge, half a millimetre apart, whose ends are
# the latch and both buffers. All four drop to the back layer between the
# indicator LEDs' resistors, run south in their own column past the PWM fan,
# and go east in the strip between the package and the latch.
#
# Each entry is the net, the via it drops through, the column it runs south in,
# and the lane it runs east on. Columns on the back, lanes on the front, so a
# lane never meets a column - the same rule the analog fan uses, for the same
# reason. A net whose lane is further south gets a column further west, which
# is what keeps each lane clear of the other columns.
# One PWM line crosses this strip on the back, and there is no lane south of it
# that still reaches the latch. Anything that has to get past steps over on the
# front for a millimetre. The signal whose lane is south of it comes out of
# that step already on the front and simply carries on, which saves it a via
# and, more to the point, saves the via from standing in another net's way.
SAFETY_STEP = (13.7, 14.7)
SAFETY_STEP_END = 15.5



SAFETY_DROPS = (
    ("TRIP_CLEAR_N", (11.9, 0.25), 11.9, SAFETY_STEP_END),
    ("PWM_ENABLE_N", (12.7, 1.1), 12.7, 12.4),
    ("TRIP_N", (13.5, 2.2), 13.5, 10.4),
)


def _safety_column(net, width, column, top, bottom) -> None:
    """A back-layer run down the strip, stepping over the PWM lane on the way."""
    first, last = min(top, bottom), max(top, bottom)
    if not first < SAFETY_STEP[0] < last:
        ROUTES.append((net, width, B, [(column, top), (column, bottom)]))
        return
    path(net, width, [
        (B, [(column, first), (column, SAFETY_STEP[0])]),
        (F, [(column, SAFETY_STEP[0]), (column, SAFETY_STEP[1])]),
        (B, [(column, SAFETY_STEP[1]), (column, last)]),
    ])


def _safety_signals() -> None:
    """The latch's inputs and the buffers' first enable, from the package."""
    for net, drop, column, lane in SAFETY_DROPS:
        width = _width_for(net, SIGNAL)
        pin = min((pad for address, pad in DESIGN["nets"][net] if address == MCU),
                  key=lambda pad: math.dist(_point(f"{MCU}:{pad}"), drop))
        ROUTES.append((net, width, F, [f"{MCU}:{pin}", drop]))
        VIAS.append((None, drop, net, *VIA))
        if lane == SAFETY_STEP_END:
            path(net, width, [
                (B, [drop, (column, SAFETY_STEP[0])]),
                (F, [(column, SAFETY_STEP[0]), (column, lane)]),
            ])
        else:
            _safety_column(net, width, column, drop[1], lane)
            VIAS.append((None, (column, lane), net, *VIA))

    # The latch's set input. Both timers' break inputs are on it; the second
    # comes off the south edge, round the bottom of the PWM fan and back up the
    # same column, which is why this column is the shortest of the three.
    width = _width_for("TRIP_N", SIGNAL)
    ROUTES.append(("TRIP_N", width, F,
                   [(13.5, 10.4), (23.2, 10.4), (23.2, 9.25), "safety.latch:3"]))
    second = min((pad for address, pad in DESIGN["nets"]["TRIP_N"] if address == MCU),
                 key=lambda pad: -_point(f"{MCU}:{pad}")[1])
    # Straight out of the pad row before it turns: the pins either side of it
    # are the core's own capacitors, and their tracks leave along this line.
    escape = (round(_point(f"{MCU}:{second}")[0], 4), 15.4)
    path("TRIP_N", width, [
        (F, [f"{MCU}:{second}", escape]),
        (B, [escape, (13.5, 15.4)]),
    ])
    _safety_column("TRIP_N", width, 13.5, 15.4, 10.4)

    # The clear input is on the far side of the latch, so this one carries on
    # past it on the back and comes back to the pad from the east.
    width = _width_for("TRIP_CLEAR_N", SIGNAL)
    over, clear = (23.0, SAFETY_STEP_END), (29.0, 9.25)
    path("TRIP_CLEAR_N", width, [
        (F, [(11.9, SAFETY_STEP_END), over]),
        (B, [over, (clear[0], over[1]), clear]),
        (F, [clear, "safety.latch:6"]),
    ])

    # The enable reaches one buffer along its lane and the other underneath the
    # fan, on the one line east of the indicators that nothing else uses.
    width = _width_for("PWM_ENABLE_N", SIGNAL)
    ROUTES.append(("PWM_ENABLE_N", width, F,
                   [(12.7, 12.4), (22.6, 12.4), "safety.buffer1:1"]))
    under = (14.5, -0.65)
    path("PWM_ENABLE_N", width, [
        (B, [(12.7, 1.1), under]),
        (F, [under, (20.0, -0.65), "safety.buffer2:1"]),
    ])

    # And each pull-up hangs off its own lane by the length of one pad.
    for address, lane in (("safety.r_clear_pullup", SAFETY_STEP_END),
                          ("safety.r_enable_pullup", 12.4)):
        net = NET_AT[(address, "2")]
        pad = _point(f"{address}:2")
        ROUTES.append((net, _width_for(net, SIGNAL), F, [(pad[0], lane), f"{address}:2"]))


# The spare DAC output and the test network beside it. Both go round rather
# than through: the test resistor's output pad faces the package and its test
# pad is on the other side of the resistor, and the DAC's spare output is on
# the far side of the DAC from the pad that brings it out.
def _dac_test_points() -> None:
    width = _width_for("DAC_TEST_OUT", SIGNAL)
    ROUTES.append(("DAC_TEST_OUT", width, F, [
        "adc.dac_test.series:2", (-12.0, 10.6), (-14.3, 11.3), "tp_dac_test:1",
    ]))
    ROUTES.append(("DAC_SPARE", _width_for("DAC_SPARE", SIGNAL), F, [
        "tp_dac_spare:1", (-12.2, -19.6), (-12.2, -23.0),
        (-15.5, -23.0), (-15.5, -24.5), "trip.dac:9",
    ]))


# --- the field buses ---------------------------------------------------------
#
# CAN and RS-485 side by side above the package, each with its transceiver, its
# termination on a jumper, and three pins out to the field.

def _field_buses() -> None:
    """
    CAN and RS-485, one above the other, each laid out so its pair can reach
    the connector without crossing itself.

    The bus pins come out of the package with the low half above the high half,
    and the connector is turned so that its high pin is the outer one. The high
    half then runs out past the low half's lane and up its own, and the two
    never meet - which is the only arrangement of these two parts that avoids a
    crossing, because two tracks on one layer cannot swap sides.

    The termination stacks between the two lanes, which are one connector pitch
    apart: the jumper taps the high half where it passes, the chain runs down,
    and its far end meets the low half.
    """
    for prefix, top in (("can", -22.0), ("rs485", -40.0)):
        PLACEMENT[f"{prefix}.transceiver"] = (2.0, top, 0)
        LABELS[f"{prefix}.transceiver"] = (0.0, -3.4)
        # Turned to match the order the bus pins come out in: the half that
        # leaves the package higher up takes the inner lane, and pin 1 of the
        # connector has to be on that lane's side.
        above = _bus_high_is_above(prefix)
        PLACEMENT[f"{prefix}.header"] = (
            INNER_LANE if above else OUTER_LANE, BUS_HEADER_Y[prefix],
            90 if above else 270)
        LABELS[f"{prefix}.header"] = (2.6, 2.6)

    PLACEMENT["can.decoupling_vcc"] = (-3.5, -20.5, 0)
    PLACEMENT["can.decoupling_vio"] = (-3.5, -23.5, 0)
    PLACEMENT["rs485.decoupling"] = (-3.5, -41.5, 0)

    # Each chain stacked between its own two lanes, which are a connector pitch
    # apart, so the parts stand on end to fit.
    for prefix, first, names in (
        ("can", -24.0, ("termination_jumper", "termination_upper", "termination_lower")),
        ("rs485", -41.5, ("termination_jumper", "termination")),
    ):
        for index, name in enumerate(names):
            PLACEMENT[f"{prefix}.{name}"] = (CHAIN_X,
                                             round(first - index * 3.5, 4), 90)
            LABELS[f"{prefix}.{name}"] = (-1.6, 0.0)
    PLACEMENT["can.termination_split"] = (12.5, -29.25, 0)
    LABELS["can.termination_split"] = (0.0, -1.6)

    for address in ("can.decoupling_vcc", "can.decoupling_vio", "rs485.decoupling"):
        LABELS[address] = (0.0, -1.6)


# The two lanes each bus runs up, and the column its termination stands in
# between them.
# Each bus gets its own pair of lanes and its own connector, side by side, one
# connector pitch clear of the package's pin column - a lane laid over a row of
# pads leaves them nowhere to escape to - and clear of each other, because both
# connectors are through-hole and sit on every layer.
# The high half takes the inner lane and the low half the outer one, because
# the high pin comes out of the package above the low one and the connector is
# turned to match. Put them the other way round and the high half has to cross
# the low half's lane on its way out.
#
# Both buses use the same two lanes at different heights: one finishes at its
# connector before the other begins.
INNER_LANE, OUTER_LANE, CHAIN_X = 7.08, 9.62, 8.35
BUS_HEADER_Y = {"can": -34.0, "rs485": -48.0}


def _bus_high_is_above(prefix: str) -> bool:
    """Whether the bus's high half leaves the package above its low half."""
    high_pin, low_pin = ("7", "6") if prefix == "can" else ("6", "7")
    return (_point(f"{prefix}.transceiver:{high_pin}")[1]
            < _point(f"{prefix}.transceiver:{low_pin}")[1])


def _field_bus_routes() -> None:
    """
    Each bus from its transceiver to the three pins it leaves on.

    The low half turns up at the nearer lane and the high half runs out past it
    and up the further one. The high half's leg out is below the low half's, so
    it passes under where the low half has already turned.
    """
    for prefix, high, low, chain in (
        ("can", "CAN_H", "CAN_L",
         ("can.termination_jumper", "can.termination_upper", "can.termination_lower")),
        ("rs485", "RS485_A", "RS485_B",
         ("rs485.termination_jumper", "rs485.termination")),
    ):
        transceiver = f"{prefix}.transceiver"
        header = f"{prefix}.header"
        high_pin, low_pin = ("7", "6") if prefix == "can" else ("6", "7")
        width = _width_for(high, SIGNAL)
        jumper, *rest = chain
        top = _point(f"{header}:1")[1] + 1.5

        above = _bus_high_is_above(prefix)
        high_lane = INNER_LANE if above else OUTER_LANE
        low_lane = OUTER_LANE if above else INNER_LANE
        for net, pin, lane, pad in ((high, high_pin, high_lane, "1"),
                                    (low, low_pin, low_lane, "2")):
            y = _point(f"{transceiver}:{pin}")[1]
            ROUTES.append((net, width, F, [
                f"{transceiver}:{pin}", (lane, y), (lane, top), f"{header}:{pad}",
            ]))

        # The termination taps each lane where it passes.
        ROUTES.append((high, width, F, [
            (high_lane, _point(f"{jumper}:1")[1]), f"{jumper}:1"]))
        ROUTES.append((low, width, F, [
            f"{rest[-1]}:2", (low_lane, _point(f"{rest[-1]}:2")[1])]))
        links = [(f"{jumper}:2", f"{rest[0]}:1")]
        links += [(f"{a}:2", f"{b}:1") for a, b in zip(rest, rest[1:])]
        for one, other in links:
            net = NET_AT.get(tuple(one.split(":")))
            ROUTES.append((net, _width_for(net, SIGNAL), F, [one, other]))

    # The split termination's midpoint capacitor sits outside both lanes, so
    # its one connection goes under the high lane rather than through it.
    mid = "CAN_TERM_MID"
    path(mid, _width_for(mid, SIGNAL), [
        # Taken from the gap between the two halves, not from a pad: the via
        # has to land on copper the chain leaves free.
        (F, ["can.termination_upper:2", (CHAIN_X, -29.25)]),
        (B, [(CHAIN_X, -29.25), (11.5, -29.25)]),
        (F, [(11.5, -29.25), "can.termination_split:1"]),
    ])


# The six field-bus signals, from the package's north edge to the two
# transceivers sitting above it.
#
# The CAN pair goes over the top of its transceiver and down its west side,
# where its receive and transmit pins are. The RS-485 trio has the CAN block in
# the way, so it goes under it on the back layer and comes up beyond.
#
# Each entry is the net, the pad it lands on, and - for the three that go
# under - the via they drop through, the y they come back up on, and the column
# they turn down. Those three are ordered so that a signal landing further
# north turns further west, which is what keeps the three from crossing.
CAN_SIGNALS = (
    ("CAN_RX", "can.transceiver:4", ((6.25, -18.0), (-1.8, -18.0), (-1.8, -20.09))),
    ("CAN_TX", "can.transceiver:1", ((5.75, -17.4), (-2.4, -17.4), (-2.4, -23.91))),
)

# The other four go under the CAN block on the back. Each drops through a via
# north of the decoupling row, runs west on its own line, turns south in the
# corridor between the transceivers' west pads and their capacitors, and comes
# up beside the pin it lands on. A signal landing further north turns further
# east, which is what keeps the four columns and four legs apart.
CAN_UNDER = (
    ("CAN_STANDBY", "can.transceiver:8", (4.75, -14.8), -3.8, -24.8, (5.3, -24.8)),
    ("RS485_TX", "rs485.transceiver:4", (3.75, -13.4), -4.1, -38.09, (-1.6, -38.09)),
    ("RS485_DE", "rs485.transceiver:3", (4.25, -12.6), -4.4, -39.37, (-1.6, -39.37)),
    ("RS485_RX", "rs485.transceiver:1", (2.25, -11.8), -4.7, -41.91, (-1.6, -41.91)),
)


def _field_bus_mcu() -> None:
    for net, target, corners in CAN_SIGNALS:
        pin = next(pad for address, pad in DESIGN["nets"][net] if address == MCU)
        ROUTES.append((net, _width_for(net, SIGNAL), F,
                       [f"{MCU}:{pin}", *corners, target]))

    for net, target, drop, column, leg, rise in CAN_UNDER:
        width = _width_for(net, SIGNAL)
        pin = next(pad for address, pad in DESIGN["nets"][net] if address == MCU)
        path(net, width, [
            (F, [f"{MCU}:{pin}", drop]),
            (B, [drop, (column, drop[1]), (column, leg), rise]),
            (F, [rise, target]),
        ])


# --- USB ---------------------------------------------------------------------
#
# The board's first differential pair. Its width and gap are not written down:
# `pair_geometry` solves the stackup in BOARD for the width that makes 90 ohm
# at the gap chosen, so a change to the fab's build changes the trace rather
# than leaving a number behind that used to be right.

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
    # Swapped over: CC1 is the connector's eastern pin and CC2 its western,
    # so the resistors sit on the same sides their pins do and neither route
    # crosses the pair between them.
    # Each turned so its first pad faces the pin it serves: a pull-down
    # approached from the wrong side is reached across its own ground pad.
    PLACEMENT["usb.cc1_pulldown"] = (32.0, -30.5, 0)
    PLACEMENT["usb.cc2_pulldown"] = (24.0, -30.5, 180)
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
    for net, line, pad, clear, lane in (("USB_DP", west, "4", 26.8, -6.75),
                                        ("USB_DM", east, "6", 29.2, -6.25)):
        ROUTES.append((net, USB_WIDTH, F, [
            f"usb.protection:{pad}", (clear, -23.4), line[0]]))
        ROUTES.append((net, USB_WIDTH, F, list(line)))
        # And the last stretch to the package, which is not part of the
        # controlled length: the two pins sit where the debug escapes used to
        # be, and this is what it took to get that back.
        pin = next(p for a, p in DESIGN["nets"][net] if a == MCU)
        ROUTES.append((net, USB_WIDTH, F,
                       [line[-1], (14.5, lane), f"{MCU}:{pin}"]))

    _usb_bus_voltage()
    _usb_fanout()


# The bus voltage goes round the outside of everything: north of the pair the
# whole way, down the east of the buffers, and back underneath the pair to the
# array's middle pad, which is the only pad on that side the pair does not
# fan out around.
USB_VBUS_EAST, USB_VBUS_LANE, USB_VBUS_RISE = 30.3, -25.4, (28.0, -25.4)


def _usb_bus_voltage() -> None:
    net = "USB_VBUS"
    width = _width_for(net, SIGNAL)
    pin = next(p for a, p in DESIGN["nets"][net] if a == MCU)
    array = next(f"{a}:{p}" for a, p in DESIGN["nets"][net] if a == "usb.protection")
    path(net, width, [
        (F, [f"{MCU}:{pin}", (USB_VBUS_EAST, -5.25), (USB_VBUS_EAST, USB_VBUS_LANE)]),
        (B, [(USB_VBUS_EAST, USB_VBUS_LANE), USB_VBUS_RISE]),
        (F, [USB_VBUS_RISE, array]),
    ])
    # The receptacle carries it on four pads, two at each end of the row, with
    # the pair's own fan-out filling the space between them. Both ends step
    # away from the row before they turn - the pads either side of each are
    # ground - and go under the connector's own fan-out on the back. Each steps
    # back onto the front for a millimetre to get past the trip bus, which runs
    # across this corner on the back on its way to the latch.
    for pad, step, column in (("A4", (30.45, -31.6), 30.3),
                              ("A9", (25.55, -32.4), 24.0)):
        here = (USB_VBUS_EAST, USB_VBUS_LANE) if pad == "A4" else USB_VBUS_RISE
        path(net, width, [
            (F, [f"usb.receptacle:{pad}", step]),
            (B, [step, (column, step[1]), (column, -29.5)]),
            # On the front for the whole depth of the static lanes and the
            # trip bus, which all cross this corner on the back.
            (F, [(column, -29.5), (column, here[1])]),
            (B, [(column, here[1]), here]),
        ])


# --- Ethernet ----------------------------------------------------------------
#
# The PHY and its clock, in the corner left of the threshold DAC. The jack is
# not here: see cpu1.py's ethernet(), and M7d.

def _usb_fanout() -> None:
    """
    The connector's own pins, joined up.

    A Type-C receptacle carries each of D+ and D- on both of its rows, which is
    what makes the plug reversible and what makes the fan-out awkward: at the
    pads the two nets interleave - B6, A7, A6, B7 from west to east - so
    joining one net's two pads passes over the other's.

    Each net takes the pad on the side its own destination is on and reaches
    its second pad underneath. Two vias each, on a full-speed pair, in the
    three millimetres between the connector and the array.
    """
    for net, trunk, second, hop in (
        ("USB_DP_CABLE", "B6", "A6", -31.8),
        ("USB_DM_CABLE", "B7", "A7", -31.2),
    ):
        first = _point(f"usb.receptacle:{trunk}")
        pad = "3" if net.endswith("DP_CABLE") else "1"
        width = _width_for(net, SIGNAL)
        ROUTES.append((net, width, F, [
            f"usb.receptacle:{trunk}", (first[0], -30.2), f"usb.protection:{pad}",
        ]))
        other = _point(f"usb.receptacle:{second}")
        path(net, width, [
            (F, [f"usb.receptacle:{second}", (other[0], hop)]),
            (B, [(other[0], hop), (first[0], hop)]),
        ])
        VIAS.append((None, (first[0], hop), net, *VIA))

    for net, pad, resistor in (("USB_CC1", "A5", "usb.cc1_pulldown"),
                               ("USB_CC2", "B5", "usb.cc2_pulldown")):
        here = _point(f"usb.receptacle:{pad}")
        ROUTES.append((net, _width_for(net, SIGNAL), F, [
            f"usb.receptacle:{pad}", (here[0], -31.5), f"{resistor}:1",
        ]))


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
    PLACEMENT["eth.dec_vddio"] = (-55.5, -10.8, 90)
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
    # Turned so the signal pad faces east. Both nets arrive from that side -
    # they come the length of the board to get here - and with the resistor
    # the other way round the line has to pass over the 3V3 pad to reach the
    # one it wants.
    PLACEMENT["eth.r_mdio_pullup"] = (-16.0, 14.0, 0)
    PLACEMENT["eth.r_reset_pullup"] = (-51.0, -6.0, 180)

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
    _ethernet_north()
    _ethernet_west()
    _gate_enable()
    _feedback()


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

    # The PHY's own supply pin and the capacitor beside it reach the plane
    # through this one: there is no room for a via on either pad's own line,
    # and until the stitching generator learned that a route between two
    # surface pads reaches nothing, it never asked for one.
    VIAS.append(("eth.dec_vdd2a:1", (-57.6, -20.6), "3V3", *VIA, SUPPLY))

    # The supply pin in the middle of the receive pins has one row of its own
    # between the pad and the first RMII line, and the generator will not find
    # it by searching: it is narrower than the step the search takes.
    VIAS.append(("eth.phy:9", (-54.25, -14.25), "3V3", *VIA, SUPPLY))
    # The PHY's exposed pad is its only ground connection and its only path for
    # heat, and the stitching generator gives any pad exactly one via. Four,
    # spread across the 2.5 mm pad, are what TI draw on the comparable
    # PowerPAD - Microchip publish a pad size and no via pattern at all, which
    # is why that part is still on the board's review list. Naming all four
    # here also takes the generator's own via off its search, which is why the
    # last of them sits where it used to put it.
    for at in ((-54.85, -17.0), (-54.0, -17.85), (-54.0, -16.15), (-53.15, -17.0)):
        VIAS.append((None, at, "GND", *VIA, SUPPLY))

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


# The buffer enable, from the package's north edge to the safety chain in the
# south-east corner. Its pin is on the wrong edge for where it goes and the
# interior is held by the relay columns, so it does what the Ethernet transmit
# lines do: it goes inward, drops through inside the pin ring, and crosses the
# die on the back, where the only things in the way are the static band's own
# legs - and those stop short of this column.
GATE_ENABLE_PATH = (
    # It drops as far east as the relay columns let it: a layer change under
    # the middle of the package is ten millimetres from the nearest capacitor
    # that ties the planes, and the return current would have to go round.
    (F, [(1.75, -9.3), (1.75, -8.9), (3.2, -7.0), (3.2, -1.0)]),
    (B, [(3.2, -1.0), (1.5, 1.0), (1.5, 13.6)]),
    # Over the one back-layer line that crosses the whole width below the
    # package, the A-phase low-side gate drive. West of the PWM fan, because
    # that fan is eight columns at half a millimetre and leaves no gap a via
    # fits in: this is the last column before it starts.
    (F, [(1.5, 13.6), (1.5, 14.8)]),
    # South of every one of the eight lines the buffer's other inputs arrive
    # on - its enable is the pin below all of them, so the line that feeds it
    # never has to cross one.
    (B, [(1.5, 14.8), (1.5, 20.5), (24.3, 20.5)]),
    (F, [(24.3, 20.5), "safety.buffer1:9"]),
)


# --- motion feedback, from the package to the connector ----------------------
#
# Eight signals that were reserved and reached nothing. On four layers they
# could not be routed: the front was walled by the PWM fan and the back by the
# 5 V spine, and there were four places left to put a via where eight were
# needed. On six there is a whole signal layer between the ground plane and the
# supply islands, and each of these is one diagonal across it.
#
# They leave the package on three different edges and arrive in one fan, which
# only works because the connector's last six rows are in the order the pins
# come out: the two on the north edge, the five on the east edge from its top,
# then the one on the south. `HEADER_FEEDBACK` says so and this depends on it.
# The two on the north edge turn inward and drop inside the pin ring, where
# In3.Cu is empty - the supply vias are a ring, and the middle of a ring is a
# hole. The one on the south edge drops just past its own pads. The five on the
# east edge drop east of the debug and trip columns, each one further east than
# the last so their columns do not meet.
#
# Columns run west to east and rows run south to north, in the same order: a
# row can only cross a column that has already turned, so the westernmost
# column has to be the one that turns furthest south.
# net: (front-layer escape points, the point it reaches In3.Cu, any corners on
# In3.Cu before the column, the column it comes south on). The column is not
# always below the drop: the two on the north edge are half a millimetre apart
# and one has to get east of the other, which it does on In3.Cu where the
# other's escape is not.
#
# West of the package there is exactly one column clear of plane vias from the
# north edge to the connector - x -5.0, between the 5 V buck's ground vias at
# -5.6 and the comparator tap at -4.5 - so HALL_2 takes it. HALL_3 drops level
# with its own pin and misses everything north of it. HALL_1 comes south at
# -2.25, which is the MCU's own 3V3 via, so it steps clear of that via before
# it starts.
FEEDBACK_OUT = {
    "ENC_SERIAL_RX": ([(18.0, 8.75)], (18.0, 9.9), [], 18.0),
    "ENC_SERIAL_TX": ([], (16.6, 8.25), [], 16.6),
    "ENC_A": ([], (15.7, 4.75), [], 15.7),
    "ENC_B": ([(15.2, 4.25)], (15.2, 3.5), [], 15.2),
    "ENC_Z": ([], (14.7, 2.75), [], 14.7),
    "HALL_1": ([(-3.75, -9.6)], (-3.3, -8.8), [(-3.3, -7.6)], -2.25),
    "HALL_3": ([], (-4.25, 12.15), [], -3.25),
    "HALL_2": ([], (-4.25, -9.2), [], -5.0),
}

# The latch's decoupling sits where two of these diagonals pass, and the
# stitching generator searches outward from a pad rather than guessing: a via
# goes through In3.Cu like every other layer, so a track there is as much in
# its way as one on the front.
FEEDBACK_LATCH_VIAS = (("safety.latch.decoupling:1", (18.52, 8.3), "3V3"),
                       ("safety.latch.decoupling:2", (19.48, 8.3), "GND"),
                       ("safety.r_enable_pullup:1", (17.49, 11.9), "3V3"))


def _feedback() -> None:
    """The eight motion-feedback signals, across In3.Cu to the connector."""
    for pad, at, net in FEEDBACK_LATCH_VIAS:
        VIAS.append((pad, at, net, *VIA, SUPPLY))

    for net, (corners, drop, lead, column) in FEEDBACK_OUT.items():
        width = _width_for(net, SIGNAL)
        pad = f"{MCU}:{_mcu_pad(net)}"
        number = HEADER_PIN[net]
        pin = f"header.digital:{number}"
        row = _header_at(number)[1]
        last = lead[-1] if lead else drop
        step = [] if last[0] == column else [(column, round(last[1] + 0.8, 4))]
        if number % 2:
            finish = [*step, (column, row), pin]
        else:
            # The second row is behind the first, and the first is through-hole:
            # the only way past it is between two of its pins, as every other
            # second-row signal on this connector does.
            between = round(row + HEADER_PITCH / 2, 4)
            finish = [*step, (column, between),
                      (HEADER_ORIGIN[0] + HEADER_PITCH, between), pin]
        path(net, width, [
            (F, [pad, *corners, drop]),
            (MID, [drop, *lead, *finish]),
        ])


def _gate_enable() -> None:
    net = "GATE_ENABLE"
    pin = next(pad for address, pad in DESIGN["nets"][net] if address == MCU)
    first = (F, [f"{MCU}:{pin}", *GATE_ENABLE_PATH[0][1]])
    path(net, _width_for(net, SIGNAL), [first, *GATE_ENABLE_PATH[1:]])


# --- the RMII, from the north edge to the PHY --------------------------------
#
# Four of the ten leave the package's north edge in the middle of it, forty
# millimetres from the part they feed, and everything between is already full:
# the field bus owns the strip immediately west of them, the analog input bank
# owns the width of the board south of that, and the analog header is a wall of
# through-hole pins the whole height of it.
#
# What is empty is the back of the package itself. Three of them turn inward
# rather than outward, drop through inside the supply ring, and run west
# underneath the die - the only other thing on the back there is the static
# band, and that is further south. They pass the west pins, climb the strip
# between the crystal and the input bank's risers, and surface onto a lane
# north of the bank that runs clear to the far edge of the board.
#
# Each entry is the net, the y it drops on beside its pin, the y it runs west
# on once it is past the corner vias, the column it climbs, the lane it
# surfaces onto, the column it comes down at the far end, and the pad. The
# three are ordered so that the net landing furthest north is furthest west at
# every single turn - that ordering is the whole of why three lines can make
# eight turns each over forty millimetres without crossing.
ETH_STEP = (-3.5, -5.0)         # where the inner lanes step north, clear of
                                # the two supply vias beside pin 131
ETH_NORTH = (
    ("ETH_TX_EN", -6.8, -7.8, -21.05, -24.2, -45.9, "eth.phy:16"),
    ("ETH_TXD0", -7.3, -8.3, -20.4, -24.75, -46.2, "eth.phy:17"),
    ("ETH_TXD1", -7.8, -8.8, -19.75, -25.3, -46.5, "eth.phy:18"),
)

# The reset line does not go under the package. It is the one signal here that
# is not clocked, so the extra millimetres cost nothing, and it takes the
# channel west of the field bus that the DC-link sense line used to block -
# out past the boot pad, north beside the threshold DAC, and west on a lane of
# its own south of the other three.
ETH_RESET_OUT = -18.3           # the row it leaves on, under the boot test pad
ETH_RESET_DROP = -5.5           # the column it takes north
ETH_RESET_LANE = -27.0
ETH_RESET_WEST = -45.3
# Its pad is the one south of the other three on the PHY's east side, so it
# cannot come at it from the north the way they do: it goes on past, down to
# the pull-up, and reaches the pin from below. On the way it has to get to the
# far side of their lane, which is the one crossing on this whole block - two
# vias, taken where the lane is three parallel lines and nothing else.
ETH_RESET_UNDER = (-26.0, -23.6)
ETH_RESET_PULL = (-49.3, -6.0, "eth.r_reset_pullup:1")


def _ethernet_north() -> None:
    """The four RMII lines that leave the package pointing the wrong way."""
    def pin_of(net: str) -> str:
        return next(pad for address, pad in DESIGN["nets"][net] if address == MCU)

    for net, drop, lane, column, surface, west, target in ETH_NORTH:
        width = _width_for(net, SIGNAL)
        pin = pin_of(net)
        x = _point(f"{MCU}:{pin}")[0]
        path(net, width, [
            (F, [f"{MCU}:{pin}", (x, drop)]),
            (B, [(x, drop), (ETH_STEP[0], drop), (ETH_STEP[1], lane),
                 (column, lane), (column, surface)]),
            (F, [(column, surface), (west, surface),
                 (west, _point(target)[1]), target]),
        ])

    net = "ETH_PHY_RESET"
    width = _width_for(net, SIGNAL)
    pin = pin_of(net)
    x = _point(f"{MCU}:{pin}")[0]
    landing = _point("eth.phy:15")[1]
    over, under = ETH_RESET_UNDER
    turn, down, pull = ETH_RESET_PULL
    path(net, width, [
        (F, [f"{MCU}:{pin}", (x, ETH_RESET_OUT), (ETH_RESET_DROP, ETH_RESET_OUT)]),
        (B, [(ETH_RESET_DROP, ETH_RESET_OUT), (ETH_RESET_DROP, ETH_RESET_LANE)]),
        (F, [(ETH_RESET_DROP, ETH_RESET_LANE), (ETH_RESET_WEST, ETH_RESET_LANE),
             (ETH_RESET_WEST, over)]),
        (B, [(ETH_RESET_WEST, over), (ETH_RESET_WEST, under)]),
        (F, [(ETH_RESET_WEST, under), (ETH_RESET_WEST, down), pull]),
    ])
    ROUTES.append((net, width, F, [(turn, down), (turn, landing), "eth.phy:15"]))


# --- the RMII, from the west and south edges to the PHY -----------------------
#
# The other six leave the package pointing south and west, which is the right
# direction and the wrong side of the analog input bank: that bank and the
# analog header between them hold every column from x -21 to x -44 over the
# whole height of the board. The one way past is south of the header's last
# pin, in the strip between the button and the 5 V spine, and from there the
# west edge of the board is empty from the bottom corner up to the PHY.
#
# So all six go the long way round: out of the package, down to that strip,
# west along it on the back, north up the empty edge, and into the PHY from
# below - which is the side its receive pins face anyway.
#
# The six are ordered so that the one landing furthest west is southernmost in
# the strip, westmost in the climb, and first to leave it. One ordering applied
# at every turn is the whole of why six lines can cross a hundred and thirty
# millimetres of board without crossing each other.

# How each one gets clear of the package. The three on the south edge step
# across to a column the analog fan's own vias leave free and come straight
# down the front. The three on the west edge cannot: their row is walled in by
# the crystal's escape on one side and the input fan's vias on the other, so
# they drop to the back and cross under that field - MDC further in than the
# other two, because at its height the field reaches the package.
ETH_SOUTH = (
    # net, the column it steps to, the row it turns west on, where it drops
    ("ETH_RXD1", -5.05, 20.9, -9.5),
    ("ETH_RXD0", -5.35, 20.4, -10.3),
    ("ETH_CRS_DV", -5.65, 19.9, -11.1),
)
ETH_SOUTH_STEP = (11.2, 11.6)
ETH_WEST_IN = {
    # net: the point it drops on, and the back-layer way to its column
    "ETH_MDIO": ((-12.4, 8.75), ()),
    # The management clock's row is the one the input fan's own vias reach
    # into, so it crosses that field at the one height where the decoupling
    # column leaves half a millimetre either side, and steps north again
    # before the crystal capacitor's via.
    "ETH_MDC": ((-9.2, 4.25), ((-12.0, 6.25), (-14.6, 6.25), (-16.5, 7.0))),
    "ETH_REF_CLK": ((-11.7, 8.25), ()),
}
ETH_WEST_COLUMN = {"ETH_MDIO": -18.6, "ETH_MDC": -19.6, "ETH_REF_CLK": -20.2}
ETH_WEST_STRIP = {"ETH_MDIO": 19.4, "ETH_MDC": 18.9, "ETH_REF_CLK": 18.4}
# The management line's pull-up sits on the column it climbs out of the
# package on, forty millimetres from the PHY: a bus pull-up is a DC term and
# does not care, and every millimetre nearer the PHY is inside the fan.
ETH_MDIO_PULL = (14.0, "eth.r_mdio_pullup:1")

# The climb up the west edge, the row each one leaves it on, and the way from
# there to its pad. The four that land on the PHY's south edge turn north into
# it; the two on its east edge step north once more first, because their pins
# are north of the row the other four cross on.
ETH_CLIMB = (
    ("ETH_RXD1", -49.35, -12.5, (-55.25,)),
    ("ETH_RXD0", -49.0, -13.0, (-54.75,)),
    ("ETH_CRS_DV", -48.65, -13.5, (-53.25,)),
    ("ETH_MDIO", -48.3, -14.0, (-52.75,)),
    ("ETH_MDC", -47.95, -14.5, (-51.0, -15.75)),
    ("ETH_REF_CLK", -47.6, -15.0, (-50.5, -16.25)),
)
ETH_CLIMB_TARGET = {
    "ETH_RXD1": "eth.phy:7", "ETH_RXD0": "eth.phy:8",
    "ETH_CRS_DV": "eth.phy:11", "ETH_MDIO": "eth.phy:12",
    "ETH_MDC": "eth.phy:13", "ETH_REF_CLK": "eth.phy:14",
}
def _ethernet_west() -> None:
    """The six RMII lines that go the long way round the analog bank."""
    strip = dict(ETH_WEST_STRIP)
    lead: dict = {}
    for net, column, row, drop in ETH_SOUTH:
        pad = f"{MCU}:{_mcu_pad(net)}"
        x = _point(pad)[0]
        strip[net] = row
        lead[net] = [
            (F, [pad, (x, ETH_SOUTH_STEP[0]), (column, ETH_SOUTH_STEP[1]),
                 (column, row), (drop, row)]),
            (B, [(drop, row)]),
        ]
    for net, (drop, corners) in ETH_WEST_IN.items():
        pad = f"{MCU}:{_mcu_pad(net)}"
        column = ETH_WEST_COLUMN[net]
        lead[net] = [
            (F, [pad, drop]),
            (B, [drop, *corners, (column, drop[1] if not corners else corners[-1][1])]),
            (F, [(column, corners[-1][1] if corners else drop[1]),
                 (column, strip[net])]),
            (B, [(column, strip[net])]),
        ]

    for net, climb, row, rest in ETH_CLIMB:
        width = _width_for(net, SIGNAL)
        legs = lead[net]
        back = [*legs[-1][1], (climb, strip[net]), (climb, row), (rest[0], row)]
        if len(rest) > 1:
            back.append((rest[0], rest[1]))
        legs[-1] = (B, back)
        path(net, width, [*legs, (F, [back[-1], ETH_CLIMB_TARGET[net]])])

    row, pull = ETH_MDIO_PULL
    ROUTES.append(("ETH_MDIO", _width_for("ETH_MDIO", SIGNAL), F,
                   [(ETH_WEST_COLUMN["ETH_MDIO"], row), pull]))


def _mcu_pad(net: str) -> str:
    return next(pad for address, pad in DESIGN["nets"][net] if address == MCU)


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


def _holes_of(address: str) -> list:
    """The part's unplated holes, which carry no net and stop no less copper."""
    library, _, name = DESIGN["parts"][address]["footprint"].partition(":")
    return layout_lib.footprint_holes(HERE / "parts" / library / f"{name}.kicad_mod")


def _absolute(address: str, x: float, y: float) -> tuple[float, float]:
    """A point in a footprint's frame, placed on the board."""
    import math

    ox, oy, *rest = PLACEMENT[address]
    angle = math.radians(rest[0] if rest else 0.0)
    return (round(ox + x * math.cos(angle) + y * math.sin(angle), 4),
            round(oy - x * math.sin(angle) + y * math.cos(angle), 4))


def _already_reached() -> set[str]:
    """
    Every `address:pad` that already has a way to its plane.

    A pad is only reached if the route it sits on changes layer somewhere - a
    route joining two surface pads to each other leaves both of them exactly as
    far from the plane as they started. This counted them as done, and the
    PHY's supply pin and its bypass capacitor sat on the front connected to
    nothing at all while the board looked stitched.
    """
    parent: dict = {}

    def find(node):
        parent.setdefault(node, node)
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    def join(one, other):
        parent[find(one)] = find(other)

    def place(point):
        x, y = _point(point)
        return (round(x, 3), round(y, 3))

    for _, _, _, points in ROUTES:
        for after in points[1:]:
            join(place(points[0]), place(after))
    # A via with an anchor is joined to the pad it is drawn from, which is how
    # a supply pin's own ring via reaches the capacitor beside it.
    for entry in VIAS:
        if entry[0] is not None:
            join(place(entry[0]), place(entry[1]))
    grounded = {find(place(entry[1])) for entry in VIAS}
    out = {entry[0] for entry in VIAS if entry[0] is not None}
    for _, _, _, points in ROUTES:
        if find(place(points[0])) in grounded:
            out |= {p for p in points if isinstance(p, str)}
    return out


def _obstacles() -> tuple[list, list]:
    """
    Every pad on the board as an upright rectangle, and every via already there.

    Rectangles rather than circles: a via wants to pass *along* a row of
    0.6 by 1.3 mm pads, and measuring them by their diagonal says there is no
    room anywhere on an SOIC. Every part on this board is placed at a right
    angle, so the rectangles stay upright and the arithmetic stays simple.

    Unplated holes count too. They carry no net, so the pad parser leaves them
    out, and the stitching generator put a ground via half a millimetre from
    the USB receptacle's mounting post before this line existed.
    """
    pads = []
    for address in PLACEMENT:
        turned = round((PLACEMENT[address][2] if len(PLACEMENT[address]) > 2 else 0)) % 180 == 90
        copper = [pad for copies in _pads_of(address).values() for pad in copies]
        for pad in copper + _holes_of(address):
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


# Where a layer change had no crossing between the planes within reach. Each
# of these is a place `test_routing.py` named, not a place that looked empty.
STITCH_PLACES = (
    (50.0, -2.0), (50.0, 2.5), (50.0, 7.0),
    (50.0, 11.5), (50.0, 16.0), (50.0, 20.5),   # beyond the digital connector
    (31.5, -28.5),                    # the USB connector's fan-out
    (20.0, -16.0),                    # the debug escapes
    # Power good, below the 5 V island rather than inside it: a 3V3 via in
    # there reaches the gap the island leaves in the 3V3 pour, and this one
    # sat in exactly that gap until the stitching generator learned to say so.
    (0.0, 40.5),
    (12.0, -26.0),                    # the CAN termination's midpoint
    (-60.0, -6.0), (-60.0, -30.0),    # the Ethernet crystal and its pairs
    # The strip the analog fan crosses layers in. Thirty-six layer changes
    # happened here in one commit and there was not a tie within ten
    # millimetres of any of them; the check said so before the board did.
    (-22.3, 8.5), (-28.5, -9.0), (-33.0, -19.5),
    (-31.0, 12.5), (-33.0, -1.0), (-33.0, -7.5), (-33.0, -15.5),
    (38.0, -42.0),                    # the static signals' way under the header
    (39.5, -15.5),                    # and where that column moved to
)


def _stitching_capacitors() -> None:
    for index, at in enumerate(STITCH_PLACES, start=1):
        PLACEMENT[f"stitch.{index}"] = (*at, 0)
        LABELS[f"stitch.{index}"] = (0.0, -1.3)


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
_sense_routes()
_trip_bus()
_dac_test_points()
_adc_to_package()
_pwm_inputs()
_tripped()
_safety_signals()
_static_routes()
_static_mcu()
_last_few()
_dac_i2c()
_vref_out()
_across_the_package()
_field_buses()
_field_bus_routes()
_field_bus_mcu()
_usb()
_ethernet()
_stitching_capacitors()
_plane_stitches()
