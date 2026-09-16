"""
What each simulated measurement has to come out as, and why.

A band with no reason behind it is a number somebody will widen the next time it
fails. Each entry is (low, high, why).

These are not independent of hw/checks/: several deliberately restate what the
design checks compute analytically, so that a disagreement between the two
methods shows up as a failure rather than as nobody noticing.
"""

MILLI = 1e-3

LIMITS = {
    "led_branch": {
        "i_branch_at_min_supply": (
            3.4 * MILLI, 4.4 * MILLI,
            "At 10.8 V each LED must still be clearly lit. hw/checks/ puts the "
            "worst case at 3.73 mA using the datasheet's highest forward "
            "voltage; a nominal LED draws a little more, and this band brackets "
            "that. If the two methods ever disagree, one of them is wrong.",
        ),
        "i_branch_at_max_supply": (
            4.6 * MILLI, 5.6 * MILLI,
            "At 13.2 V the analytic worst case is 5.07 mA with the lowest "
            "forward voltage, and a nominal LED lands just under it. Above about "
            "6 mA the series resistor would be past half its rating.",
        ),
        "v_led_at_min_supply": (
            1.85, 2.15,
            "A red AlGaInP emitter at a few milliamps sits near the bottom of "
            "its 2.0 to 2.4 V band. Outside this, the model has drifted from the "
            "datasheet point it was fitted to.",
        ),
        "v_led_at_max_supply": (
            1.90, 2.25,
            "Same, a little higher for the extra current.",
        ),
        "v_fet_drop_at_max": (
            0.10, 0.25,
            "Four branches through 7.5 ohms. Much more than this and the FET is "
            "eating headroom the LEDs need; much less and the current is lower "
            "than intended.",
        ),
    },
    "debounce": {
        "t_gate_reaches_threshold": (
            6.0e-3, 10.0e-3,
            "Pressed at 5 ms. The gate charges with a time constant of about "
            "9 ms towards roughly 11 V, so it passes the 2.5 V threshold a "
            "couple of milliseconds later. Sooner than about 1 ms after the "
            "press and contact bounce would get through; much later and the "
            "button would feel unresponsive.",
        ),
        "v_gate_held_on": (
            10.0, 11.5,
            "The divider holds the gate at the rail times 100k over 110k. Well "
            "above twice the 2.5 V threshold, which is what hw/checks/ demands "
            "so the FET is fully on rather than part-way.",
        ),
        "t_gate_falls_below_threshold": (
            300e-3, 420e-3,
            "Released at 105 ms and discharging through the pulldown alone, "
            "with a 100 ms time constant. The LEDs fade rather than snap off. "
            "Any slower and the board would feel broken.",
        ),
        "v_gate_at_rest": (
            0.0, 0.5,
            "Long after release the gate must be at ground, not floating near "
            "the threshold where the FET would sit half on.",
        ),
    },
}
