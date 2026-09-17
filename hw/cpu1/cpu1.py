#!/usr/bin/env python3
"""
cpu1 — the STM32H743 control board, as a circuit.

Built one block at a time. What exists so far is the MCU itself: every pin in
`pinmap.py` on its own named net, every unused I/O pin marked `NC`, and the
supply pins on their rails. Everything a pin will eventually connect to lands in
a later block, and until it does that net is *pending*: `_MILESTONES` below
names the block that will connect each one.

`pinmap.py` is the single table of what each MCU pin does. This file wires the
MCU from it, so a pin cannot be used here that the pin map, and therefore the
firmware header and the silicon checks, do not know about.

Run it with `make -C hw build BOARD=cpu1`.
"""

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tools"))
sys.path.insert(1, str(HERE))

# skidl_design first: it tells SKiDL where KiCad's symbol libraries are.
from skidl_design import part, run  # noqa: E402
from skidl import POWER, Net  # noqa: E402

import mcu_pins  # noqa: E402
import parts  # noqa: E402
from stm32 import Silicon  # noqa: E402

PINMAP = mcu_pins.load("cpu1")

# What the board is designed to, rather than what any one part is.
INTENT: dict[str, tuple[float, float]] = {
    # The logic rail, 3.3 V ±5 %. The MCU's own limits are checked against it.
    "rail.3v3.voltage": (3.135, 3.465),
}

# Which later block connects the other end of each net. Matched in order; a net
# matching none of these is an error, so a new pin cannot slip in unexplained.
_MILESTONES = [
    (r"^(SW\w+|HSE_\w+|LSE_\w+|CONSOLE_\w+|LED_\w+|BUTTON|BOOT0|NRST|VDDA|VREF\+|VCAP\d)$",
     "M3: the MCU core - crystals, reset and boot, debug, VDDA and VREF+, LEDs"),
    (r"^(PWM\w*|TRIP\w*|FAULT\w*|GATE_ENABLE|RELAY_\w+|STO\d_\w+|ID_STRAP\d|DAC_S\w+|ENC_\w+|HALL_\d)$",
     "M5: the safety chain and the headers to the power board"),
    (r"^(IA|IB|IC|VDC|VA|VB|VC|AUX_FAST|SLOW\d|BOARD_ID\d|OV_COMP|DAC_TEST)$",
     "M6: the ADC input networks and comparator taps"),
    (r"^(USB_\w+|CAN_\w+|ETH_\w+|RS485_\w+)$",
     "M7: USB, CAN FD, Ethernet and RS-485"),
]


def waiting_for(net: str) -> str:
    for pattern, milestone in _MILESTONES:
        if re.match(pattern, net):
            return milestone
    raise ValueError(f"net {net} has no milestone that connects it")


def build() -> Net:
    silicon = Silicon(PINMAP.PART)
    mcu = part(parts.MCU_H743, "mcu", "U1")
    by_number = {pin.num: pin for pin in mcu.pins}

    def pins_named(name: str) -> list:
        return [by_number[n] for n in silicon.pins[name].positions]

    # The rails. Nothing on the board drives them yet - the input stage and
    # regulators are a later block - so say where they come from, as led12 does
    # for its terminal-fed nets.
    v3v3 = Net("3V3")
    gnd = Net("GND")
    v3v3.drive = POWER
    gnd.drive = POWER

    # VBAT and USB's supply straight from 3V3, and PDR_ON high to keep the
    # internal reset supervisor on: decisions, not placeholders.
    for name in ("VDD", "VBAT", "VDD33_USB", "PDR_ON"):
        for pin in pins_named(name):
            v3v3 += pin
    # One ground. Analog is kept apart by placement, not by splitting the plane.
    for name in ("VSS", "VSSA"):
        for pin in pins_named(name):
            gnd += pin

    # Each pin with its own name, waiting for what it will connect to.
    for name, net in (("VDDA", "VDDA"), ("VREF+", "VREF+"), ("BOOT0", "BOOT0"), ("NRST", "NRST")):
        Net(net).connect(*pins_named(name))
    for index, pin in enumerate(pins_named("VCAP"), start=1):
        Net(f"VCAP{index}").connect(pin)

    used = set()
    for p in PINMAP.PINS:
        Net(p.name).connect(by_number[silicon.position(p.pin)])
        used.add(p.pin)

    # Unused I/O is left unconnected on purpose, and said so. Firmware sets these
    # to analog mode, the lowest-leakage state.
    for name in sorted(set(silicon.io_pins) - used):
        for pin in pins_named(name):
            pin += NC  # noqa: F821 - SKiDL puts NC in builtins

    return v3v3


def pending(circuit_nets: list[str]) -> dict[str, str]:
    """Every net with only the MCU on it, and the block that will change that."""
    return {net: waiting_for(net) for net in circuit_nets if net not in ("3V3", "GND")}


if __name__ == "__main__":
    names = ["VDDA", "VREF+", "BOOT0", "NRST", "VCAP1", "VCAP2"] + [p.name for p in PINMAP.PINS]
    sys.exit(run(build, HERE, INTENT, pending(names)))
