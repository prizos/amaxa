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

import pytest

PHY = "eth.phy"
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


def test_the_pairs_leave_on_the_pins_the_magnetics_will_meet(design, net_on, board_config):
    """
    Each of the four line pins is on its own net, and each of those is waiting
    for the jack.

    The jack is not on this board yet, so what can be checked is that the four
    nets exist, are distinct, and are declared as waiting rather than quietly
    left half-connected - which is the same net state and a different thing.
    """
    pending = design.get("pending", {})
    nets = {name: net_on(name) for name in ("TXP", "TXN", "RXP", "RXN")}
    assert len(set(nets.values())) == 4, f"the four line pins share nets: {nets}"
    for name, net in sorted(nets.items()):
        assert net in pending, f"{name} is on {net}, which is not declared pending"
        assert len(design["nets"][net]) == 1, (
            f"{net} is pending but has {len(design['nets'][net])} connections"
        )


@pytest.fixture(scope="module")
def pin_map(board_dir):
    import sys

    sys.path.insert(0, str(board_dir.parent / "tools"))
    from mcu_pins import load_source

    return load_source(board_dir / "pinmap.py", "cpu1_pinmap_eth")
