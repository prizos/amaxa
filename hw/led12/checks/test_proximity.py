"""
Decoupling and support parts placed close to what they serve.

A hand-written table, and deliberately led12's own: on a board this size every
pairing is a judgement about one part. The control board replaces this with a
check derived from the netlist, pairing every supply pin with its capacitor.
"""

import math


def distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


# (part, what it serves, how far apart they may be in mm, why)
PROXIMITY = [
    ("power.c_bulk", "power.q_rpp", 15.0,
     "bulk capacitance belongs where the current enters, not across the board"),
    ("power.c_hf", "power.c_bulk", 10.0,
     "the high-frequency capacitor works with the bulk one, not instead of it"),
    ("rail.c_in", "rail.ldo", 10.0,
     "a regulator's input capacitor is only stable if it is close to the pin"),
    ("rail.c_out", "rail.ldo", 8.0,
     "and so is its output capacitor"),
    ("switch.c_debounce", "switch.q_switch", 12.0,
     "a long gate net picks up noise the capacitor is meant to remove"),
]


def test_capacitors_are_near_what_they_serve(position):
    """
    Decoupling that is far from its load is decoupling in name only.

    The netlist cannot tell the difference: a capacitor 40 mm away is on the
    same net as one 2 mm away. Only the placed board can.
    """
    far = []
    for part, serves, limit, why in PROXIMITY:
        gap = distance(position(part), position(serves))
        if gap > limit:
            far.append(f"  {part} is {gap:.1f} mm from {serves}, limit {limit} mm — {why}")
    assert not far, "Parts placed too far from what they serve:\n" + "\n".join(far)
