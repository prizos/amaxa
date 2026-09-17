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
        pin = pad_net.get((series, "2"))
        if pin not in _FAST:
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
    """
    low, high = spec("adc", "slow_corner")
    _, source = spec("header", "source_impedance")
    outside = []
    for channel, (series, shunt) in sorted(networks.items()):
        pin = pad_net.get((series, "2"))
        if pin in _FAST or pin is None or channel == "dac_test":
            continue
        resistance = spec(series, "resistance")
        capacitance = spec(shunt, "capacitance")
        corner_low = _corner(resistance[1] + source, capacitance[1])
        corner_high = _corner(resistance[0], capacitance[0])
        if not (low <= corner_low and corner_high <= high):
            outside.append(f"  {channel}: {corner_low:.0f} to {corner_high:.0f} Hz")
    assert not outside, (
        f"Slow channels outside {low:g} to {high:g} Hz:\n" + "\n".join(outside)
    )


def test_every_network_settles_inside_the_sampling_window(spec, networks, pad_net):
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
    """
    sample, _ = spec("adc", "sampling_time")
    bits, _ = spec("adc", "resolution_bits")
    _, allowed = spec("adc", "settling_error")
    c_adc, _ = spec(MCU, "adc_sample_capacitance")
    _, source = spec("header", "source_impedance")
    lsb = 1.0 / 2 ** bits

    problems = []
    for channel, (series, shunt) in sorted(networks.items()):
        if channel == "dac_test":
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


def test_the_source_impedance_is_far_below_what_the_part_allows(spec, networks):
    """
    The series resistor against the converter's own sampling resistance.

    Not a settling check - that is the one above - but the sanity check that
    goes with it: a series resistor much larger than the 50 Ohm inside the part
    means the switch's own resistance has stopped mattering and every error
    budget shifts outside the chip.
    """
    r_adc, _ = spec(MCU, "adc_sample_resistance")
    for channel, (series, _) in sorted(networks.items()):
        _, resistance = spec(series, "resistance")
        assert resistance <= 40 * r_adc, (
            f"{channel}: {resistance:g} ohm in series against the part's own "
            f"{r_adc:g} ohm"
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


# The channels the control loop reads every PWM cycle, as the pin map names
# them. Everything else on the connector is housekeeping.
_FAST = {"IA", "IB", "IC", "VDC", "VA", "VB", "VC", "AUX_FAST", "OV_COMP"}


@pytest.fixture(scope="module")
def pin_map(board_dir):
    import sys
    sys.path.insert(0, str(board_dir.parent / "tools"))
    from mcu_pins import load_source
    return load_source(board_dir / "pinmap.py", "cpu1_pinmap_adc")
