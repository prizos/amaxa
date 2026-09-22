"""
The trip comparators, their thresholds, and what arrives on the analog connector.

The safety chain's checks establish that nothing reaches a gate driver unless
firmware allows it. These establish the other half: that something takes the
permission away fast enough, and that the thresholds it decides on mean what
they are set to.

Datasheets: TI SBOS321E (TLV3501, April 2016) and the MCP4728 data recorded in
`parts/MSOP10/MSOP10.md`, which is where the caveats about that part live.
"""

import math

import pytest

DAC = "trip.dac"
LATCH = "safety.latch"
BUFFER = "safety.buffer1"
HEADER = "header.analog"



def _derating(spec) -> float:
    """How much of a rating this board will use, from design.json."""
    _, share = spec("parts", "derating")
    return share


def _pin_count(pad_net) -> int:
    """How many pins the connector has, counted on the board rather than said."""
    return len([pad for reference, pad in pad_net if reference == HEADER])
BUS = "TRIP_SET_N"


@pytest.fixture(scope="module")
def pad_net(design):
    return {tuple(node): net for net, nodes in design["nets"].items() for node in nodes}


@pytest.fixture(scope="module")
def comparators(design, pad_net):
    """address -> (signal net, threshold net, output net), for every comparator."""
    out = {}
    for address, part in design["parts"].items():
        if part["symbol"] != "Comparator:TLV3501AIDBV":
            continue
        inverting = pad_net.get((address, "1"))
        non_inverting = pad_net.get((address, "3"))
        output = pad_net.get((address, "5"))
        out[address] = (inverting, non_inverting, output)
    return out


@pytest.fixture(scope="module")
def pin_map(board_dir):
    import sys
    sys.path.insert(0, str(board_dir.parent / "tools"))
    from mcu_pins import load_source
    return load_source(board_dir / "pinmap.py", "cpu1_pinmap_trip")


# Which declared rail each supply net is. A check that names a rail directly
# reads the same number whatever the board does; this makes it read the rail the
# part is actually wired to, which is the difference between a check and a
# comment. Verified: moving the comparators back to 3V3 fails
# test_the_comparators_can_see_the_whole_signal_range, and did not before.
RAILS = {"5V": "rail.5v", "3V3": "rail.3v3"}


def _supply_of(pad_net, address, pad, spec):
    """The band of the rail a part's supply pin is on, read from the netlist."""
    net = pad_net.get((address, pad))
    assert net in RAILS, f"{address} pin {pad} is on {net!r}, which is not a declared rail"
    return net, spec(RAILS[net], "voltage")


def _thresholds(design, pad_net):
    """Every net a DAC output drives."""
    return {
        pad_net[(DAC, pad)]
        for pad in ("6", "7", "8", "9")
        if (DAC, pad) in pad_net
    }


# --- the trip points themselves ----------------------------------------------


def test_every_phase_current_is_watched_in_both_directions(design, pad_net, comparators):
    """
    Each phase has two comparators, and they face opposite ways.

    Bipolar current sensing puts zero amps in the middle of the range, so an
    over-current leaves that point in either direction and one comparator can
    only ever catch one of them. Two facing the same way would look like a
    complete set on a schematic and protect half of what they appear to.
    """
    thresholds = _thresholds(design, pad_net)
    watched = {}
    for address, (inverting, non_inverting, _) in comparators.items():
        for signal, other, rising in ((inverting, non_inverting, True),
                                      (non_inverting, inverting, False)):
            if signal and signal.endswith("_SENSE") and other in thresholds:
                watched.setdefault(signal, []).append(rising)

    missing = []
    for phase in ("FAST1_SENSE", "FAST2_SENSE", "FAST3_SENSE"):
        senses = sorted(watched.get(phase, []))
        if senses != [False, True]:
            missing.append(
                f"  {phase}: {len(senses)} comparators, "
                f"{'both the same way round' if len(senses) == 2 else 'watching one direction'}"
            )
    assert not missing, "Phase currents:\n" + "\n".join(missing)
    assert watched.get("FAST4_SENSE") == [True], (
        f"the DC link is watched by {watched.get('FAST4_SENSE')}, and it needs one "
        "comparator that trips when it rises"
    )


def test_every_comparator_falls_on_a_trip(design, pad_net, comparators):
    """
    Whichever way round a comparator is wired, its output goes *low* on a trip.

    That is what lets seven push-pull outputs share one bus: each pulls it down
    through a diode of its own. One wired the other way would not just fail to
    trip - it would hold the bus up through its diode and mask the others.

    Which way round is which comes from the netlist: the threshold on the
    non-inverting input means the output falls as the signal rises, and the
    other way for a falling trip. Both are correct here, and this is what says
    each one is one or the other rather than neither.
    """
    thresholds = _thresholds(design, pad_net)
    wrong = []
    for address, (inverting, non_inverting, output) in sorted(comparators.items()):
        signal_on_inverting = bool(inverting and inverting.endswith("_SENSE"))
        signal_on_non_inverting = bool(non_inverting and non_inverting.endswith("_SENSE"))
        if signal_on_inverting == signal_on_non_inverting:
            wrong.append(f"  {address}: signals on {inverting!r} and {non_inverting!r}")
            continue
        threshold = non_inverting if signal_on_inverting else inverting
        if threshold not in thresholds:
            wrong.append(f"  {address}: compares against {threshold!r}, which no DAC output drives")
        if output is None:
            wrong.append(f"  {address}: output on no net")
    assert not wrong, "Comparators:\n" + "\n".join(wrong)


def test_every_comparator_reaches_the_trip_bus_through_its_own_diode(
    design, pad_net, comparators
):
    """
    Seven outputs, seven diodes, one bus, and no two outputs wired together.

    Push-pull outputs cannot be wire-ANDed: one driving high while another
    drives low is a short across both. The diodes are what make the same
    topology work - each can pull the bus down, none can hold it up, and none
    can fight another.
    """
    anodes = {
        address for address, part in design["parts"].items()
        if part["symbol"] == "Diode:BAT54A" and pad_net.get((address, "3")) == BUS
    }
    reached = {}
    for address in anodes:
        for pad in ("1", "2"):
            net = pad_net.get((address, pad))
            if net:
                reached[net] = f"{address}:{pad}"

    outputs = {output for _, _, output in comparators.values() if output}
    orphans = sorted(outputs - set(reached))
    assert not orphans, (
        "Comparator outputs that do not reach the trip bus:\n"
        + "\n".join(f"  {net}" for net in orphans)
    )
    shared = [net for net in outputs if len(design["nets"][net]) != 2]
    assert not shared, (
        "Comparator outputs sharing a net with something other than one diode:\n"
        + "\n".join(f"  {net}: {design['nets'][net]}" for net in shared)
    )


def test_the_whole_trip_path_fits_the_budget(spec, comparators):
    """
    Comparator, latch and buffer, every one of them at its worst case.

    This is the number the block exists to produce. What is left over is what
    the tap network in M6 may spend, and it is deliberately most of the budget:
    an RC that slows the edge at the comparator's input costs delay twice over,
    once in the filter and again as the comparator's own delay stretches at
    lower overdrive.
    """
    _, trip_budget = spec("trip", "budget")
    comparator = max(spec(address, "propagation_delay_max")[0] for address in comparators)
    latch, _ = spec(LATCH, "preset_to_output_max")
    buffer_off, _ = spec(BUFFER, "disable_time_max")
    spent = comparator + latch + buffer_off
    assert spent < trip_budget, (
        f"{spent * 1e9:.1f} ns of a {trip_budget * 1e9:g} ns budget before the "
        "signal has even been filtered"
    )
    # And the rest has to cover the tap network in front of the comparators,
    # which `trip.reserved_share` is the ceiling on. This comment used to say
    # the taps were raw and the reservation was headroom for a filter not yet
    # drawn; the filter was there all along, as the ADC's own capacitor on the
    # node a comparator watches. What it costs is measured in
    # `test_a_trip_stops_the_outputs_inside_the_budget` and held under this
    # share by `test_the_filter_does_not_load_the_tap_it_sits_beside`.
    _, reserved = spec("trip", "reserved_share")
    assert spent < trip_budget * (1.0 - reserved), (
        f"{spent * 1e9:.1f} ns leaves only {(trip_budget - spent) * 1e9:.1f} ns "
        f"of the {trip_budget * 1e9:g}, and {reserved * 100:g}% is reserved for "
        f"the tap filter the comparators will need"
    )


# --- what the thresholds are worth -------------------------------------------


def test_the_comparators_can_see_the_whole_signal_range(spec, pad_net, comparators):
    """
    Every voltage a signal or a threshold can reach is inside the comparators'
    common-mode range.

    This is why they run from 5 V rather than the logic rail. Their inputs are
    specified to 0.2 V below their supply, and the signals arrive scaled to
    VREF+ at 3.0 V. On a 3.3 V rail at the bottom of its band that is 3.135 −
    0.2 = 2.935 V of guaranteed range against a 3.006 V signal: outside it, by
    seventy millivolts, in the one place where being outside it means a trip
    point that quietly stops working.
    """
    _, reference_high = spec("vref.ic", "output_voltage")
    _, threshold_high = spec("rail.3v3", "voltage")
    highest = max(reference_high, threshold_high)
    for address in sorted(comparators):
        rail, (rail_low, _) = _supply_of(pad_net, address, "4", spec)
        supply_low, supply_high = spec(address, "supply_voltage")
        headroom, _ = spec(address, "common_mode_headroom")
        assert supply_low <= rail_low <= supply_high, (
            f"{address} runs from {rail} at {rail_low:g} V and takes "
            f"{supply_low:g} to {supply_high:g} V"
        )
        assert highest <= rail_low - headroom, (
            f"{address} runs from {rail}: a signal or threshold can reach "
            f"{highest:.3f} V and its inputs are specified to "
            f"{rail_low - headroom:.3f} V"
        )


def test_the_thresholds_are_as_accurate_as_the_board_claims(spec, pad_net, comparators):
    """
    What the trip point is worth, worked from where the DAC's reference comes
    from and what the comparator adds.

    The DAC's full scale *is* its supply, so the logic rail's tolerance lands
    directly on every threshold, while everything the ADCs measure is
    ratiometric to VREF+ instead. That mismatch is the dominant term and it is
    the reason this check exists rather than a comment.
    """
    rail, (rail_low, rail_high) = _supply_of(pad_net, DAC, "1", spec)
    supply_low, supply_high = spec(DAC, "supply_voltage")
    offset = max(spec(address, "input_offset_voltage")[0] for address in comparators)
    hysteresis = max(spec(address, "input_hysteresis")[0] for address in comparators)
    _, allowed = spec("trip", "threshold_tolerance")

    assert supply_low <= rail_low and rail_high <= supply_high, (
        f"the DAC runs from {rail} at {rail_low:g} to {rail_high:g} V and takes "
        f"{supply_low:g} to {supply_high:g} V"
    )
    full_scale = (rail_low + rail_high) / 2
    floor, _ = spec("trip", "threshold_floor")
    # **The threshold the errors are worst at, not full scale.** The comment
    # here said "at the least useful end: a threshold near the bottom of the
    # range, where a fixed offset is the largest fraction of it" and then
    # divided by full scale, which is the other end. At a quarter of full
    # scale every millivolt term is four times the share it was being given.
    threshold = floor * full_scale

    bits, _ = spec(DAC, "resolution_bits")
    dac_offset, _ = spec(DAC, "offset_error")
    dac_gain, _ = spec(DAC, "gain_error")
    dac_inl, _ = spec(DAC, "integral_nonlinearity")

    terms = {
        # The DAC's full scale *is* the supply, so the rail's spread lands on
        # every threshold in proportion.
        "the rail the DAC uses as its reference":
            (rail_high - rail_low) / 2 / full_scale,
        "the comparator": (offset + hysteresis) / threshold,
        # And the three the part itself declares, which were not summed at all.
        "the DAC's offset": dac_offset / threshold,
        "the DAC's gain error": dac_gain,
        "the DAC's nonlinearity": dac_inl * full_scale / 2 ** bits / threshold,
    }
    total = sum(terms.values())
    assert total <= allowed, (
        f"at a threshold of {threshold:.3f} V, {floor * 100:g} % of full scale, the "
        f"trip point is good to {total * 100:.1f} % against {allowed * 100:g} % "
        f"declared:\n" + "\n".join(
            f"  {share * 100:5.2f} % from {name}"
            for name, share in sorted(terms.items(), key=lambda kv: -kv[1]))
    )


def test_the_dac_resolves_finer_than_the_comparator_can_use(spec, pad_net, comparators):
    """
    More bits than the comparator's own offset can make use of, which is the
    right way round.

    12 bits over a 3.3 V range is under a millivolt a step, against ±6.5 mV of
    input offset. The DAC is not what limits the trip point, and this says so
    in the form that would notice if a cheaper part were dropped in.
    """
    bits, _ = spec(DAC, "resolution_bits")
    _, (_, full_scale) = _supply_of(pad_net, DAC, "1", spec)
    # The worst of the seven, not the first one's. Naming an address here made
    # the check about one comparator; the fixture already has them all.
    offset = max(spec(address, "input_offset_voltage")[0] for address in comparators)
    step = full_scale / 2 ** bits
    assert step < offset, (
        f"a DAC step is {step * 1e3:.2f} mV and the comparator's offset is "
        f"{offset * 1e3:g} mV: the resolution is what limits the trip point"
    )


def test_the_dac_has_a_channel_for_every_threshold(design, pad_net, spec):
    """Every distinct threshold has a DAC output of its own, and none is shared."""
    channels, _ = spec(DAC, "channels")
    driven = _thresholds(design, pad_net)
    assert len(driven) <= channels, (
        f"{len(driven)} thresholds from a {channels:g}-channel DAC"
    )
    for net in sorted(driven):
        sources = [
            address for address, pad in
            {tuple(node) for node in design["nets"][net]}
            if address == DAC
        ]
        assert len(sources) == 1, f"{net} is driven by {len(sources)} DAC outputs"


# --- the connector the signals arrive on -------------------------------------


def test_the_analog_connector_carries_what_the_pin_map_says(design, pad_net, pin_map):
    """The generated pinout and the netlist agree, pin by pin."""
    expected = pin_map.header_pins(pin_map.HEADER_ANALOG, pin_map.HEADER_GROUND,
                                _pin_count(pad_net))
    wrong = []
    for number, net in sorted(expected.items()):
        found = pad_net.get((HEADER, str(number)))
        if found != net:
            wrong.append(f"  pin {number}: on {found!r}, table says {net!r}")
    assert not wrong, "Analog connector pins:\n" + "\n".join(wrong)


def test_every_analog_signal_sits_next_to_a_ground(pad_net, pin_map):
    """
    Same rule as the digital connector, and it matters more here.

    A current-sense signal picking up a millivolt of crosstalk is a milliamp of
    error in whatever the control loop does next, and the return path is what
    decides how much it picks up.
    """
    pins = pin_map.header_pins(pin_map.HEADER_ANALOG, pin_map.HEADER_GROUND,
                                _pin_count(pad_net))
    lonely = []
    for number, net in pins.items():
        if net == pin_map.HEADER_GROUND:
            continue
        if not any(pins.get(n) == pin_map.HEADER_GROUND
                   for n in (number - 2, number - 1, number + 1, number + 2)):
            lonely.append(f"  pin {number} ({net})")
    assert not lonely, "Analog pins with no ground beside them:\n" + "\n".join(lonely)


def test_the_comparators_watch_what_the_connector_brings_in(design, pad_net, comparators, pin_map):
    """
    The nets the comparators sit on are the connector's own, not the filtered
    ones the ADCs see.

    This is the whole reason the tap is where it is. A filter with a corner low
    enough to be worth having on a megasample ADC costs hundreds of nanoseconds;
    the trip budget is fifty. Take the trip from behind the filter and it is not
    a trip, it is a slow apology.
    """
    on_connector = {
        pad_net[(HEADER, str(number))]
        for number in range(1, 31)
        if (HEADER, str(number)) in pad_net
    }
    watched = {
        net for inverting, non_inverting, _ in comparators.values()
        for net in (inverting, non_inverting)
        if net and net.endswith("_SENSE")
    }
    stranded = sorted(watched - on_connector)
    assert not stranded, (
        "Comparators watching nets the connector does not bring in:\n"
        + "\n".join(f"  {net}" for net in stranded)
    )


def test_the_board_sends_out_its_reference_and_an_analog_supply(design, pad_net, spec):
    """
    VREF+ and 3V3A reach the connector, and what bounds them is a part on this
    board rather than the connector.

    The power board's sensors are ratiometric to the same reference the ADCs
    use, which is the only way a measurement made there means anything here.
    The supply beside it was the 5 V rail through a bead until the pins at the
    other end of those sensors were costed; it is a regulator now, and this is
    where its ratings are held against what the connector promises.
    """
    on_connector = {
        pad_net[(HEADER, str(number))]
        for number in range(1, 31)
        if (HEADER, str(number)) in pad_net
    }
    assert {"VREF+", "3V3A"} <= on_connector, (
        f"the connector carries {sorted(on_connector)}"
    )

    regulator = [address for address, part in design["parts"].items()
                 if part["symbol"].startswith("Regulator_Linear:")]
    assert len(regulator) == 1, f"the analog supply comes from {regulator}"
    ldo = regulator[0]
    assert pad_net[(ldo, "5")] == "3V3A", (
        f"the regulator's output is on {pad_net[(ldo, '5')]}, not the rail the "
        f"connector carries"
    )

    contact, _ = spec(HEADER, "current_rating")
    _, budget = spec("analog", "supply_current")
    _, allowed = spec("analog", "supply_drop")
    rated, _ = spec(ldo, "output_current_max")
    _, accuracy = spec(ldo, "output_accuracy")
    nominal, _ = spec(ldo, "output_voltage")

    assert budget <= rated * _derating(spec), (
        f"3V3A is budgeted {budget * 1e3:g} mA against a regulator rated "
        f"{rated * 1e3:g} mA, which is past the half this board derates to"
    )
    assert budget <= contact, (
        f"3V3A is budgeted {budget * 1e3:g} mA and a contact carries "
        f"{contact:g} A"
    )

    # The bead's DC drop used to be the thing measured here. A regulator has
    # no DC drop; what moves its output away from nominal is its own accuracy,
    # and that is what the sensors' headroom is specified against.
    assert nominal * accuracy <= allowed, (
        f"{nominal * accuracy * 1e3:.0f} mV of {accuracy * 100:g}% accuracy on "
        f"a {nominal:g} V rail, against the {allowed * 1e3:g} mV the analog "
        f"supply may lose"
    )

    # And it has to have somewhere to regulate from. The dropout figure is the
    # one at the part's full 300 mA rather than at the 50 this draws, which is
    # the conservative end and still leaves a volt.
    supply_low, supply_high = spec("rail.5v", "voltage")
    _, dropout = spec(ldo, "dropout_at_max_current")
    in_low, in_high = spec(ldo, "input_voltage_min"), spec(ldo, "input_voltage_max")
    assert in_low[0] <= supply_low and supply_high <= in_high[1], (
        f"{ldo} takes {in_low[0]:g} to {in_high[1]:g} V and the rail feeding it "
        f"is {supply_low:g} to {supply_high:g} V"
    )
    assert supply_low - dropout >= nominal * (1 + accuracy), (
        f"{(supply_low - dropout):.3f} V at the regulator's input against "
        f"{nominal * (1 + accuracy):.3f} V wanted at its output"
    )

    # The 5 V rail carries this load plus whatever the regulator itself takes.
    _, quiescent = spec(ldo, "quiescent_current")
    _, rail_budget = spec("rail.5v", "current")
    assert budget + quiescent <= rail_budget, (
        f"the analog connector's {budget * 1e3:g} mA and the regulator's own "
        f"{quiescent * 1e6:g} uA against a {rail_budget * 1e3:g} mA rail"
    )


def test_the_analog_supply_is_decoupled_where_it_leaves(
    design, pad_net, spec, position, effective_capacitance
):
    """
    A bulk capacitor and a high-frequency one on 3V3A, as every rail here has -
    and enough of the first for the regulator to be stable.

    TI's figure is an *effective* capacitance of 0.1 uF, which is its own word
    for "after bias and temperature derating". The nominal fitted here is an
    order of magnitude above it, which is the margin that makes the question
    this board cannot answer elsewhere - what DC bias does to a ceramic - not
    a question here.
    """
    regulator = [address for address, part in design["parts"].items()
                 if part["symbol"].startswith("Regulator_Linear:")]
    assert len(regulator) == 1, f"the analog supply comes from {regulator}"
    _, needs = spec(regulator[0], "output_capacitance_min")

    # At the bias they sit at, not at the number on the reel - the regulator
    # asks for an *effective* 0.1 uF and says so in those words.
    _, out_bias = spec(regulator[0], "output_voltage")
    found = []
    for address, part in design["parts"].items():
        if part["symbol"] != "Device:C":
            continue
        if {pad_net.get((address, "1")), pad_net.get((address, "2"))} == {"3V3A", "GND"}:
            found.append(effective_capacitance(address, out_bias))
    assert len(found) >= 2, f"3V3A has {len(found)} capacitors on it"
    assert max(found) >= 5 * min(found), (
        f"3V3A's capacitors are {[f'{c * 1e6:.2f} uF' for c in sorted(found)]}, which is "
        "two of the same thing rather than bulk and high frequency"
    )
    assert sum(found) >= needs, (
        f"{sum(found) * 1e6:.2f} uF on 3V3A against the {needs * 1e6:g} uF the "
        f"regulator needs to be stable"
    )

    # And the input side. TI's condition is "if the device is not located
    # close to the power source", and the 5 V island is at the other end of
    # this board, so it applies - which means a capacitor somewhere on the
    # 5 V net does not answer it. It has to be *this* regulator's, and what
    # makes it so is the same reach the MCU's own decoupling is held to.
    supply = pad_net[(regulator[0], "1")]
    _, wants = spec(regulator[0], "input_capacitance_min")
    _, reach = spec("layout", "decoupling_reach")
    here = position(regulator[0])
    near = [address for address, part in design["parts"].items()
            if part["symbol"] == "Device:C"
            and {pad_net.get((address, "1")),
                 pad_net.get((address, "2"))} == {supply, "GND"}
            and math.dist(here, position(address)) <= reach]
    assert near, (
        f"nothing on {supply} sits within {reach:g} mm of {regulator[0]}, so "
        f"its input capacitor is the rail's rather than its own"
    )
    _, in_bias = spec("rail.5v", "voltage")
    across = sum(effective_capacitance(address, in_bias) for address in near)
    assert across >= wants, (
        f"{across * 1e6:.2f} uF within {reach:g} mm of {regulator[0]} against "
        f"the {wants * 1e6:g} uF it asks for at its input"
    )


def test_a_comparator_pulls_the_trip_bus_to_a_valid_low(
    design, pad_net, comparators, spec, forward_voltage
):
    """
    What the latch sees when a comparator asserts, through the diode between them.

    Same arithmetic as the fault lines, with one difference that matters: these
    comparators run from 5 V while the bus and the latch are on 3.3 V. That is
    fine in the direction that counts - a low is a low - and it is why the
    diodes are not optional even before the seven-outputs-one-node argument.
    """
    threshold, _ = spec(LATCH, "input_low_voltage_max")
    diodes = sorted(
        address for address, part in design["parts"].items()
        if part["symbol"] == "Diode:BAT54A" and pad_net.get((address, "3")) == BUS
    )
    assert diodes, "no diodes between the comparators and the trip bus"
    # At the current the bus's own pull-up passes and the temperature the
    # board declares, not at the datasheet's 0.1 mA row - the same correction
    # `test_the_trip_bus_reaches_a_valid_low_through_its_diodes` needed, and
    # the same shared interpolation.
    _, rail = spec("rail.3v3", "voltage")
    ambient, _ = spec("environment", "ambient")
    resistance, _ = spec("safety.r_trip_pullup", "resistance")
    for address in sorted(comparators):
        swing, _ = spec(address, "output_swing_from_rail")
        drop = max(forward_voltage(diode, 100e-6, 25.0) for diode in diodes)
        for _ in range(20):
            current = (rail - (swing + drop)) / resistance
            drop = max(forward_voltage(diode, current, ambient) for diode in diodes)
        reached = swing + drop
        assert reached < threshold, (
            f"{address} asserting leaves the bus at {reached:.2f} V against a "
            f"{threshold:g} V threshold"
        )


# Microchip's MCP4728 Table 3-1, Pin Function Table, read as text from
# DS22187E. `parts/MSOP10/evidence/sources.json` identifies the document.
# Pin 5, RDY/BSY, is deliberately absent: the datasheet says to leave it
# floating when it is not used, and this board does not use it.
DAC_PINS = {
    "1": "3V3",          # VDD
    "2": "DAC_SCL",      # I2C serial clock, open drain
    "3": "DAC_SDA",      # I2C serial data, open drain
    "4": "GND",          # LDAC, held low so an output follows its register
    "10": "GND",         # VSS
}


def test_the_threshold_dac_is_wired_the_way_its_pin_table_says(design, pad_net):
    """
    Every supply and control pin of the threshold DAC is on the right net.

    The review note said this part's pinout came from KiCad's symbol and
    LCSC's data because the datasheet could not be read here. It can: the pin
    table is text. So the netlist is asserted against Microchip's own table,
    and the four analog outputs are asserted to be four distinct nets rather
    than named here - which channel drives which threshold is this board's
    choice, but two thresholds sharing a channel would be a wiring mistake.

    Pin 5 is checked by its absence: the datasheet says to float RDY/BSY when
    it is unused, and a board that ties it anywhere has misread that.
    """
    wrong = [f"  pin {pin}: on {pad_net.get(('trip.dac', pin))!r}, "
             f"Microchip's table says {expected!r}"
             for pin, expected in sorted(DAC_PINS.items())
             if pad_net.get(("trip.dac", pin)) != expected]

    if pad_net.get(("trip.dac", "5")) is not None:
        wrong.append("  pin 5 (RDY/BSY): connected, and the datasheet says to leave it floating")

    outputs = [pad_net.get(("trip.dac", pin)) for pin in ("6", "7", "8", "9")]
    if len(set(outputs)) != len(outputs):
        wrong.append(f"  the four outputs are not four distinct nets: {outputs}")

    assert not wrong, (
        "Threshold DAC pins:\n" + "\n".join(wrong)
        + "\nSee parts/MSOP10/MSOP10.md."
    )


def test_the_thresholds_can_reach_the_top_of_the_signal_range(spec, pad_net):
    """
    The DAC's full scale covers everything the comparators are asked to trip on.

    A threshold that cannot be placed in the top of the measurement range is
    not a protection limit, it is a nuisance trip. Everything the sense chain
    delivers is ratiometric to VREF+, so that is the range a threshold has to
    span.

    **This is a firmware requirement, and it is the reason this check exists.**
    The MCP4728 ships with the internal 2.048 V reference selected - datasheet
    Table 4-2, committed at `parts/MSOP10/evidence/factory_default.png` - and
    2.048 V is 68 % of VREF+. A board that never writes the reference bit
    cannot set the DC-link over-voltage trip above two thirds of the sensor's
    range, and for the bipolar phase currents, which idle at mid-scale, it
    cannot set one above 37 % of the positive half.

    So the check compares the range against the reference the board *uses*,
    the supply, and the assertion below fails if that stops being enough. The
    power-up state is still the safe one - every channel ships at code zero,
    so an unprogrammed board sits tripped - which is why this is a limitation
    to program around rather than a hazard.
    """
    reference, _ = spec("vref.ic", "output_voltage")
    internal, _ = spec(DAC, "internal_reference")
    rail, (rail_low, _) = _supply_of(pad_net, DAC, "1", spec)

    assert rail_low >= reference, (
        f"the DAC runs from {rail} at {rail_low:g} V and has to place a "
        f"threshold anywhere in a {reference:g} V signal range"
    )
    assert internal < reference, (
        "the factory-default internal reference reaches "
        f"{internal:g} V of a {reference:g} V range, so nothing would have to "
        "select the supply - and this check would be pointless"
    )


def test_every_comparator_is_switched_on(design, pad_net, spec, comparators, board_dir):
    """
    The shutdown pin is at a level the datasheet calls enabled, on all seven.

    The trap is that the TLV3501 states this pin **relative to its positive
    supply**, not to ground: "within 0.9 V of the most positive supply, the
    part is disabled. When it is more than 1.7 V below the most positive
    supply, the part is enabled." Read as an ordinary active-low enable it
    comes out backwards, and a comparator that is off has no output, no trip,
    and nothing anywhere that says so - the latch simply never sets.

    Which pin it is comes from the symbol, and the level from the rails the
    part is actually on, so this holds if the comparator is ever moved to
    another supply.
    """
    import sys

    sys.path.insert(0, str(board_dir.parent / "tools"))
    from symbols import symbol_pin_names

    # Each rail twice: the supply at its lowest and the shutdown net at its
    # highest is the corner that leaves least headroom. One figure for both
    # took the optimistic one.
    low = {"GND": 0.0}
    high = {"GND": 0.0}
    for name in ("5V", "3V3"):
        low[name], high[name] = spec(f"rail.{name.lower()}", "voltage")

    wrong = []
    for address in sorted(comparators):
        names = {name: pad for pad, name in
                 symbol_pin_names(design["parts"][address]["symbol"]).items()}
        assert "SHDN" in names, f"{address}'s symbol has no SHDN pin"
        shutdown = pad_net.get((address, names["SHDN"]))
        supply = pad_net.get((address, names["V+"]))
        assert supply in low, f"{address} runs from {supply!r}, which is not a rail"
        if shutdown not in high:
            wrong.append(f"  {address}: SHDN is on {shutdown!r}, which is not a rail")
            continue
        enable_below, _ = spec(address, "shutdown_enable_below_supply")
        disable_within, _ = spec(address, "shutdown_disable_within_supply")
        headroom = low[supply] - high[shutdown]
        if headroom < enable_below:
            # Both thresholds, because between them the datasheet promises
            # nothing: a pin 1.2 V below the supply is neither enabled nor
            # disabled, and saying which of the two it is makes the difference
            # between a comparator that is off and one that might be.
            state = ("disabled" if headroom <= disable_within
                     else "in the band between the two thresholds")
            wrong.append(
                f"  {address}: SHDN sits {headroom:.2f} V below its supply, "
                f"which is {state} - the part needs {enable_below:g} V"
            )
    assert not wrong, "Comparators not switched on:\n" + "\n".join(wrong)
