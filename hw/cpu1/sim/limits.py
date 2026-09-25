"""
What each simulated measurement has to come out as, and why.

A band with no reason behind it is a number somebody will widen the next time it
fails. Each entry is (low, high, why).

These are not independent of hw/cpu1/checks/: they deliberately restate what the
design checks compute analytically, so that a disagreement between the two
methods shows up as a failure rather than as nobody noticing.
"""

import math

MEGA = 1e6


def _clear_valid_low(values: dict[str, tuple[float, float]]) -> float:
    """What the latch calls a low, which the clear has to get under."""
    return values["safety.latch.input_low_voltage_max"][1]


def _latch_input_absolute_max(values: dict[str, tuple[float, float]]) -> float:
    """And what it cannot be taken above, clamp or no clamp."""
    return values["safety.latch.input_voltage_absolute_max"][1]


def _clear_asserted(values: dict[str, tuple[float, float]]) -> float:
    """
    How long the clear stays a valid low, from the declared parts.

    The pin goes low, the node drops to the divider of the series resistor
    against the pull-up, and then climbs back toward the rail on the two of
    them in series with the coupling capacitor. It stops being a low when it
    passes the latch's own threshold:

        tau = (Rs + Rpu) * C,  V_low = V * Rs/(Rs + Rpu)
        t   = tau * ln((V - V_low) / (V - V_IL))

    Worst case throughout: the largest resistors and capacitor, which is the
    longest the clear can be asserted, against the smallest pull-up, which is
    the lowest it goes.
    """
    rail = values["rail.3v3.voltage"][1]
    series = values["safety.r_clear_series.resistance"][1]
    pull_up = values["safety.r_clear_pullup.resistance"][0]
    coupling = values["safety.c_clear.capacitance"][1]
    threshold = values["safety.latch.input_low_voltage_max"][1]
    low = rail * series / (series + pull_up)
    tau = (series + pull_up) * coupling
    return tau * math.log((rail - low) / (rail - threshold))


def _clear_asserted_low(values: dict[str, tuple[float, float]]) -> float:
    """A tenth under it."""
    return _clear_asserted(values) * 0.9


def _clear_asserted_high(values: dict[str, tuple[float, float]]) -> float:
    """And a tenth over."""
    return _clear_asserted(values) * 1.1


def _vref_below_vdda_floor(values: dict[str, tuple[float, float]]) -> float:
    """
    And how far below VDDA it may sit, which is the whole rail.

    A floor is needed because the band has two ends, and the honest one is
    that VREF+ cannot be more than a rail below VDDA: anything lower and the
    measurement is reading a node that is not there.
    """
    return -values["rail.3v3.voltage"][1]


def _vref_above_vdda(values: dict[str, tuple[float, float]]) -> float:
    """How far VREF+ may get above VDDA, which ST says is nowhere."""
    return values["mcu.vref_above_vdda_max"][1]


def _dac_out_of_spec_allowed(values: dict[str, tuple[float, float]]) -> float:
    """
    How long the DAC may be under its minimum supply once 3V3 is up.

    The reference hangs off the rail the 3V3 converter makes, so the longest
    that rail's own soft start can be is the longest anything downstream of
    it can reasonably take to follow.
    """
    return values["buck3v3.ic.soft_start_time"][1]


def _analog_pin_limit(values: dict[str, tuple[float, float]]) -> float:
    """What a TT_xx pin takes, absolutely: ST's Table 20."""
    return values["mcu.analog_input_voltage_max"][1]


def _rail_ordering_allowed(values: dict[str, tuple[float, float]]) -> float:
    """
    How long 3V3 may lag 5 V.

    The 5 V rail has to climb to the 3V3 converter's UVLO before that
    converter starts, and then it soft-starts. Both figures are declared and
    the 5 V ramp is its own declared soft start, so the whole thing follows
    from three numbers and none of it is typed.
    """
    five = values["rail.5v.voltage"][1]
    uvlo = values["buck3v3.ic.input_uvlo"][1]
    return (values["buck5.ic.soft_start_time"][1] * uvlo / five
            + values["buck3v3.ic.soft_start_time"][1])


def _rail_high(values: dict[str, tuple[float, float]]) -> float:
    """The logic rail's own ceiling: a pulled-up node cannot settle above it."""
    return values["rail.3v3.voltage"][1]


def _clear_released_low(values: dict[str, tuple[float, float]]) -> float:
    """
    Where the clear node has to be back to, with the pin still held low.

    The latch's own high threshold is the weaker statement - the node must be
    a valid high - but what this is really asserting is that the pull-up owns
    the node again, so it is held to within a tenth of the rail rather than
    to the threshold. Anything between those two is a circuit that let go
    later than it should have.
    """
    return values["rail.3v3.voltage"][1] * 0.9


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
def _rmii_setup_window(values: dict[str, tuple[float, float]]) -> float:
    """
    What a period leaves once the PHY's setup is taken out of it.

    The one number the whole transmit budget is held to, and it is two
    figures from two datasheets and nothing else: the clock period the PHY
    generates, less the setup its own Table 5.12 asks for on TXD. Everything
    the deck measures has to fit inside it.
    """
    period = values["eth.phy.rmii_clock_period"][1]
    setup = values["eth.phy.rmii_setup_min"][0]
    return period - setup


def _rmii_period(values: dict[str, tuple[float, float]]) -> float:
    """One clock period, which nothing on this bus may exceed under any reading."""
    return values["eth.phy.rmii_clock_period"][1]


def _rmii_published_delay(values: dict[str, tuple[float, float]]) -> float:
    """
    The MCU's whole published output delay, as a ceiling on the jig's share.

    `t_txd_into_jig` is subtracted from this to get the part's internal
    propagation, so a jig time larger than the figure it comes out of would
    make that negative and the headline meaningless. It comes out at about
    0.69 ns against 11.5, and the point of the band is that a driver model
    which stopped converging and returned zero - or one that charged the jig
    slower than the part is allowed to - fails here rather than quietly
    flattering the total below.
    """
    return values["mcu.rmii_transmit_data_delay_max"][1]


def _mcu_still_running(values: dict[str, tuple[float, float]]) -> float:
    """
    The 3V3 above which the MCU is guaranteed **not** to have reset.

    BOR3's falling edge at its maximum. Below this the MCU may or may not
    have reset; above it, it certainly has not, and is certainly still
    holding `PWM_ENABLE_N` low.
    """
    return values["mcu.brown_out_reset_highest"][1]


def _comparator_supply_floor(values: dict[str, tuple[float, float]]) -> float:
    """The lowest 5 V the over-current comparators are specified at."""
    return values["trip.fast1_high.supply_voltage"][0]


EXPECTED_MEASUREMENTS = 30

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
    "brown_out": {
        "v_5v_at_3v3_dropout": (
            _comparator_supply_floor, 6.0,
            "Where the 5 V rail had fallen to when 3V3 left its band. It has "
            "to still be somewhere the comparators are specified, because "
            "everything after this instant is the two rails decaying against "
            "each other and a 3V3 that outlived the protection would already "
            "have lost the race here.\n"
            "      The upper end is a sanity bound: a rail above 6 V on the "
            "way down means the model is not decaying at all.",
        ),
        "v_3v3_at_comparators_lost": (
            0.0, _mcu_still_running,
            "Where 3V3 had fallen to at the instant the comparators lost "
            "their specified supply - and therefore whether the MCU's own "
            "brown-out reset closes the window that `t_protection_margin` "
            "measures. When the MCU resets it lets `PWM_ENABLE_N` go to its "
            "pull-up, and that turns the buffers off whatever else is true.\n"
            "      So this has to be **below** the level at which the MCU is "
            "still guaranteed to be running: BOR3's falling edge at its "
            "maximum, 2.68 V, which is the highest of the four selectable "
            "levels. It comes out at 2.88.\n"
            "      **The MCU has not reset**, at any BOR setting, by the "
            "time the over-current protection stops being specified. That is "
            "the second half of the finding and the reason it is not closed "
            "by an option byte.",
        ),
        "t_protection_margin": (
            0.0, 1.0,
            "**The safety property, and nothing on this board checked it.** "
            "The PWM buffers run from 3V3 and are specified to 1.65 V; the "
            "over-current comparators run from 5 V and are specified to "
            "2.70. 3V3 comes from a converter whose input is the 5 V rail "
            "and which holds on until that falls to its UVLO less its "
            "hysteresis - as low as 2.90 V, two hundred millivolts above "
            "where the comparators stop.\n"
            "      So on every loss of supply there is a race, and this is "
            "how much the buffers win it by. Positive means the thing that "
            "drives a bridge lost its rail before the thing that stops one "
            "lost its. Negative would be a window, on every brown-out, in "
            "which this board emits PWM with nothing watching the current.\n"
            "      The upper bound is a second's worth, which no rail on "
            "this board can take to decay and which catches a measurement "
            "that did not find its edge at all.",
        ),
    },
    "rmii_transmit": {
        "t_txd_into_jig": (
            0.0, _rmii_published_delay,
            "What ST's own 20 pF test load is worth, measured by reproducing "
            "it. This is the calibration the deck's headline rests on: the "
            "published `td(TXD)` contains this RC, and a check that adds the "
            "board's copper on top of the published figure counts it twice.\n"
            "      Banded against the published delay itself, which is the "
            "only bound that is not this measurement's own formula restated. "
            "It comes out near R C ln 2 - 0.69 ns - and if it does not, the "
            "driver model is wrong and nothing else in this deck means "
            "anything.",
        ),
        "t_clk_flight": (
            0.0, _rmii_setup_window,
            "REF_CLK from the PHY's pin to the MCU's, as a transmission line "
            "rather than a length times a delay per millimetre. It is charged "
            "to the transmit budget in full, because the PHY sources the "
            "clock and the data travels back the other way.",
        ),
        "t_txd_flight": (
            0.0, _rmii_setup_window,
            "And the data's leg, to the 1.90 V a VIS input is guaranteed to "
            "have switched by. Whether this comes out near the line's one-way "
            "delay or at twice it is the question a lumped model cannot "
            "answer: the far end is nearly open, so the incident wave is the "
            "driver-to-line divider and the reflection is what finishes the "
            "job.",
        ),
        "t_transmit_total": (
            0.0, _rmii_setup_window,
            "**The headline, and a second method on the number this board has "
            "least margin in.** The clock's flight, plus the MCU's published "
            "delay less the jig that figure was taken in, plus the data's "
            "flight - against a period less the PHY's setup.\n"
            "      The analytic check computes the same budget by adding "
            "lengths and clears it by nine picoseconds. Any real disagreement "
            "between the two is a finding, which is the entire reason this "
            "deck exists.",
        ),
        "t_transmit_worst": (
            0.0, _rmii_period,
            "The same budget with the jig given no credit at all - the whole "
            "published `td(TXD)` treated as internal propagation. It comes "
            "out at 12.77 ns against the 12.5 the setup window allows, so "
            "**under this reading the bus does not close**, and the gap "
            "between it and `t_transmit_total` is 0.69 ns on a budget with "
            "one nanosecond in it.\n"
            "      It is banded against a whole period rather than against "
            "the setup window, and the reason is not that the tighter band "
            "was uncomfortable. ST states `td(TXD)` *into a 20 pF load*. A "
            "delay measured into a load contains the time to charge it, so "
            "a reading that treats none of the 11.5 ns as the load is not "
            "conservative - it contradicts the condition the figure is "
            "quoted under. This is here to show the size of the assumption "
            "the headline rests on, and to fail loudly if the deck stops "
            "converging, which is what the period catches.\n"
            "      What would settle it outright is ST stating the split, or "
            "a scope on TXD and REF_CLK at the PHY's pins.",
        ),
    },
    "trip_clear": {
        "v_clr_low": (
            0.0, _clear_valid_low,
            "The low the clear reaches at the latch. It is a divider - the "
            "series resistor against the pull-up on the far side of the "
            "coupling capacitor - and it has to land under the voltage the "
            "latch calls a low, because a clear the latch does not act on is "
            "not a clear. The band's top is the declared "
            "`input_low_voltage_max` itself.",
        ),
        "t_clr_asserted": (
            _clear_asserted_low, _clear_asserted_high,
            "How long that low lasts **with the pin still held low**, which "
            "is the abandoned-pin case the coupling capacitor exists for. "
            "Derived from the same three declared values the design check "
            "uses - tau ln((V-V_low)/(V-V_IL)) - with a tenth either side "
            "for the clamp's junction capacitance and the copper, neither of "
            "which is in that arithmetic. If the two ever part company by "
            "more than that, something in this circuit is not the single RC "
            "both of them think it is.",
        ),
        "v_clr_released": (
            _clear_released_low, _rail_high,
            "And that it really did let go. Measured at 290 us, with PG5 "
            "still low: the node must be back at the rail and the pull-up "
            "must own it again. A capacitor that had leaked, or a clamp "
            "conducting when it should not, shows up here and nowhere else.",
        ),
        "v_clr_overshoot": (
            0.0, _latch_input_absolute_max,
            "**The clamp's whole job.** When the pin goes high again the "
            "capacitor is still holding most of the rail, so the clear node "
            "is driven above it: 6.61 V from this board's own declared "
            "values, against a latch whose absolute maximum is 6.5 V and "
            "which has **no clamp diode to V_CC of its own** - that absence "
            "is what makes an LVC input tolerant of 5 V on a 3.3 V rail, and "
            "it is why D13 is fitted. The design check approximates D13 as a "
            "capacitance; here it is a diode, and this is the measurement "
            "that would notice the difference.",
        ),
        "t_clear_to_q": (
            0.0, _clear_asserted_high,
            "The latch actually coming out of the trip it was preset into, "
            "which is what makes this a test of the clear rather than of a "
            "waveform on a node. It has to happen while the clear is still "
            "asserted, so the band's top is the same figure the pulse's own "
            "length is held to: a clear that outlasts its own pulse has not "
            "cleared anything.",
        ),
    },
    "power_up": {
        "v_ref_above_vdda_max": (
            _vref_below_vdda_floor, _vref_above_vdda,
            "**The relationship the board broke once.** ST's Table 86 gives "
            "VREF+ a maximum of VDDA, and `mcu.vref_above_vdda_max` states "
            "that as the headroom it may have, which is none. `c297e58` had "
            "the reference on the 5 V rail regulating at 3.006 V for the "
            "millisecond before the 3V3 converter had started VDDA from "
            "zero, and every check on the board compared steady-state "
            "numbers and saw nothing.\n"
            "      The topology check guards the wiring; this guards the "
            "relationship, at every instant of the ramp. Move the "
            "reference's supply in this deck back to the 5 V rail and it "
            "fails, which is the historical defect reproduced.",
        ),
        "t_dac_below_spec": (
            0.0, _dac_out_of_spec_allowed,
            "How long the threshold DAC sits outside its own 2.7 V minimum "
            "*after* the logic rail is already up - the window in which the "
            "latch and both buffers are alive at 1.65 V and every trip "
            "threshold is undefined. `cpu1.py:946` describes that window on "
            "the way **down** and says nothing about the way up, and nothing "
            "has ever put a number on either.\n"
            "      The bound is the 3V3 converter's own longest soft start: "
            "the reference hangs off the rail that converter makes, so a "
            "window longer than the ramp that made it would mean something "
            "other than the ramp is holding VREF+ back.",
        ),
        "v_3v3a_max": (
            0.0, _analog_pin_limit,
            "The analog supply's ceiling at every instant, against the 4.0 V "
            "ST's Table 20 allows on a TT_xx pin. 3V3A comes off an LDO on "
            "the 5 V rail while VDDA comes off a buck *and* a ferrite, so it "
            "arrives first and nothing on the board orders the two.\n"
            "      That lead is safe, and this is the measurement that says "
            "why rather than the comment: the pin limit is **absolute** and "
            "not referred to VDDA - Table 21 rates positive injection on "
            "these pins at minus five to plus nought milliamps, so there is "
            "no injection path to be inside of. A sensor at 3.366 V while "
            "VDDA is still at one volt is inside its rating. What would not "
            "be is an LDO that overshot on start-up, and that is what this "
            "band catches.",
        ),
        "t_5v_to_3v3": (
            0.0, _rail_ordering_allowed,
            "And the ordering itself, which was four sentences of prose. The "
            "bound is the two declared soft-start times plus the 3V3 "
            "converter's own UVLO time on the 5 V ramp - if the gap were "
            "longer than that, something other than the parts' own figures "
            "is deciding when this board comes up.",
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
