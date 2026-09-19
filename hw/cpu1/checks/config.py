"""
What the common checks in hw/checks/ need to know that is specific to cpu1.
"""

# Still being built: some nets wait for blocks not drawn yet (design.json's
# `pending`), and board.mk says ROUTING := incomplete.
COMPLETE = False

# Checks that must actually run for this board, common and board-specific.
EXPECTED_CHECKS = 160

# Parameters recorded in parts.py that nothing reads, each with the reason.
UNREAD_PARAMETERS: dict[tuple[str, str], str] = {
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
    ("analog.bead", "dc_resistance"): (
        "0.9 ohm against what the power board's sensors draw from 5VA, which is "
        "a property of a board that does not exist yet. The same gap as VDDA's "
        "bead, and the same answer: measure it at bring-up"
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
    ("buck5.c_couple", "capacitance"): (
        "the coupling capacitor into the feedback node. Equation 26 of the "
        "LM5164 datasheet has now been read - CB >= t / (3 x RFB1) - and it "
        "turns a *desired* load-transient settling time into a value rather "
        "than giving one. With this board's 158 k top resistor the fitted "
        "56 pF satisfies it up to 26.5 us. Nothing on this board states a "
        "settling requirement, so there is nothing to compare that against; "
        "note that TI's reference design gets 75 us from the same 56 pF only "
        "because its divider is 446 k. See SO8EP.md"
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
    "MSOP10": ["factory_default"],
    "QFN24": ["package_outline"],
    "SO8EP": ["land_pattern"],
    "TC2030": ["pad_signals"],
}

NEEDS_A_HUMAN_EYE: dict[str, str] = {
    "HDR2X26": (
        "the fifty-two-pin header's ordering code and its LCSC number. The "
        "stock figure on file is the forty-pin part's; the number here "
        "follows the series pattern and has not been looked up"
    ),
    "LQFP144": "which supply pin each of datasheet Figure 13's decoupling values belongs to",
    "XTAL_MC306": "that the crystal is between pads 1 and 4, as KiCad's footprint has it",
    "LED0603": "pad 1 is the cathode, from KiCad's convention not KENTO's drawing",
    "SMB": "pad 1 is the cathode, the banded end",
    "SOT23": (
        "the BAT54A's common anode on pin 3, from its marking diagram rather "
        "than a package drawing. A common-cathode part in its place would tie "
        "both fault lines together"
    ),
    "SOD123": "pad 1 is the cathode, from the package drawing not the maker's",
    "XTAL5032_4P": (
        "the crystal's ESR and ppm figures, which come from LCSC's parametric "
        "data rather than a datasheet nobody here could fetch. They are the "
        "whole reason this part was chosen over two cheaper ones"
    ),
    "RJ45HR": (
        "what pin 8 is, the 1500 V isolation figure, and the 0 to +70 degC "
        "rating on a board where every other part is the industrial grade. "
        "Hanrun's datasheet could not be fetched from any mirror reachable "
        "here, so all three come from LCSC's parametric data"
    ),
    "USBC16": (
        "whether the receptacle's shell overhangs the board edge, sits flush, "
        "or wants a notch in the outline. That is a question about an enclosure "
        "that does not exist yet, and no drawing here can settle it"
    ),
}
