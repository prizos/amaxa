"""
What the common checks in hw/checks/ need to know that is specific to cpu1.
"""

# Still being built: some nets wait for blocks not drawn yet (design.json's
# `pending`), and board.mk says ROUTING := incomplete.
COMPLETE = False

# Checks that must actually run for this board, common and board-specific.
EXPECTED_CHECKS = 45

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
}

# Part libraries whose review note still says "Needs a human eye": things no
# machine here can confirm against a manufacturer's drawing.
NEEDS_A_HUMAN_EYE: dict[str, str] = {
    "LQFP144": "which supply pin each of datasheet Figure 13's decoupling values belongs to",
    "XTAL_MC306": "that the crystal is between pads 1 and 4, as KiCad's footprint has it",
    "LED0603": "pad 1 is the cathode, from KiCad's convention not KENTO's drawing",
    "TC2030": "the pad-to-signal table against Tag-Connect's own SWD pinout",
}
