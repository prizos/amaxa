"""
What the common checks in hw/checks/ need to know that is specific to cpu1.
"""

# What is finished and what is not.
#
# `COMPLETE` was True for a while and that was wrong - not because the board
# is bad, but because the gate behind it tested two things ("no pending nets",
# "routing not marked incomplete") while the flag was read as a claim about
# six. Both of its original reasons had gone, which is why it moved; neither
# of them was the reason that mattered.
#
# BLOCKING is what mattered. A board that says it is unfinished now has to say
# what is unfinished, and a board that says it is finished has to have this
# empty, so neither statement can drift from the board again.
COMPLETE = False

BLOCKING: dict[str, str] = {
    "the 3V3 budget closes on fifteen milliamps, and two of its largest "
    "terms are not maximums": (
        "`test_each_rail_carries_no_more_than_it_is_budgeted` now adds the "
        "rail up off the netlist and prints it: 784.8 mA against an 800 mA "
        "band. That is the first time the number has been derived rather "
        "than typed, and it is the arithmetic that makes the gap visible.\n\n"
        "Fifteen milliamps of margin would be comfortable if the terms were "
        "all guaranteed. Two of the largest are not:\n\n"
        "  - the PHY's **102 mA is a typical**. The LAN8742A datasheet has "
        "no maximum supply current anywhere - Table 5.5 has no MIN/TYP/MAX "
        "columns at all, each row is labelled 'Typical', and section 5.4's "
        "preamble states supplies at nominal with no temperature. Absolute "
        "Maximum Ratings, Operating Conditions and the DC Specifications "
        "were all read and none of them bounds it. If the real part draws "
        "15 % more than typical at temperature, the rail is over.\n"
        "  - the seven comparators' **5 mA each is a 25 degC figure**. "
        "SBOS321E's electrical table header reads 'At T_A = 25 degC'; the "
        "rows in it that are specified over temperature say so individually "
        "and I_Q does not. Supply current against temperature exists only as "
        "Figure 12. That one is on the 5 V rail, which has 35 mA spare, so "
        "it is the smaller of the two worries.\n\n"
        "Resolving it means measuring both on the first assembled board, or "
        "widening `rail.3v3.current` and re-deriving the converter, the fuse "
        "and the FET from the wider figure - which the checks will do, "
        "because they already take the band rather than a typed sum. What it "
        "must not mean is leaving a rail sized from a typical without "
        "anybody having said so."
    ),
}

# Checks that must actually run for this board, common and board-specific.
EXPECTED_CHECKS = 201

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
    ("power.fuse", "interrupt_rating"): (
        "50 A against the fault current the supply can deliver, which is a "
        "property of whatever is wired to the terminal and not of this board. "
        "Recorded because it is what makes the part suitable for a rail that "
        "may be fed from a battery"
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
    ("safety.buffer1", "input_low_voltage_max"): (
        "0.8 V, against what the MCU's pins drive low to - which the pages of "
        "ST's datasheet read for this board do not state. The high side is "
        "checked; this end waits for V_OL, and for the same measurement at "
        "bring-up that VDDA's current needs"
    ),
    ("safety.buffer2", "input_low_voltage_max"): "as buffer1",
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
    "SOT23_5": ["tlv70233_electrical"],
    "LED0603": ["polarity"],
    "LQFP144": ["power_supply_scheme", "thermal_characteristics",
                "power_dissipation_at_85c",
                "analog_input_absolute_maximum",
                "analog_input_injection_current"],
    "MSOP10": ["factory_default"],
    "QFN24": ["package_outline", "front_end"],
    "RJ45HR": ["schematic"],
    "SMB": ["cathode"],
    "SO8EP": ["land_pattern"],
    "SOD123": ["cathode"],
    "SOIC8": ["can_common_mode", "can_esd_ratings",
              "rs485_common_mode", "rs485_esd_ratings"],
    "SOT23": ["bat54a_common_anode", "bat54a_forward_voltage",
              "bat54a_reverse_current", "ref3030_dropout"],
    "SOT23_6": ["tlv3501_delay_vs_load"],
    "TSSOP20": ["lvc541a_current_ratings"],
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
