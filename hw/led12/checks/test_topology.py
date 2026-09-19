"""
Checks on what is wired to what.

The electrical checks compute currents and margins from part values, but they
assume a shape: that the fuse is actually in series with the input, that each
LED actually has its own resistor, that the rail feeding the gate divider is
the same rail the regulator sees. Those assumptions are what these verify.

Everything is read from the generated board, in terms of source addresses like
`power.fuse` rather than designators, which shift whenever a part is added.
"""

RAILS_NEEDING_TEST_POINTS = ["12V", "3V3", "GND", "GATE"]


def test_every_led_has_its_own_series_resistor(net_parts):
    """
    One resistor per LED, not one shared between them.

    LEDs in parallel on a single resistor divide current by forward voltage,
    which varies part to part: the dimmest gets almost nothing and the
    brightest takes most of it.
    """
    problems = []
    for i in range(4):
        anode_nets = [
            net
            for net, parts in net_parts.items()
            if f"leds[{i}].resistor" in parts and f"leds[{i}].led" in parts
        ]
        if len(anode_nets) != 1:
            problems.append(
                f"  leds[{i}]: resistor and LED share {len(anode_nets)} nets, expected 1"
            )
            continue
        members = net_parts[anode_nets[0]]
        if len(members) != 2:
            problems.append(
                f"  leds[{i}]: junction {anode_nets[0]} also touches "
                f"{sorted(members - {f'leds[{i}].resistor', f'leds[{i}].led'})}"
            )
    assert not problems, "LED branches not independent:\n" + "\n".join(problems)


def test_every_rail_has_a_test_point(net_parts):
    """A rail nobody can probe cannot be diagnosed on the bench."""
    missing = [
        rail
        for rail in RAILS_NEEDING_TEST_POINTS
        if not any(part.startswith("tp_") for part in net_parts.get(rail, set()))
    ]
    assert not missing, (
        f"Rails with no test point: {missing}. "
        f"Nets present: {sorted(net_parts)}"
    )


def test_fuse_is_first_in_the_input_path(net_parts):
    """
    Nothing sits between the screw terminal and the fuse.

    A fuse with anything upstream of it protects only what is downstream, and
    the part that was accidentally placed ahead of it is the one that burns.
    """
    upstream = net_parts.get("VIN_RAW", set())
    assert upstream == {"power.terminal", "power.fuse"}, (
        "The input net between the terminal and the fuse should touch only "
        f"those two, but touches: {sorted(upstream)}"
    )


def test_nothing_bypasses_the_reverse_polarity_fet(net_parts):
    """
    The only thing after the fuse is the FET.

    Anything else on that net sees the supply the wrong way round when the
    terminal is wired backwards, which is the whole point of the FET.
    """
    between = net_parts.get("VIN_FUSED", set())
    assert between == {"power.fuse", "power.q_rpp"}, (
        "The net between the fuse and the reverse-polarity FET should touch "
        f"only those two, but touches: {sorted(between)}"
    )


def test_protected_rail_feeds_everything_it_should(net_parts):
    """
    One 12 V net, reaching every consumer.

    The electrical checks read the rail's voltage from `power.out` and apply it
    to the gate divider, the regulator and the LED branches. That is only valid
    if they are all genuinely on the same net.

    The reverse-polarity FET's gate resistor is deliberately absent: it runs
    from that FET's gate to ground, not from the rail.
    """
    rail = net_parts.get("12V", set())
    expected = {
        "power.q_rpp",
        "power.tvs",
        "power.c_bulk",
        "power.c_hf",
        "rail.ldo",
        "rail.c_in",
        "switch.button",
        "tp_12v",
        "power.d_gate_clamp",
    } | {f"leds[{i}].resistor" for i in range(4)}

    missing = expected - rail
    unexpected = rail - expected
    assert not missing and not unexpected, (
        "The 12 V rail is not what the electrical checks assume.\n"
        f"  missing: {sorted(missing)}\n"
        f"  unexpected: {sorted(unexpected)}"
    )


def test_led_returns_go_through_the_switch(net_parts):
    """Every LED cathode reaches the low-side FET, and nothing else does."""
    ret = net_parts.get("LED_RETURN", set())
    expected = {"switch.q_switch"} | {f"leds[{i}].led" for i in range(4)}
    assert ret == expected, (
        f"LED return net is {sorted(ret)}, expected {sorted(expected)}"
    )


# (address, pad, the net that pad must be on). Taken from each part's review
# note, which records which pad number the datasheet calls what.
POLARITY = [
    ("power.tvs", "1", "12V"),       # cathode, to the rail it protects
    ("power.tvs", "2", "GND"),       # anode
    ("power.q_rpp", "1", "RPP_GATE"),
    # A P-MOSFET's body diode has its ANODE on the drain, so for reverse
    # polarity protection the drain faces the supply and the source faces the
    # load. Wired the other way round the part still switches perfectly and
    # the body diode conducts when the input is reversed, which is the entire
    # failure this device exists to prevent. This table said the other way
    # round for the whole life of the board, so correcting the design turned
    # this check red rather than green — which is what a hand-written expected
    # value buys you.
    ("power.q_rpp", "2", "12V"),        # source, on the protected side
    ("power.q_rpp", "3", "VIN_FUSED"),  # drain, on the supply side
    # Both gate clamps used to be four rows here. They are
    # test_every_gate_clamp_faces_the_way_its_fet_needs now, which reads the
    # channel out of the FET's symbol and the cathode out of the Zener's, and
    # so holds on a board this file was not written for.
    ("switch.q_switch", "1", "GATE"),
    ("switch.q_switch", "2", "GND"),       # source
    ("switch.q_switch", "3", "LED_RETURN"),  # drain
    ("rail.ldo", "1", "GND"),
    ("rail.ldo", "2", "3V3"),   # output, and the tab
    ("rail.ldo", "3", "12V"),   # input
] + [(f"leds[{i}].led", "1", "LED_RETURN") for i in range(4)]


def test_polarised_parts_face_the_right_way(net_members):
    """
    Every polarised part has the net the datasheet expects on each pin.

    This is the check that catches a diode fitted backwards. atopile's `~>`
    bridges a diode anode to cathode, so writing `rail.hv ~> tvs ~> rail.lv`
    reads naturally and puts the protection device across the rail the wrong
    way round, where it conducts at 0.7 V and shorts the supply. The build is
    perfectly happy with it and so is every check that only asks which parts
    are on a net rather than which pin.
    """
    actual = {
        (address, pad): net
        for net, members in net_members.items()
        for address, pad in members
    }
    wrong = []
    for address, pad, expected in POLARITY:
        found = actual.get((address, pad))
        if found != expected:
            wrong.append(f"  {address} pad {pad}: on {found!r}, expected {expected!r}")

    assert not wrong, "Parts wired the wrong way round:\n" + "\n".join(wrong)
