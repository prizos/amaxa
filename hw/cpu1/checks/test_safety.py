"""
The safety chain, from the netlist rather than from a drawing.

What this file is for is one sentence: **an MCU pin cannot reach a gate driver
unless firmware is holding an enable low and has cleared a latch that powers up
tripped.** Every check below is part of establishing that, and every one of them
reads the design rather than a table of what the design is supposed to be.

Datasheets: TI SCAS298N (SN74LVC541A, June 2014) and SCES794E (SN74LVC1G74,
January 2015), and the BAT54A data recorded in `parts/SOT23/SOT23.md`.
"""

import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from symbols import symbol_description, symbol_pin_names  # noqa: E402

BUFFERS = ("safety.buffer1", "safety.buffer2")
LATCH = "safety.latch"
HEADER = "header.digital"


def _pin_count(pad_net) -> int:
    """How many pins the connector has, counted on the board rather than said."""
    return len([pad for reference, pad in pad_net if reference == HEADER])


@pytest.fixture(scope="module")
def pad_net(design):
    return {tuple(node): net for net, nodes in design["nets"].items() for node in nodes}


@pytest.fixture(scope="module")
def net_pads(design):
    return {net: {tuple(node) for node in nodes} for net, nodes in design["nets"].items()}


@pytest.fixture(scope="module")
def pin_map(board_dir):
    import sys
    sys.path.insert(0, str(board_dir.parent / "tools"))
    from mcu_pins import load_source
    return load_source(board_dir / "pinmap.py", "cpu1_pinmap_checks")


def _buffer_channels(design, pad_net):
    """(input net, output net) for every channel of every octal buffer."""
    out = []
    for address in BUFFERS:
        assert address in design["parts"], f"{address} is not on the board"
        for channel in range(8):
            source = pad_net.get((address, str(2 + channel)))
            drain = pad_net.get((address, str(18 - channel)))
            out.append((address, channel, source, drain))
    return out


def _through_resistor(design, pad_net, net, symbol="Device:R"):
    """Every (address, far net) reachable from `net` through one two-pad part."""
    found = []
    for address, part in design["parts"].items():
        if part["symbol"] != symbol:
            continue
        a, b = pad_net.get((address, "1")), pad_net.get((address, "2"))
        if a == net and b is not None:
            found.append((address, b))
        elif b == net and a is not None:
            found.append((address, a))
    return found


# --- the path from a pin to the connector ------------------------------------


def test_no_pwm_pin_reaches_the_connector_except_through_a_buffer(
    design, pad_net, net_pads, pin_map
):
    """
    Nothing the timers drive is on the connector. Not one net.

    This is the check the whole block exists for. Every PWM net the MCU drives
    must end at a buffer input; if any of them also appeared on the header, the
    buffer would be decoration - the signal would reach the gate driver whether
    the latch had tripped or not.
    """
    header_pads = {pad for pad in net_pads if any(
        address == HEADER for address, _ in net_pads[pad])}
    driven = [p.net_name for p in pin_map.PINS if p.name.startswith(("PWM1_", "PWM2_"))]
    escaped = sorted(net for net in driven if net in header_pads)
    assert not escaped, (
        "PWM nets that reach the connector without passing through a buffer:\n"
        + "\n".join(f"  {net}" for net in escaped)
    )


def test_every_pwm_pin_arrives_at_a_buffer_input(design, pad_net, pin_map):
    """
    And the other half: each of them does reach one, exactly once.

    A pin that reaches no buffer is an output the firmware can drive and nobody
    can stop; a pin on two buffer inputs is a wiring mistake that would only
    show up as a strange waveform.
    """
    inputs = {}
    for _, _, source, _ in _buffer_channels(design, pad_net):
        if source is not None:
            inputs[source] = inputs.get(source, 0) + 1
    wrong = []
    for p in pin_map.PINS:
        if not p.name.startswith(("PWM1_", "PWM2_")) or p.name == "PWM_ENABLE_N":
            continue
        if inputs.get(p.net_name, 0) != 1:
            wrong.append(f"  {p.net_name}: on {inputs.get(p.net_name, 0)} buffer inputs")
    assert not wrong, "PWM pins and their buffers:\n" + "\n".join(wrong)


def test_every_buffered_output_has_a_series_resistor_and_a_pull_down(
    design, pad_net, spec
):
    """
    Each buffer output reaches the connector through a resistor, and the pin it
    reaches is held low by another.

    The pull-down is what makes "high impedance" mean "off". A buffer in
    high-impedance drives nothing at all, and a gate driver's input left
    floating is a coin toss; with 10 kOhm to ground it is a zero. This is the
    single part whose absence would leave every other check here still passing.
    """
    problems = []
    for address, channel, source, drain in _buffer_channels(design, pad_net):
        if source == "GND":
            continue  # the spare channel, tied low on purpose
        if drain is None:
            problems.append(f"  {address} channel {channel}: output on no net")
            continue
        series = _through_resistor(design, pad_net, drain)
        if len(series) != 1:
            problems.append(f"  {drain}: {len(series)} resistors in series, expected 1")
            continue
        resistor, far = series[0]
        low, high = spec(resistor, "resistance")
        if not 22 <= low <= high <= 47:
            problems.append(f"  {resistor}: {low:g}-{high:g} ohm, not a damping resistor")
        pull_downs = [
            (a, n) for a, n in _through_resistor(design, pad_net, far) if n == "GND"
        ]
        if len(pull_downs) != 1:
            problems.append(f"  {far}: {len(pull_downs)} pull-downs to ground, expected 1")
            continue
        value, _ = spec(pull_downs[0][0], "resistance")
        if value < 1_000:
            problems.append(f"  {pull_downs[0][0]}: {value:g} ohm is a load, not a pull-down")
    assert not problems, "Buffered outputs:\n" + "\n".join(problems)


def test_every_connector_signal_sits_next_to_a_ground(pad_net, pin_map):
    """
    No pin on the connector is more than one position from a return path.

    A ribbon cable to a gate driver with its grounds bunched at one end is an
    antenna with a connector on it. The pattern comes from the pin map's own
    table, so this checks the generator rather than a drawing of the result.
    """
    pins = pin_map.header_pins(pin_map.HEADER_DIGITAL, pin_map.HEADER_GROUND,
                                _pin_count(pad_net))
    lonely = []
    for number, net in pins.items():
        if net == pin_map.HEADER_GROUND:
            continue
        # Neighbours: the other pin of this position, and the ones either side.
        position = (number + 1) // 2
        neighbours = {number - 2, number - 1, number + 1, number + 2}
        if not any(pins.get(n) == pin_map.HEADER_GROUND for n in neighbours):
            lonely.append(f"  pin {number} ({net}) at position {position}")
    assert not lonely, "Connector pins with no ground beside them:\n" + "\n".join(lonely)


# --- the two things that can stop it -----------------------------------------


def test_both_buffers_are_gated_by_the_enable_and_by_the_latch(design, pad_net):
    """
    Each buffer has both of its enables used, and used for different things.

    A '541 has two, and they are in series: either one high is high impedance.
    One is the MCU's, so firmware can stop the board; the other is the latch's,
    so hardware can. Tying either permanently low would leave the other still
    working, and the board would look fine until the day it mattered.
    """
    problems = []
    for address in BUFFERS:
        first = pad_net.get((address, "1"))    # OE1
        second = pad_net.get((address, "19"))  # OE2
        if first != "PWM_ENABLE_N":
            problems.append(f"  {address}: first enable on {first!r}, not the MCU's")
        if second != "TRIPPED":
            problems.append(f"  {address}: second enable on {second!r}, not the latch's")
    assert not problems, "Buffer enables:\n" + "\n".join(problems)


def test_the_enable_is_pulled_to_off(design, pad_net, spec):
    """
    The MCU's enable is pulled up, so a pin nobody is driving means "off".

    During reset, and before firmware has configured anything, every GPIO is an
    input. Without this resistor the buffers' enable floats, and a floating CMOS
    input is not a low - it is whatever the board's leakage decides. Pulled up,
    the same moment is unambiguous: outputs off.
    """
    pulls = _through_resistor(design, pad_net, "PWM_ENABLE_N")
    to_rail = [(a, n) for a, n in pulls if n == "3V3"]
    assert len(to_rail) == 1, (
        f"the enable has {len(to_rail)} pull-ups to the rail, expected 1: {pulls}"
    )
    value, _ = spec(to_rail[0][0], "resistance")
    assert 1_000 <= value <= 100_000, f"{to_rail[0][0]} is {value:g} ohm"
    assert not [n for _, n in pulls if n == "GND"], (
        "the enable is also pulled down, which is a fight between two resistors"
    )


def _other_end(design, pad_net, address, net):
    """The net on the far side of a two-terminal part."""
    ends = {n for (a, _), n in pad_net.items() if a == address}
    return next((n for n in ends if n != net), None)


def test_every_buffer_input_is_held_somewhere_until_something_drives_it(
    design, pad_net, pin_map
):
    """
    A buffer input that no peripheral drives has a resistor holding it.

    A GPIO comes out of reset as a floating input, and stays one until
    firmware configures it. On a pin that feeds a '541 that is not merely an
    undefined output: a floating CMOS input sits the input stage near
    mid-rail and draws cross-conduction current through it for as long as it
    floats, which on a pin firmware never configures is for ever.

    Most of these inputs are timer channels - TIM1 and TIM8 drive them in
    alternate function, and the pin map says which those are - so they are
    defined as soon as the timer is. `GATE_ENABLE` is the exception: a plain
    GPIO, on PD7, feeding buffer1's A7. It had nothing. The board states this
    rule about itself in `safety_chain()`'s own comments - "every pin nobody
    is driving gets 10 k", listing the enable, both relays and every buffered
    output - and this is the check that the rule is actually followed rather
    than described.

    Which pins count as driven is read from the pin map's function column, so
    moving a signal from a timer channel to a GPIO brings it under the rule.
    """
    buffers = [address for address in design["parts"] if address in BUFFERS]
    assert buffers, "no buffers on this board"

    by_net = {}
    for (address, pad), net in pad_net.items():
        by_net.setdefault(net, set()).add(address)

    peripheral = {pin.net_name for pin in pin_map.PINS if pin.signal != "GPIO"}

    rails = set()
    for address, part in design["parts"].items():
        names = symbol_pin_names(part["symbol"])
        for (a, pad), net in pad_net.items():
            if a == address and names.get(pad) in (
                    "VCC", "VDD", "VIO", "V+", "V-", "VEE", "VSS", "GND"):
                rails.add(net)

    floating = []
    for address in sorted(buffers):
        pad_of = {net: pad for (a, pad), net in pad_net.items()
                  if a == address and pad in {str(n) for n in range(2, 10)}}
        for net in sorted(pad_of):
            if net in peripheral:
                continue                  # a timer drives it
            if net in rails:
                continue                  # tied straight to a rail, like the
                                          # spare input buffer2 grounds
            # **To a rail, and to the right one.** "Some resistor touches this
            # net" was the whole predicate, and it accepted a resistor between
            # two floating nodes and a pull-*up* on the gate-driver enable -
            # both of which leave the defect this was written for exactly as
            # it was, and both of which passed.
            #
            # Which rail is safe is not declared here either: it is whichever
            # one the far side of this buffer is pulled to at the connector,
            # where the board has already decided what an unfitted power board
            # reads as. On a '541 input A(n) is pad n+1 and output Y(n) is pad
            # 19-n, so the output of this input is pad 20-p.
            partner = pad_net.get((address, str(20 - int(pad_of[net]))))
            # The pull that decides the safe state is at the *connector*, on
            # the far side of this channel's series resistor - which is the
            # whole point of the series resistor being before it. So follow
            # one hop out of the buffer's own output before looking.
            outward = {_other_end(design, pad_net, other, partner)
                       for other in by_net.get(partner, ())
                       if design["parts"][other]["symbol"] == "Device:R"}
            safe = {far
                    for beyond in {partner} | {n for n in outward if n}
                    for other in by_net.get(beyond, ())
                    if design["parts"][other]["symbol"] == "Device:R"
                    for far in [_other_end(design, pad_net, other, beyond)]
                    if far in rails}
            held = {far for other in by_net[net]
                    if design["parts"][other]["symbol"] == "Device:R"
                    for far in [_other_end(design, pad_net, other, net)]
                    if far in rails}
            if not held:
                floating.append(
                    f"  {net} reaches {address} and is driven by a plain GPIO "
                    f"with no resistor to a rail holding it")
            elif safe and not (held & safe):
                floating.append(
                    f"  {net} is held to {sorted(held)} while {partner} - the "
                    f"same channel at the connector - is held to {sorted(safe)}. "
                    f"A buffer input pulled the opposite way to its own output "
                    f"asserts the thing the output exists to deny.")
    assert not floating, (
        "Buffer inputs left floating until firmware happens to configure "
        "them:\n" + "\n".join(floating)
    )


def test_the_latch_can_only_be_cleared_by_the_mcu(design, pad_net, spec):
    """
    One pin clears the trip, it is pulled to the inactive state, and nothing
    else on the board touches it.

    The clear is the one input that can undo a trip, so the interesting
    question is what else can reach it. The answer has to be: the MCU, and a
    resistor holding it inactive while the MCU is in reset.

    **And the MCU has to reach it through a capacitor.** A pull-up only covers
    a pin that has gone high-impedance. A pin driven low and then abandoned -
    firmware spinning in a handler that still feeds the watchdog, or a
    debugger halt with the IWDG frozen - holds the clear asserted, and a held
    clear does not leave the board tripped, it leaves it oscillating: PRE
    asserts, the outputs go off, the current decays, PRE releases, the latch
    clears itself and the outputs come back. Sustained over-current at the
    trip threshold, with TRIP_N reading "no break" throughout because both
    inputs low puts Q-bar high.

    Breaking the DC turns a level into a pulse, so a stuck pin clears once and
    then lets go. That is what is asserted here: the walk from the latch's
    clear back to the MCU has to cross a capacitor, and it must not have any
    resistive path to the MCU at all.
    """
    clear = pad_net.get((LATCH, "6"))
    members = {address for address, _ in
               {tuple(n) for n in design["nets"][clear]}}
    assert "mcu" not in members, (
        f"{clear} reaches the MCU directly. A pin driven low and abandoned "
        f"then holds the trip latch cleared, and the board rings between "
        f"tripping and re-arming instead of stopping."
    )
    pulls = _through_resistor(design, pad_net, clear)
    assert [n for _, n in pulls] == ["3V3"], (
        f"the clear is pulled to {[n for _, n in pulls]}, and it has to be the rail: "
        "pulled the other way, a reset pin would clear a trip"
    )

    # Walk back to the MCU through two-terminal parts, remembering what was
    # crossed. Rails are not routes: every pull-up on the board reaches the
    # MCU through its own supply pins, and a walk that steps onto 3V3 arrives
    # everywhere. Which nets those are is read from the symbols.
    rails = set()
    for address, part in design["parts"].items():
        names = symbol_pin_names(part["symbol"])
        for (a, pad), net in pad_net.items():
            if a == address and names.get(pad) in (
                    "VCC", "VDD", "VIO", "VDDA", "V+", "V-", "VEE", "VSS", "GND"):
                rails.add(net)

    hops = {}
    for address, part in design["parts"].items():
        pads = [net for (a, _), net in pad_net.items() if a == address]
        if len(set(pads)) == 2 and part["symbol"] in ("Device:R", "Device:C"):
            a, b = sorted(set(pads))
            hops.setdefault(a, []).append((b, address, part["symbol"]))
            hops.setdefault(b, []).append((a, address, part["symbol"]))

    def routes(net, seen):
        for far, address, symbol in hops.get(net, ()):
            if far in seen or far in rails:
                continue
            if "mcu" in {a for a, _ in design["nets"][far]}:
                yield [(address, symbol)]
                continue
            for rest in routes(far, seen | {far}):
                yield [(address, symbol)] + rest

    paths = list(routes(clear, {clear}))
    assert paths, f"nothing reaches the MCU from {clear}"
    for path in paths:
        assert any(symbol == "Device:C" for _, symbol in path), (
            f"the MCU reaches {clear} through "
            f"{', '.join(address for address, _ in path)} with no capacitor "
            f"in the way, so holding the pin low holds the trip cleared"
        )


def test_the_latch_powers_up_tripped(design, pad_net):
    """
    Reset reaches the latch's preset, so the board comes up with its outputs off.

    A flip-flop's state at power-on is not specified, and neither is it after a
    watchdog reset or a debugger halt. NRST is low in all three, and it is
    wired - through a diode, so the bus can be pulled low by other things
    without any of them pulling on NRST - to the input that sets the latch.
    Without this the board's first state after power-on is undefined, and half
    the time it would be "outputs live".
    """
    preset = pad_net.get((LATCH, "7"))
    assert preset == "TRIP_SET_N", f"the latch's preset is on {preset!r}"

    diodes = [
        address for address, part in design["parts"].items()
        if part["symbol"] == "Diode:BAT54A" and pad_net.get((address, "3")) == preset
    ]
    assert diodes, "nothing reaches the trip bus through a diode"
    cathodes = {
        pad_net.get((address, pad)) for address in diodes for pad in ("1", "2")
    } - {None}
    assert "NRST" in cathodes, (
        f"reset does not reach the trip bus; it carries {sorted(cathodes)}"
    )
    assert {"FAULT1_N", "FAULT2_N"} <= cathodes, (
        f"a gate-driver fault does not trip the latch; the bus carries {sorted(cathodes)}"
    )

    # And every supply that supervises itself. NRST is the MCU noticing its
    # *own* rail has gone, which on the way down is the last thing to happen:
    # by then the comparators and the threshold DAC have been below their
    # 2.7 V minimum for ninety microseconds while the buffers were still
    # driving. A converter's power-good output asserts at the regulation
    # threshold instead, milliseconds earlier, and on the way up as well.
    #
    # Which nets those are is read from the symbols, not listed, so a second
    # converter with a PGOOD pin has to be wired in the same way or this
    # fails. The board had one, pulled up, brought to a test pad and reaching
    # nothing, with the spare half of the very diode pair it needed sitting
    # unused beside it.
    supervisors = {
        net
        for address, part in design["parts"].items()
        for pad, name in symbol_pin_names(part["symbol"]).items()
        if name in ("PGOOD", "PG", "POK", "PWRGD")
        for net in (pad_net.get((address, pad)),)
        if net
    }
    assert supervisors, "no converter on this board reports whether it is regulating"
    missing = sorted(supervisors - cathodes)
    assert not missing, (
        f"{', '.join(missing)} says when a rail stops regulating and does not "
        f"reach the trip bus; it carries {sorted(cathodes)}. That leaves NRST "
        f"as the only supply-related preset, and NRST is late."
    )


def _leakage(spec, address: str, ambient: float) -> float:
    """
    A Schottky's reverse current at a temperature, as a maximum.

    FIG.2 is plotted at seven temperatures and this interpolates between the
    two recorded points that bracket the ambient - on a log axis, because that
    is how the quantity behaves and how the figure is drawn. Outside them it
    holds the nearest, rather than extrapolating a slope fitted somewhere
    else.

    Three of the seven curves are recorded, 25, 75 and 125 degC, so at the
    declared 45 degC this interpolates 25 to 75 across the 50 degC curve that
    is plotted and not recorded. That is conservative - the 50 degC curve sits
    below the interpolation - but it is worth knowing the brackets are the
    recorded points and not the drawn ones.

    Then the spread from typical to maximum, because those curves are typical
    and a noise budget needs the other one. The electrical table gives both at
    its own condition and their ratio is four.
    """
    curve = sorted(
        (degrees, spec(address, f"reverse_current_typical_at_{name}")[1])
        for degrees, name in ((25.0, "25c"), (75.0, "75c"), (125.0, "125c"))
    )
    spread, _ = spec(address, "reverse_current_typical_to_max")
    if ambient <= curve[0][0]:
        typical = curve[0][1]
    elif ambient >= curve[-1][0]:
        typical = curve[-1][1]
    else:
        for (t0, i0), (t1, i1) in zip(curve, curve[1:]):
            if ambient <= t1:
                share = (ambient - t0) / (t1 - t0)
                typical = i0 * (i1 / i0) ** share
                break
    return typical * spread


def test_the_trip_bus_still_reads_high_with_every_diode_leaking(design, pad_net, spec):
    """
    The other end of the trip bus's noise margin, and the one that fails on a
    hot bench rather than on a cold one.

    Twelve Schottky junctions hang off TRIP_SET_N with their cathodes at
    whatever the comparators and the fault lines are doing, and when nothing
    is tripped every one of them is reverse biased. Their leakage all flows
    the same way, out of the 10 k pull-up, and the latch will not read a high
    below 2.0 V. So the budget is (3.135 - 2.0) / 10.1 k of current shared
    between them.

    **Neither figure in the electrical table is the right one.** It gives
    2 uA at 25 V and 25 degC; these sit at about 1.6 V, and a board in a
    cabinet beside a motor drive does not sit at 25 degC. FIG.2 of the same
    datasheet plots the current against voltage at seven temperatures, and
    at the 2 V end it runs from 0.11 uA at 25 degC to 27 uA at 125. `_leakage`
    interpolates between the two recorded points that bracket the declared
    ambient and scales by the spread from typical to maximum the electrical
    table gives. An earlier version anchored at 75 degC and doubled every
    17.4 - a slope fitted across 75 to 125 and then used at 45, below its own
    anchor - and this paragraph went on describing that after the code had
    stopped doing it.

    The failure is in the safe direction - the board reads permanently
    tripped and will not run - but it is temperature-dependent, so it passes
    on a bench and fails in a cabinet, with nothing pointing at the cause.
    """
    _, ambient = spec("environment", "ambient")
    preset = pad_net[(LATCH, "7")]
    v_ih, _ = spec(LATCH, "input_high_voltage_min")
    rail_low, _ = spec("rail.3v3", "voltage")

    pullups = [address for address, part in design["parts"].items()
               if part["symbol"] == "Device:R"
               and preset in {net for net, nodes in design["nets"].items()
                              for a, _ in nodes if a == address}
               and "3V3" in {net for net, nodes in design["nets"].items()
                             for a, _ in nodes if a == address}]
    assert len(pullups) == 1, f"{preset} is pulled up by {pullups}"
    _, resistance = spec(pullups[0], "resistance")
    budget = (rail_low - v_ih) / resistance

    leaking = 0.0
    junctions = 0
    for address, part in design["parts"].items():
        if part["symbol"] != "Diode:BAT54A":
            continue
        if preset not in {net for net, nodes in design["nets"].items()
                          for a, pad in nodes if a == address and pad == "3"}:
            continue
        junctions += 2
        leaking += 2 * _leakage(spec, address, ambient)
    assert junctions, f"nothing reaches {preset} through a diode"

    assert leaking < budget, (
        f"at {ambient:g} degC the {junctions} Schottky junctions on {preset} "
        f"leak {leaking * 1e6:.0f} uA between them, and {resistance / 1e3:g} k "
        f"from {rail_low:g} V can spare {budget * 1e6:.0f} uA before the latch "
        f"stops reading a high. The board would sit permanently tripped, and "
        f"only when warm."
    )


def test_the_clear_reaches_a_valid_low_and_lets_go_by_itself(design, pad_net, spec):
    """
    The coupled clear pulse, worked out from the three parts that make it.

    Two things have to be true of an AC-coupled clear and they pull opposite
    ways. It has to go low enough, for long enough, that the latch sees it:
    when PG5 drives low the capacitor is uncharged, so the latch's clear sits
    at the divider of the series resistor against the pull-up, and it has to
    be under V_IL. And it has to let go on its own, which any finite RC does -
    that is the whole reason the capacitor is there.

    The time it spends asserted is the one that needs arithmetic. The node
    recovers through the two resistors with a time constant of (R_s + R_pu)C
    and leaves the valid-low band at

        t = tau * ln((V - V_min) / (V - V_IL))

    which has to be longer than the latch takes to respond to it at all. The
    part records 5.9 ns for clear-to-output and nothing for a minimum pulse
    width, so that is the figure this is held to; on these values the answer
    is four orders of magnitude clear of it.

    **What it is not held to is an upper bound**, because nothing on this
    board derives one. While the clear is asserted the latch cannot hold a
    trip, so the pulse is a blind window - but the firmware it replaces held
    the pin down for a millisecond, so the window shrank by a hundred times
    and the direction is the safe one either way.

    The release is the other half and it is in
    `test_the_clear_does_not_drive_the_latch_past_its_input_rating`.
    """
    latch_clear = pad_net[(LATCH, "6")]
    series = "safety.r_clear_series"
    pullup = "safety.r_clear_pullup"
    coupling = "safety.c_clear"

    r_s, _ = spec(series, "resistance")
    _, r_pu = spec(pullup, "resistance")
    _, farads = spec(coupling, "capacitance")
    rail_low, _ = spec("rail.3v3", "voltage")
    v_il, _ = spec(LATCH, "input_low_voltage_max")
    v_ih, _ = spec(LATCH, "input_high_voltage_min")
    respond, _ = spec(LATCH, "preset_to_output_max")

    # Worst case for reaching a low is the largest series resistor against the
    # smallest pull-up, so the two ends are taken the way that hurts.
    _, r_s_high = spec(series, "resistance")
    r_pu_low, _ = spec(pullup, "resistance")
    low = rail_low * r_s_high / (r_s_high + r_pu_low)
    assert low < v_il, (
        f"driving the pin low puts {latch_clear} at {low:.2f} V, and the latch "
        f"calls anything above {v_il:g} V undecided. The series resistor is too "
        f"big against the pull-up for the clear to be seen at all."
    )

    # The *shortest* time constant, which is the corner that hurts: the
    # smallest series resistor, the smallest pull-up and the smallest
    # capacitor. Taking the low end of one and the high end of the others,
    # which this did, is the most favourable corner there is and it was three
    # lines under a comment claiming the opposite - it reported 11.3 us where
    # the worst corner gives 9.1.
    r_s_low, _ = spec(series, "resistance")
    r_pu_low_again, _ = spec(pullup, "resistance")
    farads_low, _ = spec(coupling, "capacitance")
    tau = (r_s_low + r_pu_low_again) * farads_low

    # The clamp hangs on this node too, and what it contributes is its own
    # junction capacitance in parallel with the coupling capacitor, plus a
    # reverse leakage that flows *into* the node and so fights the low level
    # rather than the high one. Both are small - a few picofarads against
    # nanofarads, a microamp against three hundred - and both are read here
    # rather than declared and forgotten.
    clamps = [address for address, part in design["parts"].items()
              if "diode" in symbol_description(part["symbol"]).lower()
              and pad_net.get((address, "3")) == latch_clear]
    leaked = 0.0
    for address in clamps:
        _, junction = spec(address, "total_capacitance")
        _, ambient = spec("environment", "ambient")
        tau += (r_s_low + r_pu_low_again) * junction
        leaked += _leakage(spec, address, ambient)
    low += leaked * r_s_high            # the leak lifts the low level
    assert low < v_il, (
        f"with {leaked * 1e6:.1f} uA of clamp leakage added, {latch_clear} only "
        f"reaches {low:.2f} V and the latch wants under {v_il:g}"
    )
    asserted = tau * math.log((rail_low - low) / (rail_low - v_il))
    assert asserted > respond, (
        f"the clear is asserted for {asserted * 1e9:.0f} ns and the latch takes "
        f"{respond * 1e9:g} ns to respond to it"
    )
    # It does let go, and how long that takes is worth reporting - but there
    # is no assertion here, because there was one and it could not fail.
    # `released > asserted` reduces to ln((V-low)/(V-V_IH)) > ln((V-low)/(V-V_IL)),
    # which is true for any component values whatever simply because V_IL is
    # below V_IH. Every value cancelled; the ratio is 4.65 on this part and
    # would be 4.65 on any board. An assertion that is a restatement of
    # V_IL < V_IH is not a check, and dressing it in three component values
    # made it read like one.
    released = tau * math.log((rail_low - low) / (rail_low - v_ih))
    print(f"    clear: {low:.2f} V, asserted {asserted * 1e6:.1f} us, "
          f"valid high at {released * 1e6:.1f} us")


def test_the_clear_does_not_drive_the_latch_past_its_input_rating(
    design, pad_net, spec, forward_voltage
):
    """
    What the coupled clear does to the latch's input when the pin lets go.

    The capacitor that makes a held pin harmless makes the *release* into a
    step on top of the rail. By the time firmware raises PG5 the capacitor has
    charged to nearly the whole rail, so the node goes to

        V x (1 + R_pu / (R_s + R_pu))

    which is 6.3 V nominal and 6.6 V at the corner, and stays there for the
    tens of microseconds the RC takes to recover.

    **The latch has nothing inside it to stop that.** An LVC input's absolute
    maximum is a flat 6.5 V rather than V_CC + 0.5, and its clamp current is
    specified only for negative inputs: there is no diode to V_CC, which is
    precisely what makes the family tolerant of 5.5 V on a 3.3 V rail. The
    comment beside this network in `cpu1.py` used to say the series resistor
    held the current into "the latch's input clamp" to 0.2 mA. There was no
    clamp and so no current - just the node sitting above its recommended
    maximum on every fault recovery, on the one part between the MCU and the
    gate drivers.

    So the board has a clamp now, and this is what says it must: the check
    looks for a diode with its anode on the clear node and its cathode on a
    rail, and works the peak out with it or without it. Remove D13 and the
    unclamped peak fails against the recommended maximum.
    """
    node = pad_net[(LATCH, "6")]
    r_s, _ = spec("safety.r_clear_series", "resistance")
    _, r_pu = spec("safety.r_clear_pullup", "resistance")
    _, rail = spec("rail.3v3", "voltage")
    allowed, _ = spec(LATCH, "input_voltage_max")
    absolute, _ = spec(LATCH, "input_voltage_absolute_max")

    # Unclamped: the capacitor holds the rail, and the step lands on top of it
    # attenuated by the divider the two resistors make.
    bare = rail * (1.0 + r_pu / (r_s + r_pu))

    # A clamp is a diode whose anode is on this node and whose cathode is on a
    # rail. Read from the netlist, so removing it is what fails.
    clamps = []
    for address, part in design["parts"].items():
        if "diode" not in symbol_description(part["symbol"]).lower():
            continue
        pads = {pad: net for (a, pad), net in pad_net.items() if a == address}
        if pads.get("3") != node:
            continue
        held = {net for pad, net in pads.items() if pad in ("1", "2")}
        if held and all(net.startswith(("3V3", "5V")) for net in held):
            clamps.append(address)

    if not clamps:
        peak, how = bare, "with nothing clamping it"
    else:
        # Current into the clamp is what the series resistor passes, and the
        # forward drop at ten milliamps bounds it: the real current is about
        # three, so the datasheet's 10 mA row is the pessimistic end.
        # Three milliamps is what the series resistor passes into it.
        into = (bare - rail) / r_s
        drop = max(forward_voltage(address, into, 25.0) for address in clamps)
        peak = rail + drop
        how = f"clamped to the rail by {', '.join(sorted(clamps))}"

    assert peak <= allowed, (
        f"releasing the clear puts {node} at {peak:.2f} V {how}, against the "
        f"{allowed:g} V this part is specified to and a {absolute:g} V absolute "
        f"maximum. An LVC input has no clamp of its own."
    )


def test_the_trip_bus_reaches_a_valid_low_through_its_diodes(
    design, spec, forward_voltage
):
    """
    A fault pulling the bus down through a Schottky still counts as a low.

    This is the whole reason the diodes are Schottky. Each source pulls the bus
    to its own low level plus a diode drop, and the latch decides what is low at
    0.8 V. A silicon diode's 0.7 V spends the entire budget before the fault
    output has contributed anything.

    **At the current the bus actually runs them at, and at the temperature the
    board is declared for.** This used to take the one recorded figure, 0.24 V,
    which is the datasheet's 0.1 mA row - while the bus's own pull-up sets the
    current, and the suite computes that current sixty lines away in
    `test_the_trip_diodes_and_the_latch_are_inside_their_ratings`. It is about
    0.28 mA, nearly three times the row being read. And the forward drop of a
    Schottky rises as it cools, by 1.8 mV per degree off FIG.1, so a board
    declared down to 0 degC finds another 45 mV. The recorded margin was 160 mV
    and the real one is about half that.

    The current is solved rather than assumed, because it depends on the drop
    that depends on it: the bus sits at the source's low level plus the drop,
    and the pull-up carries whatever is left of the rail.
    """
    _, fault_low = spec("header", "fault_output_low")
    threshold, _ = spec(LATCH, "input_low_voltage_max")
    _, rail = spec("rail.3v3", "voltage")
    ambient, _ = spec("environment", "ambient")
    # The smallest pull-up passes the most current, which is the largest drop.
    resistance, _ = spec("safety.r_trip_pullup", "resistance")

    diodes = sorted(
        address for address, part in design["parts"].items()
        if part["symbol"] == "Diode:BAT54A"
    )
    assert diodes, "no diodes on the trip bus"
    for address in diodes:
        drop = forward_voltage(address, 100e-6, 25.0)
        for _ in range(20):                 # converges in three
            current = (rail - (fault_low + drop)) / resistance
            drop = forward_voltage(address, current, ambient)
        reached = fault_low + drop
        assert reached < threshold, (
            f"{address}: a source at {fault_low:g} V plus {drop:.3f} V across "
            f"the diode - at the {current * 1e6:.0f} uA the pull-up passes and "
            f"{ambient:g} degC - leaves the bus at {reached:.3f} V, and the "
            f"latch calls anything under {threshold:g} V a low"
        )


def test_both_timers_see_the_trip_on_one_piece_of_copper(design, pad_net, pin_map):
    """
    The latch's other output goes to both break inputs, with nothing in between.

    Two nets, or a resistor *in series*, would mean a break in one path that
    the other would not show. `pinmap.py` says these two pins share a node, and
    this is what makes sure the board agrees.

    A part with its other pad on a rail is a different thing: a shunt cannot
    interrupt the path, and the pull-down that makes an open latch output read
    as "break asserted" is one. So what this forbids is anything whose far pad
    is on another *signal*, which is what a series element looks like.
    """
    not_tripped = pad_net.get((LATCH, "3"))
    assert not_tripped == "TRIP_N", f"the latch's inverted output is on {not_tripped!r}"
    breaks = {p.name for p in pin_map.PINS if p.net_name == not_tripped}
    assert breaks == {"TRIP1_N", "TRIP2_N"}, (
        f"the trip reaches {sorted(breaks)}, and it has to reach both timers"
    )
    rails = {"GND", "3V3", "5V"}
    in_series = []
    for address, far in _through_resistor(design, pad_net, not_tripped):
        if far not in rails:
            in_series.append(f"{address} to {far}")
    assert not in_series, (
        f"something is in series in the trip path: {sorted(in_series)}"
    )
    members = {address for address, _ in {tuple(n) for n in design["nets"][not_tripped]}}
    shunts = {address for address, far in _through_resistor(design, pad_net, not_tripped)
              if far in rails}
    assert members - shunts == {LATCH, "mcu"}, (
        f"something else is on the trip net: {sorted(members - shunts)}"
    )


def test_a_trip_stops_the_outputs_inside_the_budget(
    design, spec, board_capacitance, pad_net
):
    """
    Comparator plus latch plus buffer, worst case, against the time a bridge
    can survive - **including what the bus between them costs.**

    Every number is a maximum from a datasheet over the full temperature
    range. What is left over is what the tap network in M6 has to fit into,
    and saying so here is the point: the budget is spent in order, and this is
    how much of it the parts already chosen have taken.

    The bus was worth nothing in that sum and it is not worth nothing. The
    comparator's 7 ns comes from a switching table that states no capacitive
    load, and Figure 5 of the same datasheet plots the delay against load: the
    table's own figure is the left-hand end of that curve, near 13 pF, and
    past it the delay grows 40 ps for every picofarad. TRIP_SET_N is 161 mm of
    track carrying twelve Schottky junctions - six BAT54A, both junctions of
    each facing the bus through their common anode, 10 pF apiece - which comes
    to about 135 pF, and that is five nanoseconds nobody was counting against
    ten of slack.

    **The copper is measured rather than assumed, and it is the small half.**
    Of the 137 pF, the twelve junctions are 120 and the 161 mm of track is 17.
    So this is live through the diode count, but not sensitively: it takes
    seven more BAT54A - more than doubling the junctions - or a Schottky above
    20.6 pF, twice what is fitted, before the reserved share goes. And it is
    not live through the routing at all: at
    40 ps/pF the 5 ns of slack is 128 pF, about 1,400 mm of extra copper on a
    board 129 mm across. An earlier version of this sentence said "route the
    bus the long way round and this notices", which is wrong by an order of
    magnitude.
    """
    _, trip_budget = spec("trip", "budget")
    latch, _ = spec(LATCH, "preset_to_output_max")
    buffer_off, _ = spec(BUFFERS[0], "disable_time_max")
    spent = latch + buffer_off
    assert spent < trip_budget, (
        f"the latch and the buffer take {spent * 1e9:.1f} ns of a "
        f"{trip_budget * 1e9:g} ns budget"
    )
    # What is left has to cover the comparators, and they are on the board
    # now, so it is their own figure rather than half the budget. The fraction
    # was written when this block existed and the trip block did not.
    comparators = [address for address, part in design["parts"].items()
                   if part["symbol"].startswith("Comparator:")]
    assert comparators, "no comparator on this board, and the budget assumes one"
    slowest = max(spec(address, "propagation_delay_max")[0] for address in comparators)

    # What the bus adds. The copper is measured; the junctions are counted off
    # the netlist at the figure their own datasheet gives.
    bus = {net for net, nodes in design["nets"].items()
           for address, pad in nodes
           if address == LATCH and pad == "7"}
    assert len(bus) == 1, f"the latch's preset is on {sorted(bus)}"
    trip_bus = bus.pop()
    loaded = board_capacitance(trip_bus)
    junctions = 0
    for address, part in design["parts"].items():
        if part["symbol"] != "Diode:BAT54A":
            continue
        if trip_bus not in {net for net, nodes in design["nets"].items()
                            for a, pad in nodes if a == address and pad == "3"}:
            continue
        junctions += 2
        loaded += 2 * spec(address, "total_capacitance")[1]
    assert junctions, f"nothing reaches {trip_bus} through a diode"

    # The worst of them on each term, not the first: seven comparators sit on
    # this bus and a board with two different parts on it would otherwise have
    # six of them go unread.
    reference = min(spec(address, "delay_load_reference")[0] for address in comparators)
    per_farad = max(spec(address, "delay_per_farad")[1] for address in comparators)
    loading = max(0.0, (loaded - reference) * per_farad)

    # **And the gate line falling, which is where the budget's own sentence
    # ends.** "How long a half bridge survives a shoot-through" is not the
    # same instant as the buffer letting go: once the '541 is in high
    # impedance the line is discharged by its pull-down alone, through
    # whatever the board's copper and the power board's input present. At the
    # 10 k these started at, the worst line took 59 ns - more than the whole
    # budget, after the chain had already spent 25 ns getting there - and
    # nothing was counting it.
    _, far_side = spec("header", "gate_line_capacitance")
    _, rail = spec("rail.3v3", "voltage")
    threshold = min(spec(address, "input_low_voltage_max")[0]
                    for address in (LATCH,))
    falling, worst = 0.0, None
    for address, part in design["parts"].items():
        if not address.startswith("safety.pulldown."):
            continue
        line = pad_net[(address, "1")]
        if not line.endswith("_OUT"):
            continue
        _, pull = spec(address, "resistance")
        driven = line[:-4] + "_B"
        loaded_line = board_capacitance(line) + far_side
        if driven in design["nets"]:
            loaded_line += board_capacitance(driven)
        takes = pull * loaded_line * math.log(rail / threshold)
        if takes > falling:
            falling, worst = takes, line

    assert spent + slowest + loading + falling < trip_budget, (
        f"{spent * 1e9:.1f} ns for the latch and buffer, {slowest * 1e9:g} ns "
        f"for the comparator at its datasheet's own load, and {loading * 1e9:.1f} "
        f"ns more for the {loaded * 1e12:.0f} pF on {trip_bus} - "
        f"{junctions} Schottky junctions and the copper between them - and "
        f"{falling * 1e9:.1f} ns for {worst} to fall to a valid low through its "
        f"pull-down, against a {trip_budget * 1e9:g} ns budget"
    )

    # And what that leaves the tap network M6 has still to draw. **Reported,
    # and recorded in BLOCKING**, because the answer is that there is nothing
    # left: the budget closes with a few hundred picoseconds to spare and the
    # 40 % held back for the filter is entirely spent by the gate line's fall.
    #
    # It cannot be fixed here. Getting the discharge under five nanoseconds
    # wants 244 ohm pull-downs, which is 114 mA out of one '541 against its
    # 50 mA total - four times over. The line's fall is really the far side's
    # problem: a gate driver with its own input pull-down solves it and this
    # board cannot assume one, so the requirement goes to the power board the
    # same way the analog clamps did.
    _, reserved = spec("trip", "reserved_share")
    left = trip_budget - (spent + slowest + loading + falling)
    print(f"    trip chain: {spent * 1e9:.1f} + {slowest * 1e9:g} + "
          f"{loading * 1e9:.1f} + {falling * 1e9:.1f} ns = "
          f"{(trip_budget - left) * 1e9:.1f} of {trip_budget * 1e9:g}, "
          f"leaving {left * 1e9:.1f} ns against the {reserved * trip_budget * 1e9:.0f} "
          f"held for the tap filter")


# --- everything else on the connector ----------------------------------------


def test_every_connector_signal_is_defined_with_nothing_attached(
    design, pad_net, pin_map, spec
):
    """
    Each input from the power board is pulled somewhere, and to the safe side.

    An unfitted or unplugged power board must not read as permission. Straps
    read as "no board" when they float high, safe-torque-off feedback reads as
    "not permitted" when it floats low, and a fault line reads as "no fault" -
    which is the one that looks wrong until you notice a board with no power
    stage cannot have a gate-driver fault.
    """
    expected = {
        "ID_STRAP0": "3V3", "ID_STRAP1": "3V3", "ID_STRAP2": "3V3", "ID_STRAP3": "3V3",
        "FAULT1_N": "3V3", "FAULT2_N": "3V3",
        "STO1_FEEDBACK": "GND", "STO2_FEEDBACK": "GND",
        "RELAY1": "GND", "RELAY2": "GND",
    }
    wrong = []
    for net, rail in expected.items():
        pulls = _through_resistor(design, pad_net, net)
        rails = sorted(far for _, far in pulls if far in ("3V3", "GND"))
        if rails != [rail]:
            wrong.append(f"  {net}: pulled to {rails or 'nothing'}, expected {rail}")
    assert not wrong, "Connector signals with no defined idle state:\n" + "\n".join(wrong)


def test_the_connector_carries_what_the_pin_map_says_it_does(design, pad_net, pin_map):
    """
    Every pin of the header is on the net the table gives it, and none is left out.

    The pinout is generated, so what this catches is the generator and the
    wiring disagreeing - which is exactly what a hand-drawn connector hides
    until someone builds a cable.
    """
    expected = pin_map.header_pins(pin_map.HEADER_DIGITAL, pin_map.HEADER_GROUND,
                                _pin_count(pad_net))
    wrong = []
    for number, net in sorted(expected.items()):
        found = pad_net.get((HEADER, str(number)))
        if found != net:
            wrong.append(f"  pin {number}: on {found!r}, table says {net!r}")
    assert not wrong, "Connector pins:\n" + "\n".join(wrong)


def test_the_buffers_drive_less_than_they_are_rated_for(design, pad_net, spec):
    """
    What each buffer's outputs pull, against what the datasheet allows.

    The load is the series resistor into the pull-down and whatever the cable
    ends in; the part of it this board decides is the divider, and at 3.3 V
    across 33 plus 10 k it is microamps. The check exists because the number
    that matters is the *total* across eight outputs, which is easy to forget
    when each one looks free.
    """
    _, rail = spec("rail.3v3", "voltage")
    per_output, _ = spec(BUFFERS[0], "output_current_max")
    total_rating, _ = spec(BUFFERS[0], "total_output_current_max")
    for address in BUFFERS:
        total = 0.0
        for owner, _, source, drain in _buffer_channels(design, pad_net):
            # Every channel of every buffer, so the one being totalled has to
            # be picked out. Without this the loop added both packages' outputs
            # into each package's total and reported twice the real current
            # under the wrong designator.
            if owner != address:
                continue
            if drain is None or source == "GND":
                continue
            series = _through_resistor(design, pad_net, drain)
            if not series:
                continue
            resistor, far = series[0]
            pull = [a for a, n in _through_resistor(design, pad_net, far) if n == "GND"]
            if not pull:
                continue
            ohms = spec(resistor, "resistance")[0] + spec(pull[0], "resistance")[0]
            current = rail / ohms
            assert current <= per_output, f"{address}: one output drives {current * 1e3:.1f} mA"
            total += current
        assert total <= total_rating, (
            f"{address}: {total * 1e3:.1f} mA across all outputs, rated "
            f"{total_rating * 1e3:g} mA"
        )


def test_every_logic_part_runs_from_the_rail_it_is_given(spec):
    """
    The 3V3 rail is inside each logic part's supply range, and a signal driven
    to that rail clears its input threshold.

    Both parts are 1.65 V devices, so this has plenty of room - but the second
    half is the one worth having. A CMOS output swings to the rail, and the
    buffers' inputs want 2.0 V to read a one; at the bottom of the rail's band
    that is still over a volt of margin, and it is the number that would move
    if anything on this board ever ran at 1.8 V.
    """
    rail_low, rail_high = spec("rail.3v3", "voltage")
    for address in (*BUFFERS, LATCH):
        low, high = spec(address, "supply_voltage")
        assert low <= rail_low and rail_high <= high, (
            f"{address} takes {low:g} to {high:g} V and the rail runs "
            f"{rail_low:g} to {rail_high:g} V"
        )
        threshold, _ = spec(address, "input_high_voltage_min")
        assert threshold < rail_low, (
            f"{address} needs {threshold:g} V to read a one and the rail can be "
            f"{rail_low:g} V"
        )


def test_complementary_pwm_outputs_go_through_the_same_buffer(design, pad_net, spec):
    """
    A bridge's high and low side pass through one package, so their skew is the
    skew within it and not the spread between two parts.

    This is why the channel assignment is not arbitrary. Inside a '541 the
    outputs are matched to a nanosecond; between two of them the only bound is
    each one's own propagation window, which is nearly four nanoseconds wide.
    Dead time has to cover whatever this is, and a bridge sees the difference as
    shoot-through the moment it does not.
    """
    dead_time, _ = spec("pwm", "dead_time")
    within, _ = spec(BUFFERS[0], "output_skew_max")
    delay_max, _ = spec(BUFFERS[0], "propagation_delay_max")
    between = delay_max - within

    buffer_of = {}
    for address, _, source, _ in _buffer_channels(design, pad_net):
        if source:
            buffer_of[source] = address

    split = []
    for phase in ("A", "B", "C"):
        for bridge in ("PWM1", "PWM2"):
            high, low = f"{bridge}_{phase}_HIGH", f"{bridge}_{phase}_LOW"
            if buffer_of.get(high) != buffer_of.get(low):
                split.append(f"  {high} and {low}: {buffer_of.get(high)} and {buffer_of.get(low)}")
    assert not split, (
        "Complementary outputs on different buffers, so their skew is the "
        f"part-to-part {between * 1e9:.1f} ns rather than {within * 1e9:g} ns:\n"
        + "\n".join(split)
    )
    assert within < dead_time / 10, (
        f"{within * 1e9:g} ns of skew against {dead_time * 1e9:.0f} ns of dead time"
    )


def test_the_connector_is_rated_for_everything_that_can_drive_it(design, pad_net, spec):
    """
    No pin of the connector can carry more than the thing driving it can source.

    The buffered outputs are the only pins this board drives, and a '541 output
    into a short is bounded by the part, not by the connector. 3 A per contact
    against 25 mA is not a close-run thing; it is here because the next
    connector might be a flat cable with a tenth of the rating.
    """
    contact, _ = spec(HEADER, "current_rating")
    source, _ = spec(BUFFERS[0], "output_current_max")
    assert contact > source, (
        f"a contact carries {contact:g} A and a buffer output can source "
        f"{source:g} A into it"
    )


def test_the_trip_diodes_and_the_latch_are_inside_their_ratings(design, pad_net, spec):
    """
    What the trip bus asks of its diodes, and the latch of its outputs.

    None of it is close to a limit, and that is the point of writing it down:
    the bus current is set by one pull-up and the latch drives nothing but CMOS
    inputs. Both would change the moment somebody hung an indicator LED off the
    latch or shrank the pull-up, which is exactly when a check should notice.
    """
    _, rail = spec("rail.3v3", "voltage")
    pull_up = _through_resistor(design, pad_net, "TRIP_SET_N")
    to_rail = [a for a, n in pull_up if n == "3V3"]
    assert len(to_rail) == 1, f"the trip bus has {len(to_rail)} pull-ups"
    bus_current = rail / spec(to_rail[0], "resistance")[0]

    for address, part in sorted(design["parts"].items()):
        if part["symbol"] != "Diode:BAT54A":
            continue
        blocking, _ = spec(address, "reverse_voltage_max")
        assert blocking > rail, (
            f"{address} blocks {blocking:g} V and idles with {rail:g} V across it"
        )
        carrying, _ = spec(address, "forward_current_max")
        assert carrying > bus_current, (
            f"{address} carries {carrying * 1e3:g} mA and the bus pulls "
            f"{bus_current * 1e3:.2f} mA through it"
        )

    rating, _ = spec(LATCH, "output_current_max")
    for output in ("TRIPPED", "TRIP_N"):
        loads = [
            spec(address, "resistance")[0]
            for address, far in _through_resistor(design, pad_net, output)
            if far in ("3V3", "GND")
        ]
        draw = sum(rail / ohms for ohms in loads)
        assert draw < rating, (
            f"{output} drives {draw * 1e3:.1f} mA of resistive load against a "
            f"{rating * 1e3:g} mA rating"
        )


# Which pad of the comparator is which input, from KiCad's
# `Comparator:TLV3501AIDBV` - the same symbol `test_symbols.py` holds to the
# part's own pin names. The output falls when + is below -, so a threshold on
# + trips as it falls and one on - trips as it rises.
COMPARATOR_INPUTS = {"3": "+", "1": "-"}
TRIPPED_BY = {"+": "GND", "-": "3V3"}


def test_every_trip_decision_fails_to_tripped(design, pad_net):
    """
    Every net that decides a trip is pulled to the side that means "tripped".

    Three of these nets used to run from one pin to another and nothing else -
    the latch's two outputs and the three threshold buses - so an open circuit
    anywhere on them left a CMOS input or a comparator reference floating, and
    a floating node is not a safe state, it is an undefined one.

    The direction is derived, not listed. A threshold on the `+` input trips
    when it falls, so it is pulled to ground; one on `-` trips when it rises,
    so it is pulled to the rail. The latch's Q disables the buffers when high
    and its Q-bar asserts both break inputs when low, so they pull opposite
    ways for the same reason.

    This is the check that says the board still fails safe when a part is
    missing, rather than only when every part is present and working.
    """
    wanted = {"TRIPPED": "3V3", "TRIP_N": "GND"}
    for address, part in design["parts"].items():
        if not part["symbol"].startswith("Comparator:"):
            continue
        for pad, side in COMPARATOR_INPUTS.items():
            net = pad_net.get((address, pad))
            if net and net.startswith("TRIP_LEVEL"):
                wanted[net] = TRIPPED_BY[side]

    wrong = []
    for net, rail in sorted(wanted.items()):
        pulls = {far for _, far in _through_resistor(design, pad_net, net)
                 if far in ("GND", "3V3", "5V")}
        if not pulls:
            wrong.append(f"  {net}: nothing holds it if its driver goes open")
        elif rail not in pulls:
            wrong.append(f"  {net}: pulled to {sorted(pulls)}, and {rail} is "
                         "the side that means tripped")
    assert not wrong, (
        "Trip decisions that do not fail safe:\n" + "\n".join(wrong)
    )
