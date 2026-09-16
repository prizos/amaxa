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


def test_led_current_in_band(branch_current):
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
        if low < low_bound or high > high_bound:
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


def test_rail_parts_survive_the_tvs_clamp(spec, footprints):
    """
    Nothing on the protected rail is rated below what the TVS lets through.

    A TVS does not hold the rail at its stand-off voltage; under surge current
    it clamps much higher. If anything downstream is rated below that clamp,
    the protection is decorative: the part it is meant to protect fails first.
    A 12 V stand-off device cannot clamp below about 15 V, so this constrains
    what may sit on the rail.
    """
    clamp, _ = spec("power.tvs", "v_clamp_max")

    # (source address, parameter) for everything the protected 12 V rail reaches.
    on_rail = [
        ("power.c_bulk", "max_voltage"),
        ("power.c_hf", "max_voltage"),
        ("power.q_rpp", "max_drain_source_voltage"),
        ("rail.c_in", "max_voltage"),
        ("rail.ldo", "v_in_max"),
        ("switch.q_switch", "max_drain_source_voltage"),
    ]

    addresses = {
        fp["properties"].get("address"): fp["designator"]
        for fp in footprints
    }
    weak = []
    for address, parameter in on_rail:
        rating, _ = spec(address, parameter)
        if rating < clamp:
            weak.append(
                f"  {addresses.get(address, '?')} ({address}): {parameter} "
                f"{rating:.1f} V < {clamp:.1f} V clamp"
            )

    assert not weak, (
        f"Parts on the 12 V rail rated below the TVS clamping voltage "
        f"of {clamp:.1f} V:\n" + "\n".join(weak)
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
