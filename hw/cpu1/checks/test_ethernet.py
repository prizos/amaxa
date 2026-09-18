"""
The Ethernet PHY, its supplies, and the clock it makes for everything else.

The LAN8742A is configured almost entirely by what is *not* wired to it: the
mode straps come up where this design wants them, and the one strap that does
not is pulled the other way with a resistor. So most of these checks are about
pins being left alone deliberately rather than by accident, which is a
distinction a schematic cannot make and a netlist can.

Datasheet: SMSC *LAN8742A/LAN8742Ai*, revision 1.1 (05-21-13). It ships
encrypted; `parts/QFN24/QFN24.md` records how it was read.
"""

import math
import sys
from pathlib import Path

import pytest

# pytest imports these files by path, so the directory they share is not on
# sys.path and the helper beside them has to be found deliberately.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import pairs  # noqa: E402

PHY = "eth.phy"
JACK = "eth.jack"
CRYSTAL = "eth.xtal.crystal"
GROUND = "GND"

RAILS = {"5V": "rail.5v", "3V3": "rail.3v3"}

# Which declared range each supply pin is held to, by the name the symbol gives
# it. VDD1A and VDD2A are the two analog channels and share one figure.
SUPPLIES = {
    "VDDIO": "io_supply_voltage",
    "VDD1A": "analog_supply_voltage",
    "VDD2A": "analog_supply_voltage",
}


@pytest.fixture(scope="module")
def pad_net(design):
    return {tuple(node): net for net, nodes in design["nets"].items() for node in nodes}


@pytest.fixture(scope="module")
def pads_of(pad_net):
    out: dict[str, dict[str, str]] = {}
    for (address, pad), net in pad_net.items():
        out.setdefault(address, {})[pad] = net
    return out


@pytest.fixture(scope="module")
def pin_names(design, board_dir):
    import sys

    sys.path.insert(0, str(board_dir.parent / "tools"))
    from symbols import symbol_pin_names

    return symbol_pin_names(design["parts"][PHY]["symbol"])


@pytest.fixture(scope="module")
def net_on(pads_of, pin_names):
    """The net on the PHY pin with a given name, or None if it has none."""
    by_name = {name: pad for pad, name in pin_names.items()}

    def lookup(name: str):
        assert name in by_name, f"the symbol has no pin called {name!r}"
        return pads_of[PHY].get(by_name[name])

    return lookup


def _parts_on(design, net, exclude=()):
    return sorted({
        address for address, _ in design["nets"].get(net, [])
        if address not in exclude
    })


# --- supplies ----------------------------------------------------------------


def test_every_supply_pin_is_on_a_rail_its_datasheet_allows(spec, net_on):
    """
    Each of the PHY's three external supplies, against the range stated for it.

    The I/O supply and the analog supplies are different ranges - 1.62 to 3.6 V
    against 3.0 to 3.6 - and a part that will run its logic from 1.8 V will not
    run its line driver from it. Both sit on 3V3 here, which satisfies both, and
    the check is that each pin is matched to its own figure rather than to the
    more generous one.
    """
    for name, parameter in sorted(SUPPLIES.items()):
        net = net_on(name)
        assert net in RAILS, f"{name} is on {net!r}, which is not a declared rail"
        low, high = spec(PHY, parameter)
        rail_low, rail_high = spec(RAILS[net], "voltage")
        assert low <= rail_low and rail_high <= high, (
            f"{name} is on {net} at {rail_low} to {rail_high} V, outside the "
            f"{low} to {high} V its datasheet allows"
        )


def test_the_core_rail_is_the_phys_own_and_nothing_drives_it(
    design, spec, spec_has, net_on, pads_of
):
    """
    VDDCR carries the internal regulator's output and meets only capacitors.

    It is a supply pin that its own silicon supplies, which makes it the one
    pin on this part that must *not* be connected to a rail: 3.3 V on a 1.2 V
    regulator output destroys the part. Nothing here would stop that but the
    fact that the net goes nowhere, so that is what is checked, along with the
    capacitors being rated for a good deal more than it carries.
    """
    core = net_on("VDDCR")
    assert core not in RAILS, f"the core rail is {core}, which is a board rail"
    _, ceiling = spec(PHY, "core_supply_voltage")

    capacitors = _parts_on(design, core, exclude=(PHY,))
    assert len(capacitors) == 2, (
        f"{core} has {len(capacitors)} parts on it; the datasheet asks for a "
        "1 uF and a 470 pF in parallel"
    )
    for address in capacitors:
        assert spec_has(address, "capacitance"), f"{address} on {core} is not a capacitor"
        assert GROUND in pads_of[address].values(), f"{address} does not reach ground"
        rating, _ = spec(address, "max_voltage")
        assert rating > ceiling, (
            f"{address} is rated {rating} V on a {ceiling} V rail"
        )

    # Two decades apart, which is what makes them a pair rather than a
    # duplicate: one holds the rail up between load steps, the other is still
    # a capacitor at the frequencies the other has stopped being one at.
    values = sorted(spec(address, "capacitance")[0] for address in capacitors)
    assert values[1] / values[0] >= 100, (
        f"the core rail's two capacitors are {values[0] * 1e12:.0f} pF and "
        f"{values[1] * 1e12:.0f} pF, which is one capacitor twice"
    )


def test_the_bias_resistor_sets_the_current_the_datasheet_expects(
    design, spec, spec_has, net_on, pads_of
):
    """
    One resistor from RBIAS to ground, at the value the part is trimmed for.

    It sets the reference current for the whole analog front end, so it sets
    the transmit amplitude, and nothing downstream adjusts for it being wrong -
    a link that works on a short cable and fails on a long one is what a bias
    resistor off by a few per cent buys.
    """
    net = net_on("RBIAS")
    resistors = _parts_on(design, net, exclude=(PHY,))
    assert len(resistors) == 1, f"{net} has {len(resistors)} parts on it, not one resistor"
    address = resistors[0]
    assert spec_has(address, "resistance"), f"{address} is not a resistor"
    assert GROUND in pads_of[address].values(), f"{address} does not go to ground"
    low, high = spec(address, "resistance")
    wanted_low, wanted_high = spec(PHY, "bias_resistance")
    assert wanted_low <= low and high <= wanted_high, (
        f"{address} is {low:g} to {high:g} ohm and the part wants "
        f"{wanted_low:g} to {wanted_high:g}"
    )


# --- the clock ---------------------------------------------------------------


def test_the_phy_can_drive_the_crystal_it_was_given(spec):
    """
    The crystal's worst-case series resistance against what the oscillator is
    specified to start.

    This is why the crystal is in a 5032 and not the cheaper 3225: at 25 MHz
    the smaller package runs 50 to 80 ohm, and this oscillator is specified to
    30. A crystal above that will often still start on a warm bench, which is
    the worst possible outcome - it fails in the cold, in the field, some of
    the time.
    """
    esr, _ = spec(CRYSTAL, "esr_max")
    allowed, _ = spec(PHY, "crystal_esr_max")
    assert esr <= allowed, (
        f"the crystal is {esr:g} ohm and the oscillator is specified to {allowed:g}"
    )
    frequency, _ = spec(CRYSTAL, "frequency")
    wanted, _ = spec(PHY, "crystal_frequency")
    assert frequency == wanted, (
        f"the crystal is {frequency / 1e6:g} MHz and the PHY multiplies up from "
        f"{wanted / 1e6:g}"
    )
    # The oscillator is drawn for a particular load, and a crystal cut for a
    # very different one is a load the circuit then has to fake with capacitors
    # far from the values the datasheet's own example uses.
    cut_for, _ = spec(CRYSTAL, "load_capacitance")
    recommended, _ = spec(PHY, "crystal_load_capacitance")
    assert cut_for == recommended, (
        f"the crystal is cut for {cut_for * 1e12:g} pF and the oscillator is "
        f"specified around {recommended * 1e12:g} pF"
    )


def test_the_crystal_sees_the_load_it_is_cut_for(design, spec, spec_has, pads_of, net_on):
    """
    The two load capacitors in series, plus what the pins and the board add.

    A crystal is cut for a particular load; present it a different one and it
    runs at a different frequency. Here that is not a cosmetic error - the
    whole link's clock comes out of this, and 100BASE-TX has fifty parts per
    million to spend on everything.

    The pin capacitance is the datasheet's; the board's stray is this design's
    own declared band, as it is for the MCU's two oscillators, and bring-up
    measures the frequency error that would show it wrong.
    """
    caps = []
    for name in ("XTAL1/CLKIN", "XTAL2"):
        net = net_on(name)
        on_it = [
            address for address in _parts_on(design, net, exclude=(PHY, CRYSTAL))
            if spec_has(address, "capacitance") and GROUND in pads_of[address].values()
        ]
        assert len(on_it) == 1, f"{name} has {len(on_it)} capacitors to ground"
        caps.append(on_it[0])

    pin, _ = spec(PHY, "xtal_pin_capacitance")
    stray_low, stray_high = spec("ethernet", "stray_capacitance")
    (c1_low, c1_high), (c2_low, c2_high) = (spec(c, "capacitance") for c in caps)
    load_low = (c1_low + pin) * (c2_low + pin) / (c1_low + c2_low + 2 * pin) + stray_low
    load_high = (c1_high + pin) * (c2_high + pin) / (c1_high + c2_high + 2 * pin) + stray_high

    wanted, _ = spec(CRYSTAL, "load_capacitance")
    assert load_low <= wanted <= load_high, (
        f"the crystal is cut for {wanted * 1e12:.1f} pF and sees "
        f"{load_low * 1e12:.2f} to {load_high * 1e12:.2f} pF"
    )


def test_the_clock_stays_inside_the_budget_the_standard_allows(spec):
    """
    Initial tolerance plus drift over temperature, against two ceilings.

    IEEE 802.3 gives the whole link ±50 ppm. The PHY's datasheet then says the
    combination of tolerance and stability must come to about ±45, leaving the
    rest for the crystal ageing over the years the board is in service - which
    is a budget nobody can measure at bring-up and everybody spends.
    """
    tolerance, _ = spec(CRYSTAL, "frequency_tolerance")
    stability, _ = spec(CRYSTAL, "frequency_stability")
    total = tolerance + stability
    part_budget, _ = spec(PHY, "crystal_ppm_budget")
    _, standard = spec("ethernet", "clock_budget")
    assert total <= part_budget, (
        f"{total * 1e6:.0f} ppm of tolerance and drift against the "
        f"{part_budget * 1e6:.0f} ppm the datasheet leaves for them"
    )
    assert total <= standard, (
        f"{total * 1e6:.0f} ppm against the standard's {standard * 1e6:.0f}"
    )


def test_the_phy_makes_the_reference_clock_rather_than_taking_one(
    design, spec_has, pads_of, net_on, pin_map
):
    """
    nINTSEL is pulled to the level that turns the nINT pin into a clock output,
    and that pin goes to the MCU's RMII clock input.

    This is the decision the whole block is arranged around: a 25 MHz crystal
    instead of a 50 MHz oscillator, at the cost of the interrupt line. Left
    alone the strap comes up the other way through its internal pull-up, the
    PHY waits for a clock nobody drives, and the interface is silent with every
    voltage on the board correct.
    """
    strap = net_on("LED2/~{INTSEL}")
    pulls = _parts_on(design, strap, exclude=(PHY,))
    assert len(pulls) == 1, f"the nINTSEL strap has {len(pulls)} resistors on it"
    assert GROUND in pads_of[pulls[0]].values(), (
        f"{pulls[0]} does not pull nINTSEL down, so the PHY comes up waiting "
        "for a reference clock this board does not generate"
    )

    clock = net_on("~{INT}/REFCLKO")
    assert clock == "ETH_REF_CLK", f"the clock pin is on {clock!r}"
    reaches = {p.pin for p in pin_map.PINS if p.net_name == clock}
    assert reaches, f"{clock} does not reach the MCU"


def test_the_straps_left_alone_are_left_alone(design, pin_names, pads_of, net_on):
    """
    Every strap that this design relies on defaulting has nothing pulling it.

    MODE[2:0] come up at 111 - all capable, auto-negotiation - through their
    own pull-ups; PHYAD0 comes up at 0; REGOFF's internal pull-down is what
    turns the 1.2 V regulator on. Each of those is a decision to add no
    component, and a decision to add nothing is invisible in a schematic: the
    only trace of it is the absence this checks for.

    MODE[2:0] share pins with three RMII outputs, so "nothing pulling them"
    means nothing but the MCU at the other end.
    """
    allowed = {"mcu", PHY}
    problems = []
    for pad, name in sorted(pin_names.items()):
        if not any(tag in name for tag in ("MODE", "PHYAD", "REGOFF")):
            continue
        net = pads_of[PHY].get(pad)
        if net is None:
            continue                      # deliberately unconnected
        others = _parts_on(design, net, exclude=())
        stray = sorted(set(others) - allowed)
        if stray:
            problems.append(f"  {name} on pin {pad} also reaches {stray}")
    assert not problems, (
        "Straps this design relies on defaulting, with something pulling "
        "them:\n" + "\n".join(problems)
    )


def test_management_and_reset_come_up_in_a_state_that_can_be_talked_to(
    design, spec_has, pads_of, net_on
):
    """
    MDIO and nRST are both held high by a resistor to a rail.

    Before firmware runs, the MCU's pins float. MDIO floating is a management
    bus with no idle level; nRST floating is a PHY that may or may not be in
    reset. Both are the difference between a board a debugger can talk to and
    one that has to be guessed at.
    """
    for name in ("MDIO", "~{RST}"):
        net = net_on(name)
        pulls = [
            address for address in _parts_on(design, net, exclude=(PHY, "mcu"))
            if spec_has(address, "resistance")
        ]
        assert len(pulls) == 1, f"{name} has {len(pulls)} resistors on it"
        assert set(pads_of[pulls[0]].values()) & set(RAILS), (
            f"{pulls[0]} does not pull {name} up to a rail"
        )


def test_each_pair_runs_from_the_package_to_the_jack_without_meeting_anything(
    design, net_on, pads_of
):
    """
    Four line pins, four nets, and each one reaching exactly the package and
    the connector.

    Between the PHY's line driver and the transformer there is meant to be
    copper and nothing else: no series part, no test point, no stub. Anything
    else on the net is a discontinuity in the one place on this board where
    that word means something.
    """
    for phy_pin, jack_pin in (("TXP", "TD+"), ("TXN", "TD-"),
                              ("RXP", "RD+"), ("RXN", "RD-")):
        net = net_on(phy_pin)
        reached = sorted({address for address, _ in design["nets"][net]})
        assert reached == sorted({PHY, JACK}), (
            f"{net} reaches {reached}; it should reach the PHY and the jack"
        )
        assert net in pads_of[JACK].values(), f"{net} does not arrive at the jack"


def test_the_pairs_present_the_impedance_the_cable_expects(spec, stack, pcb_text):
    """
    The width and separation actually on the board, put back through the
    stackup.

    Measured, not taken from the layout: the layout solves the same formulas to
    choose the width, so asking it what it chose would prove nothing. A pair
    drawn at one width and spaced for another fails here.
    """
    import sys as _sys

    _sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
    from layout_lib import differential_impedance

    low, high = spec("ethernet", "differential_impedance")
    for pair in ("ETH_TD", "ETH_RD"):
        tracks = pairs.tracks_of(pcb_text, (f"{pair}_P", f"{pair}_N"))
        assert set(tracks) == {f"{pair}_P", f"{pair}_N"}, f"{pair} is not both halves"
        width = pairs.controlled_width(tracks)
        runs = {
            net: [seg for seg in segments if round(seg[2], 4) == width]
            for net, segments in tracks.items()
        }
        gap = pairs.separation(runs[f"{pair}_P"], runs[f"{pair}_N"]) - width
        impedance = differential_impedance(width, gap, stack)
        assert low <= impedance <= high, (
            f"{pair}: {width:g} mm traces {gap:.3f} mm apart make "
            f"{impedance:.1f} ohm, outside {low:g} to {high:g}"
        )


def test_the_pairs_arrive_together_enough(spec, stack, lengths, pcb_text):
    """
    How far apart in time the two halves of each pair arrive.

    The budget here is not timing. 100BASE-TX deliberately slows its edges to
    three nanoseconds or more and its receiver equalises far worse than this;
    what mismatch costs is common mode, and common mode leaves on eighty metres
    of cable. Each pair crosses itself once on the way to the connector -
    unavoidably, because the PHY and the jack order their pins oppositely - and
    the detour that crossing needs is most of the mismatch measured here.
    """
    edge, _ = spec("ethernet", "rise_time")
    _, allowed = spec("ethernet", "skew_share")
    for pair in ("ETH_TD", "ETH_RD"):
        tracks = pairs.tracks_of(pcb_text, (f"{pair}_P", f"{pair}_N"))
        width = pairs.controlled_width(tracks)
        mismatch = abs(lengths[f"{pair}_P"] - lengths[f"{pair}_N"])
        skew = mismatch * pairs.delay_per_mm(stack, width)
        assert skew <= allowed * edge, (
            f"{pair}: {mismatch:.1f} mm of mismatch is {skew * 1e12:.0f} ps, "
            f"{skew / edge:.1%} of a {edge * 1e9:g} ns edge, over {allowed:.0%}"
        )


def test_the_centre_taps_sit_where_the_transmitter_can_use_them(spec, pads_of, design):
    """
    Both transformer centre taps on a rail the magnetics are specified for,
    each with its own bypass.

    The line driver is current-mode: it pulls current *out* of the winding, and
    the centre tap is where that current comes from. Taps on ground, which is
    what a voltage-mode PHY wants, give a transmitter with nothing to drive
    against and a link that never comes up.

    Each tap gets its own capacitor because the two windings switch at
    different moments; one shared bypass puts the transmit return through the
    receive winding's tap.
    """
    low, high = spec(PHY, "magnetics_supply_voltage")
    by_name = {}
    for pad, net in pads_of[JACK].items():
        by_name[pad] = net
    taps = {pad: by_name[pad] for pad in ("4", "5") if pad in by_name}
    assert len(taps) == 2, f"the jack has {len(taps)} centre taps connected"
    for pad, net in sorted(taps.items()):
        assert net in RAILS, f"centre tap {pad} is on {net!r}, not a rail"
        rail_low, rail_high = spec(RAILS[net], "voltage")
        assert low <= rail_low and rail_high <= high, (
            f"centre tap {pad} is on {net} at {rail_low} to {rail_high} V, "
            f"outside the {low} to {high} V the magnetics are specified for"
        )

    rail = sorted(set(taps.values()))[0]
    bypasses = [
        address for address, _ in design["nets"][rail]
        if address.startswith("eth.tap_bypass")
    ]
    assert len(bypasses) == 2, f"{len(bypasses)} bypasses for two centre taps"


def test_the_screen_and_the_termination_reach_ground(pads_of):
    """
    The jack's shell and the common of its own termination network are on the
    board's ground.

    There is one ground here - the plan says so, and the analog side is kept
    together by placement instead of by a split - so there is nothing for a
    screen to be isolated *from*. What there is, is the failure of leaving it
    floating: a screen connected at the far end of the cable and nowhere here
    is an antenna with a driven element.
    """
    for pad, what in (("SH", "the shell"), ("8", "the termination common")):
        assert pads_of[JACK].get(pad) == GROUND, (
            f"{what} is on {pads_of[JACK].get(pad)!r}, not ground"
        )


def test_the_jack_isolates_the_cable_from_the_board(spec):
    """
    The magnetics' isolation rating against what an Ethernet port has to stand.

    IEEE 802.3 asks for 1500 V rms between the cable and everything else, and
    on this board that is the only barrier there is: the cable arrives at a
    connector bolted to the same ground as the MCU.
    """
    rating, _ = spec(JACK, "isolation_voltage")
    required, _ = spec("ethernet", "isolation")
    assert rating >= required, (
        f"the jack isolates to {rating:g} V and the standard asks for {required:g}"
    )


def test_no_plane_runs_under_the_jacks_cable_end(board_dir, pcb_text):
    """
    The copper pours stop short of the half of the jack the cable goes into.

    The jack's pads keep their copper - they have to reach the plane - and what
    is cleared is where the contacts and the cable's screen sit.

    Asked as "is there pour at this point", not "does any outline corner fall
    in the region": the first version of this check asked the second question,
    and a pour drawn straight across the corner answered it correctly and
    covered the jack anyway. A plane that covers a region has no vertex in it.
    """
    import re

    sys.path.insert(0, str(board_dir.parent / "tools"))
    from mcu_pins import load_source

    description = load_source(board_dir / "layout.py", "cpu1_layout_keepout")
    x0, y0, x1, y1 = description.JACK_KEEPOUT
    middle = ((x0 + x1) / 2, (y0 + y1) / 2)

    covered = []
    for block in re.findall(r"\n\t\(zone\b.*?\n\t\)", pcb_text, re.S):
        net = re.search(r'\(net_name "([^"]*)"\)', block)
        # The whole run of (xy ...) pairs. Matching the closing parenthesis
        # loosely drops the last point, which turns the notch back into a
        # rectangle and makes this check pass for the wrong reason.
        outline = re.search(r"\(polygon\s*\(pts\s*((?:\(xy [^)]*\)\s*)+)", block, re.S)
        if not outline:
            continue
        points = [
            (float(x), float(y))
            for x, y in re.findall(r"\(xy ([-\d.]+) ([-\d.]+)\)", outline.group(1))
        ]
        if _inside(points, middle):
            covered.append(net.group(1) if net else "?")
    assert not covered, (
        f"Pours reaching under the jack's cable end at {middle}: "
        + ", ".join(sorted(covered))
    )


def _inside(polygon: list[tuple[float, float]], point: tuple[float, float]) -> bool:
    """Ray casting: how many sides a ray from the point crosses going right."""
    x, y = point
    crossings = 0
    for (x1, y1), (x2, y2) in zip(polygon, polygon[1:] + polygon[:1]):
        if (y1 > y) != (y2 > y):
            where = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if where > x:
                crossings += 1
    return crossings % 2 == 1


@pytest.fixture(scope="module")
def pin_map(board_dir):
    import sys

    sys.path.insert(0, str(board_dir.parent / "tools"))
    from mcu_pins import load_source

    return load_source(board_dir / "pinmap.py", "cpu1_pinmap_eth")
