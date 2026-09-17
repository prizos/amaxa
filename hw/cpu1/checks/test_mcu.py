"""
The MCU against the rails it is given.

Only the logic rail exists as a design value so far; VDDA and VREF+ join when the
MCU core lands, and each one gets checked against the part's own limits here.
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
