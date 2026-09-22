"""
The MCU against the rails it is given.

**This file's own promise came due and nobody noticed.** It used to end "VDDA
and VREF+ join when the MCU core lands, and each one gets checked against the
part's own limits here". The core landed; they never joined, and this file
still holds one check.

They are checked, but elsewhere and for other reasons:

  - VDDA against the part's supply range is the same 1.62 to 3.6 V as VDD, so
    the logic rail's check below covers it - VDDA is that rail less the bead,
    which only makes it smaller.
  - VDDA's *drop* across that bead, and VREF+ against VDDA, are in
    `test_power.py::test_the_reference_is_below_the_analog_supply_it_sits_under`,
    which is where the reference's own tolerance already was.

So the sentence is gone rather than the checks being moved here to satisfy
it. What is worth keeping is the shape of the mistake: a docstring that
describes future work reads as a description of present work the moment that
future arrives.
"""


def test_logic_rail_is_inside_the_mcu_supply_range(spec):
    """
    The 3.3 V rail, at both ends of its tolerance, is inside what the MCU accepts.

    The STM32H743 runs from 1.62 to 3.6 V. A rail designed to 3.3 V +/-5 % has
    plenty of room at the top, and this is what says so rather than assuming it —
    and what fails if the rail's tolerance or the part ever change.
    """
    rail_low, rail_high = spec("rail.3v3", "voltage")
    mcu_low, mcu_high = spec("mcu", "supply_voltage")
    assert mcu_low <= rail_low and rail_high <= mcu_high, (
        f"The 3.3 V rail spans {rail_low:.3f} to {rail_high:.3f} V but the MCU "
        f"accepts {mcu_low:.2f} to {mcu_high:.2f} V."
    )
