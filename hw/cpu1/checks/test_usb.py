"""
USB-C: a device port that senses power and never takes any.

The electrical questions here are about a connector a person can plug anything
into, so most of these ask what happens when they do. The geometric ones are
about the board's one differential pair, and they are answered from the copper
rather than from the numbers the layout was written with - a pair drawn to the
wrong width is exactly the case where those two disagree.

Datasheets: ST's *USBLC6-2*, Doc ID 11265 Rev 5 (October 2011), and the
STM32H743xI pin table for what a `FT_u` pin may see.
"""

import sys
from pathlib import Path

import pytest

# pytest imports these files by path, so the directory they share is not on
# sys.path and the helper beside them has to be found deliberately.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import pairs  # noqa: E402

MCU = "mcu"
CONNECTOR = "usb.receptacle"
PROTECTION = "usb.protection"
GROUND = "GND"

# The spacing the pair is drawn at, which the layout also works from.
USB_GAP = 0.2

# Which declared rail each supply net is, as elsewhere on this board.
RAILS = {"5V": "rail.5v", "3V3": "rail.3v3"}


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

    return {
        address: symbol_pin_names(part["symbol"])
        for address, part in design["parts"].items()
    }


@pytest.fixture(scope="module")
def pair_tracks(pcb_text):
    """The pair's segments, read out of the board file. See checks/pairs.py."""
    return pairs.tracks_of(pcb_text, ("USB_DP", "USB_DM"))


# --- what the port is allowed to do to the board -----------------------------


def test_vbus_is_sensed_and_goes_nowhere_else(design, pad_net, pads_of, pin_names):
    """
    VBUS reaches the sense pin, the protection device, and nothing further.

    This board is powered from its terminal or from the daughter-board header,
    beside a supply that may be at 36 V. A host that finds itself sourcing any
    of that is a host that stops being a host. There is no diode here and no
    regulator: the only defence is that the net does not go anywhere, and the
    only way to keep that true is to check it.
    """
    vbus = pad_net[(CONNECTOR, "A4")]
    reached = sorted({address for address, pad in design["nets"][vbus]})
    assert reached == sorted({CONNECTOR, PROTECTION, MCU}), (
        f"{vbus} reaches {reached}; it may only reach the connector, the "
        "protection device and the pin that senses it"
    )
    assert vbus not in RAILS, f"{vbus} is a declared rail, so USB is a power input"


def test_the_sense_pin_can_take_the_bus_voltage(spec, pad_net, design):
    """
    What the pin may see, worked out the way its datasheet states it.

    ST does not give a number for a five-volt-tolerant pin: it gives a headroom
    above the *lowest* of the part's supplies. So this reads the board's own
    rails and adds the headroom, rather than assuming the 3.3 V that makes the
    sum come out comfortable. A board whose logic rail was lowered would fail
    here, which is the point.
    """
    overhead, _ = spec(MCU, "ft_input_overhead")
    supplies = sorted({
        net for (address, _), net in pad_net.items()
        if address == MCU and net in RAILS
    })
    assert supplies, "the MCU has no pin on a declared rail"
    lowest = min(spec(RAILS[net], "voltage")[0] for net in supplies)
    _, bus = spec("usb", "vbus_voltage")
    assert bus <= lowest + overhead, (
        f"VBUS reaches {bus} V and the pin allows {lowest} + {overhead} = "
        f"{lowest + overhead} V"
    )


def test_both_cc_pins_have_their_own_pull_down(spec, design, pad_net, pads_of, pin_names):
    """
    Two resistors, one per CC pin, each to ground and each the value the
    specification names.

    A Type-C plug can go in either way up, and which CC pin the source sees
    depends on which way it went. One resistor shared between them works
    perfectly in one orientation and not at all in the other - which is the
    exact failure a reversible connector exists to prevent, reintroduced by
    saving a component.
    """
    low, high = spec("usb", "cc_pulldown")
    seen = {}
    for pad, name in sorted(pin_names[CONNECTOR].items()):
        if not name.startswith("CC"):
            continue
        net = pad_net.get((CONNECTOR, pad))
        owners = [
            address for address, other in design["nets"].get(net, [])
            if address != CONNECTOR
        ]
        assert len(owners) == 1, f"{name} reaches {owners}, not one resistor"
        resistor = owners[0]
        assert resistor not in seen.values(), (
            f"{name} and {[k for k, v in seen.items() if v == resistor][0]} "
            f"share {resistor}, so the port works in one plug orientation only"
        )
        seen[name] = resistor
        assert GROUND in pads_of[resistor].values(), f"{resistor} is not pulled to ground"
        value = spec(resistor, "resistance")
        assert low <= value[0] and value[1] <= high, (
            f"{name}'s pull-down is {value[0]} to {value[1]} ohm, outside "
            f"{low:g} to {high:g}"
        )
    assert len(seen) == 2, f"{len(seen)} CC pins found, expected two"


# --- the protection ----------------------------------------------------------


def test_nothing_reaches_the_board_without_passing_the_protection(
    design, pad_net, pads_of, pin_names, spec_has
):
    """
    Every signal on the connector meets the array before it meets anything else.

    An ESD array downstream of the thing it protects is decoration. Checked by
    asking whether the connector and the MCU ever share a net: on the pair they
    must not, because the array is in series and the two sides of it are
    different nets. On VBUS they do, which is why that one is checked above
    instead - the array clamps it rather than passing it through.
    """
    connector = set(pads_of[CONNECTOR].values()) - {GROUND, None}
    mcu = {net for (address, _), net in pad_net.items() if address == MCU}
    protection = set(pads_of[PROTECTION].values())

    shared = sorted(connector & mcu)
    assert shared == [pad_net[(CONNECTOR, "A4")]], (
        f"the connector and the MCU share {shared}; only VBUS may be common, "
        "and every other signal has to pass through the array"
    )
    # A signal may skip the array only if there is nothing on it to protect.
    # The CC pins are the case: they reach two resistors and ground and no
    # silicon at all, so a strike arriving on one finds 5.1 kohm and a plane.
    # Derived rather than named, so a CC pin later wired to a GPIO - which is
    # how a board gets orientation detection - stops being exempt.
    exposed = []
    for net in sorted(connector - protection):
        for address, _ in design["nets"][net]:
            if address in (CONNECTOR, PROTECTION):
                continue
            if not spec_has(address, "resistance"):
                exposed.append(f"  {net} reaches {address}, which is not a resistor")
            elif GROUND not in pads_of[address].values():
                exposed.append(f"  {net} reaches {address}, which does not end at ground")
    assert not exposed, (
        "Connector signals that skip the array and reach something that minds:\n"
        + "\n".join(exposed)
    )


def test_the_array_ignores_the_bus_until_something_goes_wrong(spec):
    """
    The protection stands off the highest voltage the bus may legitimately carry
    and does not break down until above it.

    A clamp that conducts at the working voltage is a short with a datasheet.
    The margin is small on purpose - a 5.25 V stand-off against a 5.25 V bus -
    because the whole value of the part is that it starts conducting soon after
    the bus stops being a bus.
    """
    _, bus = spec("usb", "vbus_voltage")
    standoff, _ = spec(PROTECTION, "standoff_voltage")
    breakdown, _ = spec(PROTECTION, "breakdown_voltage_min")
    assert bus <= standoff, (
        f"the bus reaches {bus} V and the array leaks above {standoff} V"
    )
    assert standoff < breakdown, (
        f"the array's {breakdown} V breakdown is not above its own "
        f"{standoff} V stand-off"
    )


def test_the_protection_costs_little_of_the_edge(spec):
    """
    What the array's capacitance does to a full-speed edge.

    Every ESD device on a signal line is a capacitor the driver has to charge.
    The question is not whether it slows the edge - it does - but whether it
    slows it enough to matter, against the source impedance the specification
    says the driver has and the fastest edge it says the driver may produce.
    """
    _, source = spec("usb", "driver_impedance")
    edge, _ = spec("usb", "rise_time")
    _, allowed = spec("usb", "protection_edge_share")
    line, _ = spec(PROTECTION, "line_capacitance_max")
    pair, _ = spec(PROTECTION, "pair_capacitance_max")

    constant = source * (line + pair)
    assert constant <= allowed * edge, (
        f"{constant * 1e12:.0f} ps of charging against a {edge * 1e9:g} ns "
        f"edge is {constant / edge:.0%}, over the {allowed:.0%} allowed"
    )


def test_the_connector_outlasts_what_a_source_may_put_on_it(spec):
    """
    The receptacle is rated for more than the bus it carries.

    A Type-C source can be persuaded to deliver 20 V, and the thing that stops
    this one being asked is a pair of 5.1 kohm resistors telling it the board
    is an ordinary sink. That is a resistor's worth of assurance, so the
    connector had better be built for what a source could do anyway.
    """
    _, bus = spec("usb", "vbus_voltage")
    rating, _ = spec(CONNECTOR, "voltage_rating")
    assert bus <= rating, (
        f"the bus may reach {bus} V and the receptacle is rated to {rating} V"
    )


def test_the_protection_meets_the_strike_the_port_will_see(spec):
    """
    What the array survives, against what the port is expected to survive.

    A connector on the outside of a machine gets touched by people who have
    walked across a floor. IEC 61000-4-2 level 4 is the usual expectation for
    industrial equipment, and the part has to be at least that before the
    rest of the board's protection story means anything.
    """
    required, _ = spec("usb", "esd_level")
    rated, _ = spec(PROTECTION, "esd_contact_discharge")
    assert rated >= required, (
        f"the array is rated to {rated / 1e3:g} kV by contact and the port is "
        f"expected to take {required / 1e3:g} kV"
    )


# --- the pair ----------------------------------------------------------------


def test_the_pair_is_drawn_for_the_impedance_it_has_to_present(spec, stack, pair_tracks):
    """
    The width and separation actually on the board, put back through the
    stackup.

    The layout computes the width from the same formulas, so this could agree
    with it by construction and prove nothing. It does not: the width and the
    gap here are measured off the segments in the board file, and the gap is
    measured between the two nets rather than taken from either of them. A pair
    drawn at one width and spaced for another fails here.
    """
    import sys

    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2] / "tools"))
    from layout_lib import differential_impedance

    low, high = spec("usb", "differential_impedance")
    assert set(pair_tracks) == {"USB_DP", "USB_DM"}, (
        f"the pair is {sorted(pair_tracks)}, not both halves"
    )

    controlled = pairs.controlled_width(pair_tracks)
    runs = {
        net: [seg for seg in segments if round(seg[2], 4) == controlled]
        for net, segments in pair_tracks.items()
    }
    assert all(runs.values()), "one half of the pair has no controlled-width run"

    gap = pairs.separation(runs["USB_DP"], runs["USB_DM"]) - controlled
    impedance = differential_impedance(controlled, gap, stack)
    assert low <= impedance <= high, (
        f"{controlled:g} mm traces {gap:.3f} mm apart over {stack.height:g} mm "
        f"of er {stack.epsilon_r:g} make {impedance:.1f} ohm, outside "
        f"{low:g} to {high:g}"
    )


def test_the_rule_the_fab_is_held_to_is_the_one_the_stackup_asks_for(
    spec, stack, board_dir
):
    """
    The width floor in `rules.kicad_dru`, put through the same formulas.

    DRC enforces a number in a text file; the impedance comes from the
    stackup. Those are two different things that happen to agree today, and
    nothing makes them keep agreeing - a fab changing its prepreg would move
    the impedance and leave the rule saying what it always said. So the rule's
    own figure is read back and required to land in the band.
    """
    import re
    import sys

    sys.path.insert(0, str(board_dir.parent / "tools"))
    from layout_lib import differential_impedance

    text = (board_dir / "rules.kicad_dru").read_text()
    rule = re.search(
        r"\(rule \"usb pair\".*?\(constraint track_width \(min ([\d.]+)mm\)\)",
        text, re.S,
    )
    assert rule, "rules.kicad_dru has no usb pair rule to check"
    low, high = spec("usb", "differential_impedance")
    floor = float(rule.group(1))
    # At the pair's spacing, the narrowest trace the rule would accept.
    impedance = differential_impedance(floor, USB_GAP, stack)
    assert low <= impedance <= high, (
        f"the rule admits {floor:g} mm traces, which at {USB_GAP:g} mm apart "
        f"make {impedance:.1f} ohm, outside {low:g} to {high:g}"
    )


def test_the_pair_arrives_together(spec, stack, lengths, pair_tracks):
    """
    How far apart the two halves are in time, from the copper each of them got.

    Length becomes delay through the effective permittivity a microstrip sees,
    which is neither the laminate's nor air's but between them, because half
    the field is in each. At full speed the timing is irrelevant - a bit is
    eighty nanoseconds - so this is about what mismatch turns into instead:
    common mode, on a cable, leaving the enclosure.
    """
    edge, _ = spec("usb", "rise_time")
    _, allowed = spec("usb", "skew_share")
    width = max(w for segments in pair_tracks.values() for *_, w in segments)
    mismatch = abs(lengths["USB_DP"] - lengths["USB_DM"])
    skew = mismatch * pairs.delay_per_mm(stack, width)
    assert skew <= allowed * edge, (
        f"{mismatch:.2f} mm of mismatch is {skew * 1e12:.0f} ps, "
        f"{skew / edge:.1%} of a {edge * 1e9:g} ns edge, over {allowed:.0%}"
    )


def test_the_pair_runs_over_the_plane_that_returns_it(board_dir, pair_tracks):
    """
    The layer the pair is on is the one next to the ground plane.

    A differential pair's return current runs under it, and it can only do that
    where there is an unbroken plane to run in. On this stackup that is F.Cu,
    with In1.Cu beneath it; the other outer layer faces the supply islands,
    which are neither unbroken nor at the same potential as the return.
    """
    import sys

    sys.path.insert(0, str(board_dir.parent / "tools"))
    from mcu_pins import load_source

    description = load_source(board_dir / "layout.py", "cpu1_layout_plane")
    planes = getattr(description, "PLANES", None) or [description.PLANE]
    ground = [plane for plane in planes if plane["net"] == GROUND]
    assert len(ground) == 1, f"{len(ground)} ground planes; this check assumes one"

    layers = description.BOARD["copper_layers"] if "copper_layers" in description.BOARD else None
    order = ["F.Cu"] + [f"In{n}.Cu" for n in range(1, (layers or 4) - 1)] + ["B.Cu"]
    beside = order[order.index(ground[0]["layer"]) - 1], order[
        min(order.index(ground[0]["layer"]) + 1, len(order) - 1)
    ]
    assert "F.Cu" in beside, (
        f"the ground plane is on {ground[0]['layer']}, which is not next to the "
        f"layer the pair is routed on"
    )
