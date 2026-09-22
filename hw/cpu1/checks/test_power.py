"""
The power block, against the parts' own datasheets.

Everything here is derived. The resistors that set a rail are found in the
netlist, not named; the switching frequency comes from the one on-time the
LM5164's datasheet characterises rather than from an equation typed in from a
figure; and each margin is compared against a figure recorded in `parts.py`
with the table it came from.

Datasheets: TI SNVSAU4A (LM5164, January 2019), SLVSCB0B (TPS562200, August
2014), SBVS032F (REF30xx, August 2008), Diodes DS37841 (DMP10H400SE), and the
SMBJ series table recorded in `parts/SMB/SMB.md`.
"""

import collections
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

from symbols import symbol_pin_names, symbol_pin_types  # noqa: E402

BUCK_5V = "buck5.ic"
BUCK_3V3 = "buck3v3.ic"
FET = "power.q_rpp"
TVS = "power.tvs"
FUSE = "power.fuse"
ZENER = "power.d_gate_clamp"
REFERENCE = "vref.ic"


# What a part's absolute maximum must exceed the voltage it will actually see
# by. led12 shipped a regulator rated 3 % above the clamp its own TVS produced;
# a quarter is the least that is worth calling protection.
SURGE_MARGIN = 1.25

# The fuse has to carry the board without ageing, not just without opening.
FUSE_MARGIN = 1.5


@pytest.fixture(scope="module")
def pad_net(design):
    return {tuple(node): net for net, nodes in design["nets"].items() for node in nodes}


@pytest.fixture(scope="module")
def two_pad_parts(design, pad_net):
    """address -> (net on pad 1, net on pad 2), for every two-pad passive."""
    return {
        address: (pad_net.get((address, "1")), pad_net.get((address, "2")))
        for address, part in design["parts"].items()
        if part["symbol"] in ("Device:C", "Device:R", "Device:L")
    }


def _derating(spec) -> float:
    """How much of a rating this board will use, from design.json."""
    _, share = spec("parts", "derating")
    return share


def _inside(found, wanted) -> bool:
    """
    Whether a fitted value meets a datasheet's.

    A datasheet names either a value - "connect a 0.1 uF capacitor" - or a range
    it has to fall in. For a named value the part's nominal is what is being
    asked about, because no ceramic is sold without a tolerance; for a range,
    the whole tolerance band has to fit, because the ends of a range are
    ratings. This reads both from the same pair of numbers.
    """
    nominal = (found[0] + found[1]) / 2
    if wanted[0] == wanted[1]:
        return found[0] <= wanted[0] <= found[1]
    return wanted[0] <= found[0] and found[1] <= wanted[1] and wanted[0] <= nominal <= wanted[1]


def _parts_on(design, two_pad_parts, symbol, net_a, net_b):
    return sorted(
        address
        for address, nets in two_pad_parts.items()
        if design["parts"][address]["symbol"] == symbol and set(nets) == {net_a, net_b}
    )


def _divider(design, two_pad_parts, spec, high_net, tap_net, low_net):
    """The two resistances of a divider between `high_net` and `low_net`."""
    top = _parts_on(design, two_pad_parts, "Device:R", high_net, tap_net)
    bottom = _parts_on(design, two_pad_parts, "Device:R", tap_net, low_net)
    assert len(top) == 1 and len(bottom) == 1, (
        f"expected one resistor from {high_net} to {tap_net} and one from "
        f"{tap_net} to {low_net}, found {top} and {bottom}"
    )
    return spec(top[0], "resistance"), spec(bottom[0], "resistance")


def _capacitance_on(design, two_pad_parts, spec, net_a, net_b, block=None,
                    effective=None, bias=None):
    """
    (low, high) total capacitance between two nets, optionally one block's.

    With `effective` and `bias`, the low end is what the parts are worth at
    that DC bias rather than what is printed on them - see
    `capacitors.bias_derating`. Every datasheet *minimum* here is held against
    that; no maximum is, because a ceramic does not gain capacitance.

    `block` matters wherever a datasheet asks for capacitance *at a pin*
    rather than on a rail. Without it, the 3V3 buck's "input capacitance"
    was every capacitor on the 5 V net - the 5 V buck's own output bulk and
    all seven comparator bypasses included, 25.7 uF of it - so the part
    actually fitted at its VIN pin could have been deleted and the check
    would still have passed. The design says which capacitor belongs to which
    converter in the addresses it builds them under, so that is what this
    reads.
    """
    low = high = 0.0
    for address in _parts_on(design, two_pad_parts, "Device:C", net_a, net_b):
        if block is not None and not address.startswith(f"{block}."):
            continue
        a, b = spec(address, "capacitance")
        if effective is not None:
            a = effective(address, bias)
        low, high = low + a, high + b
    return low, high


def _rail_typical(design, two_pad_parts, spec, rail, tap, regulator):
    """The rail a feedback divider sets, at typical values."""
    (r1_low, r1_high), (r2_low, r2_high) = _divider(
        design, two_pad_parts, spec, rail, tap, "GND"
    )
    v_low, v_high = spec(regulator, "v_feedback")
    return (v_low + v_high) / 2 * (1 + (r1_low + r1_high) / (r2_low + r2_high))


# --- the input stage ---------------------------------------------------------


def test_the_tvs_stands_off_the_rail_it_protects(spec):
    """
    The TVS holds off the highest voltage the input is specified to reach.

    Above its stand-off voltage a TVS is in its knee, drawing leakage nobody
    bounds and heating itself, and because avalanche breakdown has a positive
    temperature coefficient a part that merely leaks when warm conducts hard
    when cold. led12 shipped a 12 V part on a 13.2 V rail for exactly this
    reason; the check is what caught it.
    """
    _, input_high = spec("input", "voltage")
    stand_off, _ = spec(TVS, "reverse_working_voltage")
    assert stand_off > input_high, (
        f"{TVS} stands off {stand_off:g} V on an input specified to "
        f"{input_high:g} V. The protection is a load at high line."
    )


def test_the_buck_is_rated_well_above_the_tvs_clamp(spec):
    """
    The 100 V buck survives what the TVS lets through, with room.

    A TVS does not hold the rail at its stand-off voltage during a surge - it
    holds it at its clamping voltage, which for a 40 V part is 64.5 V. Choosing
    a regulator by the *rail* voltage rather than by the clamp is how led12
    ended up with a part rated 3 % above what its own protection produced.
    """
    clamp, _ = spec(TVS, "v_clamp_max")
    rating, _ = spec(BUCK_5V, "v_in_abs_max")
    assert rating >= clamp * SURGE_MARGIN, (
        f"{BUCK_5V} is rated {rating:g} V against a {clamp:g} V clamp: "
        f"{rating / clamp:.2f}x, and {SURGE_MARGIN}x is the least worth having."
    )


def test_every_capacitor_on_the_input_survives_an_unclamped_overvoltage(
    design, two_pad_parts, spec
):
    """
    The input capacitors are rated above the TVS's breakdown, not its stand-off.

    Between the stand-off voltage and the top of the breakdown band the TVS
    does nothing at all, so a supply stuck anywhere in that range leaves the
    rail unprotected and the capacitors holding it. Which capacitors those are
    comes from the netlist, so one added later is covered too.
    """
    breakdown, _ = spec(TVS, "v_breakdown_max")
    weak = []
    for net in ("VIN", "VIN_FUSED", "VIN_RAW"):
        for address in _parts_on(design, two_pad_parts, "Device:C", net, "GND"):
            rating, _ = spec(address, "max_voltage")
            if rating < breakdown:
                weak.append(f"  {address} on {net}: {rating:g} V")
    assert not weak, (
        f"Capacitors on the input rated below the TVS's {breakdown:g} V "
        "breakdown maximum:\n" + "\n".join(weak)
    )


def test_the_reverse_polarity_fet_blocks_the_whole_input(spec):
    """
    The FET is rated for the input reversed, at twice the voltage it must block.

    The TVS sits behind this FET, on the protected rail, so a reversed supply
    is not clamped by anything: the FET holds all of it off. That is the
    deliberate trade for the board doing nothing at all when the terminal is
    wired backwards, rather than blowing its fuse.
    """
    _, input_high = spec("input", "voltage")
    rating, _ = spec(FET, "max_drain_source_voltage")
    assert rating >= 2 * input_high, (
        f"{FET} is rated {rating:g} V against {input_high:g} V reversed across "
        "it, and nothing clamps a negative transient below that."
    )


def test_the_gate_clamp_keeps_the_fet_inside_its_rating_and_still_turns_it_on(spec):
    """
    The gate Zener sits between the FET's threshold and its gate-source rating.

    The gate is at ground through R6, so V_gs is the whole input voltage: 36 V
    in normal operation and up to the TVS's clamp during a surge, both beyond
    any small-signal MOSFET. The Zener has to clamp below the rating and still
    leave the FET fully enhanced at the lowest input.
    """
    v_low, v_high = spec(ZENER, "zener_voltage")
    rating, _ = spec(FET, "max_gate_source_voltage")
    _, threshold_high = spec(FET, "gate_source_threshold_voltage")
    input_low, _ = spec("input", "voltage")

    assert v_high < rating, (
        f"the clamp lets V_gs reach {v_high:g} V against a {rating:g} V rating"
    )
    assert v_low > threshold_high, (
        f"the clamp holds V_gs at {v_low:g} V against a threshold as high as "
        f"{threshold_high:g} V: the FET would not be fully on"
    )
    assert input_low > threshold_high, (
        f"at {input_low:g} V in, V_gs is {input_low:g} V against a threshold as "
        f"high as {threshold_high:g} V"
    )


def test_the_gate_clamp_survives_conducting_through_a_surge(design, two_pad_parts, spec):
    """
    The Zener and the resistor feeding it stay inside their ratings while the
    rail is at the TVS's clamp.

    This clamp conducts in normal operation - anything above its voltage on a
    rail specified to 36 V does - so unlike led12's it is a part that runs warm
    by design. What bounds the current is the gate resistor, and what sets the
    worst case is the clamp rather than the rail, because both parts are small
    enough that a surge is not obviously short compared with their thermal mass.
    """
    clamp, _ = spec(TVS, "v_clamp_max")
    v_low, v_high = spec(ZENER, "zener_voltage")
    rated, _ = spec(ZENER, "max_power")
    gate = _parts_on(design, two_pad_parts, "Device:R", "RPP_GATE", "GND")
    assert len(gate) == 1, f"expected one gate resistor to ground, found {gate}"
    resistance, _ = spec(gate[0], "resistance")
    resistor_rating, _ = spec(gate[0], "max_power")

    current = (clamp - v_low) / resistance
    assert v_high * current <= rated * _derating(spec), (
        f"{ZENER} dissipates {v_high * current * 1e3:.0f} mW at the clamp, "
        f"against {rated * 1e3:g} mW derated by half"
    )
    assert (clamp - v_low) ** 2 / resistance <= resistor_rating * _derating(spec), (
        f"{gate[0]} dissipates "
        f"{(clamp - v_low) ** 2 / resistance * 1e3:.0f} mW at the clamp"
    )


def test_the_fuse_carries_the_board_and_opens_at_the_rail_it_protects(design, spec):
    """
    The fuse passes the board's own draw with margin, and can break the rail.

    The current comes from the rails' declared budgets and the efficiency the
    design assumes, at the lowest input - which is where the input current is
    highest. The voltage rating is against the top of the TVS's breakdown band,
    because that is the most the rail can reach while the TVS still does
    nothing, and the fuse may have to open against it.
    """
    trip, _ = spec(FUSE, "trip_current")
    rating, _ = spec(FUSE, "max_voltage")
    breakdown, _ = spec(TVS, "v_breakdown_max")
    draw = _input_current(spec)

    assert trip >= draw * FUSE_MARGIN, (
        f"a {trip:g} A fuse against {draw:.2f} A drawn at the lowest input: "
        f"{trip / draw:.2f}x, and {FUSE_MARGIN}x is the least for a part that "
        "ages every time it is warm."
    )
    assert rating >= breakdown, (
        f"the fuse is rated {rating:g} V and may have to open a rail at "
        f"{breakdown:g} V"
    )


def _reflected_current(spec) -> float:
    """What the 3V3 rail's budget costs the 5 V rail.

    The 3V3 buck's input pin is on the 5 V net, so every milliamp the logic
    rail delivers is drawn again through the 5 V rail, divided by that buck's
    efficiency. Budgeting the two rails separately is how this board came to
    ask a 1 A converter for 1.36 A and a 1 A fuse for 1.04 A, with every check
    passing: the only place the two were ever added was the copper.
    """
    _, v3v3_high = spec("rail.3v3", "voltage")
    _, i3v3_high = spec("rail.3v3", "current")
    efficiency_low, _ = spec("buck3v3", "efficiency")
    v5_low, _ = spec("rail.5v", "voltage")
    return v3v3_high * i3v3_high / (efficiency_low * v5_low)


def _five_volt_current(spec) -> float:
    """Everything the 5 V converter delivers: its own rail, and the 3V3 buck."""
    _, i5_high = spec("rail.5v", "current")
    return i5_high + _reflected_current(spec)


def _input_current(spec) -> float:
    """The most the board draws at its terminal, from the rails' own budgets."""
    _, v5_high = spec("rail.5v", "voltage")
    efficiency_low, _ = spec("power", "efficiency")
    input_low, _ = spec("input", "voltage")
    return v5_high * _five_volt_current(spec) / (efficiency_low * input_low)


def test_the_fet_carries_what_the_fuse_allows(spec):
    """
    The FET passes the fuse's rating, not just the board's draw.

    A pass element that opens before the fuse does is the fuse, and a worse one:
    the current it takes to destroy it is not specified anywhere.
    """
    trip, _ = spec(FUSE, "trip_current")
    rating, _ = spec(FET, "max_continuous_drain_current")
    assert rating >= trip, (
        f"{FET} carries {rating:g} A and the fuse allows {trip:g} A"
    )


def test_the_input_reaches_the_buck_above_its_lowest_operating_voltage(spec):
    """What the FET drops still leaves the converter inside its input range."""
    input_low, input_high = spec("input", "voltage")
    resistance, _ = spec(FET, "on_resistance")
    operating_low, operating_high = spec(BUCK_5V, "v_in")
    at_the_pin = input_low - _input_current(spec) * resistance
    assert at_the_pin >= operating_low, (
        f"{at_the_pin:.2f} V reaches the converter at the lowest input, and it "
        f"needs {operating_low:g} V"
    )
    assert input_high <= operating_high, (
        f"the input is specified to {input_high:g} V and the converter to "
        f"{operating_high:g} V"
    )


# --- the 100 V buck ----------------------------------------------------------


def test_the_switching_frequency_is_the_one_intended(design, two_pad_parts, spec):
    """
    The on-time resistor lands the frequency in the band the design asked for,
    and inside what the part can do at both ends of the input range.
    """
    _, frequency, r_on = _frequency(design, two_pad_parts, spec)
    wanted_low, wanted_high = spec("buck5", "switching_frequency")
    ceiling, _ = spec(BUCK_5V, "switching_frequency_max")
    assert wanted_low <= frequency <= wanted_high, (
        f"{r_on / 1e3:g} kOhm gives {frequency / 1e3:.0f} kHz, outside the "
        f"{wanted_low / 1e3:g} to {wanted_high / 1e3:g} kHz intended"
    )
    assert frequency <= ceiling, f"{frequency / 1e3:.0f} kHz is above the part's maximum"


def test_the_on_time_stays_above_the_shortest_the_part_can_make(design, two_pad_parts, spec):
    """
    At the highest input the on-time is shortest, and it has a floor.

    Below it the converter skips pulses and the output ripples at whatever rate
    it settles into instead of the one everything else here assumes.
    """
    k, _, r_on = _frequency(design, two_pad_parts, spec)
    floor, _ = spec(BUCK_5V, "on_time_min")
    _, input_high = spec("input", "voltage")
    shortest = k * r_on / input_high
    assert shortest >= floor, (
        f"{shortest * 1e9:.0f} ns at {input_high:g} V in, against a "
        f"{floor * 1e9:g} ns floor"
    )


def test_the_5v_feedback_divider_holds_the_rail_inside_its_band(design, two_pad_parts, spec):
    """
    Worst case over the reference's band, the resistors' tolerance and the DC
    error the ripple injection costs, the rail stays where it was declared.

    A constant-on-time converter regulates the *valley* of the feedback ripple
    to its reference, so the output sits about half the injected ripple high,
    scaled back up through the divider. The datasheet says so in as many words,
    and it is the one error a divider calculation alone misses.
    """
    rail_low, rail_high = spec("rail.5v", "voltage")
    (r1_low, r1_high), (r2_low, r2_high) = _divider(
        design, two_pad_parts, spec, "5V", "FB_5V", "GND"
    )
    v_low, v_high = spec(BUCK_5V, "v_feedback")
    gain_low, gain_high = 1 + r1_low / r2_high, 1 + r1_high / r2_low
    offset = _ripple_at_feedback(design, two_pad_parts, spec)[1] / 2 * gain_high

    assert v_low * gain_low >= rail_low, (
        f"worst case the rail falls to {v_low * gain_low:.3f} V, below "
        f"{rail_low:g} V"
    )
    assert v_high * gain_high + offset <= rail_high, (
        f"worst case the rail rises to {v_high * gain_high + offset:.3f} V "
        f"(including {offset * 1e3:.0f} mV of ripple offset), above "
        f"{rail_high:g} V"
    )


def _ripple_at_feedback(design, two_pad_parts, spec):
    """
    (lowest, highest) ripple the Type 3 network puts on the feedback pin.

    The switch node is a square wave between the input and ground at duty
    V_out / V_in, so the ramp across C_A - and therefore at the feedback pin,
    which C_B couples it to - is

        V_ripple = V_out * (V_in - V_out) / (V_in * f * R_A * C_A)

    Not read from the datasheet: its equations are figures with no text layer.
    Derived here from the network, and checked against the datasheet's own
    worked example - 48 V in, 12 V out, 300 kHz, 453 kOhm and 3.3 nF - which it
    reproduces as 20.07 mV against the 20 mV that example states.
    """
    ramp = _parts_on(design, two_pad_parts, "Device:R", "SW_5V", "RAMP")
    assert len(ramp) == 1, f"expected one resistor from the switch node to the ramp, found {ramp}"
    r_low, r_high = spec(ramp[0], "resistance")
    c_low, c_high = _capacitance_on(design, two_pad_parts, spec, "RAMP", "5V")
    _, frequency, _ = _frequency(design, two_pad_parts, spec)
    v_out = _rail_typical(design, two_pad_parts, spec, "5V", "FB_5V", BUCK_5V)

    input_low, input_high = spec("input", "voltage")

    def at(v_in, r, c):
        return v_out * (v_in - v_out) / (v_in * frequency * r * c)

    # Ripple falls as R and C rise, so the *smallest* ripple - the one the
    # floor check below is about - is at the top of both tolerance bands, and
    # at the lowest input. Both were taken at `[0]`, the bottom of the bands,
    # which is the corner that makes the ripple look largest: the floor was
    # being checked against a number 25 % higher than the board can promise.
    return at(input_low, r_high, c_high), at(input_high, r_low, c_low)


def _frequency(design, two_pad_parts, spec):
    """
    The 100 V buck's switching frequency in continuous conduction, from parts.

    Its on-time is inversely proportional to the input voltage and set by one
    resistor, so a single characterised point fixes the constant:

        t_on = k * R_on / V_in,  k = t_on(ref) * V_in(ref) / R_on(ref)

    The datasheet gives four on-times; this uses the 12 V, 75 kOhm one. Three
    of the four agree with the constant that point implies to within 2 %, and
    section 8.2.2.2's worked example - "a standard 100 kOhm 1 % resistor sets
    the switching frequency at 300 kHz" for a 12 V output - agrees exactly.
    The fourth, 650 ns at 6 V and 25 kOhm, does not agree with anything: it is
    a quarter of what the other three imply and reads like a dropped digit.
    That is recorded in `parts/SO8EP/SO8EP.md`.

    In continuous conduction the duty cycle is V_out / V_in, so the frequency
    is D / t_on = V_out / (k * R_on) and does not depend on the input.
    """
    t_on, _ = spec(BUCK_5V, "on_time_at_reference")
    r_ref, _ = spec(BUCK_5V, "on_time_reference_resistance")
    v_ref, _ = spec(BUCK_5V, "on_time_reference_input_voltage")
    k = t_on * v_ref / r_ref
    on_time = _parts_on(design, two_pad_parts, "Device:R", "RON", "GND")
    assert len(on_time) == 1, (
        f"RON reaches ground through {len(on_time)} resistors ({on_time}); the "
        f"frequency below is worked from one of them and would be wrong"
    )
    r_on, _ = spec(on_time[0], "resistance")
    v_out = _rail_typical(design, two_pad_parts, spec, "5V", "FB_5V", BUCK_5V)
    return k, v_out / (k * r_on), r_on


def test_the_ripple_network_gives_the_comparator_enough_to_see(design, two_pad_parts, spec):
    """
    The injected ripple clears the datasheet's minimum at the lowest input.

    A constant-on-time converter regulates on a comparator, and a comparator
    needs a slope. Without enough ripple at the feedback pin the converter
    bursts - several on-times in quick succession, then a long silence - which
    is stable enough to miss on a bench and audible in the inductor. The ripple
    is smallest at the lowest input, which is the case this checks.
    """
    smallest, largest = _ripple_at_feedback(design, two_pad_parts, spec)
    floor, _ = spec(BUCK_5V, "feedback_ripple_min")
    target, _ = spec(BUCK_5V, "feedback_ripple_target")
    assert smallest >= floor, (
        f"{smallest * 1e3:.1f} mV at the lowest input, against a "
        f"{floor * 1e3:g} mV minimum"
    )
    assert smallest <= target <= largest, (
        f"the ripple runs {smallest * 1e3:.1f} to {largest * 1e3:.1f} mV across "
        f"the input range and never passes the {target * 1e3:g} mV the "
        "datasheet asks for at typical conditions"
    )


def test_the_lockout_starts_the_board_at_the_lowest_input_it_claims(design, two_pad_parts, spec):
    """
    The enable divider turns the converter on below the lowest declared input.

    Otherwise the board's specification is a lie in the most confusing
    direction: it sits dark at a voltage its own documentation says it takes.
    """
    (r1_low, r1_high), (r2_low, r2_high) = _divider(
        design, two_pad_parts, spec, "VIN", "UVLO", "GND"
    )
    v_low, v_high = spec(BUCK_5V, "enable_threshold")
    wanted_low, wanted_high = spec("input", "lockout")
    turn_on_low = v_low * (1 + r1_low / r2_high)
    turn_on_high = v_high * (1 + r1_high / r2_low)
    assert turn_on_high <= wanted_high, (
        f"worst case the board starts at {turn_on_high:.2f} V, above the "
        f"{wanted_high:g} V it must start below"
    )
    assert turn_on_low >= wanted_low, (
        f"worst case the board starts at {turn_on_low:.2f} V, below the "
        f"{wanted_low:g} V lockout it is meant to have"
    )


def test_the_load_each_rail_carries_is_inside_its_regulator(spec):
    """
    Each converter's rated output covers the budget declared for its rail.

    The 5 V converter's share is its own rail *plus* the 3V3 buck it feeds -
    see `_reflected_current`. The 3V3 buck's is its rail alone, because
    nothing runs from 3V3 to make another rail.
    """
    i5 = _five_volt_current(spec)
    _, i3v3 = spec("rail.3v3", "current")
    rating_5v, _ = spec(BUCK_5V, "load_current_max")
    limit_3v3, _ = spec(BUCK_3V3, "current_limit_min")
    assert rating_5v >= i5, (
        f"the 5 V converter carries {i5:.3f} A - its own rail's budget plus "
        f"{_reflected_current(spec):.3f} A for the 3V3 buck it feeds - from a "
        f"{rating_5v:g} A part"
    )
    assert limit_3v3 >= i3v3, (
        f"the 3V3 rail is budgeted {i3v3:g} A against a current limit as low as "
        f"{limit_3v3:g} A"
    )


# --- the inductors -----------------------------------------------------------


def _peak_current(inductance, frequency, v_in, v_out, load):
    ripple = v_out * (v_in - v_out) / (v_in * frequency * inductance)
    return load + ripple / 2


def test_the_inductors_are_never_the_first_thing_to_give_way(design, two_pad_parts, spec):
    """
    Each inductor's saturation current clears the converter's own peak limit.

    An inductor that saturates first takes the decision away from the part that
    has a current limit and a fold-back for exactly this: the current rises
    without limit inside one switching cycle and the converter's protection
    never sees a slope it can act on. So the comparison here is not against the
    load - it is against the highest current the converter will allow before it
    intervenes.

    Ripple is worst at the lowest inductance and the highest input, so both are
    taken at their worst.
    """
    _, frequency_5v, _ = _frequency(design, two_pad_parts, spec)
    _, input_high = spec("input", "voltage")
    _, v5_high = spec("rail.5v", "voltage")
    v5 = _rail_typical(design, two_pad_parts, spec, "5V", "FB_5V", BUCK_5V)
    v3v3 = _rail_typical(design, two_pad_parts, spec, "3V3", "FB_3V3", BUCK_3V3)
    frequency_3v3, _ = spec(BUCK_3V3, "switching_frequency")
    # Everything the 5 V converter delivers, not what the 5 V rail's own
    # budget is: L1 sits between the switch node and the rail, so the 3V3
    # buck's input current goes through it too. Budgeting the two separately
    # is the defect that had a 1 A converter asked for 1.36 A, and it had
    # survived here.
    load_5v = _five_volt_current(spec)
    _, load_3v3 = spec("rail.3v3", "current")

    cases = [
        ("SW_5V", "5V", frequency_5v, input_high, v5, load_5v,
         spec(BUCK_5V, "peak_current_limit_min")[0]),
        ("SW_3V3", "3V3", frequency_3v3, v5_high, v3v3, load_3v3,
         spec(BUCK_3V3, "current_limit_min")[0]),
    ]
    problems = []
    for switch, rail, frequency, v_in, v_out, load, limit in cases:
        found = _parts_on(design, two_pad_parts, "Device:L", switch, rail)
        assert len(found) == 1, f"expected one inductor between {switch} and {rail}, found {found}"
        address = found[0]
        inductance, _ = spec(address, "inductance")
        saturation, _ = spec(address, "saturation_current")
        rms, _ = spec(address, "rms_current")
        peak = _peak_current(inductance, frequency, v_in, v_out, load)
        if saturation < limit:
            problems.append(
                f"  {address}: saturates at {saturation:g} A, below the "
                f"{limit:g} A the converter allows before it acts"
            )
        if peak > limit:
            problems.append(
                f"  {address}: peaks at {peak:.2f} A in normal operation, past "
                f"the {limit:g} A current limit"
            )
        if rms < load:
            problems.append(f"  {address}: rated {rms:g} A rms against {load:g} A")
    assert not problems, "Inductors:\n" + "\n".join(problems)


def test_the_inductors_do_not_spend_the_efficiency_the_design_assumes(
    design, two_pad_parts, spec
):
    """
    Each inductor's winding loss is a fraction of the loss budget, not all of it.

    A part chosen on saturation current alone can have any resistance at all,
    and on these two rails the winding is in series with everything the board
    draws. The budget is what the declared efficiency leaves over; an inductor
    spending more than a third of it is the wrong part even if it never
    saturates.
    """
    efficiency_low, _ = spec("power", "efficiency")
    cases = [
        # As above: the 5 V winding carries the 3V3 buck's draw as well.
        ("SW_5V", "5V", spec("rail.5v", "voltage")[1], _five_volt_current(spec)),
        ("SW_3V3", "3V3", spec("rail.3v3", "voltage")[1], spec("rail.3v3", "current")[1]),
    ]
    problems = []
    for switch, rail, voltage, load in cases:
        address = _parts_on(design, two_pad_parts, "Device:L", switch, rail)[0]
        resistance, _ = spec(address, "dc_resistance")
        loss = load**2 * resistance
        budget = (1 - efficiency_low) * voltage * load
        if loss > budget / 3:
            problems.append(
                f"  {address}: {loss * 1e3:.0f} mW of winding loss against a "
                f"{budget * 1e3:.0f} mW budget for the whole conversion"
            )
    assert not problems, "Inductor losses:\n" + "\n".join(problems)


# --- the 3V3 buck ------------------------------------------------------------


def test_the_3v3_feedback_divider_holds_the_rail_inside_its_band(design, two_pad_parts, spec):
    """
    Worst case over the reference's band and the resistors' tolerance, the logic
    rail stays where the MCU's checks assume it is.

    No ripple offset here: this converter injects its own ramp internally, which
    is the whole point of the control scheme, so the divider is the rail.
    """
    rail_low, rail_high = spec("rail.3v3", "voltage")
    (r1_low, r1_high), (r2_low, r2_high) = _divider(
        design, two_pad_parts, spec, "3V3", "FB_3V3", "GND"
    )
    v_low, v_high = spec(BUCK_3V3, "v_feedback")
    low = v_low * (1 + r1_low / r2_high)
    high = v_high * (1 + r1_high / r2_low)
    assert low >= rail_low, f"worst case the rail falls to {low:.3f} V, below {rail_low:g} V"
    assert high <= rail_high, f"worst case the rail rises to {high:.3f} V, above {rail_high:g} V"


def test_the_3v3_converter_runs_from_the_rail_that_feeds_it(spec):
    """The 5 V rail's whole band is inside the 3V3 converter's input range."""
    rail_low, rail_high = spec("rail.5v", "voltage")
    operating_low, operating_high = spec(BUCK_3V3, "v_in")
    assert operating_low <= rail_low and rail_high <= operating_high, (
        f"the 5 V rail runs {rail_low:g} to {rail_high:g} V and the converter "
        f"takes {operating_low:g} to {operating_high:g} V"
    )


def test_the_3v3_output_filter_is_the_one_the_datasheet_specifies(
    design, two_pad_parts, spec, effective_capacitance
):
    """
    Inductance and output capacitance inside the datasheet's table for 3.3 V.

    This converter has no external compensation: the double pole of its output
    filter has to sit where the control scheme's internal zero expects it, and
    the datasheet gives that as a range of L and C rather than an equation. The
    capacitance is the whole rail's, because the whole rail is the filter - the
    MCU's decoupling is part of it whether it was chosen to be or not.
    """
    inductance = _parts_on(design, two_pad_parts, "Device:L", "SW_3V3", "3V3")[0]
    l_low, l_high = spec(inductance, "inductance")
    wanted_l_low, wanted_l_high = spec(BUCK_3V3, "inductance")
    assert wanted_l_low <= l_low and l_high <= wanted_l_high, (
        f"{inductance} is {l_low * 1e6:.1f} to {l_high * 1e6:.1f} uH, outside "
        f"the {wanted_l_low * 1e6:g} to {wanted_l_high * 1e6:g} uH specified"
    )

    # The low end is what the rail's capacitors are worth *at 3.3 V of bias*,
    # not what is printed on them. The high end is not derated: a ceramic does
    # not gain capacitance, so the ceiling has to be cleared by the label.
    _, bias = spec("rail.3v3", "voltage")
    c_low, _ = _capacitance_on(design, two_pad_parts, spec, "3V3", "GND",
                               effective=effective_capacitance, bias=bias)
    _, c_high = _capacitance_on(design, two_pad_parts, spec, "3V3", "GND")
    wanted_c_low, wanted_c_high = spec(BUCK_3V3, "output_capacitance")
    assert wanted_c_low <= c_low and c_high <= wanted_c_high, (
        f"the 3V3 rail carries {c_low * 1e6:.1f} uF at {bias:.2f} V of bias "
        f"and {c_high * 1e6:.1f} uF on the reel, outside the "
        f"{wanted_c_low * 1e6:g} to {wanted_c_high * 1e6:g} uF specified. "
        "Adding decoupling moves this."
    )


def test_each_converter_has_its_bootstrap_and_input_capacitance(
    design, two_pad_parts, spec, effective_capacitance
):
    """
    The bootstrap capacitor and the input capacitance each datasheet asks for.

    The bootstrap is the one value where more is not safer: it supplies the
    high-side gate driver and the datasheet bounds it at both ends.

    **The two parts state it differently, and that decides whether the bias
    model applies.** The LM5164 gives a range and says why either end is
    fatal - below it "is not sufficient to drive the internal gate", above it
    "stresses the internal VCC regulator and damages the device" - so the
    *effective* capacitance at the 5 V its internal regulator puts across the
    part is the thing that has to be in range, and it is held to that here.
    The TPS562200 says "connect a 0.1 uF capacitor between VBST and SW",
    which specifies a part to fit rather than a minimum to exceed: no 100 nF
    part can deliver 100 nF effective, its own tolerance forbids it before
    bias takes anything, so reading it as a floor would reject every part
    that satisfies it. Its band is compared against the nominal, and that
    difference is written down here rather than left to be noticed.
    """
    problems = []
    for regulator, switch, bootstrap, supply in (
        (BUCK_5V, "SW_5V", "BST_5V", "VIN"),
        (BUCK_3V3, "SW_3V3", "BST_3V3", "5V"),
    ):
        wanted = spec(regulator, "bst_capacitance")
        found = _capacitance_on(design, two_pad_parts, spec, bootstrap, switch)
        if not _inside(found, wanted):
            problems.append(
                f"  {regulator}: {found[0] * 1e9:.1f} to {found[1] * 1e9:.1f} nF "
                f"of bootstrap, outside {wanted[0] * 1e9:g} to {wanted[1] * 1e9:g} nF"
            )
        _, bst_bias = spec(regulator, "bst_voltage_max")
        if wanted[0] < wanted[1]:
            worth, _ = _capacitance_on(
                design, two_pad_parts, spec, bootstrap, switch,
                effective=effective_capacitance, bias=bst_bias)
            if worth < wanted[0]:
                problems.append(
                    f"  {regulator}: {worth * 1e9:.2f} nF of bootstrap at "
                    f"{bst_bias:g} V of bias, against the {wanted[0] * 1e9:g} nF "
                    f"its datasheet calls the least that will drive the gate"
                )
        minimum, _ = spec(regulator, "input_capacitance_min")
        block = regulator.rpartition(".")[0]
        # The bias here is the supply the capacitor sits on, which for the
        # 3V3 converter is the 5 V rail: at 10 V rated that was half the
        # part's capacitance gone, and the check compared the label.
        _, bias = spec("input" if supply == "VIN" else f"rail.{supply.lower()}",
                       "voltage")
        input_low, _ = _capacitance_on(
            design, two_pad_parts, spec, supply, "GND", block=block,
            effective=effective_capacitance, bias=bias)
        if input_low < minimum:
            problems.append(
                f"  {regulator}: {input_low * 1e6:.1f} uF of its own on "
                f"{supply} at {bias:.2f} V of bias, against {minimum * 1e6:g} uF "
                f"asked for"
            )
    assert not problems, "Converter capacitors:\n" + "\n".join(problems)


def test_the_power_good_pull_up_is_in_the_range_the_part_allows(design, two_pad_parts, spec):
    """An open-drain output with a pull-up the datasheet bounds at both ends."""
    wanted_low, wanted_high = spec(BUCK_5V, "pgood_pullup")
    found = _parts_on(design, two_pad_parts, "Device:R", "PGOOD", "3V3")
    assert len(found) == 1, f"expected one pull-up on PGOOD, found {found}"
    low, high = spec(found[0], "resistance")
    assert wanted_low <= low and high <= wanted_high, (
        f"{found[0]} is {low / 1e3:.1f} to {high / 1e3:.1f} kOhm, outside "
        f"{wanted_low / 1e3:g} to {wanted_high / 1e3:g} kOhm"
    )


# --- the reference -----------------------------------------------------------


def test_the_reference_is_below_the_analog_supply_it_sits_under(
    design, pad_net, spec
):
    """
    VREF+ never exceeds VDDA, which is the logic rail through a ferrite.

    The MCU's reference input is specified up to VDDA and no further, and VDDA
    here is 3V3 less a few millivolts across the bead. So the comparison that
    matters is the reference's highest against the rail's lowest.
    """
    _, reference_high = spec(REFERENCE, "output_voltage")
    rail_low, _ = spec("rail.3v3", "voltage")

    # **The bead's drop, which this used to describe and not compute.** The
    # docstring said VDDA is "3V3 less a few millivolts across the bead" and
    # then compared against the bare rail. ST states no VDDA-only current, so
    # there is nothing in the datasheet to multiply by - but this board bounds
    # it anyway: the bead is rated 100 mA and this board runs nothing past
    # half of any thermal rating, so 50 mA through 0.9 ohm is the most it can
    # drop whatever the MCU's analog section draws. Both of the bead's figures
    # were on the unread list for want of exactly this.
    beads = [address for address, part in design["parts"].items()
             if part["symbol"] == "Device:FerriteBead_Small"
             and {pad_net.get((address, "1")),
                  pad_net.get((address, "2"))} == {"3V3", "VDDA"}]
    assert len(beads) == 1, f"VDDA reaches 3V3 through {beads}"
    _, carries = spec(beads[0], "max_current")
    _, ohms = spec(beads[0], "dc_resistance")
    vdda_low = rail_low - carries * _derating(spec) * ohms

    assert reference_high < vdda_low, (
        f"the reference reaches {reference_high:g} V and VDDA falls to "
        f"{vdda_low:.3f} V - the rail's {rail_low:g} V less {carries * _derating(spec) * ohms * 1e3:.0f} mV "
        f"across {beads[0]} at the most this board will run it at"
    )


def _current_at_dropout(curve, available: float) -> float:
    """The load at which a reference's dropout uses up the headroom it has."""
    if available <= 0.0:
        return 0.0
    if available >= curve[-1][1]:
        return curve[-1][0]
    if available <= curve[0][1]:
        return curve[0][0] * available / curve[0][1]
    for (i0, v0), (i1, v1) in zip(curve, curve[1:]):
        if available <= v1:
            return i0 + (i1 - i0) * (available - v0) / (v1 - v0)
    return curve[-1][0]


def test_the_reference_runs_from_the_rail_it_is_given(design, two_pad_parts, pad_net, spec):
    """
    Its supply is inside the part's range, it clears its own dropout, its
    bypass is what it asks for - and it is the *same rail VDDA comes from*.

    **That last one is a sequencing requirement, not a steady-state one**, and
    it is the whole reason this reads the netlist for the supply net instead
    of being told "5V". The MCU specifies VREF+ up to VDDA with an absolute
    maximum of VDDA + 0.4, and a reference on a rail that comes up first
    breaks that for as long as the second rail takes to start. On this board
    the order was forced by the topology: 3V3's converter takes its input and
    its enable from the 5 V rail, so it cannot start until 5 V has cleared its
    UVLO, by which time a reference on 5 V has been regulating for a while.
    A millisecond of soft-start with VREF+ up to 3 V above VDDA, on every
    power cycle, through a structure with no positive-injection allowance.

    So what is asserted is that the reference's supply reaches VDDA through
    nothing but two-terminal passives - the ferrite - which makes "VREF+
    cannot rise before VDDA" a property of the topology rather than a timing
    argument. Move the reference back to a separate rail and this fails.
    """
    supply = pad_net[(REFERENCE, "1")]

    # Nets walked from VDDA through series supply elements. A ferrite or an
    # inductor in a rail keeps you on the same rail; a converter does not, and
    # neither does a resistor - following resistors walks out of the supply
    # network entirely through the first pull-up and arrives at every rail on
    # the board, which is how the first version of this passed its own
    # break-test.
    passives = []
    for address, part in design["parts"].items():
        if part["symbol"] not in ("Device:L", "Device:FerriteBead_Small"):
            continue
        ends = [net for net, nodes in design["nets"].items()
                if any(a == address for a, _ in nodes)]
        if len(ends) == 2:
            passives.append(tuple(ends))
    seen, edge = {"VDDA"}, ["VDDA"]
    while edge:
        net = edge.pop()
        for a, b in passives:
            far = b if a == net else a if b == net else None
            if far and far not in seen:
                seen.add(far)
                edge.append(far)
    assert supply in seen, (
        f"the reference is powered from {supply}, and VDDA is reached from "
        f"{sorted(seen)}. A reference on a rail of its own comes up when that "
        f"rail does, which on this board is before VDDA exists."
    )

    rail = f"rail.{supply.lower()}"
    rail_low, rail_high = spec(rail, "voltage")
    limit, _ = spec(REFERENCE, "v_in_max")
    assert rail_high <= limit, (
        f"the {supply} rail reaches {rail_high:g} V and the reference takes {limit:g} V"
    )
    _, output_high = spec(REFERENCE, "output_voltage")
    headroom, _ = spec(REFERENCE, "supply_headroom")
    assert rail_low >= output_high + headroom, (
        f"the {supply} rail falls to {rail_low:g} V and the reference needs "
        f"{output_high:g} + {headroom * 1e3:g} mV to regulate"
    )

    # **And at the current the board promises, not unloaded.** That 1 mV is
    # the no-load dropout - the datasheet's description says so - and the real
    # figure is a curve, about 10 mV per milliamp. VREF+ leaves this board on
    # a connector pin with no series element and the power board's sensors are
    # ratiometric to it, so something out there draws from it; until
    # `vref.supply_current` was declared, nothing said how much, and the
    # check above was comparing 129 mV of headroom against a figure that
    # assumed nobody was connected.
    _, promised = spec("vref", "supply_current")
    curve = sorted(
        (amps, spec(REFERENCE, f"dropout_at_{name}")[1])
        for amps, name in ((5e-3, "5ma"), (10e-3, "10ma"),
                           (20e-3, "20ma"), (25e-3, "25ma"))
    )
    quiescent, _ = spec(REFERENCE, "quiescent_current_max")
    drawn = promised + quiescent
    # **One assertion against whichever of the two actually binds.** Asserting
    # the part's 25 mA separately was theatre: the headroom runs out at
    # 12.9 mA, so the capability assertion needed `promised > 25 mA` and could
    # never be reached. Taking the smaller of the two and naming it means both
    # figures are read, the binding one is reported, and the check still works
    # on a board where the rail has room to spare and the part does not.
    _, capable = spec(REFERENCE, "output_current_max")
    headroom_limit = _current_at_dropout(curve, rail_low - output_high)
    allowed, why = min(
        (capable, f"{REFERENCE} can supply {capable * 1e3:g} mA"),
        (headroom_limit,
         f"the {supply} rail leaves {(rail_low - output_high) * 1e3:.0f} mV of "
         f"headroom, which this part's dropout curve reaches at "
         f"{headroom_limit * 1e3:.1f} mA"),
    )
    assert drawn <= allowed, (
        f"the board promises the power board {promised * 1e3:g} mA out of "
        f"VREF+, plus {50e-6 * 1e6:g} uA of quiescent, and {why}"
    )
    wanted, _ = spec(REFERENCE, "supply_bypass")
    # The reference's own, not the rail's: same scope error as the converters'
    # input capacitance, and the same answer.
    found_low, _ = _capacitance_on(
        design, two_pad_parts, spec, supply, "GND", block=REFERENCE.rpartition(".")[0])
    assert found_low >= wanted, (
        f"{found_low * 1e6:.2f} uF on the reference's supply, against "
        f"{wanted * 1e6:g} uF asked for"
    )


# --- ratings across the board ------------------------------------------------

# The highest voltage each net reaches in normal operation. A surge is not in
# here: it lasts microseconds and heats nothing, and the parts it does threaten
# are checked against the clamp by name above. A net not listed contributes
# nothing, which leaves every divider leg bounded by the resistor above it.
def _phy_lines(design) -> set:
    """The four nets between the Ethernet PHY and the jack's line pins.

    A termination on one of these sits between the rail and a line the PHY
    biases *to* that rail, so the voltage across it is the transmit swing and
    not the rail - which is what the generic rule would assume, and would be
    wrong by a factor of twelve in power.
    """
    jack = next((a for a, p in design["parts"].items()
                 if p["symbol"].startswith("Connector:RJ45")), None)
    if jack is None:
        return set()
    return {net for net, nodes in design["nets"].items()
            for address, pad in nodes
            if address == jack and pad in ("1", "2", "3", "6")}


def _net_voltages(spec) -> dict[str, float]:
    """
    The rails, and what to assume a node is driven from.

    Returns both, because the default is the half that mattered. An unnamed
    net used to come back as 0 V through the caller's `.get(net, 0.0)`, so a
    resistor touching nothing on this list dissipated nothing and could not
    fail its rating however small it was. **This docstring claimed that was
    fixed and it was not**; the sentence was written, the `return` was not
    changed, and thirty-two resistors went on being evaluated at zero volts -
    every safety pull-down, both trip-threshold pulls, both feedback-divider
    bottoms and both USB CC pull-downs among them.

    The default is the logic rail. Every signal net on this board is driven
    from it - the MCU, the buffers, the latch, the comparators through their
    pull-ups - and the two nets that break that, the field buses, are checked
    against their transceivers' own declared fault voltage instead by
    `test_a_bus_termination_survives_the_fault_its_transceiver_declares`.
    """
    _, input_high = spec("input", "voltage")
    _, v5 = spec("rail.5v", "voltage")
    _, v3v3 = spec("rail.3v3", "voltage")
    named = {
        "GND": 0.0,
        "VIN": input_high, "VIN_RAW": input_high, "VIN_FUSED": input_high,
        "RPP_GATE": input_high, "SW_5V": input_high, "UVLO": input_high,
        "5V": v5, "SW_3V3": v5,
        "3V3": v3v3,
    }
    # Everything else is a signal net, and on this board a signal net is
    # driven from the logic rail - the MCU, the buffers, the latch, the
    # comparators through their pull-ups. Defaulting to 0 V, which is what
    # this did, meant a resistor touching none of the names above dissipated
    # nothing and could not fail its rating however small it was: thirty-seven
    # of the eighty-five resistors on this board took that path. Defaulting to
    # the logic rail is the smallest honest assumption, and the two nets that
    # break it - the field buses, which a fault drives to tens of volts - are
    # checked against their transceivers' own declared fault voltage by
    # `test_a_bus_termination_survives_the_fault_its_transceiver_declares`.
    return named, v3v3


def _through_resistor(design, pad_net, net):
    """Every (address, far net) reachable from `net` through one resistor."""
    found = []
    for address, part in design["parts"].items():
        if part["symbol"] != "Device:R":
            continue
        a, b = pad_net.get((address, "1")), pad_net.get((address, "2"))
        if a == net and b is not None:
            found.append((address, b))
        elif b == net and a is not None:
            found.append((address, a))
    return found


def _sources(design, pad_net, spec, voltages, default, net, exclude):
    """
    What holds `net`, as (volts, series resistance between here and it).

    A named net is a rail: it holds itself, through nothing. An unnamed net is
    a node, and what holds it is whatever is on the far side of the resistors
    that reach it - the pull-down below a damping resistor, the lower leg of a
    divider. A node with no other resistor on it is driven directly by
    whatever part sits there, which on this board means the logic rail.

    One hop, deliberately. Every path on this board is a rail, one or two
    resistors, and a rail; a walker that recursed would follow ground into
    every resistor on the board and report a current through none of them.
    """
    if net in voltages:
        return [(voltages[net], 0.0)]
    onward = [(a, far) for a, far in _through_resistor(design, pad_net, net) if a != exclude]
    if not onward:
        return [(default, 0.0)]
    return [(voltages.get(far, default), spec(a, "resistance")[0]) for a, far in onward]


def test_no_resistor_runs_above_half_its_rating(design, two_pad_parts, spec):
    """
    Every resistor **between two nets whose voltage is known**, derated by half.

    Half is what a 0402 in still air is worth. **Both** ends must be named:
    this is the V^2/R case, and V^2/R only means anything when something holds
    each end. A resistor with one end on a node - a divider tap, a damping
    resistor's far side, a pull-down below a signal - belongs to the series
    check below, which derives the current instead.

    It used to take either end, and then read `max(known, unknown-as-zero)`.
    A pull-down from a signal to ground has a named end, ground, so it came
    here and was evaluated at nought volts across it.

    **What it does not cover, and why.** A resistor in series with a signal
    dissipates the load current squared times its resistance, and nothing here
    knows that current: a 10 ohm feeding an ADC input carries microamps, while
    the same 10 ohm across a rail would be a quarter of a watt. So V^2/R only
    means anything where both ends are held by something, and this walks the
    resistors where that is true. It used to say "every resistor on the board"
    and get the rest by accident, because an unnamed net came back as 0 V and
    0 W passes any rating - thirty-seven of the eighty-five took that path,
    including both field buses' terminations. Those are now checked against
    their transceivers' own fault voltage, which is the case that mattered.
    """
    voltages, _ = _net_voltages(spec)
    hot = []
    for address, (net_a, net_b) in sorted(two_pad_parts.items()):
        if design["parts"][address]["symbol"] != "Device:R":
            continue
        # **Both** ends, not either. With `or` here, a pull-down from a signal
        # to ground was taken by this check - ground is a named net - and then
        # evaluated at max(0, unknown) = 0 V, which passes any rating. Thirty
        # two resistors went through that door, including every safety
        # pull-down and both trip-threshold pulls.
        if net_a not in voltages or net_b not in voltages:
            continue                      # the series check below owns these
        if {net_a, net_b} & _phy_lines(design):
            continue                      # biased to the rail; see test_ethernet.py
        across = abs(voltages[net_a] - voltages[net_b])
        resistance, _ = spec(address, "resistance")
        rated, _ = spec(address, "max_power")
        power = across**2 / resistance
        if power > rated * _derating(spec):
            hot.append(
                f"  {address}: {power * 1e3:.0f} mW across {across:g} V, rated "
                f"{rated * 1e3:g} mW"
            )
    assert not hot, "Resistors past half their rating:\n" + "\n".join(hot)


# The LM5164 datasheet's Equation 26 and the settling time its own worked
# example uses. Both are text in SNVSAU4D section 7.2.2.6:
#
#     CB >= t_TR-settling / (3 x RFB1)
#     "CB calculates to 56pF based on a 75us settling time"
#
# Equation 26 turns a wanted settling time into a value, so it cannot say what
# CB should be on its own. TI's 75 us is the only figure either source states,
# and it is what this board is held to.
SETTLING_TIME = 75e-6


def test_the_ripple_coupling_capacitor_holds_through_a_transient(design, two_pad_parts, spec):
    """
    C_B is big enough that the feedback divider does not discharge it first.

    Equation 26. It is about light load: when the converter sleeps between
    pulses, the coupling capacitor sits there being discharged by the feedback
    divider, and once it has gone the injected ramp goes with it.

    The value came across from TI's reference design without its resistor.
    Their feedback divider is 446 k, which is what makes their 56 pF worth
    75 us; this board's top resistor is 158 k, chosen to land 5.0 V on
    standard values, and 56 pF against that is 26.5 us. This is the check that
    would have caught it, and it is written against the divider on the board so
    that changing either part moves it.
    """
    top = _parts_on(design, two_pad_parts, "Device:R", "5V", "FB_5V")
    assert len(top) == 1, f"expected one resistor from the rail to feedback, found {top}"
    r_fb1, _ = spec(top[0], "resistance")
    c_b, _ = _capacitance_on(design, two_pad_parts, spec, "FB_5V", "RAMP")

    supported = 3 * r_fb1 * c_b
    assert supported >= SETTLING_TIME, (
        f"{c_b * 1e12:.0f} pF against a {r_fb1 / 1e3:g} kOhm top resistor satisfies "
        f"Equation 26 only to {supported * 1e6:.1f} us, short of the "
        f"{SETTLING_TIME * 1e6:g} us the datasheet's own example is sized for. "
        f"It wants at least {SETTLING_TIME / (3 * r_fb1) * 1e12:.0f} pF."
    )


def test_no_series_resistor_runs_above_half_its_rating(design, two_pad_parts, pad_net, spec):
    """
    A resistor in series feeding another resistor to a rail, at the current
    that divider actually passes.

    This is the other half of the resistors on this board, and V^2/R says
    nothing about them: what a series element dissipates is the load current
    squared times its resistance, not the rail squared over it. Where the load
    is itself a resistor the netlist knows the whole path, so the current is
    derivable - which covers every damping resistor between a PWM buffer and
    the connector, each of which feeds the pull-down that holds that gate line
    low.

    The sixteen of them were unchecked until now, and the check above could not
    have covered them: it would have put the whole logic rail across 33 ohms
    and called 0.36 W on a 62.5 mW part a failure, when the real figure is
    four microwatts.

    **The first version of this check could not fail.** It selected resistors
    with neither end on a named net and then, inside the loop, required one
    end to be on a named net - so the body never ran, `worst` stayed zero, and
    every resistor passed. It would have raised `NameError` if it had ever got
    there, because the helper it called lives in another file and was never
    imported. It was written, read, and committed looking correct.

    What it does now is walk outward one hop from each end to whatever holds
    it - a rail directly, or the far side of the one other resistor on that
    node - and take the largest current any of those pairs implies. That
    covers a divider, a damping resistor into its pull-down, and a lone
    pull-down off a driven node, which is every shape on this board. Swapping
    one 10 k pull-down for a 33 ohm now reports 367.5 mW on a 62.5 mW part.
    """
    voltages, default = _net_voltages(spec)
    hot = []
    for address, (net_a, net_b) in sorted(two_pad_parts.items()):
        if design["parts"][address]["symbol"] != "Device:R":
            continue
        if net_a in voltages and net_b in voltages:
            continue                      # the check above owns these
        if {net_a, net_b} & _phy_lines(design):
            continue                      # biased to the rail; see test_ethernet.py
        series, _ = spec(address, "resistance")
        rated, _ = spec(address, "max_power")
        worst = 0.0
        near_side = _sources(design, pad_net, spec, voltages, default, net_a, address)
        far_side = _sources(design, pad_net, spec, voltages, default, net_b, address)
        for v_near, r_near in near_side:
            for v_far, r_far in far_side:
                current = abs(v_near - v_far) / (series + r_near + r_far)
                worst = max(worst, current**2 * series)
        if worst > rated * _derating(spec):
            hot.append(f"  {address}: {worst * 1e3:.1f} mW, rated {rated * 1e3:g} mW")
    assert not hot, "Series resistors past half their rating:\n" + "\n".join(hot)


def test_a_bus_termination_survives_the_fault_its_transceiver_declares(
    design, two_pad_parts, pad_net, spec, spec_has
):
    """
    The field buses' terminations, against the voltage their own part says the
    bus can be driven to - but only where the copper actually completes.

    Both transceivers declare a `bus_fault_voltage`, 58 V for the CAN part and
    18 V for the RS-485 one, and it was already used to check that the
    connector's contacts can take it. A termination is a resistor across that
    same voltage, and nothing asked what it dissipates.

    It matters that the answer is derived rather than assumed either way. Both
    terminations sit behind a `SolderJumper_2_Open`, so on a board as
    fabricated there is no DC path across the bus at all: CAN's lower resistor
    reaches CAN_L on one side and a 4.7 nF capacitor on the other, which
    passes no direct current, and the RS-485 resistor's far end stops at the
    open jumper. Nothing dissipates, and the check says so by walking the path
    instead of by an exemption somebody wrote down.

    **Close either jumper and that changes.** 58 V across CAN's 120.8 ohm
    split is 0.48 A and 13.9 W in each 0402; 18 V across the RS-485 120 ohm is
    2.7 W. A terminated node does not survive a bus short to battery, which is
    normal for CAN and is why termination lives at the cable ends - but it is
    a thing to know before closing a jumper, and `parts/R0402/R0402.md` now
    says it.

    That paragraph used to be prose beside an assertion that could not run,
    and the first attempt at fixing it did not fix it. Bridging the jumpers
    and computing the power was right; asking whether one of the resistor's
    own *pads* sat on CAN_H or CAN_L was not, because on a split termination
    the jumpers sit between the resistors and the wires. Every CAN resistor
    was discarded before the arithmetic, so the worked example above was still
    evaluated by nothing - and a hard-wired CANL leg dissipating 56 W in an
    0402 passed, excused by the open jumper in the *other* leg.

    Both halves are reachability now. A resistor is on this transceiver's bus
    if it can get there through anything that conducts; and it is protected
    only if it can **not** get there once the jumpers are open again. Fit a
    termination directly, or close a jumper in the design, and the arithmetic
    that was only ever a comment is what fails.
    """
    voltages, _ = _net_voltages(spec)

    # What a direct current can actually flow through: a resistor or a bridged
    # jumper. Not a capacitor, and not a jumper that is open as fabricated.
    def conductors(bridged: bool) -> list:
        out = []
        for address, part in design["parts"].items():
            symbol = part["symbol"]
            jumper = symbol.startswith("Jumper:")
            if symbol == "Device:R" or (jumper and (bridged or "Open" not in symbol)):
                a, b = pad_net.get((address, "1")), pad_net.get((address, "2"))
                if a and b:
                    out.append((address, a, b))
        return out

    unprotected = []
    working = []
    for transceiver in sorted(design["parts"]):
        if not spec_has(transceiver, "bus_fault_voltage"):
            continue
        fault, _ = spec(transceiver, "bus_fault_voltage")
        # The *bus* is what leaves the board: a net the transceiver shares
        # with a connector. Its logic pins are on the same part and are not
        # what a fault drives, so a pull-down on a driver enable is not a
        # termination however the walk below happens to reach it.
        on_part = {net for (address, _), net in pad_net.items() if address == transceiver}
        connectors = {a for a, part in design["parts"].items()
                      if part["symbol"].startswith("Connector")}
        bus = {net for net in on_part - set(voltages)
               if any(address in connectors for address, _ in design["nets"][net])}
        driven = bus | set(voltages)

        def reaches(start, conducting, skip):
            """The nets reachable from `start`, never back through `skip`."""
            seen, edge = {start}, [start]
            while edge:
                net = edge.pop()
                for other, x, y in conducting:
                    if other == skip:
                        continue
                    far = y if x == net else x if y == net else None
                    if far and far not in seen:
                        seen.add(far)
                        edge.append(far)
            return seen

        bridged = conductors(True)
        shipped = conductors(False)

        # Every resistor that gets to this bus once the jumpers are bridged,
        # in series across the pair. That is what the driver works into.
        across = sum(
            spec(address, "resistance")[0]
            for address, a, b in bridged
            if design["parts"][address]["symbol"] == "Device:R"
            and (reaches(a, bridged, address) | reaches(b, bridged, address)) & bus
        )
        for address, net_a, net_b in bridged:
            if design["parts"][address]["symbol"] != "Device:R":
                continue
            # **Reachability, not pad membership.** Asking whether one of this
            # resistor's own pads is on CAN_H or CAN_L threw away the entire
            # split termination, because the jumpers sit between the resistors
            # and the wires - so the docstring's worked example was evaluated
            # by nothing at all, in both passes, and a hard-wired CANL leg
            # passed this check while dissipating 56 W in an 0402.
            from_a = reaches(net_a, bridged, address)
            from_b = reaches(net_b, bridged, address)
            if not (from_a & driven and from_b & driven):
                continue                     # no complete path: nothing flows
            if not ((from_a | from_b) & bus):
                continue                     # not on this transceiver's bus
            resistance, _ = spec(address, "resistance")
            rated, _ = spec(address, "max_power")

            # Normal operation first. The driver's own differential output
            # appears across the whole termination, so each element carries
            # the same current and dissipates its own share.
            if spec_has(transceiver, "differential_output_max"):
                _, swing = spec(transceiver, "differential_output_max")
                # The whole termination across the pair, which for a split one
                # is both halves in series. Every element carries the same
                # current and dissipates its own share of it.
                carried = swing / across
                normal = carried**2 * resistance
                if normal > rated * _derating(spec):
                    working.append(
                        f"  {address}: {normal * 1e3:.0f} mW with {transceiver} "
                        f"driving {swing:g} V across {across:.1f} ohm, rated "
                        f"{rated * 1e3:g} mW and derated to "
                        f"{rated * _derating(spec) * 1e3:.0f}")

            # And the voltage across it under that same fault, which is not
            # the same question as the power. A thick-film chip has a working
            # voltage limit set by the film's length, and an 0402 is 50 V
            # against the 58 the CAN part declares: the termination could be
            # inside its power rating and still be flashed over. The rating is
            # declared on the two terminations and nowhere else, because these
            # are the only resistors on the board a bus fault reaches.
            if spec_has(address, "max_voltage"):
                standoff, _ = spec(address, "max_voltage")
                if fault > standoff:
                    unprotected.append(
                        f"  {address}: {fault:g} V across a part rated "
                        f"{standoff:g} V if {transceiver}'s bus is driven to "
                        f"its declared fault voltage")
            else:
                unprotected.append(
                    f"  {address}: on {transceiver}'s bus with no max_voltage "
                    f"declared, and the fault it must stand off is {fault:g} V")

            power = fault**2 / resistance
            if power <= rated * _derating(spec):
                continue
            # It survives only if no current can flow through it once the
            # jumpers are open again - which means **both** of its ends have
            # to stop reaching something driven, not just one. Touching the
            # bus is not dissipating: RS-485's 120 ohm has a pad directly on
            # RS485_B and its other end dead-ends at an open jumper, so it
            # carries nothing.
            #
            # The previous version looked for an open jumper anywhere in the
            # closure reached from either end, which excused CAN's low leg on
            # account of the jumper in the *high* leg.
            left = reaches(net_a, shipped, address) & driven
            right = reaches(net_b, shipped, address) & driven
            _ = (left, right)
            if left and right:
                unprotected.append(
                    f"  {address}: {power:.1f} W if {transceiver}'s bus is driven "
                    f"to {fault:g} V, rated {rated * 1e3:g} mW, and with the "
                    f"jumpers as they ship it still runs from "
                    f"{', '.join(sorted(left))} to {', '.join(sorted(right))}")
    # And what it dissipates when somebody *does* close the jumper, driving
    # normally. That is the configuration these parts exist for, and for a
    # while the only case computed was the bus fault - which the open jumper
    # excuses, so nothing evaluated the intended use.
    #
    # **This was reported rather than asserted, and recorded in BLOCKING.**
    # Every termination failed it: RS-485's 120 ohm took 103 mW from an 0402
    # rated 62.5, and CAN's two 60.4 ohm took 46 mW each against a 31 mW
    # derated limit. The answer was a bigger package - a 1206 for RS-485 and
    # 0805s for CAN's two halves - and once the parts could do the job there
    # was no reason to keep printing it instead of holding them to it.
    assert not working, (
        "Terminations past their rating with their own driver on the bus:\n"
        + "\n".join(sorted(set(working)))
        + "\nA termination behind a jumper still has to survive the jumper "
          "being closed, which is the only reason it is fitted."
    )
    assert not unprotected, (
        "Terminations a declared fault destroys, fitted with nothing open in the "
        "way:\n" + "\n".join(sorted(set(unprotected)))
        + "\nTermination belongs at the cable ends; on this board it belongs "
          "behind a jumper that ships open."
    )


# --- what each rail actually carries -----------------------------------------

RAILS = (("3V3", "rail.3v3"), ("5V", "rail.5v"))

# Symbol libraries whose parts cannot source current into a net.
PASSIVES = {"Device", "Connector", "Jumper", "TestPoint", "Diode", "Switch"}

# Which declared parameter belongs to which supply pin. Not a table of values -
# a part states its own current; this says which of a multi-supply part's pins
# that current comes out of, which the symbol alone cannot say.
_DRAWN = ("supply_current_max", "supply_current_max_at_25c",
          "supply_current_typical", "quiescent_current", "quiescent_current_max")
SUPPLY_PINS = {
    "VCC": _DRAWN,
    "VDD": _DRAWN,
    "V+": _DRAWN,
    "IN": ("quiescent_current",),
    "VIO": ("io_supply_current_max",),
    "VDDIO": ("supply_current_typical", "io_supply_current_max"),
}

# A parameter whose name says the datasheet did not guarantee it over the
# board's conditions. `loads.unguaranteed_margin` is added to these and to
# nothing else, so a figure that *is* a maximum over temperature is taken at
# face value and one that is not carries its own uncertainty into the sum.
UNGUARANTEED = ("_typical", "_at_25c")


# What a pin of this type can do to the net it sits on. A part *drives* a net
# only through one of these; an `input` or a `power_in` sits on a net and
# sources nothing into it. The netlist cannot say which is which - a node is a
# node - so this comes from the symbol, and it is the difference between a
# buffer's output and a converter's feedback pin.
DRIVING = {"output", "bidirectional", "tri_state", "open_collector", "open_emitter"}
SUPPLY = {"power_in"}


def _paths_to_ground(design, pad_net, spec):
    """
    net -> (series ohms, forward volts) for the lowest-resistance DC path from
    that net down to ground.

    Dijkstra from GND outwards over every two-pad part that conducts DC: a
    resistor contributes its resistance, a diode or an LED contributes its
    forward drop and no resistance. Lowest resistance is what carries the most
    current, which is the corner a budget wants.

    **A walk rather than a chain.** The first version of this took maximal
    runs of resistors and stopped wherever three met, which silently dropped
    `GATE_ENABLE_OUT` - series resistor, pull-down and the gate kill's drain
    resistor all on one net - and never reached the indicator LEDs at all,
    because their path to ground goes through a diode. Between them that was
    5 mA of continuous 3V3 draw in no sum.
    """
    import heapq

    edges: dict[str, list] = {}
    for address, part in design["parts"].items():
        a, b = pad_net.get((address, "1")), pad_net.get((address, "2"))
        if not (a and b) or a == b:
            continue
        if part["symbol"] == "Device:R":
            ohms, drop = spec(address, "resistance")[0], 0.0
        elif part["symbol"] in ("Device:LED", "Device:D"):
            ohms, drop = 0.0, spec(address, "forward_voltage")[1]
        else:
            continue
        edges.setdefault(a, []).append((b, ohms, drop))
        edges.setdefault(b, []).append((a, ohms, drop))

    best: dict[str, tuple[float, float]] = {}
    queue = [(0.0, 0.0, "GND")]
    while queue:
        ohms, drop, net = heapq.heappop(queue)
        if net in best:
            continue
        best[net] = (ohms, drop)
        for far, more, volts in edges.get(net, ()):
            if far not in best:
                heapq.heappush(queue, (ohms + more, drop + volts, far))
    best.pop("GND", None)
    return best


def _drivers_of(design, pad_net, net, pin_types):
    """Every part that can source current into `net`, with the rails it runs from."""
    out = []
    for address, part in design["parts"].items():
        types = pin_types(part["symbol"])
        drives = any(pad_net.get((address, str(pad))) == net and kind in DRIVING
                     for pad, kind in types.items())
        if not drives:
            continue
        out.append((address, {pad_net.get((address, str(pad)))
                              for pad, kind in types.items() if kind in SUPPLY}))
    return out


def test_each_rail_carries_no_more_than_it_is_budgeted(
    design, pad_net, two_pad_parts, spec, spec_has
):
    """
    Add up what is actually on each rail, and hold it against the band the
    converter, the fuse and the inductors are all sized from.

    **`rail.3v3.current` and `rail.5v.current` are declared bands, and what is
    on them was a prose comment.** An itemised list somebody typed, in
    milliamps, summed by hand, sitting beside the declaration. Every check
    read the band; nothing read the board.

    It failed once, quietly. Taking the fifteen gate-line pull-downs from 10 k
    to 1.2 k added 43 mA of continuous draw and put the 3V3 rail at 806 mA
    against its own 800. No check moved - the band had not changed, and the
    comment was still describing the board from before. The pull-downs went
    back to 10 k for other reasons and took the regression with them, which is
    luck and not a gate.

    So the sum comes off the netlist, in three parts:

      - **what each part says it draws**, attributed to the pin it draws it
        from, so a transceiver with a 5 V supply and a 3.3 V I/O pin does not
        charge its bus-driver current to the logic rail;
      - **what a driver works into off the board**, where a part states both a
        differential output and the load it is specified into and its own
        current figure is the unloaded one;
      - **every resistor chain with a DC path to ground**, at the rail that
        feeds it - whether that is a divider straight off the rail or a
        buffered output through a series resistor into its pull-down. That
        last is the one the 1.2 k slipped past.

    What it does not carry is a pull-up that ends at a pin: it draws only
    while that pin is low, and this board states no duty cycle for any of
    them. Those are milliamps, and they are the known conservatism gap here.

    The declared promises - what the connectors may take, what the reference
    may supply - are read from the block that owns them, so they stay in the
    sum without anyone re-typing them.
    """
    import functools

    pin_types = functools.lru_cache(maxsize=None)(
        lambda symbol: symbol_pin_types(symbol))
    paths = _paths_to_ground(design, pad_net, spec)
    rail_nets = {rail_net for rail_net, _ in RAILS}
    drivers = {source: _drivers_of(design, pad_net, source, pin_types)
               for source in paths}
    _, margin = spec("loads", "unguaranteed_margin")
    problems = []
    for net, rail in RAILS:
        _, volts = spec(rail, "voltage")
        _, budget = spec(rail, "current")
        items = []

        blocks_counted = set()
        for address, part in design["parts"].items():
            # Which of this part's supply pins land on this rail. A figure is
            # per *part*, not per pin - the MCU has fourteen VDD pads and one
            # 500 mA - so each parameter is counted once, on the rail the pin
            # that carries it sits on.
            here = {name.upper() for pad, name in symbol_pin_names(part["symbol"]).items()
                    if pad_net.get((address, str(pad))) == net}
            if not here:
                continue
            wanted = {parameter for name in here for parameter in SUPPLY_PINS.get(name, ())}
            for parameter in sorted(wanted):
                if not spec_has(address, parameter):
                    continue
                draws = spec(address, parameter)[1]
                if parameter.endswith(UNGUARANTEED):
                    draws *= 1.0 + margin
                    items.append((f"{address}.{parameter}+{margin * 100:g}%", draws))
                else:
                    items.append((f"{address}.{parameter}", draws))

            # A driver whose own figure is the unloaded one, plus what it
            # pushes into the cable. Only where the part says both, which is
            # how the CAN transceiver - whose figure is measured *with* its
            # load - avoids being charged for its bus twice.
            if spec_has(address, "bus_load_min") and spec_has(
                    address, "differential_output_max"):
                _, swing = spec(address, "differential_output_max")
                load, _ = spec(address, "bus_load_min")
                items.append((f"{address}.bus", swing / load))

            # And what the block this part belongs to has promised to supply
            # off the board - a connector's draw, a reference's output. The
            # promise is owned by the block, so it is counted once however
            # many of its parts sit on the rail.
            block = address.partition(".")[0]
            if block not in blocks_counted and spec_has(block, "supply_current"):
                blocks_counted.add(block)
                items.append((f"{block}.supply_current",
                              spec(block, "supply_current")[1]))

        # Everything with a DC path to ground, charged to the rail that holds
        # its far end up: the rail itself where the path ends on it, or a part
        # that runs from this rail and *drives* that net.
        #
        # "Drives" is a pin type, not a connection. Asking only whether a part
        # powered from this rail touched the net charged the 3V3 feedback
        # divider to both rails at once - the CAN transceiver's V_IO pin sits
        # on 3V3 and its V_CC on 5 V, so every 3V3 chain looked driven from
        # 5 V, at a voltage that never appears across it. A converter's
        # feedback pin and a comparator's inputs did the same thing.
        for source, (ohms, drop) in sorted(paths.items()):
            if ohms <= 0.0:
                continue
            if source in rail_nets:
                if source != net:
                    continue                      # the other rail's own path
                name = source
            else:
                powered = [address for address, supplies in drivers.get(source, ())
                           if net in supplies]
                if not powered:
                    continue
                name = f"{source} from {powered[0]}"
            across = volts - drop
            if across <= 0.0:
                continue
            items.append((f"{name} through {ohms:.0f} ohm", across / ohms))

        total = sum(current for _, current in items)
        if total > budget:
            worst = sorted(items, key=lambda x: -x[1])[:6]
            problems.append(
                f"  {rail}: {total * 1e3:.1f} mA against a {budget * 1e3:g} mA "
                f"budget. Largest: "
                + ", ".join(f"{name} {current * 1e3:.1f}" for name, current in worst))
        # Printed on every run, because a budget nobody can see is the thing
        # this check exists to replace. Everything above a milliamp, which is
        # where the itemised comment this replaced stopped too.
        print(f"    {rail}: {total * 1e3:.1f} mA of {budget * 1e3:g}, "
              f"from {len(items)} loads")
        for name, current in sorted(items, key=lambda x: -x[1]):
            if current >= 1e-3:
                print(f"        {current * 1e3:8.1f} mA  {name}")
    assert not problems, (
        "Rails carrying more than they are budgeted:\n" + "\n".join(problems)
        + "\nThe band is what the converter, the fuse and the inductors are "
          "sized from; it is not a wish."
    )
