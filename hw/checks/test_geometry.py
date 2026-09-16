"""
Checks on where things ended up.

Everything else reads the netlist, which says what is connected but not how far
apart it is. These read the placed board. A decoupling capacitor at the far end
of the board is connected to exactly the right net and does nothing useful.
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


def test_every_part_is_on_the_board(footprints, board_outline):
    """
    A part whose origin is outside the outline was never placed.

    The board file happily holds footprints off the edge of the board, and the
    only sign is that the render looks sparse.
    """
    min_x, min_y, max_x, max_y = board_outline
    outside = [
        f"  {fp['designator']} at ({fp['x']:.1f}, {fp['y']:.1f})"
        for fp in footprints
        if not (min_x <= fp["x"] <= max_x and min_y <= fp["y"] <= max_y)
    ]
    assert not outside, (
        f"Parts outside the board outline "
        f"[{min_x:.1f}, {min_y:.1f}] to [{max_x:.1f}, {max_y:.1f}]:\n"
        + "\n".join(outside)
    )


def test_nothing_is_stacked_at_the_origin(footprints):
    """
    Two parts at the same spot means the placement table missed them.

    atopile drops unplaced footprints in a grid, so this catches the case where
    the layout description and the board have drifted apart in a way the layout
    engine did not notice.
    """
    seen: dict[tuple[float, float], list[str]] = {}
    for fp in footprints:
        seen.setdefault((fp["x"], fp["y"]), []).append(fp["designator"])
    stacked = {pos: refs for pos, refs in seen.items() if len(refs) > 1}
    assert not stacked, f"Parts sharing a position: {stacked}"


def test_the_board_is_actually_routed(pcb_text):
    """
    There is copper on the board, and the pour has been filled.

    Every other check here passes on a board that was generated but never laid
    out: the pads carry their nets from the netlist whether or not anything
    joins them. Only DRC notices, and only if it is run. This says plainly that
    the layout step happened.
    """
    tracks = pcb_text.count("(segment")
    vias = pcb_text.count("(via")
    filled = pcb_text.count("(filled_polygon")

    assert tracks, "The board has no tracks. Run `make -C hw layout`."
    assert vias, "The board has no vias, so nothing reaches the ground plane."
    assert filled, (
        "The ground pour has an outline but no copper in it. kicad-cli cannot "
        "fill zones; `make -C hw layout` runs tools/fill_zones.py, which can."
    )
