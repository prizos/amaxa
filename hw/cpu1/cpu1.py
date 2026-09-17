#!/usr/bin/env python3
"""
cpu1 — the STM32H743 control board, as a circuit.

Built one block at a time. What exists so far:

- the MCU, with every pin in `pinmap.py` on its own named net and every unused
  I/O pin marked `NC`;
- its core: supply decoupling, the core regulator's capacitors, the filtered
  analog supply, both crystals, reset and boot, the Tag-Connect debug footprint,
  three LEDs, a button and test pads on the console.

Everything a pin will eventually connect to lands in a later block, and until it
does that net is *pending*: `_MILESTONES` below names the block that will
connect each one.

`pinmap.py` is the single table of what each MCU pin does. This file wires the
MCU from it, so a pin cannot be used here that the pin map, and therefore the
firmware header and the silicon checks, do not know about.

Component values come from ST's datasheet for the part (DocID030538 Rev 3) and
from each part's own listing; `parts/<LIB>/<LIB>.md` records which, and
`checks/test_core.py` re-derives what depends on them.

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
    # Pin and board capacitance each crystal's load capacitors sit alongside.
    # ST's datasheet offers 10 pF as a rough estimate; these crystals are placed
    # a few millimetres from their pins, so a tighter band is assumed, and it is
    # the thing to measure at bring-up - the oscillator's frequency error is
    # what it moves.
    "hse.stray_capacitance": (3e-12, 5e-12),
    "lse.stray_capacitance": (2e-12, 4e-12),
    # An indicator LED that can be seen in a lit room, at the least current the
    # tolerances allow.
    "leds.visible_current": (0.5e-3, 20e-3),
}

# Which later block connects the other end of each net. Matched in order; a net
# matching none of these is an error, so a new pin cannot slip in unexplained.
_MILESTONES = [
    (r"^VREF\+$",
     "M4: the power block - VREF+ comes from the external 3.0 V reference"),
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

    nets = {}
    for name, net in (("VDDA", "VDDA"), ("VREF+", "VREF+"), ("BOOT0", "BOOT0"), ("NRST", "NRST")):
        nets[net] = Net(net)
        nets[net].connect(*pins_named(name))
    for index, pin in enumerate(pins_named("VCAP"), start=1):
        nets[f"VCAP{index}"] = Net(f"VCAP{index}")
        nets[f"VCAP{index}"].connect(pin)

    used = set()
    for p in PINMAP.PINS:
        nets[p.name] = Net(p.name)
        nets[p.name].connect(by_number[silicon.position(p.pin)])
        used.add(p.pin)

    mcu_core(silicon, mcu, by_number, v3v3, gnd, nets)

    # Unused I/O is left unconnected on purpose, and said so. Firmware sets these
    # to analog mode, the lowest-leakage state.
    for name in sorted(set(silicon.io_pins) - used):
        for pin in pins_named(name):
            pin += NC  # noqa: F821 - SKiDL puts NC in builtins

    return v3v3


def mcu_core(silicon, mcu, by_number, v3v3, gnd, nets) -> None:
    """Everything the MCU needs before it will run, and nothing it only uses."""

    def pin_number(name: str) -> list[str]:
        return silicon.pins[name].positions

    # One 100 nF at every supply pin, named for the pin it serves, so placement
    # can find it and the decoupling check can pair it back. Datasheet
    # Figure 13: N x 100 nF plus one 4.7 uF on VDD.
    for name in ("VDD", "VDD33_USB", "VBAT"):
        for number in pin_number(name):
            cap = part(parts.CAP_100N_0402, f"core.dec.p{number}", f"C{100 + int(number)}")
            v3v3 += cap[1]
            gnd += cap[2]
    bulk = part(parts.CAP_4U7_0603, "core.bulk", "C1")
    v3v3 += bulk[1]
    gnd += bulk[2]
    usb_bulk = part(parts.CAP_1U_0402, "core.usb_bulk", "C2")
    v3v3 += usb_bulk[1]
    gnd += usb_bulk[2]

    # The core regulator's capacitors: 2.2 uF, ESR under 100 mOhm, on each VCAP
    # pin. Datasheet Table 24.
    for index, number in enumerate(pin_number("VCAP"), start=1):
        cap = part(parts.CAP_2U2_0402, f"core.vcap.p{number}", f"C{2 + index}")
        nets[f"VCAP{index}"] += cap[1]
        gnd += cap[2]

    # The analog supply, through a ferrite from the logic rail, with 1 uF and
    # 100 nF at the pin. One ground: the ADCs' return is the plane, and analog
    # parts are kept apart by where they sit, not by a split.
    bead = part(parts.FERRITE_600R_0402, "core.vdda.bead", "FB1")
    v3v3 += bead[1]
    nets["VDDA"] += bead[2]
    # A bead is passive, so ERC cannot see that the rail behind it drives VDDA.
    # It does: the drive is declared here, on the one net that needs it.
    nets["VDDA"].drive = POWER
    for address, spec, ref in (
        ("core.vdda.c1u", parts.CAP_1U_0402, "C5"),
        (f"core.dec.p{pin_number('VDDA')[0]}", parts.CAP_100N_0402, f"C{100 + int(pin_number('VDDA')[0])}"),
    ):
        cap = part(spec, address, ref)
        nets["VDDA"] += cap[1]
        gnd += cap[2]

    # 8 MHz crystal and its load capacitors. No series resistor: the drive
    # level is well inside the crystal's 200 uW, and the check says whether the
    # gain margin needs one.
    hse = part(parts.XTAL_8M, "core.hse.crystal", "Y1")
    nets["HSE_IN"] += hse[1]
    nets["HSE_OUT"] += hse[2]
    for address, net, ref in (("core.hse.c_in", "HSE_IN", "C6"), ("core.hse.c_out", "HSE_OUT", "C7")):
        cap = part(parts.CAP_8P2_0402, address, ref)
        nets[net] += cap[1]
        gnd += cap[2]

    # 32.768 kHz crystal. Its pins 2 and 3 are internal and must not be
    # connected - Epson's datasheet says so in as many words.
    lse = part(parts.XTAL_32K, "core.lse.crystal", "Y2")
    nets["LSE_IN"] += lse[1]
    nets["LSE_OUT"] += lse[4]
    lse[2] += NC  # noqa: F821
    lse[3] += NC  # noqa: F821
    for address, net, ref in (("core.lse.c_in", "LSE_IN", "C8"), ("core.lse.c_out", "LSE_OUT", "C9")):
        cap = part(parts.CAP_6P8_0402, address, ref)
        nets[net] += cap[1]
        gnd += cap[2]

    # Reset: the internal 30-50 k pull-up plus 100 nF, datasheet Figure 21.
    nrst_cap = part(parts.CAP_100N_0402, "core.nrst.cap", "C10")
    nets["NRST"] += nrst_cap[1]
    gnd += nrst_cap[2]

    # Boot from flash unless a probe or a bridge on the pad says otherwise.
    boot_pull = part(parts.RES_10K_0402, "core.boot0.pulldown", "R1")
    nets["BOOT0"] += boot_pull[1]
    gnd += boot_pull[2]
    nets["BOOT0"] += part(parts.TEST_PAD, "tp_boot0", "TP1")[1]

    # SWD on a Tag-Connect footprint: no connector fitted, the cable's pogo pins
    # land on the pads.
    swd = part(parts.TAG_CONNECT, "core.swd", "J1")
    v3v3 += swd["VCC"]
    gnd += swd["GND"]
    nets["SWDIO"] += swd["SWDIO"]
    nets["SWCLK"] += swd["SWCLK"]
    nets["SWO"] += swd["SWO"]
    nets["NRST"] += swd[3]

    # The console, and the ROM bootloader, on bare pads.
    nets["CONSOLE_TX"] += part(parts.TEST_PAD, "tp_console_tx", "TP2")[1]
    nets["CONSOLE_RX"] += part(parts.TEST_PAD, "tp_console_rx", "TP3")[1]
    gnd += part(parts.TEST_PAD, "tp_gnd", "TP4")[1]
    v3v3 += part(parts.TEST_PAD, "tp_3v3", "TP5")[1]

    # Indicators, driven high from the MCU through 1 k.
    for index, (name, spec) in enumerate(
        (("LED_STATUS", parts.LED_YELLOW_GREEN_0603), ("LED_FAULT", parts.LED_RED_0603),
         ("LED_COMMS", parts.LED_YELLOW_GREEN_0603)),
        start=1,
    ):
        key = name.lower().removeprefix("led_")
        resistor = part(parts.RES_1K_0402, f"core.led.{key}.resistor", f"R{1 + index}")
        led = part(spec, f"core.led.{key}.led", f"D{index}")
        nets[name] += resistor[1]
        Net(f"{name}_A").connect(resistor[2], led["A"])
        gnd += led["K"]

    # The button, active high with an external pull-down, as on the NUCLEO the
    # firmware was written for.
    button = part(parts.BUTTON_6MM, "core.button.switch", "SW1")
    v3v3 += button[1]
    nets["BUTTON"] += button[2]
    pull = part(parts.RES_10K_0402, "core.button.pulldown", "R5")
    nets["BUTTON"] += pull[1]
    gnd += pull[2]


def pending(circuit_nets: list[str]) -> dict[str, str]:
    """Every net with only the MCU on it, and the block that will change that."""
    return {net: waiting_for(net) for net in circuit_nets if net not in ("3V3", "GND")}


if __name__ == "__main__":
    # Nets the MCU core connects are no longer waiting for anything.
    core = re.compile(r"^(SW\w+|HSE_\w+|LSE_\w+|CONSOLE_\w+|LED_\w+|BUTTON|BOOT0|NRST|VDDA|VCAP\d)$")
    names = ["VREF+"] + [p.name for p in PINMAP.PINS if not core.match(p.name)]
    sys.exit(run(build, HERE, INTENT, pending(names)))
