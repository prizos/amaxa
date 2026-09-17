#!/usr/bin/env python3
"""
cpu1 — the STM32H743 control board, as a circuit.

Built one block at a time. What exists so far:

- the MCU, with every pin in `pinmap.py` on its own named net and every unused
  I/O pin marked `NC`;
- its core: supply decoupling, the core regulator's capacitors, the filtered
  analog supply, both crystals, reset and boot, the Tag-Connect debug footprint,
  three LEDs, a button and test pads on the console;
- the power block: 9 to 36 V in through a fuse, a reverse-polarity FET and a
  TVS, a 100 V buck to 5 V, a second buck to 3V3, and the series reference that
  drives VREF+.

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
    # What the board accepts at its terminal. 24 V nominal industrial, +50 %,
    # down to a 12 V battery at the end of its discharge.
    "input.voltage": (9.0, 36.0),
    # Where the input undervoltage lockout must sit: above the voltage at which
    # nothing useful runs, and below the lowest input the board claims to take,
    # so it starts at 9 V rather than on the way to it.
    "input.lockout": (7.0, 8.9),
    # The logic rail, 3.3 V ±5 %. The MCU's own limits are checked against it.
    "rail.3v3.voltage": (3.135, 3.465),
    # What each rail is designed to deliver. Nothing on the board measures this;
    # it is the budget the magnetics, the regulators and the fuse are sized to,
    # and the checks hold them to it.
    "rail.3v3.current": (0.0, 0.8),
    "rail.5v.voltage": (4.75, 5.25),
    "rail.5v.current": (0.0, 0.7),
    # What each conversion is assumed to manage, end to end. Nothing on the
    # board measures it either; it is what the fuse, the FET and the inductors
    # are sized against, and it is the first thing to measure at bring-up.
    "power.efficiency": (0.80, 0.95),
    # The 100 V buck's switching frequency, set by one resistor. High enough for
    # a small inductor, low enough that switching losses at 36 V stay modest.
    "buck5.switching_frequency": (350e3, 450e3),
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

    # The rails. Every regulator reaches its rail through an inductor, and an
    # inductor is passive, so ERC cannot see that anything drives these nets.
    # It does - power_block() below - and the drive is declared here.
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
    power_block(v3v3, gnd, nets)

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

    # VREF+ is a supply pin like any other as far as decoupling goes: 100 nF at
    # the pin, named for it so placement and the decoupling check find it, and a
    # 1 uF beside it. What drives it is the reference in power_block().
    for address, spec, ref in (
        (f"core.dec.p{pin_number('VREF+')[0]}", parts.CAP_100N_0402, f"C{100 + int(pin_number('VREF+')[0])}"),
        ("core.vref.c1u", parts.CAP_1U_0402, "C11"),
    ):
        cap = part(spec, address, ref)
        nets["VREF+"] += cap[1]
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


def power_block(v3v3, gnd, nets) -> None:
    """
    9 to 36 V in, and the three rails the board runs on.

    Input protection, a 100 V buck to 5 V, a small buck to 3V3, and a series
    reference for VREF+. Every value here is checked back in
    `checks/test_power.py` against the figures in `parts.py`, which come from
    the parts' own datasheets.
    """
    vin = Net("VIN")
    vin.drive = POWER
    v5 = Net("5V")
    v5.drive = POWER

    # --- the input stage -----------------------------------------------------
    #
    # Terminal, fuse, P-FET, then the TVS. The order is the design:
    #
    # The DRAIN faces the supply and the SOURCE faces the load, so the body
    # diode points the way current should flow and the FET blocks when the
    # supply is reversed. Wired the other way round the board still works on the
    # bench and the body diode conducts under reverse polarity - led12's defect,
    # and test_power.py derives the orientation rather than tabulating it.
    #
    # The TVS sits BEHIND the FET, on the protected rail. In front of it a
    # reversed supply would forward-bias the TVS into a short and take the fuse
    # with it, which makes the FET pointless: reverse the terminal here and
    # nothing at all happens. The cost is that the FET sees the full reverse
    # voltage, which is why it is a 100 V part.
    terminal = part(parts.SCREW_TERM_2, "power.terminal", "J2")
    fuse = part(parts.FUSE_1A, "power.fuse", "F1")
    q_rpp = part(parts.PFET_RPP, "power.q_rpp", "Q1")
    r_gate = part(parts.RES_100K_0402, "power.r_gate", "R6")
    d_clamp = part(parts.ZENER_GATE_CLAMP, "power.d_gate_clamp", "D4")
    tvs = part(parts.TVS_40V, "power.tvs", "D5")

    Net("VIN_RAW").connect(terminal[1], fuse[1])
    gnd += terminal[2]
    Net("VIN_FUSED").connect(fuse[2], q_rpp["D"])
    vin += q_rpp["S"]

    # The gate is at ground through R6, so V_gs is the whole input voltage until
    # D4 clamps it. Cathode to the source, anode to the gate: the Zener conducts
    # when the source is more than its voltage above the gate.
    Net("RPP_GATE").connect(q_rpp["G"], r_gate[1], d_clamp[2])
    vin += d_clamp[1]
    gnd += r_gate[2]

    vin += tvs[1]
    gnd += tvs[2]
    vin += part(parts.TEST_PAD, "tp_vin", "TP6")[1]

    # --- 5 V ------------------------------------------------------------------
    #
    # A constant-on-time buck: the switching frequency comes from R9, and the
    # feedback comparator needs ripple of its own at FB. R12/C16 make a ramp
    # from the switch node in phase with the inductor current and C17 couples it
    # in - the datasheet's Type 3 network, the one its own reference design
    # uses, and the one that keeps the output ripple to millivolts.
    buck5 = part(parts.BUCK_100V, "buck5.ic", "U2")
    gnd += buck5["GND"], buck5["EP"]
    vin += buck5["VIN"]

    for address, spec, ref in (
        ("buck5.c_in1", parts.CAP_2U2_100V_1210, "C12"),
        ("buck5.c_in2", parts.CAP_2U2_100V_1210, "C13"),
        ("buck5.c_in_hf", parts.CAP_100N_100V_0603, "C14"),
    ):
        cap = part(spec, address, ref)
        vin += cap[1]
        gnd += cap[2]

    # Input undervoltage lockout: the converter starts when EN/UVLO passes
    # 1.5 V, so this divider is what sets the input voltage that happens at.
    r_uvlo_top = part(parts.RES_226K_0402, "buck5.r_uvlo_top", "R7")
    r_uvlo_bottom = part(parts.RES_49K9_0402, "buck5.r_uvlo_bottom", "R8")
    vin += r_uvlo_top[1]
    Net("UVLO").connect(r_uvlo_top[2], r_uvlo_bottom[1], buck5["EN/UVLO"])
    gnd += r_uvlo_bottom[2]

    r_on = part(parts.RES_31K6_0402, "buck5.r_on", "R9")
    Net("RON").connect(buck5["RON"], r_on[1])
    gnd += r_on[2]

    # Pad 1 faces the switch pin and pad 2 the bootstrap pin, which is how the
    # capacitor sits on the board.
    c_bst = part(parts.CAP_2N2_0402, "buck5.c_bst", "C15")
    Net("BST_5V").connect(buck5["BST"], c_bst[2])

    sw5 = Net("SW_5V")
    sw5.connect(buck5["SW"], c_bst[1])
    inductor = part(parts.IND_33U, "buck5.inductor", "L1")
    sw5 += inductor[1]
    v5 += inductor[2]

    for address, spec, ref in (
        ("buck5.c_out1", parts.CAP_10U_0805, "C18"),
        ("buck5.c_out2", parts.CAP_10U_0805, "C19"),
    ):
        cap = part(spec, address, ref)
        v5 += cap[1]
        gnd += cap[2]

    r_fb_top = part(parts.RES_158K_0402, "buck5.r_fb_top", "R10")
    r_fb_bottom = part(parts.RES_49K9_0402, "buck5.r_fb_bottom", "R11")
    v5 += r_fb_top[1]
    fb5 = Net("FB_5V")
    fb5.connect(r_fb_top[2], r_fb_bottom[1], buck5["FB"])
    gnd += r_fb_bottom[2]

    r_ramp = part(parts.RES_121K_0402, "buck5.r_ramp", "R12")
    c_ramp = part(parts.CAP_3N3_0402, "buck5.c_ramp", "C16")
    c_couple = part(parts.CAP_56P_0402, "buck5.c_couple", "C17")
    sw5 += r_ramp[1]
    Net("RAMP").connect(r_ramp[2], c_ramp[1], c_couple[2])
    v5 += c_ramp[2]
    fb5 += c_couple[1]

    # Power good, pulled up to the rail it reports on the far side of, and
    # brought to a pad. No MCU pin: the pin map is fixed and this is a bring-up
    # signal, not one firmware acts on.
    # 49.9k and not 10k: the datasheet's range starts at 10 k, and a 10 k part
    # at 1 % starts below it. Higher is better here anyway - the pin's own
    # pull-down is 30 ohm, so the low level is microvolts either way.
    r_pgood = part(parts.RES_49K9_0402, "buck5.r_pgood", "R13")
    v3v3 += r_pgood[2]
    Net("PGOOD").connect(r_pgood[1], buck5["PGOOD"], part(parts.TEST_PAD, "tp_pgood", "TP7")[1])
    v5 += part(parts.TEST_PAD, "tp_5v", "TP8")[1]

    # --- 3V3 -------------------------------------------------------------------
    #
    # D-CAP2, so there is nothing to compensate and no ripple to inject: the
    # inductor and output capacitance come straight from the datasheet's table
    # for a 3.3 V output, and the checks hold them to it.
    buck3 = part(parts.BUCK_3V3, "buck3v3.ic", "U3")
    gnd += buck3["GND"]
    v5 += buck3["VIN"], buck3["EN"]

    for address, spec, ref in (
        ("buck3v3.c_in", parts.CAP_10U_0805, "C20"),
        ("buck3v3.c_in_hf", parts.CAP_100N_0402, "C21"),
    ):
        cap = part(spec, address, ref)
        v5 += cap[1]
        gnd += cap[2]

    c_bst3 = part(parts.CAP_100N_0402, "buck3v3.c_bst", "C22")
    Net("BST_3V3").connect(buck3["VBST"], c_bst3[2])
    sw3 = Net("SW_3V3")
    sw3.connect(buck3["SW"], c_bst3[1])
    inductor3 = part(parts.IND_3U3, "buck3v3.inductor", "L2")
    sw3 += inductor3[1]
    v3v3 += inductor3[2]

    for address, spec, ref in (
        ("buck3v3.c_out1", parts.CAP_22U_0805, "C23"),
        ("buck3v3.c_out2", parts.CAP_22U_0805, "C24"),
    ):
        cap = part(spec, address, ref)
        v3v3 += cap[1]
        gnd += cap[2]

    r_fb3_top = part(parts.RES_33K2_0402, "buck3v3.r_fb_top", "R14")
    r_fb3_bottom = part(parts.RES_10K_0402, "buck3v3.r_fb_bottom", "R15")
    v3v3 += r_fb3_top[1]
    Net("FB_3V3").connect(r_fb3_top[2], r_fb3_bottom[1], buck3["VFB"])
    gnd += r_fb3_bottom[2]

    # --- VREF+ -------------------------------------------------------------------
    #
    # A series reference from the 5 V rail, not a divider off 3V3 and not the
    # MCU's own VREFBUF: everything the ADCs measure is scaled by this voltage,
    # so its 0.2 % and 75 ppm/degC are the board's measurement accuracy. It
    # needs no output capacitor; the 1 uF and 100 nF at the pin are the MCU's.
    vref = part(parts.VREF_3V0, "vref.ic", "U4")
    v5 += vref["IN"]
    gnd += vref["GND"]
    nets["VREF+"] += vref["OUT"]
    nets["VREF+"].drive = POWER
    c_vref_in = part(parts.CAP_1U_0402, "vref.c_in", "C25")
    v5 += c_vref_in[1]
    gnd += c_vref_in[2]
    nets["VREF+"] += part(parts.TEST_PAD, "tp_vref", "TP9")[1]


def pending(circuit_nets: list[str]) -> dict[str, str]:
    """Every net with only the MCU on it, and the block that will change that."""
    return {net: waiting_for(net) for net in circuit_nets if net not in ("3V3", "GND")}


if __name__ == "__main__":
    # Nets the MCU core connects are no longer waiting for anything.
    core = re.compile(r"^(SW\w+|HSE_\w+|LSE_\w+|CONSOLE_\w+|LED_\w+|BUTTON|BOOT0|NRST|VDDA|VCAP\d)$")
    names = [p.name for p in PINMAP.PINS if not core.match(p.name)]
    sys.exit(run(build, HERE, INTENT, pending(names)))
