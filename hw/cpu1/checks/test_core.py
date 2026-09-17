"""
The MCU core, against ST's datasheet and the parts' own figures.

Every expectation here is derived: which pins need decoupling comes from ST's
pin data, which capacitor serves which pin from the netlist and the placed board,
and every margin from values recorded in parts.py with their source. Nothing
names a designator or an address the design could rename.

The datasheet is STM32H743xI, DocID030538 Rev 3; ST's oscillator guidance is
AN2867, whose rule this applies but whose text was not re-read here.
"""

import math
import sys
from pathlib import Path

import pytest

HW_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HW_DIR / "tools"))

from layout_lib import footprint_pads  # noqa: E402
from stm32 import Silicon  # noqa: E402

MCU = "mcu"

# How far a supply pin's own capacitor may sit from it: centre of the pad to
# centre of the capacitor. ST's datasheet says "as close as possible"; an 0402
# just outside a 0.5 mm-pitch ring, clear of its neighbours, is a little over
# 2 mm, and this leaves room for the spread a neighbouring capacitor forces.
DECOUPLING_REACH = 3.0  # mm

# AN2867's rule: the MCU's maximum critical transconductance should be at least
# five times what the crystal needs, or the oscillator may not start reliably
# across temperature and part spread.
GAIN_MARGIN = 5.0

POWER_DERATING = 0.5


# --- reading the design ------------------------------------------------------------


@pytest.fixture(scope="module")
def silicon():
    return Silicon("STM32H743ZITx")


@pytest.fixture(scope="module")
def pad_net(design):
    """(address, pad) -> net name."""
    return {tuple(node): net for net, nodes in design["nets"].items() for node in nodes}


@pytest.fixture(scope="module")
def two_pad_parts(design, pad_net):
    """address -> (net on pad 1, net on pad 2), for every two-pad passive."""
    out = {}
    for address, part in design["parts"].items():
        if part["symbol"] in ("Device:C", "Device:R", "Device:FerriteBead_Small"):
            out[address] = (pad_net.get((address, "1")), pad_net.get((address, "2")))
    return out


def symbol_of(design, address):
    return design["parts"][address]["symbol"]


def capacitors_between(design, two_pad_parts, net_a, net_b):
    return sorted(
        address
        for address, nets in two_pad_parts.items()
        if symbol_of(design, address) == "Device:C" and set(nets) == {net_a, net_b}
    )


def resistors_between(design, two_pad_parts, net_a, net_b):
    return sorted(
        address
        for address, nets in two_pad_parts.items()
        if symbol_of(design, address) == "Device:R" and set(nets) == {net_a, net_b}
    )


@pytest.fixture(scope="module")
def mcu_pad_position(design, footprints, board_dir):
    """MCU pad number -> absolute (x, y), from the placed footprint and its file."""
    library, _, name = design["parts"][MCU]["footprint"].partition(":")
    pads = footprint_pads(board_dir / "parts" / library / f"{name}.kicad_mod")
    fp = next(f for f in footprints if f["properties"].get("address") == MCU)
    rotation = math.radians(-fp.get("rotation", 0.0))

    def at(number: str) -> tuple[float, float]:
        pad = pads[number][0]
        return (
            fp["x"] + pad.x * math.cos(rotation) - pad.y * math.sin(rotation),
            fp["y"] + pad.x * math.sin(rotation) + pad.y * math.cos(rotation),
        )

    return at


# --- supply decoupling -----------------------------------------------------------------


def test_every_supply_pin_has_its_own_capacitor(design, silicon, pad_net, two_pad_parts,
                                                 mcu_pad_position, position, spec):
    """
    Each MCU supply pin has a 100 nF capacitor to ground, its own, beside it.

    Datasheet Figure 13: one 100 nF per VDD pin, and 100 nF on VDDA and on
    VDD33USB and VBAT. "Its own" is the part the netlist cannot say: every VDD
    pin is on the same 3V3 net, so one capacitor on that net would satisfy a
    check that only looked at nets. So pins and capacitors are matched one to
    one, each within reach of the pin it serves - a pairing that has to exist
    for every pin at once, not just capacitor by capacitor.
    """
    supply_pins = [
        number
        for name in ("VDD", "VDD33_USB", "VBAT", "VDDA")
        for number in silicon.pins[name].positions
    ]
    candidates = {}
    for number in supply_pins:
        net = pad_net[(MCU, number)]
        px, py = mcu_pad_position(number)
        candidates[number] = [
            address
            for address in capacitors_between(design, two_pad_parts, net, "GND")
            if math.dist((px, py), position(address)) <= DECOUPLING_REACH
            and _contains(spec(address, "capacitance"), 100e-9)
        ]

    matched = _match(candidates)
    unserved = sorted((n for n in supply_pins if n not in matched), key=int)
    assert not unserved, (
        "Supply pins without their own 100 nF capacitor within "
        f"{DECOUPLING_REACH} mm:\n"
        + "\n".join(
            f"  pin {n} ({pad_net[(MCU, n)]}): candidates {candidates[n] or 'none'}"
            for n in unserved
        )
    )


def test_supplies_have_their_bulk_capacitance(design, two_pad_parts, spec):
    """
    The logic rail carries a 4.7 uF, and the logic rail and VDDA each a 1 uF.

    Datasheet Figure 13's "1 x 4.7 uF" on VDD and "100 nF + 1 x 1 uF" pairs. Which
    supply pins those pairs sit on is not legible in the extracted figure, so
    this holds both rails to a 1 uF and the review note records the doubt.
    """
    missing = []
    for net, value in (("3V3", 4.7e-6), ("3V3", 1e-6), ("VDDA", 1e-6)):
        found = [
            a for a in capacitors_between(design, two_pad_parts, net, "GND")
            if _contains(spec(a, "capacitance"), value)
        ]
        if not found:
            missing.append(f"  {net}: no {value * 1e6:g} uF capacitor to ground")
    assert not missing, "Bulk capacitance missing:\n" + "\n".join(missing)


def test_each_vcap_pin_has_its_regulator_capacitor(design, silicon, pad_net, two_pad_parts, spec):
    """
    Each VCAP pin has exactly one capacitor to ground, of the value ST specifies.

    Datasheet Table 24: CEXT 2.2 uF per VCAP pin, ESR under 100 mOhm. The core
    regulator is unstable without it; with two it is a different, untested
    filter. ESR is not in the capacitor's listing and is not checked here.
    """
    cext, _ = spec(MCU, "vcap_capacitance")
    wrong = []
    for number in silicon.pins["VCAP"].positions:
        net = pad_net[(MCU, number)]
        caps = capacitors_between(design, two_pad_parts, net, "GND")
        if len(caps) != 1:
            wrong.append(f"  pin {number} ({net}): {len(caps)} capacitors to ground, needs exactly 1")
        elif not _contains(spec(caps[0], "capacitance"), cext):
            low, high = spec(caps[0], "capacitance")
            wrong.append(f"  pin {number}: {caps[0]} is {low * 1e6:.2f}-{high * 1e6:.2f} uF, not {cext * 1e6:g} uF")
    assert not wrong, "Core regulator capacitors:\n" + "\n".join(wrong)


def test_every_capacitor_is_rated_for_the_rail(design, spec):
    """No capacitor on the board is rated below the highest the logic rail reaches."""
    _, rail_high = spec("rail.3v3", "voltage")
    weak = [
        f"  {a}: {spec(a, 'max_voltage')[0]:g} V"
        for a, part in design["parts"].items()
        if part["symbol"] == "Device:C" and spec(a, "max_voltage")[0] < rail_high
    ]
    assert not weak, f"Capacitors rated below {rail_high:.3f} V:\n" + "\n".join(weak)


# --- clocks ------------------------------------------------------------------------------


def _crystal(design, prefix):
    return next(a for a in design["parts"] if a == f"core.{prefix}.crystal")


def _load_caps(design, two_pad_parts, crystal, pad_net):
    """The capacitors from each of a crystal's two terminals to ground."""
    part = design["parts"][crystal]
    terminals = ("1", "4") if part["symbol"] == "Device:Crystal_GND23" else ("1", "2")
    return [
        capacitors_between(design, two_pad_parts, pad_net[(crystal, t)], "GND")
        for t in terminals
    ]


@pytest.mark.parametrize("oscillator", ["hse", "lse"])
def test_crystal_sees_its_load_capacitance(oscillator, design, two_pad_parts, pad_net, spec):
    """
    The load the crystal sees is the load it is cut for, at every corner.

    Its two capacitors in series, plus the pin and board capacitance alongside
    them. ST's datasheet sizes that stray at 10 pF "as a rough estimate"; the
    design states its own band in design.json, because these crystals sit a few
    millimetres from their pins, and bring-up measures the frequency error that
    would show it wrong. The HSE capacitors must also be inside the 5-25 pF the
    datasheet recommends for that oscillator.
    """
    crystal = _crystal(design, oscillator)
    caps = _load_caps(design, two_pad_parts, crystal, pad_net)
    assert all(len(c) == 1 for c in caps), f"{crystal}: needs one capacitor from each terminal to ground, has {caps}"
    (c1_low, c1_high), (c2_low, c2_high) = spec(caps[0][0], "capacitance"), spec(caps[1][0], "capacitance")
    stray_low, stray_high = spec(oscillator, "stray_capacitance")
    load_low = c1_low * c2_low / (c1_low + c2_low) + stray_low
    load_high = c1_high * c2_high / (c1_high + c2_high) + stray_high
    wanted, _ = spec(crystal, "load_capacitance")
    assert load_low <= wanted <= load_high, (
        f"{crystal} is cut for {wanted * 1e12:.1f} pF but sees "
        f"{load_low * 1e12:.2f} to {load_high * 1e12:.2f} pF"
    )
    if oscillator == "hse":
        range_low, range_high = spec(MCU, "hse_load_capacitor")
        for c in (caps[0][0], caps[1][0]):
            low, high = spec(c, "capacitance")
            assert range_low <= low and high <= range_high, (
                f"{c} is {low * 1e12:.2f}-{high * 1e12:.2f} pF, outside the "
                f"{range_low * 1e12:g}-{range_high * 1e12:g} pF ST recommends"
            )


@pytest.mark.parametrize("oscillator", ["hse", "lse"])
def test_oscillator_has_gain_margin(oscillator, design, spec):
    """
    The MCU can drive the crystal with margin to spare.

    gm_crit = 4 x ESR x (2 pi f)^2 x (C0 + CL)^2, at the crystal's worst stated
    ESR and shunt capacitance; the MCU's maximum critical gm must be at least
    five times it. This is the check that rejected every in-stock 8 MHz crystal
    in 3225 and HC-49S, and the common 12.5 pF 32 kHz parts: each would start on
    a bench and might not start cold.
    """
    crystal = _crystal(design, oscillator)
    esr, _ = spec(crystal, "esr_max")
    _, c0 = spec(crystal, "shunt_capacitance")
    cl, _ = spec(crystal, "load_capacitance")
    frequency, _ = spec(crystal, "frequency")
    available, _ = spec(MCU, f"{oscillator}_gm_crit_max")
    needed = 4 * esr * (2 * math.pi * frequency) ** 2 * (c0 + cl) ** 2
    margin = available / needed
    assert margin >= GAIN_MARGIN, (
        f"{crystal}: gain margin {margin:.1f}, needs {GAIN_MARGIN:g}. The MCU offers "
        f"{available * 1e6:.2f} uA/V and the crystal needs {needed * 1e6:.3f} uA/V."
    )


# --- reset, boot, indicators, button ---------------------------------------------------


def test_reset_has_its_capacitor(design, two_pad_parts, spec):
    """NRST carries the 100 nF of datasheet Figure 21, against parasitic resets."""
    wanted, _ = spec(MCU, "nrst_capacitor")
    caps = capacitors_between(design, two_pad_parts, "NRST", "GND")
    assert len(caps) == 1 and _contains(spec(caps[0], "capacitance"), wanted), (
        f"NRST should have one {wanted * 1e9:g} nF capacitor to ground, has {caps}"
    )


@pytest.mark.parametrize("net", ["BOOT0", "BUTTON"])
def test_inputs_rest_low(net, design, two_pad_parts, spec):
    """
    BOOT0 and the button read low unless something deliberately pulls them up.

    BOOT0 high boots the ROM bootloader instead of the firmware; the button is
    active high, and the firmware expects the pull-down on the board. Each
    resistor must also survive the whole logic rail across it.
    """
    resistors = resistors_between(design, two_pad_parts, net, "GND")
    assert len(resistors) == 1, f"{net}: {len(resistors)} pull-downs to ground, needs 1"
    r_low, _ = spec(resistors[0], "resistance")
    rated, _ = spec(resistors[0], "max_power")
    _, rail_high = spec("rail.3v3", "voltage")
    assert rail_high**2 / r_low <= rated * POWER_DERATING, f"{resistors[0]} is over half its rating"


def test_indicators_are_visible_and_within_ratings(design, two_pad_parts, pad_net, spec):
    """
    Each LED, driven from an MCU pin through its resistor, is visibly lit and
    inside both its own rating and the pin's.

    The chain is found from the netlist: an LED whose cathode is ground and whose
    anode shares a net with one resistor, whose other end is an MCU pin.
    """
    rail_low, rail_high = spec("rail.3v3", "voltage")
    visible_low, visible_high = spec("leds", "visible_current")
    pin_max, _ = spec(MCU, "io_current_max")
    problems, found = [], 0
    for address, part in design["parts"].items():
        if part["symbol"] != "Device:LED":
            continue
        found += 1
        # KiCad's LED symbol: pin 1 cathode, pin 2 anode.
        assert pad_net[(address, "1")] == "GND", f"{address}: cathode not on ground"
        anode = pad_net[(address, "2")]
        series = [a for a, nets in two_pad_parts.items()
                  if symbol_of(design, a) == "Device:R" and anode in nets]
        assert len(series) == 1, f"{address}: {len(series)} resistors on its anode"
        drive_net = next(n for n in two_pad_parts[series[0]] if n != anode)
        assert any(node[0] == MCU for node in design["nets"][drive_net]), (
            f"{address}: {series[0]} is not driven from an MCU pin"
        )
        vf_low, vf_high = spec(address, "forward_voltage")
        led_max, _ = spec(address, "max_current")
        r_low, r_high = spec(series[0], "resistance")
        least = (rail_low - vf_high) / r_high
        most = (rail_high - vf_low) / r_low
        ceiling = min(visible_high, led_max, pin_max)
        if least < visible_low or most > ceiling:
            problems.append(f"  {address}: {least * 1e3:.2f} to {most * 1e3:.2f} mA")
        rated, _ = spec(series[0], "max_power")
        if most**2 * r_high > rated * POWER_DERATING:
            problems.append(f"  {series[0]}: over half its power rating")
    assert found, "no indicator LEDs found"
    assert not problems, "Indicators outside their bands:\n" + "\n".join(problems)


def test_analog_supply_is_filtered_from_the_logic_rail(design, two_pad_parts):
    """
    VDDA reaches 3V3 through a ferrite and nothing else.

    A resistor or a zero-ohm link in its place would pass the digital noise the
    bead exists to keep off the ADCs' supply.
    """
    between = [a for a, nets in two_pad_parts.items() if set(nets) == {"3V3", "VDDA"}]
    kinds = sorted(symbol_of(design, a) for a in between)
    assert kinds == ["Device:FerriteBead_Small"], f"VDDA to 3V3 through {kinds or 'nothing'}"


# --- helpers ------------------------------------------------------------------------------


def _contains(band: tuple[float, float], value: float) -> bool:
    low, high = band
    return low <= value <= high


def _match(candidates: dict[str, list[str]]) -> dict[str, str]:
    """Maximum one-to-one matching of pins to capacitors (Kuhn's algorithm)."""
    owner: dict[str, str] = {}

    def claim(pin: str, seen: set[str]) -> bool:
        for cap in candidates[pin]:
            if cap in seen:
                continue
            seen.add(cap)
            if cap not in owner or claim(owner[cap], seen):
                owner[cap] = pin
                return True
        return False

    for pin in candidates:
        claim(pin, set())
    return {pin: cap for cap, pin in owner.items()}
