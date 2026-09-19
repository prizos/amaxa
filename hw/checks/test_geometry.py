"""
Checks on where things ended up.

Everything else reads the netlist, which says what is connected but not how far
apart it is. These read the placed board. A decoupling capacitor at the far end
of the board is connected to exactly the right net and does nothing useful.

Proximity rules are a board's own, in `<board>/checks/`.
"""


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


def test_no_two_vias_share_a_hole(pcb_text):
    """
    Every via is a hole a drill visits once.

    Two vias at the same coordinate are one hole asked for twice. The board
    file takes both, the plot looks right, and the drill file carries the same
    coordinate twice - which a fab will either merge silently or query. The
    generator produced twenty-seven of them on cpu1, all from routes that
    branch at a layer change: each branch asked for the via it needed and
    neither knew about the other.

    Read off the finished board rather than off the generator's list, because
    the generator is the thing being checked.
    """
    import re
    from collections import Counter

    places = Counter(
        (round(float(x), 4), round(float(y), 4))
        for block in re.findall(r"\n\t\(via\n(?:\t\t[^\n]*\n)+\t\)", pcb_text)
        for x, y in re.findall(r"\(at ([-\d.]+) ([-\d.]+)\)", block)
    )
    doubled = [f"  ({x:g}, {y:g}): {n} vias" for (x, y), n in sorted(places.items()) if n > 1]
    assert not doubled, "Vias sharing a hole:\n" + "\n".join(doubled)
