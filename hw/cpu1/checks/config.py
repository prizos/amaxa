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
    "analog inputs have no over-voltage protection": (
        "This board hands the power board's sensors 5VA, which reaches 5.2 V, "
        "and takes their outputs into TT_xx analog pins that ST's Table 20 "
        "caps at 4.0 V absolute - with no positive-injection allowance at all "
        "(Table 21 rates it at -5 to +0 mA). An op-amp rails to its own "
        "supply during exactly the over-current the trip chain exists for. "
        "`docs/research/07` called for clamps; they are not fitted and do not "
        "fit, and the requirement now sits on a board that does not exist "
        "yet."
    ),
    "the converters' capacitance is checked at nominal, and nothing on this "
    "board knows what DC bias does to it": (
        "Every ceramic capacitance check here - the 3V3 buck's 10 uF input "
        "minimum, its 20 to 68 uF D-CAP2 output window, the 5 V buck's 2.2 uF "
        "input - compares a nominal value and its tolerance against a "
        "datasheet requirement. A Class II ceramic at half its rated voltage "
        "is worth well under its nominal, and the parts here are exactly that "
        "case: buck3v3.c_in is a 22 uF 10 V X7R in 0805 sitting at 5 V. Two "
        "of the three requirements fail on any reasonable derating - 17.6 uF "
        "of tolerance-corner input becomes 8.8 against a 10 uF minimum - and "
        "the board already knows the effect exists, because the Ethernet "
        "reset capacitor's delay is argued with its capacitance 'derated to a "
        "third by its own DC bias'.\n\n"
        "What stops this being fixed rather than recorded is that no maker "
        "here publishes the curve. HRE's datasheet for CGA0805X7R226M100MT "
        "carries no bias data at all; Samsung's CL21 series PDF gives "
        "temperature coefficients and no bias characteristic - that data "
        "lives in their online tool, which `make offline` cannot reach and "
        "which is not a document to cite. Inventing a flat derating is worse "
        "than the gap: at 50 % the D-CAP2 window becomes unsatisfiable by any "
        "number of 22 uF parts, because three of them exceed its 68 uF "
        "ceiling at the other tolerance corner. The number has to be real.\n\n"
        "Resolving it means either parts whose datasheets plot capacitance "
        "against bias - Murata and TDK do, and JLCPCB stock some - or a "
        "measurement on the first assembled board. Until then the 3V3 rail's "
        "input ripple and its loop stability are both unverified."
    ),
    "the bus terminations cannot take their own driver's output if anyone "
    "fits them": (
        "Both terminations ship behind a jumper that is open, so a board as "
        "delivered is not affected - but they exist to be closed, and closing "
        "one runs the resistor past its rating. The figures are now recorded "
        "and the arithmetic is in "
        "`test_a_bus_termination_survives_the_fault_its_transceiver_declares`, "
        "which prints them.\n\n"
        "The THVD1450 drives up to 3.5 V differential into 54 ohm, so across "
        "the 120 ohm this board fits that is 103 mW in a part rated 62.5 - "
        "past the absolute maximum, not merely past the board's own 50 % "
        "derating. The TCAN1044V drives up to 3.3 V, which puts 46 mW into "
        "each of the two 60.4 ohm halves: inside the 62.5 mW absolute rating "
        "and past the 31 mW derated one.\n\n"
        "Only the fault case was ever computed, and the open jumper excused "
        "it, so the configuration these parts exist for was never evaluated. "
        "Resolving it means a package with the power to do the job - 120 ohm "
        "at 103 mW wants a 1206 to keep the derating - or splitting each "
        "termination across several 0402s, or a stated transmit duty cycle "
        "this board has nowhere to declare. All three are decisions, and the "
        "column the chain stands in is already full."
    ),
    "the trip budget closes only because nothing is left for the tap filter "
    "M6 has still to draw": (
        "`trip.budget` is 50 ns and its own words are 'how long a half bridge "
        "survives a shoot-through' - which is not the instant the buffer lets "
        "go, but the instant the gate line is actually low. Nothing was "
        "counting the difference. When a trip puts the '541s into high "
        "impedance the line is discharged by its pull-down alone, and at the "
        "10 k those started at, the worst line measured 59 ns to reach a valid "
        "low: more than the entire budget, on top of the 25 ns the chain "
        "spends getting there.\n\n"
        "The pull-downs are 1.2 k now, which is as low as the buffer's own "
        "50 mA total allows with eight lines on a package, and that brings the "
        "fall to 24.5 ns with 10 pF allowed for the far side. The sum is then "
        "12.9 + 7 + 5.0 + 24.5 = 49.7 ns of 50 - it closes, by three hundred "
        "picoseconds, and the 40 % `trip.reserved_share` holds back for M6's "
        "anti-alias tap is entirely gone.\n\n"
        "It cannot be closed on this board. Five nanoseconds of fall wants "
        "244 ohm, which is 114 mA out of one '541 against its 50 mA total. "
        "The line's fall belongs to the far side: a gate driver with its own "
        "input pull-down makes this disappear, and this board cannot assume "
        "one. So the requirement goes to the power board, next to the analog "
        "clamps - and until M6 is drawn against a real number rather than a "
        "reserved fraction, the tap filter has no time to spend."
    ),
    "the comparator taps share a node with the ADC filter, so a fast edge "
    "reaches them 17 to 29 per cent low": (
        "The taps are on the unfiltered side of each input network and the "
        "design says so repeatedly - 'ahead of everything, so it is fast'. "
        "Being on the unfiltered side of a series resistor is not the same as "
        "being unfiltered: the capacitor is a shunt branch on the *same node*, "
        "and the power board drives that node through up to the 2 ohm "
        "`header.source_impedance` promises. That makes the tap a lead-lag "
        "network - unity at DC, so nothing static notices, and R/(Rs+R) to a "
        "step.\n\n"
        "9.9/(2+9.9) = 0.832, so a fast fault edge arrives 17 % low and the "
        "effective trip point sits 20 % *above* where the DAC set it, for the "
        "131 ns the node takes to recover. The trip budget is 50 ns, so the "
        "comparator decides deep inside that window, and "
        "`trip.threshold_tolerance` is 12 %. FAST4 - the DC-link "
        "over-voltage channel - is worst precisely because it was given a "
        "second independent network for redundancy: two 10 ohm branches in "
        "parallel are 4.95, which is 29 % low and a 40 % error over 153 ns.\n\n"
        "No value fixes it. The 10 ohm and the 10 nF are jointly fixed by the "
        "converter's charge injection and the 1-2 MHz corner; 100 ohm with "
        "1 nF holds the same corner and brings the error to 2 %, but a 1 nF "
        "reservoir against the converter's own 4 pF sampling capacitor leaves "
        "1.5 LSB in the 236 ns window where half of one is allowed. Isolating "
        "the tap properly needs a buffer, or the comparator thresholds need to "
        "be specified dynamically rather than at DC. Either is a decision.\n\n"
        "`test_the_filter_does_not_load_the_tap_it_sits_beside` does the "
        "arithmetic and prints it on every run."
    ),
}

# Checks that must actually run for this board, common and board-specific.
EXPECTED_CHECKS = 196

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
    "LQFP144": ["power_supply_scheme", "thermal_characteristics",
                "power_dissipation_at_85c"],
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
