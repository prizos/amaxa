"""
What the common checks in hw/checks/ need to know that is specific to cpu1.
"""

# Still being built: some nets wait for blocks not drawn yet (design.json's
# `pending`), and board.mk says ROUTING := incomplete.
COMPLETE = False

# Checks that must actually run for this board, common and board-specific.
EXPECTED_CHECKS = 110

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
    ("buck5.c_couple", "capacitance"): (
        "the coupling capacitor into the feedback node. Its value comes from "
        "the LM5164 datasheet's Equation 26, which is a figure with no text "
        "layer; 56 pF is the value TI's own reference design uses with the "
        "same 3.3 nF ramp capacitor. It sets how long a light-load sleep "
        "interval can get before the feedback divider discharges it, which is "
        "not a rating anything here can bound. See SO8EP.md"
    ),
}

# Part libraries whose review note still says "Needs a human eye": things no
# machine here can confirm against a manufacturer's drawing.
NEEDS_A_HUMAN_EYE: dict[str, str] = {
    "LQFP144": "which supply pin each of datasheet Figure 13's decoupling values belongs to",
    "XTAL_MC306": "that the crystal is between pads 1 and 4, as KiCad's footprint has it",
    "LED0603": "pad 1 is the cathode, from KiCad's convention not KENTO's drawing",
    "TC2030": "the pad-to-signal table against Tag-Connect's own SWD pinout",
    "SO8EP": (
        "the LM5164's ripple-injection equations 24 to 26, and its exposed "
        "pad's dimensions - both are figures with no text layer, so the "
        "coupling capacitor and the land pattern came from TI's own reference "
        "design and LCSC's footprint instead"
    ),
    "SOT223": (
        "the P-FET's pin-out drawing, which is an image. 1 = G, 2 = D, 3 = S "
        "came from LCSC's symbol; getting it wrong puts the gate on the supply"
    ),
    "SMB": "pad 1 is the cathode, the banded end",
    "MSOP10": (
        "the threshold DAC's factory-default EEPROM value, which is what makes "
        "an unprogrammed board trip as it powers up. Its datasheet is a "
        "scanned-font PDF nothing here could read, and the pinout came from two "
        "other sources instead"
    ),
    "SOT23": (
        "the BAT54A's common anode on pin 3, from its marking diagram rather "
        "than a package drawing. A common-cathode part in its place would tie "
        "both fault lines together"
    ),
    "SOD123": "pad 1 is the cathode, from the package drawing not the maker's",
}
