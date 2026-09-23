"""
CAN FD and RS-485: two pairs of wires that leave the board.

Everything here is worked out from the netlist rather than from the names in
`cpu1.py`. Each bus is found by asking which nets a transceiver shares with a
connector, and its termination by walking from one of those nets to the other
through whatever two-terminal parts lie between them. A termination wired to
the wrong pair, or with one half missing, is not a thing this can be told about
- it has to fall out of the walk.

Datasheets: TI SLLSF41 (TCAN1044V, October 2019) and SLLSEZ6 (THVD1450,
June 2017).
"""

import itertools
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from symbols import (  # noqa: E402
    symbol_description, symbol_pin_names, symbol_pin_types,
)

# Which declared rail each supply net is, as in test_trip.py: a check that names
# a rail reads the same number whatever the board does.
RAILS = {"5V": "rail.5v", "3V3": "rail.3v3"}

GROUND = "GND"


@pytest.fixture(scope="module")
def pad_net(design):
    return {tuple(node): net for net, nodes in design["nets"].items() for node in nodes}


@pytest.fixture(scope="module")
def pads_of(design, pad_net):
    """address -> {pad: net}, for looking at one part's connections at a time."""
    out: dict[str, dict[str, str]] = {}
    for (address, pad), net in pad_net.items():
        out.setdefault(address, {})[pad] = net
    return out


@pytest.fixture(scope="module")
def pin_names(design, board_dir):
    """address -> {pad: the symbol's name for it}, so checks can say what a pin is."""
    import sys

    sys.path.insert(0, str(board_dir.parent / "tools"))
    from symbols import symbol_pin_names

    return {
        address: symbol_pin_names(part["symbol"])
        for address, part in design["parts"].items()
    }


@pytest.fixture(scope="module")
def buses(design, pads_of):
    """
    bus -> (transceiver address, header address, the two nets between them).

    The pair is what a transceiver and a connector have in common once ground is
    set aside. Nothing declares which nets those are; if a bus pin were wired to
    the wrong connector pin the pair found here would be wrong too, and every
    check below would be asking about a bus that does not exist - which is why
    the first check is that each pair has exactly two wires in it.
    """
    out = {}
    for address in design["parts"]:
        if not address.endswith(".transceiver"):
            continue
        bus = address[: -len(".transceiver")]
        header = f"{bus}.header"
        assert header in design["parts"], f"{bus} has a transceiver and no connector"
        shared = (set(pads_of[address].values()) & set(pads_of[header].values())) - {GROUND}
        out[bus] = (address, header, sorted(shared))
    assert out, "no field buses found, and this file is about them"
    return out


def _termination_path(design, pads_of, start: str, finish: str) -> list[str] | None:
    """
    The two-terminal parts between two nets, in order, or None if there are none.

    A plain depth-first walk: from a net, through any part with exactly two pads,
    to the net on its other pad. What comes back is the termination as it is
    actually wired, including a jumper left open, which a part list would not
    distinguish from one that is not there.
    """
    def walk(net: str, seen: frozenset) -> list[str] | None:
        for address, pads in pads_of.items():
            if address in seen or len(pads) != 2:
                continue
            nets = list(pads.values())
            if net not in nets:
                continue
            other = nets[1] if nets[0] == net else nets[0]
            if other == finish:
                return [address]
            if other in (GROUND, net):
                continue
            rest = walk(other, seen | {address})
            if rest is not None:
                return [address] + rest
        return None

    return walk(start, frozenset())


@pytest.fixture(scope="module")
def terminations(design, pads_of, buses):
    """bus -> the ordered parts between its two wires."""
    out = {}
    for bus, (_, _, pair) in buses.items():
        assert len(pair) == 2, f"{bus}: {len(pair)} wires between transceiver and connector"
        path = _termination_path(design, pads_of, pair[0], pair[1])
        assert path, f"{bus}: nothing connects {pair[0]} to {pair[1]}"
        out[bus] = path
    return out


# --- what the bus is, physically ---------------------------------------------


def test_each_bus_is_a_pair_with_a_ground_beside_it(design, pads_of, buses):
    """
    Two wires and a ground, on a connector that carries nothing else.

    The ground is not the return - a differential pair is its own return - it is
    the reference the two receivers have to share for the common-mode range to
    mean anything. A pair run without it works on a bench and fails between two
    machines on different supplies, which is the only place it matters.
    """
    problems = []
    for bus, (transceiver, header, pair) in sorted(buses.items()):
        pins = pads_of[header]
        if len(pair) != 2:
            problems.append(f"  {bus}: {len(pair)} wires shared with its connector: {pair}")
        grounds = [pad for pad, net in pins.items() if net == GROUND]
        if len(grounds) != 1:
            problems.append(f"  {bus}: {len(grounds)} ground pins on its connector")
        stray = sorted(set(pins.values()) - set(pair) - {GROUND})
        if stray:
            problems.append(f"  {bus}: its connector also carries {stray}")
    assert not problems, "Field bus connectors:\n" + "\n".join(problems)


def test_each_transceiver_runs_from_rails_its_datasheet_allows(
    pads_of, pin_names, buses, spec, spec_has
):
    """
    Every supply pin is on a declared rail, and on one its range covers.

    A part with two supplies has a logic side and a bus side, and they are not
    interchangeable: the CAN transceiver's I/O supply sets what a logic high is
    to it, and its VCC sets what a dominant bit is on the cable. Swapped, both
    pins are still on a rail the board has, the board still powers up, and the
    bus drives to the wrong levels - so the two have to be told apart, not just
    counted. Which pin is which comes from the symbol, and which rail is which
    from the netlist; neither is written here.

    The check that came before this one matched rails to ranges in any order,
    which is the same thing said carelessly: swapping the CAN transceiver's two
    supplies passed it, because the set of rails was unchanged.
    """
    for bus, (transceiver, _, _) in sorted(buses.items()):
        supplies = {
            _SUPPLY_NAMES[name.upper()]: (pad, net)
            for pad, name in pin_names[transceiver].items()
            if name.upper() in _SUPPLY_NAMES
            and (net := pads_of[transceiver].get(pad)) is not None
        }
        declared = {
            name: spec(transceiver, name)
            for name in ("supply_voltage", "io_supply_voltage")
            if spec_has(transceiver, name)
        }
        assert set(supplies) == set(declared), (
            f"{bus}: its symbol has supply pins for {sorted(supplies)} and "
            f"parts.py states ranges for {sorted(declared)}"
        )
        for name, (pad, net) in sorted(supplies.items()):
            assert net in RAILS, (
                f"{bus}: {name} on pin {pad} is on {net!r}, not a declared rail"
            )
            low, high = declared[name]
            rail_low, rail_high = spec(RAILS[net], "voltage")
            assert low <= rail_low and rail_high <= high, (
                f"{bus}: {name} on pin {pad} is on {net} at {rail_low} to "
                f"{rail_high} V, outside the {low} to {high} V it states"
            )


# What a supply pin is called, and which declared range belongs to it. The CAN
# transceiver's I/O supply is the reason this is a mapping and not a list: the
# symbol is the SN65HVD230's, where pin 5 is a reference *output* called Vref,
# and on the part actually fitted it is the level-shifter supply. See
# parts/SOIC8/SOIC8.md.
_SUPPLY_NAMES = {
    "VCC": "supply_voltage",
    "VDD": "supply_voltage",
    "V+": "supply_voltage",
    "VIO": "io_supply_voltage",
    "VREF": "io_supply_voltage",
}


# --- the termination ---------------------------------------------------------


def test_each_bus_can_be_terminated_and_is_not_terminated_when_it_arrives(
    design, pads_of, terminations, buses
):
    """
    With the jumpers as they ship, nothing of the termination hangs on either
    wire.

    A bus wants two terminations, one at each end. A board that is terminated
    because it was built that way can only ever be an end, and two of them in
    the middle of a working bus is the fault that looks like a cable problem
    for a day. Open by default is the only state that is right more often than
    not: a board added to a bus is usually not the end of it.

    **This used to count jumpers instead of asking what they disconnect**, and
    a count cannot tell a termination that is isolated from one that is half
    isolated. CAN's split termination had exactly one jumper, in the CANH leg,
    and passed - while CANL went on carrying 60.4 ohm in series with the
    4.7 nF midpoint capacitor straight to ground on every board shipped. One
    line of the pair loaded and the other not is worse than both loaded: it is
    differential-to-common-mode conversion on a cable leaving the machine, and
    at 2 Mbit/s FD it stretched that one edge by a quarter of a bit.

    So the question is the one that matters: walk out from each wire through
    everything that conducts, with the open jumpers open, and see whether it
    arrives anywhere. **Anywhere means ground, a rail, or the other wire** -
    somewhere the signal actually loses energy. A resistor left hanging on one
    wire with its far end at an open jumper's pad is not a load, which is how
    RS-485's single 120 ohm is built and why one jumper is right there and
    wrong on a split termination: CAN's low leg walked from CAN_L through
    60.4 ohm to the midpoint and straight on through 4.7 nF to ground.
    """
    conducting = []
    for address, part in design["parts"].items():
        symbol = part["symbol"]
        if symbol.startswith("Jumper:") and "Open" in symbol:
            continue                      # open as fabricated: not a path
        pads = pads_of[address]
        if len(pads) == 2:
            conducting.append((address, *pads.values()))

    # Where a walk can land and count as a load: ground, or any net a symbol
    # calls a supply pin. Read from the symbols rather than listed, so a new
    # rail is a rail here the moment something is powered from it.
    rails = {GROUND}
    for address, part in design["parts"].items():
        names = symbol_pin_names(part["symbol"])
        for pad, net in pads_of[address].items():
            if names.get(pad) in ("VCC", "VDD", "VIO", "V+", "V-", "VEE", "VSS", "GND"):
                rails.add(net)

    for bus, path in sorted(terminations.items()):
        jumpers = [address for address in path
                   if design["parts"][address]["symbol"].startswith("Jumper:")]
        assert jumpers, (
            f"{bus}: nothing between its two wires is a jumper, so its "
            "termination cannot be chosen once the board is built"
        )
        for address in jumpers:
            assert design["parts"][address]["value"] == "open", (
                f"{bus}: {address} arrives closed, so this board is always an "
                "end of the bus"
            )

        _, _, wires = buses[bus]
        for wire in wires:
            partner = {other for other in wires if other != wire}
            seen, edge = {wire}, [wire]
            through = []
            while edge:
                net = edge.pop()
                for address, a, b in conducting:
                    far = b if a == net else a if b == net else None
                    if far is None or far in seen:
                        continue
                    seen.add(far)
                    through.append(address)
                    edge.append(far)
            landed = seen & (rails | partner)
            hanging = sorted(set(through) & set(path))
            assert not (landed and hanging), (
                f"{bus}: with its jumpers open, {wire} still reaches "
                f"{', '.join(sorted(landed))} through {', '.join(hanging)}. "
                f"A termination disconnected on one leg loads one line of the "
                f"pair and not the other, which is worse than loading both."
            )


def test_each_termination_matches_the_cable_it_terminates(spec, terminations, spec_has):
    """
    The resistance between the two wires is the cable's impedance.

    Everything in the path that has a resistance counts, whether the bus is
    terminated with one resistor or with two either side of a midpoint, because
    what the cable sees is the total. Too low and the driver runs out of current
    before it reaches a dominant level; too high and the far end of the cable
    reflects, which at these edge rates is a second copy of every bit.
    """
    low, high = spec("bus", "termination")
    for bus, path in sorted(terminations.items()):
        parts = [address for address in path if spec_has(address, "resistance")]
        assert parts, f"{bus}: nothing in its termination has a resistance"
        total_low = sum(spec(address, "resistance")[0] for address in parts)
        total_high = sum(spec(address, "resistance")[1] for address in parts)
        assert low <= total_low and total_high <= high, (
            f"{bus}: {total_low:.1f} to {total_high:.1f} ohm across the pair, "
            f"outside {low:g} to {high:g}"
        )


def test_a_split_termination_is_split_evenly(spec, terminations, spec_has):
    """
    Where a termination is in two halves, the halves are equal.

    The midpoint only stays at the common-mode voltage while the two halves
    match. Unequal, it moves with every dominant bit, and the difference comes
    out of the pair as common mode - the thing the split was added to remove.
    Two resistors one value apart pass every other check here.
    """
    for bus, path in sorted(terminations.items()):
        halves = [address for address in path if spec_has(address, "resistance")]
        if len(halves) < 2:
            continue
        values = {spec(address, "resistance") for address in halves}
        assert len(values) == 1, (
            f"{bus}: its termination is split into "
            f"{[f'{low}-{high}' for low, high in sorted(values)]} ohm, which "
            "puts the midpoint off centre"
        )


def test_a_split_midpoint_shunts_common_mode_and_nothing_else(
    design, pads_of, spec, spec_has, buses, terminations
):
    """
    The capacitor at the midpoint, as the impedance it offers common mode at the
    fastest bit rate the transceiver can signal at.

    It sits where the differential signal is zero, so it loads common mode and
    nothing else. Its value is the whole point: large enough that common mode at
    the signalling frequency finds ground through it rather than through the
    cable and whatever the cable is near, and it does not have to be any larger
    because the differential pair never sees it at all.
    """
    import math

    _, allowed = spec("can", "common_mode_shunt")
    checked = 0
    for bus, path in sorted(terminations.items()):
        inside = {
            net
            for address in path
            for net in pads_of[address].values()
            if sum(net in pads_of[other].values() for other in path) > 1
        }
        # Asked in this order deliberately: `spec_has` counts as a read, and
        # probing every part on the board for a capacitance would quietly mark
        # capacitors nothing here looks at as checked.
        shunts = sorted(
            address
            for address, pads in pads_of.items()
            if set(pads.values()) & inside
            and GROUND in pads.values()
            and spec_has(address, "capacitance")
        )
        if not shunts:
            continue
        assert len(shunts) == 1, f"{bus}: {len(shunts)} capacitors on its midpoint"
        halves = [address for address in path if spec_has(address, "resistance")]
        assert len(halves) == 2, (
            f"{bus}: a midpoint capacitor with {len(halves)} termination "
            "halves, so there is no midpoint for it to be at"
        )
        transceiver = buses[bus][0]
        rate, _ = spec(transceiver, "data_rate_max")
        capacitance, _ = spec(shunts[0], "capacitance")
        half, _ = spec(halves[0], "resistance")
        impedance = 1.0 / (2 * math.pi * rate * capacitance)
        ratio = impedance / (half / 2)
        assert ratio <= allowed, (
            f"{bus}: {impedance:.1f} ohm to ground at {rate / 1e6:g} Mbit/s "
            f"against {half / 2:.1f} ohm of termination, a ratio of "
            f"{ratio:.2f} where {allowed:g} is the most that counts as a shunt"
        )
        checked += 1
    assert checked, "no split termination found, and this check is about them"


# --- what the bus does to the rest of the board ------------------------------


def test_a_bus_at_its_worst_case_voltage_stays_inside_the_connector_rating(
    spec, spec_has, buses, terminations
):
    """
    A wire in the cable shorted to whatever the transceiver is rated to survive,
    against what the connector pin it arrives on is rated to carry.

    The transceiver's bus-fault rating is the reason to pick that part: it says
    the silicon lives through a wire touching a supply. It says nothing about
    the termination, which is then a resistor across that voltage, or about the
    connector pin the current goes through on its way there. A part that
    survives a fault on a board that does not is a worse outcome than neither
    surviving, because it looks like it worked.
    """
    for bus, (transceiver, header, _) in sorted(buses.items()):
        fault, _ = spec(transceiver, "bus_fault_voltage")
        resistance = sum(
            spec(address, "resistance")[0]
            for address in terminations[bus]
            if spec_has(address, "resistance")
        )
        assert resistance, f"{bus}: no resistance in its termination"
        current = fault / resistance
        rating, _ = spec(header, "current_rating")
        assert current <= rating, (
            f"{bus}: {current:.2f} A through the connector if a wire sits at "
            f"the {fault:g} V its transceiver survives, against {rating:g} A "
            "per pin"
        )


def test_the_can_transceivers_leave_room_in_the_bit_they_arbitrate_in(
    spec, spec_has, buses
):
    """
    Two transceiver delays inside one arbitration bit.

    CAN arbitration is decided by every node seeing the same bus level within
    the bit it is sent in: a node's dominant bit has to reach the far end of the
    cable and its own receiver has to see the result, so each arbitration bit
    contains a round trip. The transceivers are the fixed part of that budget -
    the cable's share depends on how long it is, and this is what is left for it
    once the silicon has taken its cut.
    """
    _, rate = spec("can", "arbitration_rate")
    _, allowed = spec("can", "transceiver_delay_share")
    for bus, (transceiver, _, _) in sorted(buses.items()):
        if not spec_has(transceiver, "loop_delay_max"):
            continue
        _, loop = spec(transceiver, "loop_delay_max")
        share = 2 * loop * rate
        assert share <= allowed, (
            f"{bus}: two loop delays of {loop * 1e9:.0f} ns are "
            f"{share:.0%} of a bit at {rate / 1e3:g} kbit/s, over the "
            f"{allowed:.0%} the cable is left"
        )


def test_no_bus_is_clocked_faster_than_its_transceiver_signals(spec, buses, spec_has):
    """
    The rate firmware will run each bus at, against what the part does.

    Both rates are written down in `INTENT` because they are firmware's to
    choose, and a part chosen for its price rather than its speed is only found
    this way - a 500 kbit/s transceiver on a 1 Mbit/s bus works at the bench
    length and degrades with cable, which is the hardest kind of fault to find.
    """
    for bus, (transceiver, _, _) in sorted(buses.items()):
        if not spec_has(transceiver, "data_rate_max"):
            continue
        limit, _ = spec(transceiver, "data_rate_max")
        wanted = f"{bus}.baud" if bus == "rs485" else f"{bus}.arbitration_rate"
        _, rate = spec(*wanted.rsplit(".", 1))
        assert rate <= limit, (
            f"{bus}: {rate / 1e3:g} kbit/s asked of a part that does "
            f"{limit / 1e3:g}"
        )


def test_every_receiver_enable_is_tied_to_the_state_that_listens(
    design, pads_of, pin_names, buses
):
    """
    A receiver enable is held asserted, whichever way round the part wants it.

    Half duplex means the driver and the receiver share the pair, and a node
    that stops listening while it transmits cannot hear a collision with
    another node that started in the same moment. Both then carry on, and what
    arrives at every other node is neither message. Holding the receiver on
    costs nothing: the bytes it reads back are its own, and firmware discards
    them.

    Which pin that is, and which level asserts it, come from the symbol - `RE`
    is active high and `~{RE}` active low - so a part swapped for one with the
    opposite polarity is a failure here rather than a board that never receives.
    """
    found = 0
    for bus, (transceiver, _, _) in sorted(buses.items()):
        for pad, name in sorted(pin_names[transceiver].items()):
            bare = name.replace("~{", "").replace("}", "")
            if bare != "RE":
                continue
            found += 1
            net = pads_of[transceiver].get(pad)
            wanted = GROUND if name != bare else "a supply rail"
            asserted = net == GROUND if name != bare else net in RAILS
            assert asserted, (
                f"{bus}: {name} on pin {pad} is on {net!r}, not {wanted}, so "
                "the receiver is not held on"
            )
    assert found, "no receiver enable found, and this check is about them"


def test_every_transceiver_that_has_a_mode_pin_boots_into_a_state_the_board_wants(
    design, pads_of, pin_names, buses
):
    """
    A transceiver's mode pin is held, by the board or by the part, and the
    state it is held in is written down.

    `test_every_receiver_enable_is_tied_to_the_state_that_listens` looks for a
    pin called `RE`. The CAN transceiver has none - its mode pin is `Rs` on
    the symbol and `STB` on the part it actually is - so that check found the
    RS-485 part, asserted `found` was non-zero, and skipped the other bus
    entirely. Half a board's worth of coverage behind an assertion that one
    thing was found.

    What this asserts instead is the thing that matters and does not depend on
    a pin's name: every pin on a transceiver that is neither a supply, a
    ground, a bus line nor a data line is a **mode** pin, and a mode pin must
    reach something that decides its state - a rail, a resistor, or an MCU
    pin whose reset level the pin map states.

    **It does not assert which state.** That is the part's own business and
    differs between them: RS-485's `~{RE}` is held low on this board because
    a half-duplex node that stops listening cannot hear a collision, while
    CAN's `STB` is left to the transceiver's internal pull-up and boots into
    standby, which is a decision recorded in `cpu1.py` and in the pin map
    rather than a preference this check could hold.
    """
    known = {"VCC", "VDD", "GND", "V+", "V-", "VIO", "VREF"}
    problems = []
    checked = 0
    for bus, (transceiver, header, pair) in sorted(buses.items()):
        for pad, name in sorted(pin_names[transceiver].items()):
            bare = name.replace("~{", "").replace("}", "")
            net = pads_of[transceiver].get(pad)
            if bare.upper() in known or net in pair or net == GROUND:
                continue
            if symbol_pin_types(design["parts"][transceiver]["symbol"]).get(pad) == "output":
                continue                      # a receiver output, not a mode pin
            checked += 1
            if net is None:
                problems.append(f"  {bus}: {name} on pin {pad} reaches nothing at all")
    assert checked >= len(buses), (
        f"{checked} mode or control pins found across {len(buses)} buses; "
        f"every transceiver here has at least one and this check is about them"
    )
    assert not problems, (
        "Transceiver control pins with no defined state:\n" + "\n".join(problems)
    )


def test_nothing_unrated_for_a_strike_sits_on_a_bus_terminal(
    design, pads_of, spec, spec_has, buses
):
    """
    Every piece of silicon a cable can reach is qualified for a discharge.

    CAN and RS-485 leave this board on connectors a person can touch, and a
    person carries a few kilovolts across a carpet. IEC 61000-4-2 level 4 is
    8 kV by contact, which is what anything with a connector on the outside of
    a machine is expected to survive, and it is what `bus.esd_level` asks for.

    Neither bus has a protection device on it. That is a decision rather than
    an omission: both transceivers are qualified on their bus pins, at 8 kV
    powered contact and 18 kV contact respectively, and a TVS array in front
    of a part already rated higher than the array adds capacitance to a pair
    whose impedance matters and buys nothing.

    What the check holds is the thing that decision depends on - that the only
    parts a bus terminal reaches are passives and parts carrying a rating.
    Swap in a cheaper transceiver with no system-level qualification and this
    fails; hang an unrated buffer or a bias network's amplifier on the pair and
    it fails the same way, which is the case a named transceiver would miss.
    """
    required, _ = spec("bus", "esd_level")
    for bus, (_, header, wires) in sorted(buses.items()):
        assert wires, f"{bus} has no bus nets"
        for net in wires:
            exposed = {
                address for address, pads in pads_of.items()
                if net in pads.values() and address != header
            }
            assert exposed, f"{net} reaches the connector and nothing else"
            for address in sorted(exposed):
                # Two terminals is not the question. A termination resistor,
                # a jumper or a capacitor has no junction to punch through and
                # no datasheet figure to hold it to; a TVS or a clamp diode on
                # the same two pads is the part whose whole job is the rating.
                #
                # The exemption tried to say that once by also requiring the
                # part to declare no supply pin, and that clause did nothing:
                # no two-pin symbol on this board names a pin VCC or GND, so
                # the exempt set was still "anything small" and a TVS on a bus
                # terminal was still skipped by being small. The symbol answers
                # the real question itself - KiCad's Description is the one
                # machine-readable statement of what a part *is*, and every
                # junction part on this board says "diode" in it while no
                # passive does.
                symbol = design["parts"][address]["symbol"]
                junction = "diode" in symbol_description(symbol).lower()
                if len(pads_of[address]) <= 2 and not junction:
                    continue
                assert spec_has(address, "esd_contact_discharge"), (
                    f"{bus}: {address} sits on {net}, which leaves the board, "
                    f"and states no contact-discharge rating"
                )
                rated, _ = spec(address, "esd_contact_discharge")
                assert rated >= required, (
                    f"{bus}: {address} is rated {rated / 1e3:g} kV by contact "
                    f"against the {required / 1e3:g} kV a connector on the "
                    f"outside of a machine has to survive"
                )


def test_a_cable_ground_tied_straight_to_the_boards_is_one_the_parts_can_afford(
    design, pads_of, spec, buses
):
    """
    Neither connector's ground pin has a resistor in it, and that is a choice.

    Industrial practice on RS-485 puts a hundred ohms between the cable's
    reference and the board's, so that two machines whose grounds sit a few
    volts apart drive a bounded current down the cable instead of whatever the
    wire will carry. TI's own design guide says so. This board does not do it.

    What makes that defensible is the transceivers. Each standard states the
    ground offset a receiver must tolerate - ISO 11898-2 asks CAN for -2 to
    7 V, TIA-485 asks RS-485 for -7 to 12 - and both parts here are specified
    well past it, ±12 V and ±15 V. The offset that would break the link is
    therefore one the standards do not require anybody to survive, and a
    resistor sized to protect against more than that has to dissipate it: at
    the ±15 V edge, a hundred ohms at each end of the cable is more than half
    a watt in an 0402.

    So the check is on the thing the choice rests on, not on the choice. Swap
    either transceiver for one that only meets its standard and the margin
    that justified the hard tie is gone, and this fails.

    **What it does not cover**: a long cable between two machines on separate
    supplies, where the offset is not bounded by anything. The answer there is
    an isolated transceiver, not a resistor, and that is a different part and a
    different plan.
    """
    for bus, (transceiver, header, _) in sorted(buses.items()):
        grounds = [pad for pad, net in pads_of[header].items() if net == GROUND]
        if not grounds:
            continue    # a bus whose reference is not tied straight down
        low, high = spec(bus, "common_mode_required")
        part_low, _ = spec(transceiver, "common_mode_low")
        _, part_high = spec(transceiver, "common_mode_high")
        margin, _ = spec("bus", "common_mode_margin")
        # Both halves, because each says something the other cannot. The width
        # ratio is the margin the hard tie is justified by; containment is what
        # makes the ratio mean anything. A part rated 0 to +30 V is 1.58 times
        # as wide as TIA-485's -7 to +12 and tolerates none of its negative
        # half, and for two machines whose grounds sit apart - the entire
        # subject of this check - the negative half is where the offset goes.
        # The width test alone was the whole check for one commit.
        assert part_low <= low and part_high >= high, (
            f"{bus}: its connector's ground pin goes straight to the board's, "
            f"and {transceiver} tolerates {part_low:g} to {part_high:g} V of "
            f"offset, which does not cover the {low:g} to {high:g} V its "
            f"standard requires"
        )
        assert (part_high - part_low) >= margin * (high - low), (
            f"{bus}: its connector's ground pin goes straight to the board's, "
            f"and {transceiver} tolerates {part_low:g} to {part_high:g} V of "
            f"offset - {(part_high - part_low) / (high - low):.2f} times the "
            f"{low:g} to {high:g} V its standard requires, against the "
            f"{margin:g} the tie is justified by"
        )


def test_each_bus_pair_is_drawn_the_way_its_rule_claims(buses, pcb_text, board_dir):
    """
    Both halves of each bus pair are the same width, and arrive together.

    `rules.kicad_dru` says of these four nets: "they are differential pairs
    leaving the board on a cable, so they are wider than a signal that stays
    on it, and the two halves of each pair are the same width as each other -
    a difference in width is a difference in impedance, and the impedance is
    the only thing a terminated bus cares about."

    **A `(min ...)` constraint cannot make that true.** It sets a floor, and a
    floor does not equalise anything: two nets can both clear 0.2 mm at 0.2
    and 0.4. Nor could any check see it - this file never opened the board
    file at all, so no width, length or separation was computed for CAN or
    RS-485 anywhere on this board. The widths agree today only because the
    layout generator gives both halves the same floor.

    So equality alone would be a check that cannot fail, and the thing that
    *can* is next to it: `layout.py` computes one width from the **high** half
    and draws both with it. If a rule ever asked more of the low half - a
    later rule matching `CAN_L`, or a pattern that catches one name and not
    the other - the generator would draw it too narrow. So each net's drawn
    width is held against what its own rule requires, read out of the rules
    file, which is the comparison the generator's shortcut can lose.

    **What is not claimed, and is not checked, is impedance.** Measured, the
    two halves of each pair run 2.54 mm apart - header pitch, over 0.19 mm of
    prepreg - which is not a coupled pair at all but two single-ended traces
    that happen to be adjacent. That is a legitimate choice at CAN and RS-485
    edge rates over this distance, and it is why the rule's sentence stops at
    width. Saying so here is what stops someone reading "differential pair"
    and assuming a controlled one.
    """
    import re as _re

    names = {m.group(1): m.group(2)
             for m in _re.finditer(r'\(net (\d+) "([^"]*)"\)', pcb_text)}
    widths: dict[str, set] = {}
    for block in _re.findall(r"\n\t\(segment\n(?:\t\t[^\n]*\n)+\t\)", pcb_text):
        net = _re.search(r"\(net (\d+)\)", block)
        width = _re.search(r"\(width ([\d.]+)\)", block)
        if net and width:
            widths.setdefault(names.get(net.group(1), ""), set()).add(float(width.group(1)))

    # What each net's own rules ask of it, from the rules file rather than
    # from the generator that consumed it.
    import fnmatch

    required: list[tuple[str, float]] = []
    text = (board_dir / "rules.kicad_dru").read_text()
    for block in text.split("(rule ")[1:]:
        condition = _re.search(r'\(condition "([^"]*)"\)', block)
        width = _re.search(r"\(constraint track_width \(min ([\d.]+)mm\)\)", block)
        if not (condition and width):
            continue
        for pattern in _re.findall(r"A\.NetName == '([^']*)'", condition.group(1)):
            required.append((pattern, float(width.group(1))))
    assert required, "no track_width rules found to check against"

    problems = []
    for bus, (_, _, pair) in sorted(buses.items()):
        assert len(pair) == 2, f"{bus} is {pair}, not a pair"
        drawn = [widths.get(net, set()) for net in pair]
        for net, found in zip(pair, drawn):
            assert found, f"{net} has no copper on the board"
        if drawn[0] != drawn[1]:
            problems.append(
                f"  {bus}: {pair[0]} is drawn at {sorted(drawn[0])} mm and "
                f"{pair[1]} at {sorted(drawn[1])} mm - the rule says both "
                f"halves are the same width as each other"
            )
        for net, found in zip(pair, drawn):
            wants = max([0.0] + [w for pattern, w in required
                                 if fnmatch.fnmatchcase(net, pattern)])
            if min(found) < wants - 1e-9:
                problems.append(
                    f"  {bus}: {net} is drawn at {min(found):g} mm and its own "
                    f"rule asks for {wants:g} mm. The layout takes one width "
                    f"from the pair's high half and draws both with it, so a "
                    f"rule that asks more of the other half is lost"
                )
    assert not problems, (
        "Bus pairs whose halves are drawn differently:\n" + "\n".join(problems)
    )
