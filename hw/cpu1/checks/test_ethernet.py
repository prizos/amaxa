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
import re
import sys
from pathlib import Path

import pytest

# pytest imports these files by path, so the directory they share is not on
# sys.path and the helper beside them has to be found deliberately.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import pairs  # noqa: E402
from series import closest  # noqa: E402

# The same three dielectric heights the comparator separation is derived from:
# past that, two microstrips have largely stopped coupling.
SEPARATION_IN_HEIGHTS = 3

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


def test_the_crystal_sees_the_load_it_is_cut_for(
    design, spec, spec_has, pads_of, net_on, board_capacitance
):
    """
    The two load capacitors in series, plus what the pins and the board add.

    A crystal is cut for a particular load; present it a different one and it
    runs at a different frequency. Here that is not a cosmetic error - the
    whole link's clock comes out of this, and 100BASE-TX has fifty parts per
    million to spend on everything.

    The pin capacitance is the datasheet's. The board's is **measured off the
    board file**, per leg, rather than declared: each terminal's copper sits in
    parallel with that terminal's own capacitor, and this board's two legs are
    not the same length - the four-pad crystal puts its terminals on a
    diagonal, so one track goes the long way round, 2.08 pF against 1.22. A
    single declared figure across the pair hides that, and hid a load error of
    more than a picofarad while reading as though it had been thought about.

    What the check then asks is not that the load land exactly on the cut: no
    capacitor value can do that, because the values come in a series and the
    ideal here is 35.5 pF. It asks that **no value in the series gets closer**,
    which is the strongest statement available and needs nothing this board
    cannot measure. Turning the residual into parts per million would need the
    crystal's motional capacitance, and this manufacturer prints "N/A" against
    it - so the ppm is not derivable, and is not asserted.
    """
    caps = []
    strays = []
    for name in ("XTAL1/CLKIN", "XTAL2"):
        net = net_on(name)
        on_it = [
            address for address in _parts_on(design, net, exclude=(PHY, CRYSTAL))
            if spec_has(address, "capacitance") and GROUND in pads_of[address].values()
        ]
        assert len(on_it) == 1, f"{name} has {len(on_it)} capacitors to ground"
        caps.append(on_it[0])
        strays.append(board_capacitance(net))

    pin, _ = spec(PHY, "xtal_pin_capacitance")
    (c1_low, c1_high), (c2_low, c2_high) = (spec(c, "capacitance") for c in caps)
    assert (c1_low, c1_high) == (c2_low, c2_high), (
        f"{caps[0]} and {caps[1]} are different values; the load below is "
        f"worked from one of them"
    )

    def load(value: float) -> float:
        """The series load a pair of `value` capacitors presents, as built."""
        legs = [value + pin + stray for stray in strays]
        return legs[0] * legs[1] / sum(legs)

    wanted, _ = spec(CRYSTAL, "load_capacitance")
    nominal = (c1_low + c1_high) / 2
    best = closest(nominal, lambda v: abs(load(v) - wanted))
    assert abs(best - nominal) < 1e-15, (
        f"the crystal is cut for {wanted * 1e12:.1f} pF; a pair of "
        f"{nominal * 1e12:g} pF presents {load(nominal) * 1e12:.2f} pF and a "
        f"pair of {best * 1e12:g} pF would present {load(best) * 1e12:.2f}. "
        f"The board's own copper is {strays[0] * 1e12:.2f} and "
        f"{strays[1] * 1e12:.2f} pF of that"
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

    Exactly one resistor on each net reaches a rail. nRST also carries the
    resistor that feeds its delay capacitor, and that one goes to neither
    rail - which is how the two are told apart here rather than by name.
    `test_the_phy_is_held_in_reset_long_enough_after_power_up` is what holds
    the delay itself to the part's 25 ms.
    """
    for name in ("MDIO", "~{RST}"):
        net = net_on(name)
        resistors = [
            address for address in _parts_on(design, net, exclude=(PHY, "mcu"))
            if spec_has(address, "resistance")
        ]
        pulls = [address for address in resistors
                 if set(pads_of[address].values()) & set(RAILS)]
        assert len(pulls) == 1, (
            f"{name} has {len(pulls)} resistors to a rail on it, out of "
            f"{sorted(resistors)}"
        )


def test_each_pair_runs_from_the_package_to_the_jack_without_meeting_anything(
    design, net_on, pads_of
):
    """
    Four line pins, four nets, and each one reaching exactly the package and
    the connector.

    Between the PHY's line driver and the transformer there is meant to be
    copper and nothing else **in series**: no series part, no test point.
    Anything in the path is a discontinuity in the one place on this board
    where that word means something.

    A shunt is a different thing, and the distinction matters because
    Microchip's own front end is made of them. Figure 3.23 of the LAN8742A
    datasheet - rendered at `parts/QFN24/evidence/front_end.png` - hangs a
    49.9 ohm from each of these four nets to a ferrite-fed bias node, which is
    what makes the current-mode driver work into 50 ohms instead of 100. This
    board does not have them, and this check used to be written so that adding
    them would fail the build: it asserted the net reached *exactly* the PHY
    and the jack. A check that forbids the manufacturer's reference circuit is
    worse than no check, so it now forbids only what it means to.
    """
    rails = {"GND", "3V3", "5V", "ETH_VDDA"}
    pad_net = {tuple(node): net for net, nodes in design["nets"].items() for node in nodes}
    for phy_pin, jack_pin in (("TXP", "TD+"), ("TXN", "TD-"),
                              ("RXP", "RD+"), ("RXN", "RD-")):
        net = net_on(phy_pin)
        reached = {address for address, _ in design["nets"][net]}
        shunts = set()
        for address in reached - {PHY, JACK}:
            far = {pad_net.get((address, pad)) for pad in ("1", "2")} - {net}
            if far and far <= rails:
                shunts.add(address)       # one pad here, the other on a rail
        assert reached - shunts == {PHY, JACK}, (
            f"{net} reaches {sorted(reached - shunts)} in series; it should "
            "reach the PHY and the jack"
        )
        assert net in pads_of[JACK].values(), f"{net} does not arrive at the jack"


def test_the_rule_that_bounds_the_pairs_admits_only_their_impedance(
    spec, stack, board_dir
):
    """
    The narrowest track the DRU would accept still makes 100 ohm.

    The rule's comment said `test_ethernet.py` read this floor back and put it
    through the solver. **It did not.** One check opened rules.kicad_dru on
    this board and it was the USB one; the 0.2 mm here was the only
    impedance-bearing number on the board that nothing derived, sitting under
    a comment claiming otherwise.

    What it guards is the case the width check above cannot see: DRC passes a
    board whose pair was redrawn narrower, because the rule's floor is what
    DRC compares against, and a floor written once goes on saying the same
    thing after the fab changes the prepreg and `ETH_WIDTH` moves with it.
    """
    import re
    import sys

    sys.path.insert(0, str(board_dir.parent / "tools"))
    from layout_lib import differential_impedance
    from mcu_pins import load_source

    gap = load_source(board_dir / "layout.py", "cpu1_layout_eth").ETH_GAP
    text = (board_dir / "rules.kicad_dru").read_text()
    # Bounded to the rule's own body - `[^(]*` cannot cross into the next
    # `(rule`, so a rule that loses its own track_width fails here instead of
    # quietly reporting a later rule's.
    rule = re.search(
        r'\(rule "ethernet pairs"(?:[^(]|\((?!rule ))*?'
        r"\(constraint track_width \(min ([\d.]+)mm\)\)",
        text, re.S,
    )
    assert rule, "rules.kicad_dru has no ethernet pairs rule to check"
    low, high = spec("ethernet", "differential_impedance")
    floor = float(rule.group(1))
    impedance = differential_impedance(floor, gap, stack)
    assert low <= impedance <= high, (
        f"the rule admits {floor:g} mm traces, which at {gap:g} mm apart "
        f"make {impedance:.1f} ohm, outside {low:g} to {high:g}"
    )


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


def test_each_pair_runs_as_a_pair_for_most_of_its_length(
    spec, stack, pcb_text
):
    """
    How much of each pair is actually coupled, and what the rest costs.

    A differential pair is a pair where its two halves are close enough to
    couple. Everything else - the fan out of the package, the spread to the
    jack's pads, and on this board the excursion one half takes to the back
    layer to cross over its partner - is two single tracks carrying a
    differential signal between them, presenting about twice the single-ended
    impedance instead of the hundred ohms the cable expects.

    **Nothing measured this.** `tracks_of` looked at F.Cu only, so the back
    layer excursion was invisible, and `separation` reports the distance of
    the single longest parallel overlap - which certified five millimetres of
    a twenty-five millimetre route. The comment in layout.py put the crossing's
    cost at "a millimetre and a half of copper facing the wrong plane"; it is
    3.20 mm on the transmit pair and 4.96 on the receive one.

    What bounds it is the edge, not a fraction of the route: a discontinuity
    much shorter than the distance an edge travels while it rises is
    electrically short. At 100BASE-TX's 3 ns these pairs' uncoupled stretches
    are about three per cent of one, against the tenth `ethernet.rise_time`
    and `ethernet.rise_time` together imply. There is no band for it any more:
    `ethernet.uncoupled_edge_share` outlived its assertion by two commits,
    still declared and still carrying fourteen lines of justification, because
    the guard that hunts unread intent asks whether a value is *looked up* and
    this one still was - into a message. `tools/mutate.py` is what finds that,
    and it did: a band nothing notices when you set it to zero or to a million
    has no check behind it.

    The pairs are 51 % and 40 % coupled on their longer halves, and that is as
    good as this placement gets: lengthening the parallel run collides with
    the jack's own pads, which was tried. What is left is package and
    connector pitch.

    **Two bounds.** The first is the physics. It used to sum every uncoupled
    stretch on the route and compare the total against the distance an edge
    travels, which could not fail for any routing at all: the sum is bounded
    by the route's own length, 24.7 mm here, while a tenth of a 3 ns edge is
    48.7 mm. It also asked the wrong question. A pair fans out at the package,
    crosses over in the middle and spreads again at the jack, and those are
    three separate discontinuities; what decides whether one matters is its
    own extent against the edge, not the sum of all of them. So the bound is
    now on the longest *unbroken* stretch, and on its round trip, because a
    discontinuity is short when the reflection returns inside the rise. A pair
    with its halves on opposite corners has one long stretch and fails.

    The second is a ratchet, and is labelled as one: `ethernet.coupled_fraction`
    is set just under what this placement achieves and is what catches a
    regression. It is not derived from anything, and it is the only bound on
    this quantity that is tight.
    """
    rise, _ = spec("ethernet", "rise_time")          # the fastest, so the worst
    wanted, _ = spec("ethernet", "coupled_fraction")

    loose = []
    for pair in ("ETH_TD", "ETH_RD"):
        tracks = pairs.tracks_of(pcb_text, (f"{pair}_P", f"{pair}_N"))
        assert set(tracks) == {f"{pair}_P", f"{pair}_N"}, f"{pair} is not both halves"
        width = pairs.controlled_width(tracks)
        for net, partner in ((f"{pair}_P", f"{pair}_N"), (f"{pair}_N", f"{pair}_P")):
            coupled, total, alone = pairs.coupled_length(
                tracks[net], tracks[partner], width, SEPARATION_IN_HEIGHTS * stack.height)
            edge = rise / pairs.delay_per_mm(stack, width)
            # Reported, not asserted - see the docstring. The round trip of
            # the longest uncoupled stretch against the edge is what would
            # decide it, if anything that fits on this board could get near
            # the limit. Nothing can: it wants 24.3 mm running alone and
            # three of the four halves are shorter than that in total.
            print(f"    {net}: {alone:.2f} mm alone of {total:.2f}, round trip "
                  f"{2 * alone / edge * 100:.1f}% of a {rise * 1e9:g} ns edge")
            if coupled / total < wanted:
                loose.append(
                    f"  {net}: only {coupled / total * 100:.1f}% of its "
                    f"{total:.2f} mm runs beside its partner, against "
                    f"{wanted * 100:g}% this placement achieves"
                )
    assert not loose, "Pairs that are not pairs for enough of their length:\n" + "\n".join(loose)


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


def test_the_rmii_bus_arrives_with_its_own_clock(spec, stack, lengths, pcb_text, design):
    """
    Nine single-ended signals at 50 MHz, and how far each lands from the clock
    that samples it.

    **This block had twenty-one checks and none of them was about the RMII.**
    The two differential pairs to the jack are checked for impedance, for
    coupling, for skew, for what runs beside them and for what plane returns
    them. The bus that feeds those pairs - REF_CLK, RXD[1:0], CRS_DV,
    TXD[1:0], TX_EN, MDC, MDIO - was checked for being wired to the right
    pins and for nothing else, and it is the only 50 MHz bus on the board.

    What is asserted is the copper's share of the timing and not the timing:
    closing the real budget needs the MCU's own RMII output delay and setup
    window, and the pages of ST's datasheet vendored here do not state them.
    The board's copper contributes skew between a data line and the clock
    edge that latches it, and that share is what the board controls.

    `ethernet.rmii_skew_share` is a **ratchet**, in the same sense as
    `ethernet.coupled_fraction`: this placement achieves 0.31 % of a clock
    period and the bound is half a per cent, so a change that lets one of the
    nine wander has to be argued for rather than discovered on a bench.

    The datasheet's own figures are declared and printed beside it, so the
    margin the copper is eating into is visible even though this does not
    spend it: at 20 ns of period, the PHY's data is valid from 7.0 ns after
    one edge until 3.0 ns after the next, and it wants 7.5 ns of setup and
    2.0 of hold on what the MCU sends back. Two nanoseconds of hold is the
    smallest of those and the one skew subtracts from directly.
    """
    phy = next((address for address, part in design["parts"].items()
                if part["symbol"].startswith("Interface_Ethernet:")), None)
    assert phy, "no Ethernet PHY on this board, and this check is about its bus"

    _, period = spec(phy, "rmii_clock_period")
    _, share = spec("ethernet", "rmii_skew_share")
    hold, _ = spec(phy, "rmii_hold_min")
    valid, _ = spec(phy, "rmii_output_valid_max")
    setup, _ = spec(phy, "rmii_setup_min")

    # **Two paths, two windows, and they are checked separately.** This took
    # the smaller of the two and held everything to it, which made the receive
    # window dead: the transmit one is always tighter, so the receive figures
    # were read, put in a message and compared against nothing. The board's
    # own mutation tester found that, which is the exact failure
    # `tools/mutate.py` exists to catch, committed the same day.
    #
    # `toinvld` came out of `parts.py` entirely for the same reason: it only
    # widens the receive window and this board is two hundred times inside it,
    # so no value of it decides anything. The window below is a period less
    # `toval` alone, which is the conservative reading of the same table.
    #
    # They are different paths. The PHY drives RXD and CRS_DV and the MCU
    # samples them; the MCU drives TXD and TX_EN and the PHY samples those.
    # Each has its own skew and its own window, so each is held to its own.
    #
    # Neither is this board's whole budget - the MCU's share is missing from
    # both, because ST does not state it in the pages vendored here - but skew
    # larger than a window is not a tight budget, it is a bus that cannot work.
    paths = {
        "receive": (["ETH_RXD0", "ETH_RXD1", "ETH_CRS_DV"],
                    period - valid,
                    "a period less the toval the PHY takes to drive RXD"),
        "transmit": (["ETH_TXD0", "ETH_TXD1", "ETH_TX_EN"],
                     period - setup - hold,
                     "what a period leaves once the PHY's own setup and hold "
                     "are taken out of it"),
    }

    clock = "ETH_REF_CLK"
    assert clock in lengths, f"{clock} has no copper"
    # MDC and MDIO are left out on purpose: the management interface is its
    # own clock at 2.5 MHz and is not sampled against this one.
    missing = [net for nets, _, _ in paths.values() for net in nets
               if net not in lengths]
    assert not missing, f"no copper on {missing}"

    width = pairs.controlled_width(pairs.tracks_of(pcb_text, (clock,)))
    per_mm = pairs.delay_per_mm(stack, width)

    overall_net, overall = None, 0.0
    for direction, (nets, window, why) in sorted(paths.items()):
        net = max(nets, key=lambda n: abs(lengths[n] - lengths[clock]))
        gap = abs(lengths[net] - lengths[clock])
        skew = gap * per_mm
        if skew > overall:
            overall_net, overall = net, skew

        print(f"    RMII {direction}: {net} is {gap:.1f} mm from {clock}, "
              f"{skew * 1e12:.0f} ps, {skew / period:.3%} of a "
              f"{period * 1e9:g} ns period; its window is {window * 1e9:.1f} ns")

        # The physical bound, per path, because it is the one that is not a
        # judgement: whatever the MCU adds, the copper alone cannot be allowed
        # to eat a window the datasheet states.
        assert skew < window, (
            f"{net} is {skew * 1e12:.0f} ps from {clock} and the {direction} "
            f"window is {window * 1e9:.1f} ns - {why}. The MCU's own share is "
            f"on top of this and is not stated in the pages vendored here, so "
            f"a bus this skewed does not have a tight budget, it has none."
        )

    # And the ratchet, on the worst of the two.
    assert overall <= share * period, (
        f"{overall_net} is {abs(lengths[overall_net] - lengths[clock]):.1f} mm "
        f"from {clock}, which is {overall * 1e12:.0f} ps - "
        f"{overall / period:.2%} of a {period * 1e9:g} ns clock period, over "
        f"the {share:.1%} this board holds itself to. The bound is a ratchet "
        f"on the placement and not a timing budget; the timing it eats into "
        f"is {hold * 1e9:g} ns of hold at the PHY, the smallest number in "
        f"Table 5.12."
    )


def test_the_centre_taps_sit_where_the_transmitter_can_use_them(
    spec, pads_of, design, pcb_text
):
    """
    Both transformer centre taps on a rail the magnetics are specified for,
    each with its own bypass.

    The line driver is current-mode: it pulls current *out* of the winding, and
    the centre tap is where that current comes from. Taps on ground, which is
    what a voltage-mode PHY wants, give a transmitter with nothing to drive
    against and a link that never comes up.

    Each tap needs a capacitor between that rail and ground close to it,
    because the transmit current comes out of the rail at the tap and has to
    get back to ground somewhere near, and every millimetre of that loop is
    common-mode current in the plane.

    **"Its own" used to mean a name.** The check counted parts called
    `eth.tap_bypass*` on the rail, so two capacitors at the far corner of the
    board satisfied it and renaming any other decoupling capacitor satisfied
    it too. Each tap is now matched to a *distinct* capacitor by distance on
    the placed board, and any rail-to-ground capacitor counts - because on
    this board the taps sit on the 3V3 plane, and a plane does not care which
    capacitor is called what.

    **The sentence that used to end this paragraph was wrong.** It said "the
    two dedicated parts are the nearest two". They are not: measured on the
    placed board, `eth.tap_bypass1` is 7.72 mm from tap 4 and 10.18 mm from
    tap 5, `eth.tap_bypass2` is 9.99 and 12.26 - and what actually serves
    tap 5 is `stitch.12`, a plane-stitching capacitor 8.72 mm away on the far
    side of the jack. That is electrically fine, and it is exactly what the
    paragraph above argues: same rail, same plane pair, same return. But it
    means the check was passing on a part nobody placed for the job while the
    parts that were placed for it would have failed the bound - so the
    sentence is corrected rather than the board.

    **The bound is the jack's own pad field**, not a typed 10.0. The argument
    the old constant carried in its message - "the jack is 22 mm deep and
    everything closer than that is inside its outline" - is the right one and
    was not what the number said.

    **And it is weak. On this board it cannot currently fail**, which is worth
    stating rather than dressing up. Fifty-three capacitors tie 3V3 to ground
    here and the bound is the jack's 20.7 mm span, so something always
    qualifies: moving both dedicated bypasses to the far corner of the board,
    and even moving the jack itself, leaves this passing. What still has teeth
    is the matching - two distinct capacitors, so one cannot serve both taps -
    and the rail and voltage assertions above it.

    Getting the dedicated parts nearer was tried and the board refuses: every
    position within 6 mm of the taps is inside the jack's keepout or in the
    band the RMII's west climb and the four line terminations already fill,
    and the placer reports no room for their plane vias. So 7.7 mm is what
    this geometry allows, the stitch ring covers the rest, and the thing that
    would actually settle it - the return loop's inductance - is measured by
    nothing on this board.
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

    placement, tap_at = {}, {}
    for block in pcb_text.split("\n\t(footprint ")[1:]:
        address = re.search(r'\(property "address" "([^"]+)"', block)
        at = re.search(r"\n\t\t\(at ([-\d.]+) ([-\d.]+)(?: ([-\d.]+))?\)", block)
        if not (address and at):
            continue
        ox, oy = float(at.group(1)), float(at.group(2))
        angle = math.radians(float(at.group(3) or 0))
        placement[address.group(1)] = (ox, oy)
        if address.group(1) != JACK:
            continue
        for m in re.finditer(r'\(pad "([^"]+)"[^\n]*\n\s*\(at ([-\d.]+) ([-\d.]+)', block):
            px, py = float(m.group(2)), float(m.group(3))
            tap_at[m.group(1)] = (ox + px * math.cos(angle) + py * math.sin(angle),
                                  oy - px * math.sin(angle) + py * math.cos(angle))

    candidates = [
        address for address, part in design["parts"].items()
        if part["symbol"] == "Device:C"
        and {rail, GROUND} <= set(pads_of[address].values())
        and address in placement
    ]
    assert len(candidates) >= 2, (
        f"{len(candidates)} capacitors tie {rail} to ground near the jack"
    )

    # The jack's own pad field is the distance: a bypass further from a tap
    # than the connector is wide is not at the connector.
    span = [tap_at[pad] for pad in tap_at]
    reach = max(math.dist(a, b) for a in span for b in span)
    assert reach > 0, "the jack's pads are all at one point"

    # A *complete* matching, not a greedy walk. The greedy version asserted
    # `len(taken) == 2` afterwards, which could not fail: two picks from a
    # set that excludes what is already taken are always distinct. What can
    # fail, and is the thing meant, is that both taps are served at once -
    # so both assignments are tried and the better one has to fit.
    pads = sorted(taps)
    best, how = None, None
    for first in candidates:
        for second in candidates:
            if first == second:
                continue
            worst = max(math.dist(tap_at[pads[0]], placement[first]),
                        math.dist(tap_at[pads[1]], placement[second]))
            if best is None or worst < best:
                best, how = worst, (first, second)
    assert best is not None, "fewer than two distinct capacitors to match"
    assert best <= reach, (
        f"the further centre tap is {best:.1f} mm from its own bypass "
        f"({how[0]} and {how[1]}), and the jack's pads span {reach:.1f} mm - "
        f"so it is further from a bypass than the connector is wide"
    )


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
    # A grid across the whole keepout, not its centre. The centre alone is one
    # sample where the defect is an area: a pour covering nine tenths of the
    # cable end and stopping just short of the middle answered correctly, and
    # so did one shaped like a ring. The step is a millimetre, which is finer
    # than any pour feature this board can produce - `min_thickness` on every
    # zone is 0.25 mm, but a notch narrower than a millimetre in a plane is
    # not something the generator can draw.
    step = 1.0
    samples = [
        (x, y)
        for i in range(int((x1 - x0) / step) + 1)
        for j in range(int((y1 - y0) / step) + 1)
        for x, y in [(min(x0 + i * step, x1), min(y0 + j * step, y1))]
    ]

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
        inside = [point for point in samples if _inside(points, point)]
        if inside:
            covered.append(
                f"  {net.group(1) if net else '?'}: {len(inside)} of "
                f"{len(samples)} sample points, first at "
                f"({inside[0][0]:g}, {inside[0][1]:g})"
            )
    assert not covered, (
        "Pours reaching under the jack's cable end:\n" + "\n".join(sorted(covered))
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


# HanRun's HR911105A datasheet, REV. A/2, page 1: the schematic inside the
# jack, and the note beneath it. parts/RJ45HR/evidence/ holds the figure.
JACK_PINS = {
    "1": "ETH_TD_P",   # TD+
    "2": "ETH_TD_N",   # TD-
    "3": "ETH_RD_P",   # RD+
    "6": "ETH_RD_N",   # RD-
    "8": "GND",        # CHS GND - "Connect CHS GND to PCB Ground"
}


def test_the_ethernet_jack_is_wired_the_way_hanrun_draws_it(design, pad_net):
    """
    Every pin of the RJ45 carries what HanRun's internal schematic says it does.

    This part's review note used to list three things nobody could check,
    because the datasheet could not be fetched. It can, and pin 8 is CHS GND
    with an instruction under the drawing to tie it to PCB ground - which is
    what the board had already assumed, on the reasoning that tying an unknown
    jack pin to ground is safe. That reasoning is not a check.

    Pins 4 and 5 are the centre taps and are held only to being the same net as
    each other: what that net should be is the PHY's business, not the jack's.
    Pin 7 is NC, and is checked by staying that way.
    """
    wrong = [f"  pin {pin}: on {pad_net.get(('eth.jack', pin))!r}, "
             f"HanRun's schematic says {expected!r}"
             for pin, expected in sorted(JACK_PINS.items())
             if pad_net.get(("eth.jack", pin)) != expected]

    taps = {pad_net.get(("eth.jack", pin)) for pin in ("4", "5")}
    if len(taps) != 1 or None in taps:
        wrong.append(f"  pins 4 and 5 are the centre taps and are on {taps}")
    if pad_net.get(("eth.jack", "7")) is not None:
        wrong.append("  pin 7 is NC in HanRun's schematic, and is connected here")

    assert not wrong, (
        "Ethernet jack pins:\n" + "\n".join(wrong)
        + "\nSee parts/RJ45HR/evidence/schematic.png."
    )


def test_the_line_terminations_stay_inside_their_rating(design, pad_net, spec):
    """
    Each 49.9 ohm against the swing the PHY's own datasheet specifies.

    The generic resistor rule puts the whole rail across anything with one pad
    on it, which for these would be 3.465 V and 243 mW on a 62.5 mW part. That
    is not what happens: the PHY biases each line *to* that rail through the
    transformer winding, so what appears across the termination is the
    transmit swing - Table 5.8's 1050 mV peak - and not the rail.

    So the check is the same arithmetic against the right voltage, and the
    voltage is the one the part states rather than one chosen to make the
    answer come out.
    """
    swing, _ = spec(PHY, "transmit_amplitude_max")
    lines = {net for net, nodes in design["nets"].items()
             for address, pad in nodes
             if address == PHY and pad in ("20", "21", "22", "23")}

    hot = []
    for address, part in sorted(design["parts"].items()):
        if part["symbol"] != "Device:R":
            continue
        nets = {pad_net.get((address, pad)) for pad in ("1", "2")}
        if not nets & lines:
            continue
        resistance, _ = spec(address, "resistance")
        rated, _ = spec(address, "max_power")
        power = swing**2 / resistance
        if power > rated * 0.5:
            hot.append(f"  {address}: {power * 1e3:.0f} mW at a {swing:g} V swing, "
                       f"rated {rated * 1e3:g} mW")
    assert hot == [], "Line terminations past half their rating:\n" + "\n".join(hot)


def test_the_phy_is_held_in_reset_long_enough_after_power_up(design, pad_net, spec):
    """
    The RC on nRST keeps the PHY in reset for the 25 ms its datasheet asks for.

    Section 3.8.6.1 requires a hardware reset after power-up and Table 5.11
    puts a 25 ms minimum on it, from the supplies being at level to nRST being
    released. A pull-up on its own releases in microseconds - 10 k into the
    pin's 2 pF - so the reset would be over before it began, and the straps
    that decide REF_CLK direction and the PHY address are latched on that
    edge. A PHY that latches the wrong mode comes up silent with every voltage
    on the board correct.

    Everything is derived: the two resistors and the capacitor are found by
    walking out from the reset net, the capacitor is taken at the low end of
    its own tolerance, and the threshold and the 25 ms come from the part.
    """
    wanted, _ = spec(PHY, "reset_release_delay_min")
    threshold, _ = spec(PHY, "reset_input_high")
    _, rail = spec("rail.3v3", "voltage")

    reset = next(net for net, nodes in design["nets"].items()
                 if (PHY, "15") in {tuple(n) for n in nodes})

    def through(net, symbol):
        for address, part in design["parts"].items():
            if part["symbol"] != symbol:
                continue
            a, b = pad_net.get((address, "1")), pad_net.get((address, "2"))
            if a == net and b:
                yield address, b
            elif b == net and a:
                yield address, a

    pull_up = [a for a, far in through(reset, "Device:R") if far == "3V3"]
    delaying = [(a, far) for a, far in through(reset, "Device:R") if far != "3V3"]
    assert len(pull_up) == 1 and len(delaying) == 1, (
        f"expected one pull-up and one delay resistor on {reset}, found "
        f"{pull_up} and {delaying}"
    )
    series, node = delaying[0]
    holding = [a for a, far in through(node, "Device:C") if far == "GND"]
    assert len(holding) == 1, f"expected one capacitor from {node} to ground, found {holding}"

    resistance = spec(pull_up[0], "resistance")[0] + spec(series, "resistance")[0]
    capacitance = spec(holding[0], "capacitance")[0]
    delay = resistance * capacitance * math.log(rail / (rail - threshold))
    assert delay >= wanted, (
        f"{resistance / 1e3:g} k into {capacitance * 1e6:g} uF releases nRST "
        f"after {delay * 1e3:.0f} ms, and the part asks for {wanted * 1e3:g} ms"
    )
