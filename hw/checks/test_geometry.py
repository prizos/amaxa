"""
Checks on where things ended up.

Everything else reads the netlist, which says what is connected but not how far
apart it is. These read the placed board. A decoupling capacitor at the far end
of the board is connected to exactly the right net and does nothing useful.

Proximity rules are a board's own, in `<board>/checks/`.
"""

import math
import re
import sys

import pytest


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


def test_no_two_designators_are_printed_over_each_other(pcb_text):
    """
    Every reference designator can be read.

    Silkscreen is how a board is assembled and how it is debugged, and a
    designator printed over its neighbour is the same as no designator at all.
    A fixed offset from each part puts them in exactly that position wherever
    parts are close together: cpu1 had twenty-six such pairs in the comparator
    and input-network fields, and the only way to find out was to look.

    The boxes are derived from the board file - each designator's placed
    position, its text size, and how many characters it has - so this measures
    the silkscreen that will be printed rather than the offsets that were asked
    for. A designator over a part's *outline* is untidy and still legible; this
    is about the ones over other text.
    """
    import math
    import re

    boxes = []
    for block in pcb_text.split("\n\t(footprint ")[1:]:
        at = re.search(r"\n\t\t\(at ([-\d.]+) ([-\d.]+)(?: ([-\d.]+))?\)", block)
        field = re.search(
            r'\(property "Reference" "([^"]+)"\s*\(at ([-\d.]+) ([-\d.]+)(?: [-\d.]+)?\)'
            r'[\s\S]*?\(size ([\d.]+) ([\d.]+)\)',
            block,
        )
        if not (at and field):
            continue
        name, lx, ly, w, h = field.groups()
        ox, oy = float(at.group(1)), float(at.group(2))
        turn = math.radians(float(at.group(3) or 0))
        x = ox + float(lx) * math.cos(turn) + float(ly) * math.sin(turn)
        y = oy - float(lx) * math.sin(turn) + float(ly) * math.cos(turn)
        half_w, half_h = len(name) * float(w) * 0.72 / 2, float(h) / 2
        boxes.append((name, x - half_w, y - half_h, x + half_w, y + half_h))

    assert boxes, "no reference designators on the board"
    clashes = [
        f"  {a[0]} and {b[0]}"
        for i, a in enumerate(boxes)
        for b in boxes[i + 1:]
        if a[1] < b[3] and b[1] < a[3] and a[2] < b[4] and b[2] < a[4]
    ]
    assert not clashes, "Designators printed over each other:\n" + "\n".join(sorted(clashes))


# KiCad's two-pad polarised symbols - Device:D, Device:D_Zener, Device:D_TVS,
# Device:LED - all put the cathode on pin 1, and their footprints mark it with
# a silkscreen bar reaching past that pad. The manufacturers do not have to
# agree, and one of them does not: KENTO number the LED's terminals the other
# way round (see parts/LED0603/evidence/polarity.png). That is only safe while
# the board's own silkscreen says which end the cathode goes, because that mark
# - not a pad number - is what an assembler orients a two-terminal part by.
CATHODE_PAD = "1"
POLARISED = ("Device:D", "Device:LED")


def test_every_polarised_part_marks_its_cathode_on_the_silkscreen(pcb_text, design):
    """
    A diode's silkscreen bar is on the end its netlist calls the cathode.

    Two-terminal parts are not placed by pad number. The machine orients them
    by the polarity mark on the part against the polarity mark on the board,
    so a footprint whose bar sits at the wrong end fits, passes DRC, builds,
    and lights nothing - or clamps backwards.

    KENTO's drawing for this board's LEDs numbers terminal 1 as the anode,
    where KiCad's symbol and footprint both call pad 1 the cathode. The two
    conventions disagree and the board is still right, but only because the
    silkscreen is what decides. This is that silkscreen.
    """
    symbols = {address: part["symbol"] for address, part in design["parts"].items()}

    problems = []
    for block in pcb_text.split("\n\t(footprint ")[1:]:
        address = re.search(r'\(property "address" "([^"]+)"', block)
        if not address or not symbols.get(address.group(1), "").startswith(POLARISED):
            continue
        pads = {m.group(1): (float(m.group(2)), float(m.group(3)))
                for m in re.finditer(r'\(pad "(\d)"[^\n]*\n\s*\(at ([-\d.]+) ([-\d.]+)', block)}
        silk = [(float(x), float(y)) for x, y in re.findall(
            r"\((?:start|end|xy) ([-\d.]+) ([-\d.]+)\)",
            "".join(m.group(0) for m in re.finditer(r"\(fp_(?:line|poly)(?:.*?)\n\t\t\)", block, re.S)
                    if '"F.SilkS"' in m.group(0)))]
        if len(pads) != 2 or not silk:
            problems.append(f"  {address.group(1)}: {len(pads)} pads, {len(silk)} silkscreen points")
            continue

        cathode = pads[CATHODE_PAD][0]
        anode = pads["2" if CATHODE_PAD == "1" else "1"][0]
        low, high = min(p[0] for p in silk), max(p[0] for p in silk)
        # How far the silkscreen reaches out past each pad, along the part's
        # axis. A polarity bar is the end that sticks out further.
        if cathode < anode:
            past_cathode, past_anode = cathode - low, high - anode
        else:
            past_cathode, past_anode = high - cathode, low - anode
        if past_cathode <= past_anode:
            problems.append(
                f"  {address.group(1)}: the silkscreen reaches {past_anode:.2f} mm past "
                f"the anode and {past_cathode:.2f} mm past the cathode on pad {CATHODE_PAD}")
        elif past_cathode < 0.3:
            problems.append(f"  {address.group(1)}: only {past_cathode:.2f} mm of "
                            "silkscreen past the cathode - not a mark anyone can place by")

    assert problems == [], (
        "Polarised parts whose silkscreen does not mark the cathode:\n" + "\n".join(problems)
        + "\nSee <board>/parts/*/LED*.md."
    )


def _point_to_segment(point, a, b) -> float:
    """How close a point comes to a line segment, not to its endpoints."""
    (px, py), (ax, ay), (bx, by) = point, a, b
    dx, dy = bx - ax, by - ay
    if dx == 0.0 and dy == 0.0:
        return math.dist(point, a)
    along = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.dist(point, (ax + along * dx, ay + along * dy))


def test_the_board_has_mounting_holes_and_nothing_is_in_them(pcb_text, board_dir):
    """
    Every declared mounting hole is on the board, with clear copper around it.

    The holes are circles on the edge layer, which is how an unplated hole is
    milled - so they carry no net and DRC has no pad to measure clearance
    from. That makes this the only thing standing between a hole and the track
    someone routes through it later.

    The margin is the hole's own radius plus a screw head's worth: an M3 washer
    is 7 mm across, so 3.5 mm from the centre is what has to stay empty for the
    fastener, never mind the drill.
    """
    sys.path.insert(0, str(board_dir.parent / "tools"))
    from mcu_pins import load_source

    description = load_source(board_dir / "layout.py", f"{board_dir.name}_layout_holes")
    holes = description.BOARD.get("mounting_holes", ())
    if not holes:
        pytest.skip(f"{board_dir.name} declares no mounting holes")

    circles = {(round(float(x), 3), round(float(y), 3)) for x, y in
               re.findall(r"\(gr_circle\s*\(center ([-\d.]+) ([-\d.]+)\)", pcb_text)}
    missing = [(x, y) for x, y, _ in holes if (round(x, 3), round(y, 3)) not in circles]
    assert not missing, f"mounting holes declared but not on the board: {missing}"

    copper = [(float(a), float(b), float(c), float(d)) for a, b, c, d in
              re.findall(r"\(segment\s*\(start ([-\d.]+) ([-\d.]+)\)\s*\(end ([-\d.]+) ([-\d.]+)\)",
                         pcb_text)]
    vias = [(float(a), float(b)) for a, b in
            re.findall(r"\(via\s*\(at ([-\d.]+) ([-\d.]+)\)", pcb_text)]

    fouled = []
    for hx, hy, diameter in holes:
        keep = max(3.5, diameter)
        for x1, y1, x2, y2 in copper:
            # The whole track, not its two ends. A long segment running
            # straight over a hole has both endpoints well clear of it, and
            # that is exactly the track this check exists to find - "the only
            # thing standing between a hole and the track someone routes
            # through it later", which it could not see.
            near = _point_to_segment((hx, hy), (x1, y1), (x2, y2))
            if near < keep:
                fouled.append(f"  a track passes {near:.1f} mm "
                              f"from the hole at ({hx:g}, {hy:g})")
                break
        for vx, vy in vias:
            if math.dist((hx, hy), (vx, vy)) < keep:
                fouled.append(f"  a via is {math.dist((hx,hy),(vx,vy)):.1f} mm "
                              f"from the hole at ({hx:g}, {hy:g})")
                break
    assert not fouled, "Mounting holes with copper in the way:\n" + "\n".join(sorted(set(fouled)))
