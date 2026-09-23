"""
What each simulated measurement has to come out as, and why.

A band with no reason behind it is a number somebody will widen the next time it
fails. Each entry is (low, high, why).

These are not independent of hw/cpu1/checks/: they deliberately restate what the
design checks compute analytically, so that a disagreement between the two
methods shows up as a failure rather than as nobody noticing.
"""

MEGA = 1e6


def _trip_budget(values: dict[str, tuple[float, float]]) -> float:
    """How long a trip may take, as the design declares it."""
    return values["trip.budget"][1]


def _comparator_delay_low(values: dict[str, tuple[float, float]]) -> float:
    """
    The comparator's own figure, less the residual its calibration leaves.

    A tenth either side. The model is fitted to reproduce
    `propagation_delay_max` at the datasheet's own reference load, and the
    correction for that load is approximate because the output's current
    ceiling makes the first part of an edge a ramp; 0.4 % is what it actually
    leaves, and a tenth is the room that gets without becoming a band that
    would accept a model fitted to something else.
    """
    return values["trip.fast4_high.propagation_delay_max"][1] * 0.9


def _comparator_delay_high(values: dict[str, tuple[float, float]]) -> float:
    """The other side of it."""
    return values["trip.fast4_high.propagation_delay_max"][1] * 1.1


def _latch_delay_low(values: dict[str, tuple[float, float]]) -> float:
    """The latch's own figure, less a tenth, for the same reason."""
    return values["safety.latch.preset_to_output_max"][1] * 0.9


def _latch_delay_high(values: dict[str, tuple[float, float]]) -> float:
    """And the other side."""
    return values["safety.latch.preset_to_output_max"][1] * 1.1


def _corner_low(values: dict[str, tuple[float, float]]) -> float:
    """The bottom of the band a fast channel's corner is declared in."""
    return values["adc.fast_corner"][0]


def _corner_high(values: dict[str, tuple[float, float]]) -> float:
    """
    The top of it.

    Written as a function of the declared band rather than as `2.0 * MEGA`,
    because the two entries that used a constant here are the two the band
    could drift away from without anything saying so - and the whole reason
    this measurement exists is that a band with only one end tested is a band
    half tested.
    """
    return values["adc.fast_corner"][1]


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
EXPECTED_MEASUREMENTS = 13

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
        "f_corner_high": (
            _corner_low, _corner_high,
            "The same channel at the other end of its tolerance: nothing in "
            "front of it, and both passives at the bottom of their bands. It "
            "is here because the deck used to measure only the slow corner, "
            "which meant it could agree with `checks/test_adc.py` about the "
            "low end and had nothing to say about the high one - and a 3.3 nF "
            "part in place of the 4.7 put the fast corner at 2.46 MHz, "
            "outside the declared band, while this deck reported 1.81 and "
            "passed.\n"
            "      The band is the declared `adc.fast_corner`, both ends, "
            "worked out here from the corner frequency rather than typed: an "
            "aliasing filter whose corner has left the band it was specified "
            "in is not doing the job either way round.",
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
    "trip_chain": {
        "t_trip_total": (
            0.0, _trip_budget,
            "The whole chain: a fault current crossing the threshold at the "
            "connector, to the gate line below the threshold the power board "
            "is promised. `trip.budget` is 50 ns and "
            "`test_a_trip_stops_the_outputs_inside_the_budget` sums five "
            "terms to 40.5 of it. This is the same quantity with one "
            "excitation integrated instead, and the band is the declared "
            "budget itself - so the deck is a second method on the number "
            "the board exists to make true, not on a proxy for it.",
        ),
        "t_comparator_out": (
            0.0, _trip_budget,
            "The tap and the comparator together, which the check computes "
            "separately as `R_source * sum of the shunt capacitors` and "
            "`propagation_delay_max`. It is a smaller share here than there, "
            "because the check sums both shunt capacitors as though both sat "
            "on the sense node when one is behind 22 ohm and the other "
            "behind 1 k. Banded against the whole budget rather than against "
            "a share of it: what matters is that no single term eats it, and "
            "a share would be a number chosen to fit what the term does.",
        ),
        "t_bus_low": (
            0.0, _trip_budget,
            "And the bus. The check extrapolates the comparator's Figure 5 "
            "straight line to 137 pF, past the 100 pF the fit was taken "
            "from; here the output stage is a resistance and a current "
            "ceiling and the bus is twelve diode junctions whose "
            "capacitance falls as it discharges. The two should be close and "
            "the deck is worth having only while they can part company.",
        ),
        "t_tripped_high": (
            0.0, _trip_budget,
            "One latch output holding two buffer enables and a transistor "
            "gate. The check gives each of them the full 24 mA by taking a "
            "max over the buffer's disable time and the FET's turn-on; here "
            "they share one source, so this is the term most likely to come "
            "out worse than the arithmetic says.",
        ),
        "t_comp_in_jig": (
            _comparator_delay_low, _comparator_delay_high,
            "**Not part of the board.** The comparator's own datasheet test "
            "circuit - its 13 pF reference load - built beside the chain so "
            "that a model which has drifted from the figure it was fitted to "
            "fails here rather than downstream, where it would look like a "
            "finding about copper. The band is the declared "
            "`propagation_delay_max` with a tenth either side, which is the "
            "residual the fit leaves: the current ceiling makes the first "
            "volt of an edge a ramp rather than an exponential, so the "
            "correction for the reference load is approximate and measured "
            "rather than assumed. See models/SOURCE.md.",
        ),
        "t_latch_in_jig": (
            _latch_delay_low, _latch_delay_high,
            "The same for the latch, and it matters more: `tfit` in "
            "`lvc1g74.lib` is the one number in these models that the design "
            "does not state. It was solved by bisection against this jig - "
            "50 pF with 500 ohm to ground, taken at 1.5 V, SCES794E Figure 3 "
            "- because the gate's ramp and the output stage's charging "
            "overlap rather than add and there is no closed form. A fitted "
            "constant goes quietly wrong when something upstream of it "
            "moves; this is what stops it being quiet.",
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
