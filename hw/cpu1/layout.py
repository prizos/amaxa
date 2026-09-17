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

from layout_lib import qfp_pins  # noqa: E402

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
    for number, address in served.items():
        pin = PINS[number]
        across = 0.0
        for neighbour in (str(int(number) - 1), str(int(number) + 1)):
            if neighbour in served:
                across += SPREAD if PINS[neighbour].centre_along < pin.centre_along else -SPREAD
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



_supply_vias()
_decoupling()
_analog_supply()
_crystals()
_placed()


def _pour_outline() -> list[tuple[float, float]]:
    width, height = BOARD["size"]
    x, y = width / 2 - BOARD["pour_inset"], height / 2 - BOARD["pour_inset"]
    return [(-x, -y), (x, -y), (x, y), (-x, y)]


# Ground on the first inner layer, 3V3 on the second. The 3V3 plane becomes
# supply islands once the power block exists; for now it is the only supply.
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
]
