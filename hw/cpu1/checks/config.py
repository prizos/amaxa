"""
What the common checks in hw/checks/ need to know that is specific to cpu1.
"""

# Drawn, routed and checked. Both reasons this used to be False have gone:
# design.json has no `pending` nets, and board.mk says ROUTING := complete.
# `test_a_board_declaring_itself_unfinished_says_what_is_unfinished` is what
# stops this lagging the board again - a board that claims to be incomplete
# now has to point at the thing that is.
#
# What it means: DRC reports no violations and no unconnected items, the
# outputs and the IPC-D-356 net list build, `make reproducible` regenerates
# the same board, `make offline` builds with the network refusing every call,
# both BSPs compile, and `NEEDS_A_HUMAN_EYE` and `WAITING_ON_A_DECISION` are
# empty. What it does not mean is that anybody has built one.
COMPLETE = True

# Checks that must actually run for this board, common and board-specific.
EXPECTED_CHECKS = 188

# Parameters recorded in parts.py that nothing reads, each with the reason.
UNREAD_PARAMETERS: dict[tuple[str, str], str] = {
    ("buck5.c_out1", "capacitance"): (
        "the 5 V buck's output bulk. The LM5164's datasheet gives an input "
        "capacitance minimum and no output figure, so there is nothing to "
        "compare these against: the value follows from the ripple wanted, and "
        "this board states no ripple target for the 5 V rail. Worth one before "
        "a second spin - it is a loop-stability number as well as a ripple one"
    ),
    ("buck5.c_out2", "capacitance"): "the second half of buck5.c_out1, and the same gap",
    ("can.decoupling_vcc", "capacitance"): (
        "a 100 nF bypass at a supply pin. That it exists, and sits beside its own pin, is checked; its *value* is convention and neither this part's datasheet nor anything else on this board states a figure to hold it to. It became visible when the converters' input-capacitance checks stopped summing the whole 5 V net - which is how these were being 'read' before, as part of an answer to a different question"
    ),
    ("trip.fast1_high.decoupling", "capacitance"): (
        "as can.decoupling_vcc: a bypass whose presence is checked and whose value nothing states"
    ),
    ("trip.fast1_low.decoupling", "capacitance"): (
        "as can.decoupling_vcc: a bypass whose presence is checked and whose value nothing states"
    ),
    ("trip.fast2_high.decoupling", "capacitance"): (
        "as can.decoupling_vcc: a bypass whose presence is checked and whose value nothing states"
    ),
    ("trip.fast2_low.decoupling", "capacitance"): (
        "as can.decoupling_vcc: a bypass whose presence is checked and whose value nothing states"
    ),
    ("trip.fast3_high.decoupling", "capacitance"): (
        "as can.decoupling_vcc: a bypass whose presence is checked and whose value nothing states"
    ),
    ("trip.fast3_low.decoupling", "capacitance"): (
        "as can.decoupling_vcc: a bypass whose presence is checked and whose value nothing states"
    ),
    ("trip.fast4_high.decoupling", "capacitance"): (
        "as can.decoupling_vcc: a bypass whose presence is checked and whose value nothing states"
    ),
    ("core.vdda.bead", "dc_resistance"): (
        "its drop is VDDA's current times 0.9 ohm, and VDDA's current is not in "
        "the datasheet pages read for this board, so there is nothing to bound "
        "it against. Expected to be millivolts; measured at bring-up"
    ),
    ("core.vdda.bead", "max_current"): (
        "100 mA against VDDA's current, which is not stated in the datasheet "
        "pages read; the same gap as its DC resistance"
    ),
    ("power.fuse", "interrupt_rating"): (
        "50 A against the fault current the supply can deliver, which is a "
        "property of whatever is wired to the terminal and not of this board. "
        "Recorded because it is what makes the part suitable for a rail that "
        "may be fed from a battery"
    ),
    ("vref.ic", "output_current_max"): (
        "25 mA against what VREF+ draws, which the pages of ST's datasheet "
        "read for this board do not state - the same gap as VDDA's current. "
        "The 1 uF and 100 nF at the pin supply the conversion transients; the "
        "steady draw is what needs measuring at bring-up"
    ),
    ("vref.ic", "temperature_drift"): (
        "75 ppm/degC is the board's measurement accuracy, and there is nothing "
        "to compare it against until the ADC input networks exist and the "
        "error budget has a second term in it. M6"
    ),
    ("safety.buffer1", "enable_time_max"): (
        "7 ns from the enable going low to the outputs driving again. Turning "
        "on is not time-critical - firmware chooses when - and the number that "
        "is, turning off, is disable_time_max, which the trip budget uses"
    ),
    ("safety.buffer2", "enable_time_max"): "as buffer1: turning on is not timed",
    ("safety.buffer2", "disable_time_max"): (
        "both buffers are the same part, so the trip budget is worked with one "
        "of them. This is the second copy of the same 7 ns"
    ),
    ("safety.buffer1", "input_low_voltage_max"): (
        "0.8 V, against what the MCU's pins drive low to - which the pages of "
        "ST's datasheet read for this board do not state. The high side is "
        "checked; this end waits for V_OL, and for the same measurement at "
        "bring-up that VDDA's current needs"
    ),
    ("safety.buffer2", "input_low_voltage_max"): "as buffer1",
    ("safety.buffer2", "propagation_delay_max"): (
        "both buffers are the same part; the skew check works with one set of "
        "timings and this is the second copy"
    ),
    ("safety.buffer2", "output_skew_max"): "as buffer1's, and the same part",
    ("safety.buffer2", "output_current_max"): "as buffer1's, and the same part",
    ("safety.buffer2", "total_output_current_max"): "as buffer1's, and the same part",
    ("usb.receptacle", "current_rating"): (
        "5 A per contact against a port that draws none: VBUS reaches a sense "
        "pin and a clamp and stops there, which is the whole design of it. "
        "Recorded because this is the connector to reuse if a later board does "
        "take power from USB, and then this is the number that decides"
    ),
    ("usb.protection", "clamping_voltage_max"): (
        "17 V while passing 5 A of an 8/20 us surge. There is nothing here to "
        "compare it against: the MCU pin's 7.1 V limit is a DC rating, and "
        "putting a microsecond clamp beside it would be comparing two "
        "different questions. What the pin's own structures then absorb is not "
        "a figure either datasheet gives"
    ),
}

# Part libraries whose review note still says "Needs a human eye": things no
# machine here can confirm against a manufacturer's drawing.
# Claims read out of a manufacturer's own drawing, with the crop that settles
# each one committed in <LIB>/evidence/ and its source recorded beside it.
# `tools/datasheet.py evidence` writes both. Moving an entry here from
# NEEDS_A_HUMAN_EYE is a claim that the figure was rendered and read, and
# test_a_confirmed_review_left_its_evidence_behind makes that checkable.
CONFIRMED_FROM_A_RENDER: dict[str, list[str]] = {
    "SOT223": ["pinout", "land_pattern"],
    "LED0603": ["polarity"],
    "LQFP144": ["power_supply_scheme"],
    "MSOP10": ["factory_default"],
    "QFN24": ["package_outline", "front_end"],
    "RJ45HR": ["schematic"],
    "SMB": ["cathode"],
    "SO8EP": ["land_pattern"],
    "SOD123": ["cathode"],
    "SOT23": ["bat54a_common_anode"],
    "TC2030": ["pad_signals"],
    "XTAL5032_4P": ["parameters"],
    "XTAL_MC306": ["internal_connection"],
}

# Part libraries whose review note says "Waiting on a decision": questions no
# document can answer, because the thing they depend on has not been designed
# yet. These are not unread datasheets and must not be filed as if they were.
# The difference is whether reading something would settle it.
WAITING_ON_A_DECISION: dict[str, str] = {}

# Part libraries whose review note still says "Needs a human eye": a figure in
# a manufacturer's document that nobody has read. Everything that was on this
# list has been fetched, rendered and read - CONFIRMED_FROM_A_RENDER is where
# each one went, with the crop that settles it. It stays here, empty, because
# the next part added to this board will land on it.
NEEDS_A_HUMAN_EYE: dict[str, str] = {}
