"""
What the common checks in hw/checks/ need to know that is specific to led12.

Everything here is a deliberate, reviewable declaration: changing a number or a
list below is the act of accepting a change to what the board is checked
against, so it belongs in the same commit as whatever made it necessary.
"""

# Finished: no pending nets, and routing is complete.
COMPLETE = True

# Checks that must actually run for this board, common and board-specific
# together. Removing one, skipping one, or losing a whole file fails the suite
# until this is updated in the same commit.
EXPECTED_CHECKS = 49

# Parameters recorded in parts.py that no check and no deck consumes, each with
# the reason it is not a hole. Everything not named here must be read by
# something, which is what makes an entry cost something to add.
UNREAD_PARAMETERS = {
    ("power.q_rpp", "on_resistance"): (
        "the pass element's drop is under a millivolt at this board's 55 mA, so "
        "no margin depends on it. Recorded because a higher-current board would "
        "care, and the part would be chosen on it"
    ),
    ("power.q_rpp", "max_continuous_drain_current"): (
        "checked by hand at 4.3 A against a 1 A fuse: the fuse is the binding "
        "constraint and test_fuse_headroom covers that end"
    ),
    ("switch.q_switch", "max_continuous_drain_current"): (
        "115 mA against a measured 20 mA of LED current. The LED current is "
        "checked directly, twice, so this would restate it"
    ),
    ("power.tvs", "v_breakdown_max"): (
        "the two figures that bound the design are the stand-off voltage and "
        "the clamping voltage, and both are checked. Breakdown sits between "
        "them and constrains nothing on its own"
    ),
    ("power.c_hf", "capacitance"): (
        "decoupling, sized by convention rather than by a calculation this "
        "board makes. Its placement is checked instead, which is the property "
        "that actually matters for a 100 nF part"
    ),
    ("power.c_bulk", "capacitance"): (
        "the declared band is manufacturing tolerance only, and the number that "
        "would matter is the effective capacitance under DC bias — an X5R 1210 "
        "delivers roughly half its marked value at 12 V. Checking 47 uF +/-20% "
        "against anything would be checking a figure the part does not have on "
        "this rail. Recorded in parts/C1210/C1210.md, not modelled anywhere"
    ),
}

# Part libraries whose review note still says "Needs a human eye": pin mappings
# no machine here can confirm against a manufacturer drawing. Every one is a way
# to turn a board into scrap, and one says the board may short 3V3 to GND if its
# assumption is wrong. Clearing this list is a precondition for ordering.
NEEDS_A_HUMAN_EYE = {
    "LED0805": "pad 1 is the cathode, taken from the footprint rather than the drawing",
    "SMB": "pad 1 is the cathode (banded end)",
    "SOD123": "pad 1 is the cathode (banded end)",
    "SOT223": "the tab is bonded to pin 2 (VOUT) and not to ground",
    "SOT23": "the AO3407A pinout, taken from a distributor symbol",
}
