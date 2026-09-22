"""
The ADC input networks: what they filter, and what they cost to sample.

Each channel is one RC between the connector and a pin. Both numbers in it are
constrained from opposite directions - the capacitor has to be large enough to
roll off what the converter would alias and small enough to recharge inside the
sampling window - so neither can be chosen without the other, and neither is
written down anywhere as an expected value.

ST's datasheet is STM32H743xI, DocID030538 Rev 3; the ADC figures are Table 84.
"""

import math

import pytest

MCU = "mcu"


@pytest.fixture(scope="module")
def pad_net(design):
    return {tuple(node): net for net, nodes in design["nets"].items() for node in nodes}


@pytest.fixture(scope="module")
def networks(design, pad_net):
    """
    channel -> (series resistance band, shunt capacitance band, from, to).

    Found by pairing the parts the design named for each channel, and then
    reading the nets off them, so a network wired to the wrong signal is not
    quietly checked as though it were right.
    """
    out = {}
    for address in design["parts"]:
        if not address.startswith("adc.") or not address.endswith(".shunt"):
            continue
        channel = address[len("adc."):-len(".shunt")]
        series = f"adc.{channel}.series"
        assert series in design["parts"], f"{channel} has a capacitor and no resistor"
        out[channel] = (series, address)
    return out


def _corner(resistance: float, capacitance: float) -> float:
    return 1.0 / (2 * math.pi * resistance * capacitance)


def test_every_analog_pin_has_exactly_one_network(design, pad_net, networks, pin_map):
    """
    Each ADC pin is reached through one series resistor, from the connector, and
    has one capacitor to ground. Not two, and not none.

    Two capacitors is a filter nobody calculated. None is an antenna wired to a
    sampling switch. Both look the same on a schematic sheet and neither shows
    up until the measurements are wrong.
    """
    analog = {
        p.net_name for p in pin_map.PINS
        if p.signal.startswith("ADC") or p.signal.startswith("COMP")
    }
    served = {}
    for channel, (series, shunt) in networks.items():
        far = pad_net.get((series, "2"))
        served.setdefault(far, []).append(channel)

    problems = []
    for net in sorted(analog):
        found = served.get(net, [])
        if len(found) != 1:
            problems.append(f"  {net}: {len(found)} networks")
    assert not problems, "ADC pins and their input networks:\n" + "\n".join(problems)


def test_each_network_sits_between_the_connector_and_its_pin(design, pad_net, networks):
    """
    The resistor's far end is the raw signal from the connector and its near end
    is the pin, with the capacitor across the near end.

    Wired the other way round the capacitor would sit on the connector, where it
    would do nothing for the pin and something unwelcome to the comparators
    watching the same net.
    """
    wrong = []
    for channel, (series, shunt) in sorted(networks.items()):
        source = pad_net.get((series, "1"))
        pin = pad_net.get((series, "2"))
        across = {pad_net.get((shunt, "1")), pad_net.get((shunt, "2"))}
        if not (source or "").endswith("_SENSE"):
            wrong.append(f"  {channel}: fed from {source!r}, which is not a connector net")
        if across != {pin, "GND"}:
            wrong.append(f"  {channel}: capacitor across {sorted(across)}, not {pin} to ground")
    assert not wrong, "Input networks:\n" + "\n".join(wrong)


def test_the_fast_channels_roll_off_where_they_were_meant_to(spec, networks, pad_net):
    """
    Every channel the control loop reads has its corner inside the declared band.

    Too low and the loop measures a current that happened a moment ago, which is
    phase lag in something that is about to be differentiated. Too high and the
    converter aliases whatever the switching node is doing at a few megahertz
    straight into the measurement.
    """
    low, high = spec("adc", "fast_corner")
    _, source = spec("header", "source_impedance")
    outside = []
    for channel, (series, shunt) in sorted(networks.items()):
        if _band_of(channel) != "fast":
            continue
        resistance = spec(series, "resistance")
        capacitance = spec(shunt, "capacitance")
        corner_low = _corner(resistance[1] + source, capacitance[1])
        corner_high = _corner(resistance[0], capacitance[0])
        if not (low <= corner_low and corner_high <= high):
            outside.append(
                f"  {channel}: {corner_low / 1e6:.2f} to {corner_high / 1e6:.2f} MHz, "
                f"including up to {source:g} ohm from whatever drives it"
            )
    assert not outside, (
        f"Fast channels outside {low / 1e6:g} to {high / 1e6:g} MHz:\n" + "\n".join(outside)
    )


def test_the_slow_channels_roll_off_much_lower(spec, networks, pad_net):
    """
    The housekeeping channels get three decades more filtering, because nothing
    is waiting on them.

    A temperature that settles in a millisecond is still a thousand times faster
    than the thing it measures, and every decade of corner is a decade of
    rejection of whatever the power stage is radiating.

    The two board-ID channels used to be counted here and are not any more:
    see `test_a_board_id_strap_settles_before_anything_reads_it`.
    """
    low, high = spec("adc", "slow_corner")
    outside = []
    for channel, (series, shunt) in sorted(networks.items()):
        if _band_of(channel) != "slow":
            continue
        _, source = spec("header", "source_impedance")
        resistance = spec(series, "resistance")
        capacitance = spec(shunt, "capacitance")
        corner_low = _corner(resistance[1] + source, capacitance[1])
        corner_high = _corner(resistance[0], capacitance[0])
        if not (low <= corner_low and corner_high <= high):
            outside.append(f"  {channel}: {corner_low:.0f} to {corner_high:.0f} Hz")
    assert not outside, (
        f"Slow channels outside {low:g} to {high:g} Hz:\n" + "\n".join(outside)
    )


def test_every_network_settles_inside_the_sampling_window(spec, networks, pad_net, pin_map):
    """
    What the converter's own sampling capacitor costs, and whether the resistor
    puts it back in time.

    **This deliberately does not use ST's Equation 1.** That equation asks how
    long a source takes to charge the whole input capacitance from nothing, and
    it is the right question when there is no capacitor at the pin. Here there
    is one, it stays charged between conversions, and the only charge that
    moves is what the 4 pF sampling capacitor takes when the switch closes:

        droop    = C_adc / (C_adc + C_ext)        - instantly, by sharing
        residual = droop * exp(-t_sample / (R * C_ext))

    Applying Equation 1 to this topology rejects every value that works and
    accepts none that do, which is worth writing down because it is the first
    thing anyone checking this will reach for.

    The worst case is the shortest sampling time firmware will use, the largest
    sampling capacitor and the smallest external one.

    **Only the pins that are sampled.** A network ending at a comparator input
    or a DAC output has no sampling switch behind it and takes no charge, so
    there is nothing to settle; asking the question anyway would force a
    reservoir onto a node whose whole job is to be fast. Which pins those are
    comes from the pin map's own signal names, not from a list here - the list
    this replaced named `dac_test` and would have gone on exempting it after
    the pin moved.
    """
    sample, _ = spec("adc", "sampling_time")
    bits, _ = spec("adc", "resolution_bits")
    _, allowed = spec("adc", "settling_error")
    c_adc, _ = spec(MCU, "adc_sample_capacitance")
    _, source = spec("header", "source_impedance")
    lsb = 1.0 / 2 ** bits
    sampled = {p.net_name for p in pin_map.PINS if p.signal.startswith("ADC")}

    problems = []
    for channel, (series, shunt) in sorted(networks.items()):
        if pad_net.get((series, "2")) not in sampled:
            continue
        resistance, _ = spec(series, "resistance")
        capacitance, _ = spec(shunt, "capacitance")
        droop = c_adc / (c_adc + capacitance)
        residual = droop * math.exp(-sample / ((resistance + source) * capacitance))
        if residual > allowed * lsb:
            problems.append(
                f"  {channel}: {residual / lsb:.2f} LSB left at the end of the "
                f"window, from {droop / lsb:.1f} LSB of charge sharing"
            )
    assert not problems, (
        f"Channels not settled to {allowed:g} LSB in {sample * 1e9:.0f} ns:\n"
        + "\n".join(problems)
    )


def test_the_source_impedance_is_below_what_the_part_allows(spec, networks):
    """
    The series resistor against the ceiling ST's Table 84 puts on it.

    **This used to compare it with forty times the converter's own 50 Ohm**,
    and forty was not from anywhere. The table states the limit directly -
    R_AIN, external input impedance, 50 kOhm max - so that is what it reads
    now, and the number stopped being this file's opinion.

    It is a loose bound and it is meant to be. The tight one is the settling
    check above, which the design is sized by; this is the part's own ceiling,
    and what it catches is a resistor off by orders of magnitude rather than by
    a factor - the settling check would catch the second anyway.
    """
    allowed, _ = spec(MCU, "adc_external_impedance_max")
    r_adc, _ = spec(MCU, "adc_sample_resistance")
    for channel, (series, _) in sorted(networks.items()):
        _, resistance = spec(series, "resistance")
        assert resistance <= allowed, (
            f"{channel}: {resistance:g} ohm in series, against the "
            f"{allowed / 1e3:g} kOhm Table 84 allows outside the pin and the "
            f"{r_adc:g} ohm inside it"
        )


def test_the_comparators_see_the_signal_before_the_filter(design, pad_net, networks):
    """
    No comparator input is on the far side of an RC from the connector.

    The whole reason the taps are where they are: a filter with a corner low
    enough to be worth having costs hundreds of nanoseconds, and the trip budget
    is fifty. This is the same fact `test_trip.py` checks from the comparators'
    side, asked here from the filters' side, because it is the one arrangement
    in this design that a later change would break silently.
    """
    filtered = {pad_net.get((series, "2")) for series, _ in networks.values()}
    watched = set()
    for address, part in design["parts"].items():
        if part["symbol"] != "Comparator:TLV3501AIDBV":
            continue
        watched |= {pad_net.get((address, "1")), pad_net.get((address, "3"))}
    behind = sorted((watched & filtered) - {None})
    assert not behind, (
        "Comparators watching the filtered side of an input network:\n"
        + "\n".join(f"  {net}" for net in behind)
    )


def test_the_filter_does_not_load_the_tap_it_sits_beside(design, pad_net, networks, spec):
    """
    Being on the unfiltered side of an RC is not the same as being unfiltered.

    The check above asserts a topological fact - no comparator sits past a
    series resistor - and the design comments used to call the taps "ahead of
    everything, so it is fast". But the capacitor is a shunt branch on the
    *same node*, and the power board drives that node through an impedance the
    board itself declares. So the tap is a lead-lag network, not a clean tap:

        H(s) = (1 + sRC) / (1 + s(Rs + R)C)

    unity at DC, so nothing static notices. Two things follow, and they are
    not the same thing:

      - **amplitude**, R/(Rs + R) to a step, so a fast edge arrives low and
        the effective trip point sits that much high. This is what the series
        resistor fixes, and only the series resistor: it is a ratio.
      - **time**, because the same network delays a *ramp* - which is what a
        rising fault current is - by exactly Rs*C, whatever R is. This is
        what the capacitor fixes, and only the capacitor.

    At 10 ohm and 10 nF the first was 17 % against a 12 % threshold tolerance
    and the second was 20 ns, the entire share of the trip budget reserved for
    a filter nobody had noticed was already fitted. FAST4 was worse on both
    because it carried a second identical network for redundancy: two 10 ohm
    branches in parallel are 4.95 ohm and 20 nF, so 29 % and 40 ns. The
    redundancy cost it accuracy and time.

    At 22 ohm and 4.7 nF the first is 8.3 % and the second 9.4 ns, and the
    second network is 1 kohm and 100 pF - which it can be because PB2 is a
    comparator input with nothing sampling it, so it needs no reservoir. Both
    numbers are worked out here from the parts and held against what the board
    declares, rather than printed.
    """
    _, source = spec("header", "source_impedance")
    _, tolerance = spec("trip", "threshold_tolerance")
    _, budget = spec("trip", "budget")
    _, reserved = spec("trip", "reserved_share")

    watched = set()
    for address, part in design["parts"].items():
        if not part["symbol"].startswith("Comparator:"):
            continue
        watched |= {pad_net.get((address, "1")), pad_net.get((address, "3"))}

    # Every RC branch hanging off a node a comparator watches, in parallel.
    branches: dict[str, list[tuple[float, float]]] = {}
    for channel, (series, shunt) in networks.items():
        node = pad_net.get((series, "1"))
        if node not in watched:
            continue
        branches.setdefault(node, []).append(
            (spec(series, "resistance")[0], spec(shunt, "capacitance")[1]))

    assert branches, "no comparator shares a node with an input network"
    wrong = []
    for node, rc in sorted(branches.items()):
        parallel = 1.0 / sum(1.0 / r for r, _ in rc)
        total = sum(c for _, c in rc)
        error = source / (source + parallel)
        delay = source * total
        if error > tolerance:
            wrong.append(
                f"  {node}: {len(rc)} branch(es) of {parallel:.2f} ohm, so a step "
                f"arrives {error * 100:.1f}% low and the trip point sits that "
                f"much high, against {tolerance * 100:g}% of threshold tolerance")
        if delay > reserved * budget:
            wrong.append(
                f"  {node}: {total * 1e9:.2f} nF behind {source:g} ohm delays a "
                f"ramp by {delay * 1e9:.1f} ns, against the "
                f"{reserved * budget * 1e9:.0f} ns of the {budget * 1e9:g} ns trip "
                f"budget reserved for the tap")
    assert not wrong, (
        "The ADC filter loads the comparator tap beside it:\n" + "\n".join(wrong))


def _is_fast(channel: str) -> bool:
    """
    Whether a channel is one the control loop reads every PWM cycle.

    From the channel's own name, which is the address the design builds it
    under - `adc.fast3`, `adc.slow1`, `adc.comp_fast4`. This used to be a
    written-out set of net names, and the failure it invited was quiet: a
    channel added to the pin map and not added to the set fell through to the
    *slow* check, which a fast network passes by being three decades out of
    the band it was silently moved into. Nothing would have said so.
    """
    return "fast" in channel


def _band_of(channel: str) -> str:
    """Which corner band a channel belongs in, or raises if it belongs in none."""
    if _is_fast(channel):
        return "fast"
    if channel.startswith("slow"):
        return "slow"
    if channel.startswith("board_id"):
        return "strap"                    # a DC level, not a bandwidth
    if channel == "dac_test":
        return "neither"                  # an output, and the only one
    raise AssertionError(
        f"{channel} is neither fast nor slow by its name, so no corner band "
        f"claims it. Name it so, or give it a band of its own"
    )


@pytest.fixture(scope="module")
def pin_map(board_dir):
    import sys
    sys.path.insert(0, str(board_dir.parent / "tools"))
    from mcu_pins import load_source
    return load_source(board_dir / "pinmap.py", "cpu1_pinmap_adc")


def test_no_analog_input_may_be_presented_more_than_its_pin_allows(
    design, spec, networks, pad_net
):
    """
    What the connector may present, against what the pin is rated for - and
    against the rail this board hands the thing doing the presenting.

    These are TT_xx analog inputs and ST's Table 20 caps them at **4.0 V
    absolute**. Not VDDA plus a diode drop, which is the number everybody
    reaches for: Table 21 rates injection current on them at minus five to
    *plus nought* milliamps, so there is no positive-injection path to be
    inside of. The limit is a voltage and there is nothing below it.

    **This used to be a requirement on a board that does not exist yet.** The
    analog rail was 5 V through a bead, an op-amp rails to its own supply when
    the thing it measures goes wrong, and the 22 ohm in series is what the
    ADC's settling window needs rather than anything that limits a fault. So
    the figure was written down and handed to the power board, along with the
    clamps that would not fit on this one.

    The rail is regulated to 3.3 V now, so the worst a sensor running from
    this board can rail to is a number this board sets: the regulator's
    nominal output at the top of its own accuracy. That is what the second
    assertion derives, and it is why the first one stopped being a promise
    nobody here could keep.
    """
    _, presented = spec("analog", "input_voltage_max")
    limit, _ = spec(MCU, "analog_input_voltage_max")
    assert presented <= limit, (
        f"the analog connector may present {presented:g} V and the pins take "
        f"{limit:g} V"
    )

    # What this board actually hands the far side, from the part that makes
    # it. A sensor powered from here cannot exceed its own supply.
    regulator = [address for address, part in design["parts"].items()
                 if part["symbol"].startswith("Regulator_Linear:")]
    assert len(regulator) == 1, f"the analog supply comes from {regulator}"
    nominal, _ = spec(regulator[0], "output_voltage")
    _, accuracy = spec(regulator[0], "output_accuracy")
    rails_to = nominal * (1 + accuracy)
    assert rails_to <= limit, (
        f"the analog rail reaches {rails_to:.3f} V and the pins take "
        f"{limit:g} V - a sensor running from it rails to its own supply"
    )
    # The promise *is* the rail, not a number beside it. It used to be 4.0,
    # exactly ST's absolute maximum, so `presented <= limit` compared a value
    # with itself; tying it to the regulator makes it a derivation and leaves
    # the silicon's limit a real margin away.
    assert abs(presented - rails_to) < 1e-9, (
        f"the connector is documented to present {presented:g} V and the "
        f"analog rail reaches {rails_to:.3f} V - the promise is meant to be "
        f"the rail this board hands out, so that a sensor running from it "
        f"cannot exceed it"
    )
    assert presented < limit, (
        f"the promise is {presented:g} V against a {limit:g} V absolute "
        f"maximum, which leaves nothing"
    )
    assert rails_to <= presented, (
        f"the rail this board supplies reaches {rails_to:.3f} V, above the "
        f"{presented:g} V the connector is documented to present. The band is "
        f"what the power board is told; it cannot be under what this board "
        f"itself hands out"
    )

    # Every fast channel, however many there are. This used to assert there
    # were eight, which is a belief about the pin map bolted onto a check
    # about voltage ratings.
    assert any(_band_of(channel) == "fast" for channel in networks), (
        "no fast channel found, and this check is about them"
    )


def test_a_board_id_strap_settles_before_anything_reads_it(spec, networks):
    """
    The ID straps are a DC level, and what they owe is a settling time.

    These two channels were counted as slow ones and held to the slow band's
    corner, with the same two-ohm source impedance as every other input on the
    connector. Both halves of that were wrong. The pin map specifies them as
    "resistor divider on the power board", and a divider cannot present two
    ohms without drawing hundreds of milliamps - so the board was asking the
    power board for something the same repository had already told it not to
    build, and computing a 1.45 kHz corner for a network whose real one is
    nearer 130 Hz.

    Nothing was harmed, because a board-ID strap does not have a bandwidth
    requirement. It has a deadline: firmware reads it once at start-up and it
    has to be right by then. So that is what is asserted, at the impedance a
    strap divider really presents, and to the resolution the converter can
    tell apart.
    """
    _, budget = spec("adc", "strap_settling")
    _, source = spec("header", "strap_impedance")
    bits, _ = spec("adc", "resolution_bits")
    _, error = spec("adc", "settling_error")

    # Settle to within the error the board allows, expressed in counts.
    counts = 2.0 ** bits
    turns = math.log(counts / error)

    slow = []
    for channel, (series, shunt) in sorted(networks.items()):
        if _band_of(channel) != "strap":
            continue
        resistance = spec(series, "resistance")[1] + source
        capacitance = spec(shunt, "capacitance")[1]
        settles = resistance * capacitance * turns
        if settles > budget:
            slow.append(
                f"  {channel}: {resistance / 1e3:.1f} k into "
                f"{capacitance * 1e9:.0f} nF takes {settles * 1e3:.1f} ms to "
                f"settle within {error:g} of a count")
    assert not slow, (
        f"Board-ID straps that have not settled {budget * 1e3:g} ms after "
        f"power-up:\n" + "\n".join(slow)
    )
