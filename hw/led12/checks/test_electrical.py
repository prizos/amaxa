"""
The electrical checks: claims that relate two quantities.

None of these can live in the design source. SKiDL carries part values but has
no parameter solver at all, and the tool before it had one that silently dropped
every inequality and never propagated arithmetic across two parameters — so an
`assert` there relating a rail voltage to a resistor value would look like a
check and do nothing. See hw/README.md, "Why not atopile".

Every value below is read from the build, never written here. Worst cases are
taken at the corners of each declared range, so a part swap that narrows or
widens a tolerance moves the result without anyone editing this file.
"""

import pytest

# --- design intent ----------------------------------------------------------
# These are the numbers the board is designed to, and the only constants here.
# Everything else is read from what the build produced.

LED_CURRENT_BAND = (3e-3, 8e-3)  # A, per branch, across the whole supply range
POWER_DERATING = 0.5  # fraction of a part's rated power it may reach
GATE_DRIVE_MARGIN = 2.0  # V_gs must be at least this times V_gs(th) max
DEBOUNCE_RISE_BAND = (5e-3, 50e-3)  # s, time constant when the button is pressed
DEBOUNCE_FALL_LIMIT = 250e-3  # s, time constant on release: the LEDs must not linger
FUSE_HEADROOM = 1.5  # trip current over worst-case load

BRANCHES = [f"leds[{i}]" for i in range(4)]


@pytest.fixture(scope="session")
def branch_current(spec):
    """
    Worst-case low and high current through one LED branch, in amps.

    All four branches return through one low-side FET, so the FET's drop
    depends on the total current and each branch depends on that drop:

        I = (V_rail - V_f) / (R + n * R_ds(on))

    which is exact while the branches are identical.
    """
    v_lo, v_hi = spec("power.out", "voltage")
    rds_lo, rds_hi = spec("switch.q_switch", "on_resistance")
    n = len(BRANCHES)

    def current(branch: str) -> tuple[float, float]:
        r_lo, r_hi = spec(f"{branch}.resistor", "resistance")
        vf_lo, vf_hi = spec(f"{branch}.led", "forward_voltage")
        low = (v_lo - vf_hi) / (r_hi + n * rds_hi)
        high = (v_hi - vf_lo) / (r_lo + n * rds_lo)
        return low, high

    return current


def test_led_current_in_band(spec, branch_current):
    """
    Every LED gets a sensible current at every point in the supply range.

    Too little and it is invisible; too much and the LED or the resistor is
    outside its rating. Checked at the corners: lowest supply against the
    highest forward voltage and largest resistor, and the reverse.
    """
    low_bound, high_bound = LED_CURRENT_BAND
    out_of_band = {}
    for branch in BRANCHES:
        low, high = branch_current(branch)
        # The design band is the tighter of the two, but the LED's own rating
        # is the one that is physically binding, so take whichever is lower and
        # let a part swap move it rather than this file.
        led_max, _ = spec(f"{branch}.led", "max_current")
        if low < low_bound or high > min(high_bound, led_max):
            out_of_band[branch] = (low, high)

    assert not out_of_band, "LED branch current outside %.1f-%.1f mA:\n%s" % (
        low_bound * 1e3,
        high_bound * 1e3,
        "\n".join(
            f"  {b}: {lo * 1e3:.2f} to {hi * 1e3:.2f} mA"
            for b, (lo, hi) in out_of_band.items()
        ),
    )


def test_led_resistor_power_margin(spec, branch_current):
    """
    The series resistors keep half their rated power in hand.

    This is the one that catches a 5 V habit applied to a 12 V rail: the LED
    drops about 2 V and the resistor takes the other ten, so its dissipation is
    five times what the same current costs on a 5 V board.
    """
    over = {}
    for branch in BRANCHES:
        _, current_high = branch_current(branch)
        _, r_high = spec(f"{branch}.resistor", "resistance")
        rated, _ = spec(f"{branch}.resistor", "max_power")
        dissipated = current_high**2 * r_high
        if dissipated > rated * POWER_DERATING:
            over[branch] = (dissipated, rated)

    assert not over, "Series resistors over %.0f%% of rated power:\n%s" % (
        POWER_DERATING * 100,
        "\n".join(
            f"  {b}: {p * 1e3:.1f} mW in a {rated * 1e3:.0f} mW part "
            f"({p / rated * 100:.0f}%)"
            for b, (p, rated) in over.items()
        ),
    )


def test_gate_drive_margin(spec):
    """
    The low-side FET is driven properly on, not part-way.

    The gate sits on a divider: the button feeds it through the series resistor
    and the pulldown holds it at ground. A FET biased near its threshold runs in
    its linear region, dissipates far more than expected, and behaves
    differently from part to part.
    """
    v_rail_low, _ = spec("power.out", "voltage")
    _, r_series_high = spec("switch.r_series", "resistance")
    r_down_low, _ = spec("switch.r_pulldown", "resistance")
    _, v_th_max = spec("switch.q_switch", "gate_source_threshold_voltage")

    # Worst case: lowest rail, largest series resistor, smallest pulldown.
    v_gate = v_rail_low * r_down_low / (r_series_high + r_down_low)
    required = v_th_max * GATE_DRIVE_MARGIN

    assert v_gate >= required, (
        f"Gate reaches only {v_gate:.2f} V at the worst corner, against a "
        f"threshold of up to {v_th_max:.2f} V. At least {required:.2f} V is "
        f"needed ({GATE_DRIVE_MARGIN}x threshold)."
    )


def test_debounce_timing(spec):
    """
    The debounce network is slow enough to hide contact bounce and fast enough
    to feel immediate.

    Pressed, the capacitor charges through the series resistor with the
    pulldown in parallel. Released, it discharges through the pulldown alone,
    which is much slower — that is what makes the LEDs fade rather than snap
    off, and it is checked separately.
    """
    r_series_lo, r_series_hi = spec("switch.r_series", "resistance")
    r_down_lo, r_down_hi = spec("switch.r_pulldown", "resistance")
    c_lo, c_hi = spec("switch.c_debounce", "capacitance")

    def parallel(a: float, b: float) -> float:
        return a * b / (a + b)

    rise_low = parallel(r_series_lo, r_down_lo) * c_lo
    rise_high = parallel(r_series_hi, r_down_hi) * c_hi
    band_low, band_high = DEBOUNCE_RISE_BAND

    assert band_low <= rise_low and rise_high <= band_high, (
        f"Press time constant is {rise_low * 1e3:.1f} to {rise_high * 1e3:.1f} ms, "
        f"outside {band_low * 1e3:.0f} to {band_high * 1e3:.0f} ms."
    )

    fall_high = r_down_hi * c_hi
    assert fall_high <= DEBOUNCE_FALL_LIMIT, (
        f"Release time constant is {fall_high * 1e3:.0f} ms, over the "
        f"{DEBOUNCE_FALL_LIMIT * 1e3:.0f} ms limit. The LEDs would linger."
    )


def test_fuse_headroom(spec, branch_current):
    """
    The fuse is well above the current the board actually draws.

    A fuse close to the working current nuisance-blows; this one only has to
    catch a fault.
    """
    worst_load = sum(branch_current(b)[1] for b in BRANCHES)

    # Plus the 3.3 V rail's fixed load, at its own worst corner.
    r_load_low, _ = spec("rail.r_load", "resistance")
    _, v_3v3_high = spec("rail.ldo", "v_out")
    worst_load += v_3v3_high / r_load_low

    trip, _ = spec("power.fuse", "trip_current")
    required = worst_load * FUSE_HEADROOM

    assert trip >= required, (
        f"Fuse trips at {trip * 1e3:.0f} mA but the board can draw "
        f"{worst_load * 1e3:.1f} mA, needing at least {required * 1e3:.1f} mA."
    )


def test_rail_parts_survive_the_tvs_clamp(spec, spec_has, footprints, net_parts):
    """
    Nothing on the protected rail is rated below what the TVS lets through.

    A TVS does not hold the rail at its stand-off voltage; under surge current
    it clamps much higher. If anything downstream is rated below that clamp,
    the protection is decorative: the part it is meant to protect fails first.
    A 12 V stand-off device cannot clamp below about 15 V, so this constrains
    what may sit on the rail.
    """
    clamp, _ = spec("power.tvs", "v_clamp_max")

    # The parameter that carries a part's rail-voltage limit, by kind of part.
    # A part on the rail is covered if it declares any one of these.
    RATINGS = ("max_voltage", "max_drain_source_voltage", "v_in_max")

    # Parts on the rail with no absolute maximum to compare, each with the
    # reason it is not a hole. Anything not named here MUST declare a rating,
    # so a part added to the rail cannot pass by simply describing nothing.
    EXEMPT = {
        "power.tvs": "it is the clamp; its own rating is what everything else is measured against",
        "tp_12v": "a bare copper pad, which has no breakdown voltage to exceed",
        "switch.button": (
            "its 12 V is a contact switching rating, not a dielectric maximum, "
            "and this circuit puts 110 uA through it - five hundred times below "
            "its 50 mA - so there is no arc energy for that rating to bound. "
            "See parts/SW6MM/SW6MM.md"
        ),
        "power.d_gate_clamp": (
            "a 15 V Zener deliberately placed to break down below the clamp; "
            "conducting is its job, and its 500 mW is checked as energy, not voltage"
        ),
    }

    addresses = {
        fp["properties"].get("address"): fp["designator"]
        for fp in footprints
    }
    # Derived from the netlist, not listed here. A hard-coded membership list is
    # a place the design grows past the check in silence: this one named six
    # addresses while the rail actually reached twelve, so a 6.3 V capacitor
    # added to the rail passed every gate.
    on_rail = sorted(net_parts.get("12V", set()))

    weak, unrated = [], []
    for address in on_rail:
        declared = [(p, spec(address, p)[0]) for p in RATINGS if spec_has(address, p)]
        if not declared:
            if address not in EXEMPT:
                unrated.append(f"  {addresses.get(address, '?')} ({address})")
            continue
        for parameter, rating in declared:
            if rating < clamp:
                weak.append(
                    f"  {addresses.get(address, '?')} ({address}): {parameter} "
                    f"{rating:.1f} V < {clamp:.1f} V clamp"
                )

    assert not weak, (
        f"Parts on the 12 V rail rated below the TVS clamping voltage "
        f"of {clamp:.1f} V:\n" + "\n".join(weak)
    )
    assert not unrated, (
        "Parts on the 12 V rail with no voltage rating to check:\n"
        + "\n".join(unrated)
        + f"\nDeclare one of {RATINGS} in parts.py, or add the address to "
        "EXEMPT here with the reason it does not need one. A part that "
        "describes nothing cannot be checked against anything."
    )


def test_tvs_stands_off_the_rail_it_protects(spec):
    """
    The TVS does not conduct at the highest voltage the rail is allowed to be.

    Stand-off voltage is the most it will hold off while still counting as
    non-conducting. Above it the part is into its knee, drawing unspecified
    leakage and heating; and because avalanche breakdown has a positive
    temperature coefficient, a part that merely leaks at room temperature is in
    full conduction when it is cold. A protection device that conducts in
    normal operation is a load, not a protection device.

    Nothing compared these two numbers before. The check is one line and the
    two quantities sat four files apart.
    """
    stand_off, _ = spec("power.tvs", "reverse_working_voltage")
    _, rail_high = spec("power.out", "voltage")

    assert stand_off >= rail_high, (
        f"The TVS stands off {stand_off:.1f} V but the rail is specified up to "
        f"{rail_high:.1f} V, so it conducts in normal operation at high line — "
        "and sooner than that when cold, because its breakdown voltage falls "
        "with temperature. It needs a higher stand-off part."
    )


def test_fet_gates_survive_the_tvs_clamp(spec):
    """
    Neither FET's gate-source voltage exceeds its rating during a surge.

    This is the defect that rejected the Si2301, in the form it takes one layer
    down. The reverse-polarity FET's source rides the clamped rail while its
    gate is held near ground, so V_gs is the clamping voltage unless something
    stops it — which is what the Zener is for. The low-side FET sees the rail
    through its gate divider instead.

    The gate rating was not written down anywhere a check could reach until
    this existed, which is how a board can be rejected for a gate rating once
    and reacquire the same fault later.
    """
    clamp, _ = spec("power.tvs", "v_clamp_max")
    failures = []

    # The P-FET: clamped by the Zener, so its worst case is the Zener's own
    # highest breakdown voltage rather than the rail's clamp.
    _, v_zener_high = spec("power.d_gate_clamp", "zener_voltage")
    rating, _ = spec("power.q_rpp", "max_gate_source_voltage")
    if v_zener_high > rating:
        failures.append(
            f"  power.q_rpp: the gate clamp lets V_gs reach {v_zener_high:.1f} V "
            f"against a {rating:.1f} V rating"
        )

    # The N-FET: its gate hangs on the divider, so it sees a fraction of the
    # clamped rail — and then its own Zener, if that is lower still.
    _, r_series_high = spec("switch.r_series", "resistance")
    _, r_down_high = spec("switch.r_pulldown", "resistance")
    _, v_switch_zener_high = spec("switch.d_gate_clamp", "zener_voltage")
    v_divider = clamp * r_down_high / (r_series_high + r_down_high)
    v_gate = min(v_divider, v_switch_zener_high)
    rating, _ = spec("switch.q_switch", "max_gate_source_voltage")
    if v_gate > rating:
        failures.append(
            f"  switch.q_switch: the divider puts {v_gate:.1f} V on the gate "
            f"during a {clamp:.1f} V clamp, against a {rating:.1f} V rating"
        )

    assert not failures, (
        "FET gates over their rating during a TVS clamp event:\n"
        + "\n".join(failures)
    )


def test_gate_clamp_never_conducts_in_normal_operation(spec):
    """
    The gate clamp is off at the highest voltage the rail is allowed to reach.

    A Zener sitting on its knee in normal operation pulls the FET's gate up,
    wastes current through the gate resistor and dissipates continuously. The
    part is chosen so its *lowest* breakdown voltage is above the rail's
    *highest* voltage — both worst cases, in the direction that matters.
    """
    _, rail_high = spec("power.out", "voltage")
    _, r_series_high = spec("switch.r_series", "resistance")
    r_down_low, _ = spec("switch.r_pulldown", "resistance")

    # What each clamp actually sees at the top of the rail's range. The P-FET's
    # is across the rail itself; the N-FET's is below the gate divider.
    highest = {
        "power.d_gate_clamp": rail_high,
        "switch.d_gate_clamp": rail_high * r_down_low / (r_series_high + r_down_low),
    }
    conducting = []
    for address, applied in highest.items():
        v_zener_low, _ = spec(address, "zener_voltage")
        if v_zener_low <= applied:
            conducting.append(
                f"  {address}: breaks down from {v_zener_low:.1f} V, but sees "
                f"{applied:.1f} V in normal operation"
            )

    assert not conducting, (
        "Gate clamps that conduct in normal operation rather than only during a "
        "surge:\n" + "\n".join(conducting)
    )


def test_rail_meets_its_promise(spec):
    """
    The 3.3 V rail the board promises is a rail its regulator can actually hold.

    `rail.power_out.voltage` is design intent — what anything hanging off this
    rail is entitled to assume. `rail.ldo.v_out` is the part's own accuracy
    band. The promise is only worth making if the part's band fits inside it,
    at both ends.

    This existed as a number in the design and was read by nothing for the
    whole life of the board. `sim/rail3v3.cir.in` now measures the same rail
    from the other direction, through a regulator model that drops out and
    current-limits; between them the claim is checked analytically and by
    simulation, which is how every other claim here is treated.
    """
    promised_low, promised_high = spec("rail.power_out", "voltage")
    part_low, part_high = spec("rail.ldo", "v_out")

    assert promised_low <= part_low and part_high <= promised_high, (
        f"The regulator holds {part_low:.3f} to {part_high:.3f} V, which does "
        f"not fit inside the {promised_low:.3f} to {promised_high:.3f} V the "
        "board promises at rail.power_out. Either the promise is too tight for "
        "the part, or the part is the wrong one for the promise."
    )


# Every resistor that is not an LED series resistor, and the design value that
# bounds the voltage across it. Each one is a claim about where the resistor
# sits, which is why it is written down rather than guessed: the branch
# resistors are covered separately, from their own measured current.
RESISTOR_WORST_CASE = {
    "power.r_gate": ("power.tvs", "v_clamp_max"),
    "switch.r_series": ("power.tvs", "v_clamp_max"),
    "switch.r_pulldown": ("power.tvs", "v_clamp_max"),
    "rail.r_load": ("rail.power_out", "voltage"),
}


def test_every_other_resistor_keeps_its_power_margin(spec):
    """
    The resistors that are not in an LED branch also stay inside their ratings.

    `test_led_resistor_power_margin` walks the four branches and stops there,
    so four more resistors declared a power rating that nothing compared
    against anything. Each is bounded here by the largest voltage its node can
    reach — the clamped rail for the three on the 12 V side, the regulated rail
    for the load — which is pessimistic for all of them, and pessimistic is the
    right direction for a rating.
    """
    over = []
    for address, (source_path, source_name) in RESISTOR_WORST_CASE.items():
        _, v_high = spec(source_path, source_name)
        r_low, _ = spec(address, "resistance")
        rated, _ = spec(address, "max_power")
        dissipated = v_high**2 / r_low
        if dissipated > rated * POWER_DERATING:
            over.append(
                f"  {address}: {dissipated * 1e3:.1f} mW in a {rated * 1e3:.0f} mW "
                f"part ({dissipated / rated * 100:.0f}%), with {v_high:.1f} V across it"
            )

    assert not over, "Resistors over %.0f%% of rated power:\n%s" % (
        POWER_DERATING * 100,
        "\n".join(over),
    )


def test_gate_clamps_absorb_the_surge_they_are_for(spec):
    """
    Each gate clamp's dissipation during a TVS event is inside its rating.

    A Zener that clamps a gate has to survive doing it. Both of these are fed
    through a resistor from the clamped rail, so the current is bounded by that
    resistor and the worst case is the clamped rail against the Zener's lowest
    breakdown voltage — the largest drop across the feed resistor, and so the
    most current.
    """
    clamp, _ = spec("power.tvs", "v_clamp_max")
    # (clamp address, the resistor feeding it)
    fed_through = {
        "power.d_gate_clamp": "power.r_gate",
        "switch.d_gate_clamp": "switch.r_series",
    }

    over = []
    for address, feed in fed_through.items():
        v_zener_low, v_zener_high = spec(address, "zener_voltage")
        r_low, _ = spec(feed, "resistance")
        rated, _ = spec(address, "max_power")
        current = max(0.0, clamp - v_zener_low) / r_low
        dissipated = current * v_zener_high
        if dissipated > rated * POWER_DERATING:
            over.append(
                f"  {address}: {dissipated * 1e3:.1f} mW in a {rated * 1e3:.0f} mW "
                f"part, fed through {feed}"
            )

    assert not over, (
        "Gate clamps over %.0f%% of their rating during a surge:\n%s"
        % (POWER_DERATING * 100, "\n".join(over))
    )


# Parts that are not on the 12 V net, and the design value bounding the voltage
# their node can reach. `test_rail_parts_survive_the_tvs_clamp` derives its own
# list from the netlist; these sit one component away from it, where membership
# no longer answers the question, so where each one sits is stated.
OFF_RAIL_NODES = {
    # The gate network: fed from the rail through the button, so a surge
    # reaches it. Bounded by the clamp rather than by D7, deliberately - if D7
    # is ever removed this must still hold.
    ("power.r_gate", "max_voltage"): ("power.tvs", "v_clamp_max"),
    ("switch.r_series", "max_voltage"): ("power.tvs", "v_clamp_max"),
    ("switch.r_pulldown", "max_voltage"): ("power.tvs", "v_clamp_max"),
    ("switch.c_debounce", "max_voltage"): ("power.tvs", "v_clamp_max"),
    # The low-side FET's drain sits at the rail whenever it is off, because the
    # LED branches pull it up. So it sees the clamp too.
    ("switch.q_switch", "max_drain_source_voltage"): ("power.tvs", "v_clamp_max"),
    # Behind the regulator, which is where the surge stops.
    ("rail.r_load", "max_voltage"): ("rail.power_out", "voltage"),
    ("rail.c_out", "max_voltage"): ("rail.power_out", "voltage"),
}


def test_parts_off_the_rail_are_rated_for_their_node(spec):
    """
    Parts one component away from the 12 V rail are rated for what reaches them.

    The rail check covers everything on the 12 V net. These are the parts just
    off it — the gate network, which a surge reaches through the button, and the
    3.3 V side, where it does not. Their voltage ratings were the largest block
    of numbers in the design that nothing compared against anything.
    """
    weak = []
    for (address, parameter), (source_path, source_name) in OFF_RAIL_NODES.items():
        rating, _ = spec(address, parameter)
        _, applied = spec(source_path, source_name)
        if rating < applied:
            weak.append(
                f"  {address}: {parameter} {rating:.1f} V < the {applied:.1f} V "
                f"its node can reach"
            )

    assert not weak, (
        "Parts rated below the voltage their own node can reach:\n" + "\n".join(weak)
    )
