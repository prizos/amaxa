"""
What each simulated measurement has to come out as, and why.

A band with no reason behind it is a number somebody will widen the next time it
fails. Each entry is (low, high, why).

These are not independent of hw/cpu1/checks/: they deliberately restate what the
design checks compute analytically, so that a disagreement between the two
methods shows up as a failure rather than as nobody noticing.
"""

MEGA = 1e6


def _after_sharing(values: dict[str, tuple[float, float]]) -> float:
    """
    How far the pin must *still* be below a 1 V input once the sampling
    capacitor has taken its share, and no further.

    Charge sharing alone puts it at 1 - C_adc/(C_adc + C_ext), from the two
    capacitances the design declares - the largest sampling capacitor against
    the smallest external one, which is the deepest the droop can be. The
    tenth allowed above that is for what the series resistor gives back while
    the switch is closing, which the deck models and this arithmetic does not.
    """
    c_adc = values["mcu.adc_sample_capacitance"][1]
    c_ext = values["adc.fast1.shunt.capacitance"][0]
    droop = c_adc / (c_adc + c_ext)
    return 1.0 - droop * 1.1

# The guard on the guards, as checks/test_check_count.py is for the design
# checks. A deck that quietly stops measuring something leaves a suite that
# passes with less coverage than it had.
EXPECTED_MEASUREMENTS = 6

LIMITS = {
    "adc_corner": {
        "f_corner": (
            1.0 * MEGA, 2.0 * MEGA,
            "Where a fast channel rolls off. checks/test_adc.py computes the "
            "same corner from the same values and holds it to the same band; "
            "this measures it with the sampling switch and the converter's own "
            "resistance in the circuit. The two should agree to a few percent, "
            "and the deck is worth having only while they can disagree.",
        ),
        "t_tau": (
            80e-9, 160e-9,
            "The time constant the corner is read from. Banded as well as the "
            "corner it produces, because a deck that stops converging and "
            "returns a time of zero would otherwise report an infinite corner "
            "and pass nothing but the wrong test.",
        ),
        "t_settled": (
            0.0, 1.2e-6,
            "How soon after a step the pin is within a tenth of a percent of "
            "it: ln(1000) time constants, near enough seven, which is 0.92 us "
            "at the values fitted. The first version of this band said four and "
            "a half - that is the figure for one percent, not a tenth of one - "
            "and the deck is what said so. It bounds how quickly a channel may "
            "be re-read after the thing it measures moves, and it is a fiftieth "
            "of a PWM period at 20 kHz.",
        ),
    },
    "adc_settling": {
        "settling_error_lsb": (
            0.0, 0.5,
            "What the converter is left holding at the end of the shortest "
            "sampling window firmware will use, against full scale. The design "
            "check derives this from charge sharing and a single exponential; "
            "this simulates it with the switch, so if the simplification is "
            "wrong in some way that matters, the two numbers part company. "
            "Half an LSB is where a measurement stops being limited by this and "
            "starts being limited by the converter.",
        ),
        "v_held": (
            0.9998, 1.0,
            "The same measurement said the other way round, as a voltage "
            "against a 1 V input. Here so that a deck which stops converging "
            "and returns zero fails loudly rather than reporting a suspiciously "
            "good error.",
        ),
        "v_pin_after_sharing": (
            _after_sharing, 1.0,
            "The node immediately after the sampling capacitor takes its share, "
            "before the series resistor has put any of it back. This is the "
            "number the analytic check starts from, and it is measured here to "
            "confirm the starting point rather than only the answer.\n"
            "      The low end is not a constant: it is 1 - C_adc/(C_adc+C_ext) "
            "worked out from the same two values the design states, with a "
            "tenth of it allowed for the little the resistor gives back inside "
            "the switch's own closing time. Written out as a number it was "
            "0.9994, chosen when the capacitor was 10 nF, and changing the "
            "capacitor to 4.7 turned it into a band that failed for the right "
            "reason with the wrong message.",
        ),
    },
}
