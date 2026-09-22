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
from series import closest  # noqa: E402
from stm32 import Silicon  # noqa: E402
from symbols import symbol_pin_names  # noqa: E402

MCU = "mcu"

# How far a supply pin's own capacitor may sit from it: centre of the pad to
# centre of the capacitor. ST's datasheet says "as close as possible"; an 0402
# just outside a 0.5 mm-pitch ring, clear of its neighbours, is a little over
# 2 mm, and this leaves room for the spread a neighbouring capacitor forces.

# AN2867's rule: the MCU's maximum critical transconductance should be at least
# five times what the crystal needs, or the oscillator may not start reliably
# across temperature and part spread.
GAIN_MARGIN = 5.0



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


def _derating(spec) -> float:
    """How much of a rating this board will use, from design.json."""
    _, share = spec("parts", "derating")
    return share


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

    Datasheet Figure 13: one 100 nF per VDD pin, and 100 nF on VDDA, VREF+,
    VDD33USB and VBAT. "Its own" is the part the netlist cannot say: every VDD
    pin is on the same 3V3 net, so one capacitor on that net would satisfy a
    check that only looked at nets. So pins and capacitors are matched one to
    one, each within reach of the pin it serves - a pairing that has to exist
    for every pin at once, not just capacitor by capacitor.

    "Beside it" is `layout.decoupling_reach`, which the analog regulator's
    input capacitor is held to as well. It used to be a bare constant here.
    """
    _, reach = spec("layout", "decoupling_reach")
    supply_pins = [
        number
        for name in ("VDD", "VDD33_USB", "VBAT", "VDDA", "VREF+")
        for number in silicon.pins[name].positions
    ]
    candidates = {}
    for number in supply_pins:
        net = pad_net[(MCU, number)]
        px, py = mcu_pad_position(number)
        candidates[number] = [
            address
            for address in capacitors_between(design, two_pad_parts, net, "GND")
            if math.dist((px, py), position(address)) <= reach
            and _contains(spec(address, "capacitance"), 100e-9)
        ]

    matched = _match(candidates)
    unserved = sorted((n for n in supply_pins if n not in matched), key=int)
    assert not unserved, (
        "Supply pins without their own 100 nF capacitor within "
        f"{reach} mm:\n"
        + "\n".join(
            f"  pin {n} ({pad_net[(MCU, n)]}): candidates {candidates[n] or 'none'}"
            for n in unserved
        )
    )


def test_supplies_have_their_bulk_capacitance(design, two_pad_parts, spec):
    """
    The logic rail carries a 4.7 uF, and it, VDDA and VREF+ each a 1 uF.

    Datasheet Figure 13, rendered and read at parts/LQFP144/evidence/: the
    4.7 uF belongs to VDD, and the "100 nF + 1 x 1 uF" pairs to **VDDA and
    VREF+**. The figure asks for no bulk on VDD beyond that 4.7 uF, so the
    1 uF this board also puts on 3V3 is surplus rather than required - it is
    checked for because it is fitted, not because ST ask for it.
    """
    missing = []
    for net, value in (("3V3", 4.7e-6), ("3V3", 1e-6), ("VDDA", 1e-6), ("VREF+", 1e-6)):
        found = [
            a for a in capacitors_between(design, two_pad_parts, net, "GND")
            if _contains(spec(a, "capacitance"), value)
        ]
        if not found:
            missing.append(f"  {net}: no {value * 1e6:g} uF capacitor to ground")
    assert not missing, "Bulk capacitance missing:\n" + "\n".join(missing)


def test_each_vcap_pin_has_its_regulator_capacitor(
    design, silicon, pad_net, two_pad_parts, spec, effective_capacitance
):
    """
    Each VCAP pin has exactly one capacitor to ground, worth what ST asks for
    once its tolerance and its own DC bias are taken off.

    Datasheet Table 24: CEXT 2.2 uF per VCAP pin, ESR under 100 mOhm. The core
    regulator is unstable without it; with two it is a different, untested
    filter. ESR is not in the capacitor's listing and is not checked here.

    **This used to compare the number on the reel.** A 2.2 uF +-20 % part is
    1.76 uF before anything else happens, and the one fitted was rated 6.3 V
    with 1.25 V across it - a fifth of its rating - so what reached the pin
    was 1.41 uF against ST's 2.2. Thirty-six per cent short of the figure that
    stabilises the core regulator, and the check said it was the right part,
    because `2.2` was inside `2.2 +- 20 %`.

    A 2.2 uF part cannot answer a 2.2 uF requirement: its own tolerance
    forbids it before bias is considered. So the part is a 4.7 uF at 10 V,
    which is worth 3.29 at this bias. ST states no ceiling - the same section
    notes that two capacitors may be connected to the VCAPx pins - and the
    one-capacitor-per-pin rule above is what keeps that from being a licence.
    """
    cext, _ = spec(MCU, "vcap_capacitance")
    _, core = spec(MCU, "core_voltage")
    wrong = []
    for number in silicon.pins["VCAP"].positions:
        net = pad_net[(MCU, number)]
        caps = capacitors_between(design, two_pad_parts, net, "GND")
        if len(caps) != 1:
            wrong.append(f"  pin {number} ({net}): {len(caps)} capacitors to ground, needs exactly 1")
            continue
        worth = effective_capacitance(caps[0], core)
        if worth < cext:
            low, high = spec(caps[0], "capacitance")
            wrong.append(
                f"  pin {number}: {caps[0]} is {low * 1e6:.2f}-{high * 1e6:.2f} uF "
                f"on the reel and {worth * 1e6:.2f} uF at {core:g} V of bias, "
                f"against the {cext * 1e6:g} uF ST asks for")
    assert not wrong, "Core regulator capacitors:\n" + "\n".join(wrong)


def test_every_capacitor_is_rated_for_the_node_it_sits_on(design, two_pad_parts, spec):
    """
    Each capacitor against the highest voltage **its own nets** reach.

    This used to hold every capacitor to the logic rail's 3.465 V, which is
    the right number for most of them and far too low for the rest: thirteen
    capacitors on this board sit on the 5 V rail, including the 5 V buck's own
    output bulk, and a part rated 4 V would have passed. Nothing else covered
    them - the input-side check is restricted to the three nets in front of
    the fuse.

    The voltage comes from the nets the capacitor is actually between. A net
    that is not a declared rail is a signal net, and on this board a signal
    net is driven from the logic rail.
    """
    _, input_high = spec("input", "voltage")
    _, v5 = spec("rail.5v", "voltage")
    _, v3v3 = spec("rail.3v3", "voltage")
    rails = {
        "GND": 0.0,
        "VIN": input_high, "VIN_RAW": input_high, "VIN_FUSED": input_high,
        "RPP_GATE": input_high, "SW_5V": input_high, "UVLO": input_high,
        "5V": v5, "SW_3V3": v5, "3V3A": v3v3,
        "3V3": v3v3,
    }

    weak = []
    for address, part in sorted(design["parts"].items()):
        if part["symbol"] != "Device:C":
            continue
        nets = two_pad_parts.get(address, (None, None))
        across = max(rails.get(net, v3v3) for net in nets)
        rated, _ = spec(address, "max_voltage")
        if rated < across:
            weak.append(f"  {address}: rated {rated:g} V, sits across {across:.3f} V "
                        f"between {nets[0]} and {nets[1]}")
    assert not weak, "Capacitors rated below the node they sit on:\n" + "\n".join(weak)


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

    # And the value is the best the series offers, not merely one whose band
    # happens to straddle the cut. A wide declared stray makes that band wide
    # too, and 6.8 pF satisfied it on the 32 kHz oscillator while presenting
    # 6.9 pF against a 6 pF cut - fifteen per cent out, and invisible.
    assert (c1_low, c1_high) == (c2_low, c2_high), (
        f"{crystal}'s two load capacitors are different values"
    )
    nominal = (c1_low + c1_high) / 2
    middle = (stray_low + stray_high) / 2

    def presents(value: float) -> float:
        return value / 2 + middle

    best = closest(nominal, lambda v: abs(presents(v) - wanted))
    assert abs(best - nominal) < 1e-15, (
        f"{crystal} is cut for {wanted * 1e12:.1f} pF; a pair of "
        f"{nominal * 1e12:g} pF presents {presents(nominal) * 1e12:.2f} pF and "
        f"a pair of {best * 1e12:g} would present {presents(best) * 1e12:.2f}"
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
def test_the_stray_an_oscillator_declares_covers_its_own_copper(
    oscillator, design, pad_net, spec, board_capacitance
):
    """
    The declared stray is at least what the tracks and pads account for.

    ST gives no capacitance for the OSC pins, so the load check above works
    from a band this design declares - and a declared band is a belief until
    something measures it. The copper can be measured: every track's width and
    length and every pad's area are in the board file, and what they are worth
    against the plane below follows from the stackup.

    That does not make the declaration redundant. It has to cover the MCU pin
    as well, which no datasheet here states, so the check is one-sided: the
    floor may sit above the copper and not below it. The LSE's floor sat below
    it - 2.0 pF declared against 2.1 pF of copper on its longer leg, which left
    the pin nothing at all and made the low corner of the load a figure that
    could not happen.
    """
    crystal = _crystal(design, oscillator)
    part = design["parts"][crystal]
    terminals = ("1", "4") if part["symbol"] == "Device:Crystal_GND23" else ("1", "2")
    declared_low, _ = spec(oscillator, "stray_capacitance")
    for terminal in terminals:
        net = pad_net[(crystal, terminal)]
        copper = board_capacitance(net)
        assert copper <= declared_low, (
            f"{oscillator} declares {declared_low * 1e12:.2f} pF of stray at "
            f"its low corner and {net} is {copper * 1e12:.2f} pF of copper "
            f"before the pin is counted"
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
    assert rail_high**2 / r_low <= rated * _derating(spec), f"{resistors[0]} is over half its rating"


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
        if most**2 * r_high > rated * _derating(spec):
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


# Tag-Connect's own TC2030-CTX datasheet, "Connections", for the 6-pin TC2030
# footprint. Not a convention and not KiCad's opinion: the manufacturer's table,
# in text, from the document `parts/TC2030/evidence/sources.json` identifies.
TAG_CONNECT_PADS = {
    "1": "3V3",      # VCC, which on this board is the 3V3 rail
    "2": "SWDIO",    # SWDIO / TMS
    "3": "NRST",     # nRESET
    "4": "SWCLK",    # SWCLK / TCK
    "5": "GND",      # GND, also the cable's GNDDetect
    "6": "SWO",      # SWO / TDO
}


def test_the_debug_pads_are_wired_the_way_the_cable_is(pad_net):
    """
    Every Tag-Connect pad carries the signal Tag-Connect's cable puts on it.

    The pad-to-signal table used to come from KiCad's symbol alone, and the
    review note said so: a pinout nobody had checked against the cable it has
    to mate with. Tag-Connect publish the mapping as text in the TC2030-CTX
    datasheet, so it can be asserted rather than believed.

    Getting this wrong is not subtle - SWDIO and SWCLK swapped is a board no
    debugger will enumerate - but it is invisible until the first bring-up, at
    which point the board is already made.
    """
    wrong = []
    for pad, expected in sorted(TAG_CONNECT_PADS.items()):
        found = pad_net.get(("core.swd", pad))
        if found != expected:
            wrong.append(f"  pad {pad}: on {found!r}, Tag-Connect's table says {expected!r}")
    assert not wrong, (
        "Tag-Connect debug pads:\n" + "\n".join(wrong)
        + "\nSee parts/TC2030/evidence/pad_signals.png."
    )


def test_the_32khz_crystal_leaves_its_case_pads_alone(design, pad_net):
    """
    The 32 kHz crystal's pads 2 and 3 go nowhere, because Epson say so.

    The MC-306's two right-hand pads are the case, not terminals, and the
    datasheet's outline drawing carries the instruction in as many words:
    *do not connect #2 and #3 to external devices*. Grounding a crystal's can
    is common enough elsewhere to be a reflex, and a reflex is what this
    catches - the part would still oscillate on the bench and its frequency
    would sit outside the tolerance it was chosen for.

    See parts/XTAL_MC306/evidence/internal_connection.png.
    """
    crystal = next((a for a, part in design["parts"].items()
                    if part["symbol"].startswith("Device:Crystal_GND23")), None)
    assert crystal, "no four-pad crystal on this board"
    joined = {pad: pad_net.get((crystal, pad)) for pad in ("2", "3")}
    assert not any(joined.values()), (
        f"{crystal}: Epson's outline says not to connect #2 and #3, but "
        f"{ {p: n for p, n in joined.items() if n} } "
    )


def test_every_part_that_states_a_temperature_range_covers_the_air_it_sits_in(
    design, spec, spec_has
):
    """
    The board declares the ambient it is for, and nothing on it is graded
    narrower than that.

    Nothing declared one before. Two parts here have ranges worth arguing
    about and neither was ever compared with anything: the MCU's T6 suffix is
    a minus-forty to eighty-five part, and the Ethernet jack is graded zero to
    seventy - a genuine substitution decision that `parts/RJ45HR/RJ45HR.md`
    already calls one, sitting on a board that never said what temperature it
    was for. `environment.ambient` is that statement, and the jack is what set
    it.

    The band only grows as parts record their grades, which is the intended
    shape: a part with nothing to say about temperature says nothing here, and
    one that does is held to it.
    """
    low, high = spec("environment", "ambient")
    assert low < high, f"the declared ambient is {low} to {high}"

    graded = [address for address in sorted(design["parts"])
              if spec_has(address, "ambient_max")]
    assert graded, "no part on this board states a temperature range"

    outside = []
    for address in graded:
        part_low, _ = spec(address, "ambient_min")
        _, part_high = spec(address, "ambient_max")
        if part_low > low or part_high < high:
            outside.append(
                f"  {address} is graded {part_low:g} to {part_high:g} degC")
    assert not outside, (
        f"Parts narrower than the {low:g} to {high:g} degC this board says it "
        f"is for:\n" + "\n".join(outside)
    )


def test_nothing_runs_hotter_inside_than_its_datasheet_allows(
    design, pad_net, spec, spec_has
):
    """
    Junction temperature, for every part that states what it takes to work it
    out - and the MCU is the one that does.

    ST give the equation in Section 7.9 of DocID030538 and both numbers for
    it in the same document: T_J max = T_A max + P_D max x theta_JA, with
    43.7 degC/W for the LQFP-144 20x20 and 125 degC for the junction. The
    dissipation is the rail budget's own figure, Table 30's 500 mA at 400 MHz
    with every peripheral on, which is 1.65 W and 72 degC of rise.

    **That is what set `environment.ambient`.** Nothing on this board declared
    a temperature and nothing compared these numbers with each other, so the
    board was buying an 85 degC part, fitting a 70 degC jack, and had a
    package that could not clear 49 degC at its own budgeted current. That is
    what the arithmetic leaves; forty-five is it with four degrees in hand,
    and it is a real
    constraint on where this board can live: a cabinet beside a motor drive
    can be hotter than that. Raising it means justifying a lower current than
    ST's worst case, or getting heat out of the package another way.

    The rest of the board is comfortable - the PHY dissipates a third of a
    watt in a QFN with an exposed pad, the converters a fraction of that - and
    none of them states a thermal resistance yet, so none of them is checked
    here. This grows the same way the temperature grades do.
    """
    _, ambient = spec("environment", "ambient")
    considered, hot = [], []
    for address in sorted(design["parts"]):
        if not (spec_has(address, "thermal_resistance_junction_ambient")
                and spec_has(address, "junction_temperature_max")
                and spec_has(address, "supply_current_max")):
            continue
        _, current = spec(address, "supply_current_max")
        # The rail it is actually given, not the range it would tolerate. A
        # part specified from 1.62 to 3.6 V does not dissipate 3.6 V worth of
        # current on a 3.3 V board, and reading the part's own band here
        # overstated the MCU by nine per cent.
        names = symbol_pin_names(design["parts"][address]["symbol"])
        rails = {net for (a, pad), net in pad_net.items()
                 if a == address and names.get(pad) in ("VDD", "VCC", "V+")}
        assert len(rails) == 1, f"{address} is powered from {sorted(rails)}"
        _, supply = spec(f"rail.{rails.pop().lower()}", "voltage")
        _, resistance = spec(address, "thermal_resistance_junction_ambient")
        _, limit = spec(address, "junction_temperature_max")
        considered.append(address)
        # Before using them, check ST's own three figures close on each other.
        # The junction limit is the one that is easy to read off the wrong
        # table - the absolute-maximum section gives 125 degC for every
        # suffix, while the operating table gives an ambient range per grade -
        # and this part's own Table 23 settles it: 85 degC of ambient plus
        # 915 mW through 43.7 degC/W is 125.0, so the three agree.
        if spec_has(address, "power_dissipation_at_reference_ambient"):
            _, stated = spec(address, "power_dissipation_at_reference_ambient")
            _, at = spec(address, "power_dissipation_reference_ambient")
            implied = at + stated * resistance
            assert abs(implied - limit) < 1.0, (
                f"{address}: the datasheet allows {stated * 1e3:g} mW at "
                f"{at:g} degC, which through {resistance:g} degC/W implies a "
                f"junction limit of {implied:.1f} degC - not the {limit:g} "
                f"recorded. One of the three figures is off the wrong table."
            )
        dissipated = current * supply
        junction = ambient + dissipated * resistance
        if junction > limit:
            hot.append(
                f"  {address}: {dissipated:.2f} W at {resistance:g} degC/W is "
                f"{dissipated * resistance:.0f} degC of rise, so a {ambient:g} degC "
                f"ambient puts its junction at {junction:.0f} against {limit:g}. "
                f"It can be declared for {limit - dissipated * resistance:.0f} degC."
            )
    assert considered, (
        "nothing on this board states a thermal resistance, a junction limit, "
        "a supply current and a supply voltage together, so this check has "
        "nothing to work out"
    )
    assert not hot, (
        "Parts whose junction leaves its datasheet at the ambient this board "
        "declares:\n" + "\n".join(hot)
    )
