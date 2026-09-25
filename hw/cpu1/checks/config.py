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
    "brown-out leaves the PWM driving with nothing watching it": (
        "On a loss of supply the over-current comparators lose their "
        "specified 5 V supply **76 microseconds before** the PWM buffers "
        "lose their 3V3 supply, and for all of that window this board emits "
        "whatever its timers are producing into a power stage that has its "
        "own supply and its own charged DC link. `sim/brown_out.cir.in` "
        "measures it; nothing else on this board could, because every check "
        "that touches the rails compares steady-state numbers.\n"
        "      The ordering is not an accident of values, it is the "
        "topology: 3V3 comes from a converter whose input is the 5 V rail, "
        "and that converter holds on until its input falls to its UVLO less "
        "its hysteresis - as low as 2.90 V - while the comparators on the "
        "same rail are specified only to 2.70. Whatever the two rails' "
        "capacitors are, the thing that drives a bridge is fed through the "
        "thing that stops one.\n"
        "      **The MCU's brown-out reset does not close it.** When the "
        "comparators lose their supply, 3V3 is still at 2.88 V, above BOR3's "
        "2.68 V falling edge - the highest of the four selectable levels - "
        "so the MCU is guaranteed still running and still holding "
        "`PWM_ENABLE_N` low. And a BOR level is an option byte, which no "
        "check here could enforce even if the number were favourable.\n"
        "      What would close it: a supervisor on the 5 V rail asserting "
        "the trip latch, or the buffers' enable referenced to the "
        "comparators' rail rather than to the logic rail. Both are spin-2. "
        "Accepting it instead is a decision that belongs to whoever owns "
        "the machine this drives, and it is recorded here so that it is a "
        "decision rather than an oversight."
    ),
}

# Checks that must actually run for this board, common and board-specific.
EXPECTED_CHECKS = 216

# Parameters recorded in parts.py that nothing reads, each with the reason.
UNREAD_PARAMETERS: dict[tuple[str, str], str] = {
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
    ("safety.buffer1", "enable_time_max"): (
        "7 ns from the enable going low to the outputs driving again. Turning "
        "on is not time-critical - firmware chooses when - and the number that "
        "is, turning off, is disable_time_max, which the trip budget uses"
    ),
    ("safety.buffer2", "enable_time_max"): "as buffer1: turning on is not timed",
    ("safety.buffer2", "input_low_voltage_max"): (
        "0.8 V, against what the MCU's pins drive low to - which the pages of "
        "ST's datasheet read for this board do not state. The high side is "
        "checked; this end waits for V_OL, and for the same measurement at "
        "bring-up that VDDA's current needs. buffer1's copy of this figure is "
        "no longer excused: `sim/trip_chain.cir.in` reads it as the threshold "
        "its enable model switches at. That is not the comparison this "
        "exemption was about - the deck uses it as a property of the part, "
        "not as a bound on what drives it - but it is a reader, and the gate "
        "does not distinguish. The open question is the same one for both "
        "packages and it is recorded here"
    ),
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
                "analog_input_injection_current",
                "current_consumption_scheme",
                "vref_against_vdda",
                "rmii_timing", "rmii_conditions"],
    "MSOP10": ["factory_default", "absolute_maximum", "settling_and_its_load"],
    "TSOT23_6": ["uvlo_and_soft_start"],
    "QFN24": ["package_outline", "front_end"],
    "RJ45HR": ["schematic"],
    "SMB": ["cathode"],
    "SO8EP": ["land_pattern"],
    "SOD123": ["cathode"],
    "SOIC8": ["can_common_mode", "can_esd_ratings",
              "rs485_common_mode", "rs485_esd_ratings"],
    "SOT23": ["ref3030_electrical", "bat54a_common_anode", "bat54a_forward_voltage",
              "bat54a_reverse_current", "ref3030_dropout"],
    "SOT23_6": ["tlv3501_delay_vs_load", "tlv3501_output_drive",
                "tlv3501_offset", "tlv3501_typ_to_max"],
    "TSSOP20": ["lvc541a_current_ratings", "lvc541a_dc_limits"],
    "VSSOP8": ["test_load"],
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
