"""
What the routing generators produce, checked against what they promised.

The layout is written as generators rather than coordinates, which moves the
mistakes from "one via in the wrong place" to "every via in the wrong place for
the same reason". Both of the defects these were written for were of that
second kind, and neither showed up as a DRC violation: DRC asks whether the
copper is legal, and these ask whether it does anything.

Everything here reads the finished board file.
"""

import math
import re
import sys
from pathlib import Path

import pytest

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / "tools"))
from layout_lib import point_to_segment  # noqa: E402
from symbols import symbol_pin_names  # noqa: E402

GROUND = "GND"
PLANES = ("GND", "3V3", "5V")


@pytest.fixture(scope="module")
def net_names(pcb_text) -> dict[str, str]:
    return dict(re.findall(r'\n\t\(net (\d+) "([^"]*)"\)', pcb_text))


@pytest.fixture(scope="module")
def vias(pcb_text, net_names) -> list[tuple[float, float, str]]:
    """Every via as (x, y, net)."""
    out = []
    for block in re.findall(r"\n\t\(via\n(?:\t\t[^\n]*\n)+\t\)", pcb_text):
        at = re.search(r"\(at ([-\d.]+) ([-\d.]+)\)", block)
        net = re.search(r"\(net (\d+)\)", block)
        if at and net:
            out.append((float(at.group(1)), float(at.group(2)),
                        net_names.get(net.group(1), "")))
    assert out, "no vias on the board"
    return out


@pytest.fixture(scope="module")
def segments(pcb_text, net_names) -> list:
    """Every track as ((x1, y1), (x2, y2), layer, net, width)."""
    out = []
    for block in re.findall(r"\n\t\(segment\n(?:\t\t[^\n]*\n)+\t\)", pcb_text):
        start = re.search(r"\(start ([-\d.]+) ([-\d.]+)\)", block)
        end = re.search(r"\(end ([-\d.]+) ([-\d.]+)\)", block)
        layer = re.search(r'\(layer "([^"]+)"\)', block)
        net = re.search(r"\(net (\d+)\)", block)
        width = re.search(r"\(width ([\d.]+)\)", block)
        if start and end and layer and net and width:
            out.append(((float(start.group(1)), float(start.group(2))),
                        (float(end.group(1)), float(end.group(2))),
                        layer.group(1), net_names.get(net.group(1), ""),
                        float(width.group(1))))
    return out


@pytest.fixture(scope="module")
def stitch_vias(vias, segments) -> list:
    """
    The vias whose only job is to reach a plane, as opposed to the ones a route
    uses to change layer.

    The board file does not say which is which, and the difference matters: a
    via a route uses has copper on both layers and may be anywhere, while one
    that exists to meet a plane has copper only on the front and is useless if
    the plane is not underneath it. What separates them is exactly that - a
    track on the back layer.
    """
    back = [(a, b) for a, b, layer, _, _ in segments if layer == "B.Cu"]

    def on_the_back(point) -> bool:
        # Anywhere along a track, not only at its ends: a route that runs
        # straight past a via it drops through has no vertex there, and the
        # first version of this counted seven such vias as stitches.
        return any(_near_segment(point, a, b) < 0.05 for a, b in back)

    return [v for v in vias if not on_the_back((v[0], v[1]))]


def _near_segment(point, a, b) -> float:
    """How close a point comes to a line segment."""
    ax, ay = b[0] - a[0], b[1] - a[1]
    length = ax * ax + ay * ay
    if not length:
        return math.dist(point, a)
    along = max(0.0, min(1.0, ((point[0] - a[0]) * ax + (point[1] - a[1]) * ay) / length))
    return math.dist(point, (a[0] + along * ax, a[1] + along * ay))


@pytest.fixture(scope="module")
def pad_places(pcb_text) -> set:
    """Where every pad sits on the board, rounded, for spotting a track's end."""
    out = set()
    for block in pcb_text.split("\n\t(footprint ")[1:]:
        at = re.search(r"\n\t\t\(at ([-\d.]+) ([-\d.]+)(?: ([-\d.]+))?\)", block)
        if not at:
            continue
        ox, oy = float(at.group(1)), float(at.group(2))
        angle = math.radians(float(at.group(3) or 0.0))
        for pad in block.split("(pad ")[1:]:
            here = re.search(r"\(at ([-\d.]+) ([-\d.]+)", pad)
            if not here:
                continue
            px, py = float(here.group(1)), float(here.group(2))
            out.add((round(ox + px * math.cos(angle) + py * math.sin(angle), 3),
                     round(oy - px * math.sin(angle) + py * math.cos(angle), 3)))
    return out


@pytest.fixture(scope="module")
def plane_outlines(board_dir) -> dict[str, list]:
    """Each plane's outline, from the layout that drew it."""
    sys.path.insert(0, str(board_dir.parent / "tools"))
    from mcu_pins import load_source

    description = load_source(board_dir / "layout.py", "cpu1_layout_routing")
    planes = getattr(description, "PLANES", None) or [description.PLANE]
    # Keyed by net *and layer*, because two pours can share a net: this board
    # grounds In1.Cu and In4.Cu, and keying on the net alone kept whichever
    # came last, so half the ground on the board was never asked about. The
    # bare net name still resolves, to the first pour that carries it, for the
    # checks that want "the 5 V island" and do not care which layer it is on.
    out: dict[str, list] = {}
    for plane in planes:
        out.setdefault(plane["net"], plane["outline"])
        out[f"{plane['net']} on {plane['layer']}"] = plane["outline"]
    return out


@pytest.fixture(scope="module")
def stitchers(pcb_text, design, plane_layers, plane_outlines) -> list[tuple[float, float]]:
    """
    Where the ground plane and the supply planes are tied together.

    A capacitor with one pad on ground and the other on a rail. These are the
    only places a return current can cross between the two inner layers, so
    they are what a track changing layer has to stay near.

    **A capacitor only counts where both pours it is meant to join exist
    underneath it.** Two things were being counted that join nothing. A
    GND-to-5V capacitor ties ground to the 5 V *island*, which is a pour on an
    outer layer and nobody's reference - it is not a crossing between planes
    at all, and there were fifty-nine of those in this list against four that
    even sat over the island. And a capacitor outside a plane's own outline
    ties ground to that supply's track, not to its pour. The docstring of
    `test_every_layer_change_has_a_way_back_for_its_return_current` described
    both filters; neither was implemented, and all sixty-three capacitors went
    to the detour measurement.

    So the supply nets here are the ones the stackup says are references, and
    each capacitor has to sit inside that net's pour.
    """
    pad_net = {tuple(node): net for net, nodes in design["nets"].items() for node in nodes}
    supplies = {net for net in plane_layers["plane_nets"] if net != GROUND}
    assert supplies, "no supply plane in this stackup for anything to tie to"

    out = []
    for block in pcb_text.split("\n\t(footprint ")[1:]:
        address = re.search(r'\(property "address" "([^"]+)"', block)
        at = re.search(r"\n\t\t\(at ([-\d.]+) ([-\d.]+)", block)
        if not (address and at):
            continue
        sides = {pad_net.get((address.group(1), pad)) for pad in ("1", "2")}
        joined = sides & supplies
        if GROUND not in sides or not joined:
            continue
        here = (float(at.group(1)), float(at.group(2)))
        # **This filter excludes nothing on this board**, and the docstring
        # above used to credit it as one of two that narrow the set. Measured:
        # all 53 placed ground-to-3V3 capacitors are inside, because the 3V3
        # pour is `_pour_outline()` - the whole board less the jack's notch -
        # so the only place it could exclude anything is that notch. The other
        # filter, dropping ground-to-5V capacitors, removes 14 and does the
        # work. This one is kept for a board whose supply pour is a real
        # island rather than a full layer, which is what the 5 V one is.
        outline = plane_outlines.get(next(iter(joined)))
        if outline and not _inside(outline, here):
            continue                      # over that supply's track, not its pour
        out.append(here)
    assert out, "no capacitor ties the ground plane to a supply plane"
    return out




def _edge_crossings(polygon, a, b) -> list[tuple[float, float]]:
    """
    Every point where the segment a-b crosses the polygon's boundary.

    Not "are the two ends on the same side": a track running straight through
    an island leaves its reference on the way in and takes it back on the way
    out, and both ends are outside. HALL_2 and HALL_3 do exactly that, in at
    the island's south edge and out at its north, and an endpoint test saw
    neither of the two crossings.
    """
    out = []
    for (x1, y1), (x2, y2) in zip(polygon, polygon[1:] + polygon[:1]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        ex, ey = x2 - x1, y2 - y1
        denominator = dx * ey - dy * ex
        if abs(denominator) < 1e-12:
            continue                      # parallel, including running along it
        s = ((x1 - a[0]) * ey - (y1 - a[1]) * ex) / denominator
        u = ((x1 - a[0]) * dy - (y1 - a[1]) * dx) / denominator
        if 0.0 <= s <= 1.0 and 0.0 <= u <= 1.0:
            out.append((a[0] + s * dx, a[1] + s * dy))
    return out


def _inside(polygon, point) -> bool:
    x, y = point
    crossings = 0
    for (x1, y1), (x2, y2) in zip(polygon, polygon[1:] + polygon[:1]):
        if (y1 > y) != (y2 > y) and x1 + (y - y1) * (x2 - x1) / (y2 - y1) > x:
            crossings += 1
    return crossings % 2 == 1


def test_no_via_reaches_for_a_plane_that_is_not_there(stitch_vias, plane_outlines):
    """
    Every via on a plane net lands where that plane actually is.

    A via to a plane is a hole with a stub attached, and if the plane is
    somewhere else that is all it is. The stitching generator assumed a pad on
    a plane net could always find its plane below it, and put four 5 V vias
    thirty millimetres from the 5 V island - over ground and 3V3, joined to
    nothing. Nothing complained: the board had the right number of vias, DRC
    found no violation, and the pads stayed unrouted.

    The plane's own outline is what decides, read from the layout that drew it.
    Vias a route uses to change layer are a different thing and are left alone;
    `stitch_vias` says how the two are told apart.
    """
    lost = []
    for x, y, net in stitch_vias:
        # Every pour carrying this net, not one of them. Two layers ground
        # this board and the outlines were keyed by net alone, so only the
        # last of the two was ever asked about.
        pours = [outline for key, outline in plane_outlines.items()
                 if key.startswith(f"{net} on ")]
        if not pours:
            continue
        if not any(_inside(outline, (x, y)) for outline in pours):
            lost.append(
                f"  {net} via at ({x:g}, {y:g}) is outside all "
                f"{len(pours)} {net} pours"
            )
    assert not lost, (
        "Vias reaching for a plane that is not underneath them:\n" + "\n".join(lost)
    )


def test_every_layer_change_has_a_way_back_for_its_return_current(
    spec, vias, segments, stitchers, plane_layers
):
    """
    Each signal that changes layer, against the nearest crossing its return has.

    A track's return runs in the nearest ground plane to it. A via that moves
    the signal from one layer to another moves its return too, and if the two
    layers' nearest grounds are different planes the return has to get between
    them somehow. How far it detours to do that is the loop it makes, and the
    loop is what radiates.

    **What counts as a crossing depends on the stackup, so it is derived.** If
    the two planes are both ground, any via on the ground net joins them - all
    vias here are through-holes. If one of them is a supply plane, the only
    crossings are the capacitors that tie that supply to ground, and then a
    capacitor only counts where its own pour actually exists. That filter now
    lives in the `stitchers` fixture, next to the code that applies it; this
    docstring described it for two commits while the fixture went on handing
    over every GND-to-rail capacitor on the board, most of which tie ground to
    an outer-layer island and cross nothing at all.

    This is the check that is easiest to satisfy by accident and hardest to
    notice failing: nothing about a long detour is visible in the layout, in
    DRC, or on a working bench.
    """
    _, allowed = spec("routing", "reference_change_distance")
    grounds, planes = plane_layers["grounds"], plane_layers["planes"]
    apart = plane_layers["apart"]

    def reference(layer):
        """The plane a signal on this layer returns through: the nearest one."""
        return min(planes, key=lambda plane: apart(layer, plane))

    # **Which layers the route uses, not which layers the via spans.** Every
    # via here is a through-hole, and this used to reason from that: a layer
    # change is F to B, so the reference change is the same for all of them.
    # It is a property of the via and not of the route. Eight routes on this
    # board drop from F.Cu to In3.Cu and stop there, and their reference goes
    # from a ground plane to the supply plane - a change that needs a tie
    # between the two, not a ground via. They were being measured against 211
    # ground vias, which are irrelevant to that hop.
    ground_vias = [(x, y) for x, y, net in vias if net == GROUND]
    by_net: dict[str, list] = {}
    for start, end, layer, net, _ in segments:
        by_net.setdefault(net, []).append((start, end, layer))

    far = []
    for x, y, net in vias:
        if net in PLANES:
            continue                      # a plane via is the return path
        here = (x, y)
        layers = {
            layer for start, end, layer in by_net.get(net, [])
            if point_to_segment(here, start, end) < 1e-3
        }
        references = {reference(layer) for layer in layers}
        if len(references) <= 1:
            continue                      # one plane serves both ends of the hop
        if all(r in grounds for r in references):
            crossings, what = ground_vias, "ground via"
        else:
            crossings, what = stitchers, "tie between the planes"
        assert crossings, f"no {what} on this board"
        detour = min(math.dist(here, c) for c in crossings)
        if detour > allowed:
            far.append(
                f"  {net} changes from {sorted(layers)} at ({x:g}, {y:g}), "
                f"{detour:.1f} mm from the nearest {what}"
            )
    assert not far, (
        f"Layer changes further than {allowed:g} mm from a way back:\n" + "\n".join(far)
    )


@pytest.fixture(scope="module")
def plane_layers(board_dir) -> dict:
    """Which copper layer each plane is on, and the board's layer order."""
    sys.path.insert(0, str(board_dir.parent / "tools"))
    from mcu_pins import load_source

    description = load_source(board_dir / "layout.py", "cpu1_layout_layers")
    planes = getattr(description, "PLANES", None) or [description.PLANE]
    count = description.BOARD.get("copper_layers", 4)
    order = ["F.Cu"] + [f"In{n}.Cu" for n in range(1, count - 1)] + ["B.Cu"]
    # How far apart the copper layers are, which is what decides which plane a
    # signal is really referenced to. Adjacency by index says In3.Cu touches
    # two planes and stops there; the stackup says one is 0.175 mm away and
    # the other 0.43, and the near one takes most of the return.
    dielectrics = description.BOARD["stack"]
    assert len(dielectrics) == len(order) - 1, "a dielectric between every pair of layers"

    def apart(a: str, b: str) -> float:
        low, high = sorted((order.index(a), order.index(b)))
        return sum(d["thickness"] for d in dielectrics[low:high])

    # A pour on an outer layer is local copper, not a reference plane: the
    # layer still carries routing, and whatever is under it is what its
    # signals return through. So the outer layers are always signal layers,
    # and only the inner pours count as references. Without this, moving the
    # 5 V island to B.Cu would have quietly taken B.Cu off the list of layers
    # that must have ground beside them.
    poured = {plane["layer"] for plane in planes}
    outer = {"F.Cu", "B.Cu"}
    references = poured - outer
    return {"order": order,
            "planes": references,
            "poured": poured,
            "grounds": {p["layer"] for p in planes if p["net"] == GROUND} - outer,
            "signals": [l for l in order if l in outer or l not in poured],
            "plane_nets": {p["net"]: p["layer"] for p in planes
                           if p["layer"] in references},
            "apart": apart,
            "island": next(p["layer"] for p in planes if p["net"] == "5V")}


def test_every_signal_layer_has_a_ground_plane_beside_it(plane_layers):
    """
    Every layer that carries a signal has solid ground immediately next to it.

    This is the property that decides whether a return current has anywhere to
    go. A signal layer whose only neighbouring plane is a supply layer has its
    field terminating on copper that is cut into islands, and the return has
    to find its way across an island's edge through whatever capacitor happens
    to join the two - which is the four-layer problem this board had, and
    which it still had on six until the inner assignments were swapped.

    "Immediately next to" means no other plane in between. A ground two
    dielectrics away with a supply plane between does not count: the field
    stops at the first plane it meets.
    """
    order, planes = plane_layers["order"], plane_layers["planes"]
    grounds = plane_layers["grounds"]
    assert grounds, "this board is meant to have a ground plane"

    stranded = []
    for layer in plane_layers["signals"]:
        at = order.index(layer)
        beside = set()
        for step in (-1, 1):
            n = at + step
            while 0 <= n < len(order) and order[n] not in planes:
                n += step                      # skip other signal layers
            if 0 <= n < len(order):
                beside.add(order[n])
        if not beside & grounds:
            stranded.append(f"  {layer}: nearest planes {sorted(beside)}, none of them ground")
    assert not stranded, (
        "Signal layers with no ground plane beside them:\n" + "\n".join(stranded)
        + "\nTheir return current has to cross a supply plane's island edges."
    )


def test_no_signal_beside_a_supply_island_crosses_its_edge(
    pcb_text, net_names, plane_outlines, plane_layers, stitchers, spec
):
    """
    No signal on a layer the supply islands reference crosses from over one
    island to over another.

    A signal's return runs in the nearest plane, and at an island's edge that
    plane changes. A track crossing it hands its return from the 3V3 pour to
    the 5 V island halfway along, and those two are joined only where a
    capacitor joins them.

    *Which* layer that is comes from the stackup, not from this file. It used
    to be B.Cu, because on four layers the back faced the islands. On six it
    faces solid ground and the layer at risk is the signal layer on the other
    side of the islands - which is the one the motion feedback runs on. A check
    that names a layer is a check that silently stops applying when the
    stackup changes, and this one did.

    The plane nets themselves are exempt: a 5 V track leaving the 5 V island is
    the island's own connection to the rest of the board, not a signal losing
    its reference.
    """
    island = plane_outlines.get("5V")
    assert island, "this board is meant to have a 5 V island"

    planes = plane_layers["planes"]
    on = plane_layers["island"]
    if on not in planes:
        # The island is nobody's reference, so nothing crosses its edge and
        # the walk below has nothing to walk. That is where the 5 V island
        # ended up and the reason it moved - see the layer table in README.md.
        #
        # But "nobody's reference" has to be *measured*, not taken from the
        # same layout.py that says where the pour is. Comparing one declared
        # constant against another is how this returned for thirty-seven dead
        # lines while still being counted as coverage of island-edge
        # crossings. What makes a poured layer a signal layer rather than a
        # reference is that signals are routed on it, and the board file says
        # so: count the track on it that belongs to no plane net.
        routed = 0.0
        for block in re.findall(r"\n\t\(segment\n(?:\t\t[^\n]*\n)+\t\)", pcb_text):
            layer = re.search(r'\(layer "([^"]+)"\)', block)
            net = re.search(r"\(net (\d+)\)", block)
            start = re.search(r"\(start ([-\d.]+) ([-\d.]+)\)", block)
            end = re.search(r"\(end ([-\d.]+) ([-\d.]+)\)", block)
            if not (layer and net and start and end) or layer.group(1) != on:
                continue
            if net_names.get(net.group(1), "") in PLANES:
                continue
            routed += math.dist(
                (float(start.group(1)), float(start.group(2))),
                (float(end.group(1)), float(end.group(2))))
        assert routed > 0, (
            f"the 5 V island is on {on}, which carries no signal track: that "
            f"makes it a reference plane with a split in it, and the walk "
            f"below is what has to run instead of this branch"
        )
        return

    # Which signal layers the islands are the *nearest* plane to.
    #
    # This used to ask whether the layer had a ground plane on its other side
    # and exempt it if so - "a layer with solid ground hugging its other face
    # keeps a continuous return whatever the supply plane does". That ignores
    # the two numbers which decide it, and they are sitting in the stackup.
    # In3.Cu is **0.175 mm** from the islands and **0.43 mm** from the ground
    # below it, so about seven tenths of its return flows in the split plane
    # and the ground that was supposed to excuse the crossing carries the
    # minority. `facing` came out empty and the loop below walked nothing.
    #
    # Nearest is the whole mechanism - the sentence above is "the field stops
    # at the first plane it meets" - so nearest is what this asks, and there
    # is no threshold to pick.
    apart = plane_layers["apart"]
    facing = {
        layer for layer in plane_layers["signals"]
        if min(planes, key=lambda plane: apart(layer, plane)) == plane_layers["island"]
    }

    # What a crossing costs is the loop its return takes to follow it, and a
    # tie between the two pours nearby makes that a short hop. The board
    # already says how long a hop may be, for a track changing layer; this is
    # the same question and takes the same number. Only ties over the island
    # count - a capacitor tying ground to a 5 V *track* joins nothing here.
    _, allowed = spec("routing", "reference_change_distance")
    ties = [c for c in stitchers if _inside(island, c)]
    assert ties, "nothing ties the 5 V island to ground over the island itself"

    crossing = []
    for block in re.findall(r"\n\t\(segment\n(?:\t\t[^\n]*\n)+\t\)", pcb_text):
        layer = re.search(r'\(layer "([^"]+)"\)', block)
        net = re.search(r"\(net (\d+)\)", block)
        start = re.search(r"\(start ([-\d.]+) ([-\d.]+)\)", block)
        end = re.search(r"\(end ([-\d.]+) ([-\d.]+)\)", block)
        if not (layer and net and start and end) or layer.group(1) not in facing:
            continue
        name = net_names.get(net.group(1), "")
        if name in PLANES:
            continue
        a = (float(start.group(1)), float(start.group(2)))
        b = (float(end.group(1)), float(end.group(2)))
        for point in _edge_crossings(island, a, b):
            detour = min(math.dist(point, tie) for tie in ties)
            if detour > allowed:
                crossing.append(
                    f"  {name} on {layer.group(1)} crosses at "
                    f"({point[0]:.2f}, {point[1]:.2f}), {detour:.1f} mm from "
                    f"the nearest tie between the two pours"
                )
    assert not crossing, (
        f"Tracks on {sorted(facing)} handing their return across the island's "
        f"edge further than {allowed:g} mm from anywhere it can follow:\n"
        + "\n".join(crossing)
    )


def test_every_stub_is_short_enough_to_be_a_stub(
    spec, segments, stitch_vias, pad_places
):
    """
    The tracks the stitching generator draws from a pad to its via.

    They exist to get a surface pad down to a plane, and their length is
    inductance in series with whatever that pad was decoupling. The generator
    searches outward until it finds room, and without a limit it would keep
    searching: the point of the limit is that a pad which needs a long stub
    wants to be moved, not reached for.

    A stub runs from a pad to a via and nowhere else. A track on a plane net
    with a via at one end and open board at the other is a route - the 5 V leg
    that feeds the reference, say - and is not this check's business.
    """
    _, allowed = spec("routing", "stub_length")
    reaching = {(round(x, 3), round(y, 3)) for x, y, _ in stitch_vias}

    long_ones = []
    for a, b, _, net, _ in segments:
        if net not in PLANES:
            continue
        ends = [(round(p[0], 3), round(p[1], 3)) for p in (a, b)]
        if not any(end in reaching for end in ends):
            continue
        if not any(end in pad_places for end in ends):
            continue                      # a route from the plane, not a stub
        length = math.dist(a, b)
        if length > allowed:
            long_ones.append(f"  {net}: {length:.2f} mm at ({a[0]:g}, {a[1]:g})")
    assert not long_ones, (
        f"Stubs longer than {allowed:g} mm:\n" + "\n".join(long_ones)
    )


# TI's land pattern for the LM5164's DDA0008B package draws four 0.2 mm vias on
# a 1.3 mm grid inside the exposed pad; parts/SO8EP/evidence/land_pattern.png is
# that drawing. Microchip's LAN8742A pad is the PHY's only ground connection and
# its only path for heat, and their outline gives the pad's size but no via
# pattern - see parts/QFN24/evidence/. Four is the number the one manufacturer
# who publishes it publishes.
THERMAL_VIAS = 4
# The footprint says so itself: KiCad names a land pattern with a thermal pad
# "...-1EP...". Picking these out by pad area instead caught an inductor's
# terminals and a push button, which are large pads and not thermal ones.
EXPOSED_PAD = re.compile(r"-\d+EP")


@pytest.fixture(scope="module")
def exposed_pads(pcb_text) -> dict[str, tuple[float, float, float, float, str]]:
    """Every pad big enough to be a thermal pad, as (x0, y0, x1, y1, net)."""
    out = {}
    for block in pcb_text.split("\n\t(footprint ")[1:]:
        address = re.search(r'\(property "address" "([^"]+)"', block)
        at = re.search(r"\n\t\t\(at ([-\d.]+) ([-\d.]+)(?: ([-\d.]+))?\)", block)
        if not (address and at and EXPOSED_PAD.search(block.split("\n", 1)[0])):
            continue
        ox, oy = float(at.group(1)), float(at.group(2))
        angle = math.radians(float(at.group(3) or 0.0))
        biggest = max(
            (float(s.group(1)) * float(s.group(2))
             for s in re.finditer(r"\(size ([\d.]+) ([\d.]+)\)", block)), default=0.0)
        for pad in block.split("(pad ")[1:]:
            number = re.match(r'"([^"]*)"', pad)
            here = re.search(r"\(at ([-\d.]+) ([-\d.]+)", pad)
            size = re.search(r"\(size ([\d.]+) ([\d.]+)\)", pad)
            on = re.search(r'\(net \d+ "([^"]*)"\)', pad)
            if not (number and here and size):
                continue
            w, h = float(size.group(1)), float(size.group(2))
            if w * h < biggest:
                continue
            px, py = float(here.group(1)), float(here.group(2))
            x = ox + px * math.cos(angle) + py * math.sin(angle)
            y = oy - px * math.sin(angle) + py * math.cos(angle)
            if round(math.degrees(angle)) % 180:
                w, h = h, w
            out[f"{address.group(1)}:{number.group(1)}"] = (
                x - w / 2, y - h / 2, x + w / 2, y + h / 2,
                on.group(1) if on else "")
    return out


def test_every_exposed_pad_has_its_thermal_vias(exposed_pads, vias):
    """
    A part's thermal pad reaches the ground plane, and not through one via.

    An exposed pad is the only path a PowerPAD or QFN has for heat, and on both
    of the parts here it is a ground connection as well. A pad soldered to
    copper that goes nowhere is a part that runs hot and a ground that is only
    as good as the pad's own island.

    The number comes from the one manufacturer who draws it: TI's land pattern
    for the LM5164 shows four. Microchip's LAN8742A outline gives the pad's
    size and no via pattern at all, which is why that part is still on the
    board's review list - but a pad with fewer vias than TI asks for is worth
    catching whoever made it.
    """
    thin = []
    for pad, (x0, y0, x1, y1, net) in sorted(exposed_pads.items()):
        assert net, f"{pad} is an exposed pad on no net at all"
        # The via has to be on the pad's own net, not merely inside its
        # outline. A via of some other net that happens to land in the
        # rectangle is copper the heat never reaches, and counting it made the
        # pad look connected while it was not.
        inside = [v for v in vias
                  if x0 <= v[0] <= x1 and y0 <= v[1] <= y1 and v[2] == net]
        if len(inside) < THERMAL_VIAS:
            thin.append(f"  {pad}: {len(inside)} vias on {net} inside "
                        f"{x1 - x0:.2f} x {y1 - y0:.2f} mm, wanted {THERMAL_VIAS}")
    assert not thin, (
        "Exposed pads without their thermal vias:\n" + "\n".join(thin)
        + "\nSee parts/SO8EP/evidence/land_pattern.png."
    )


# How far a track that decides a trip has to stay from a track that does not.
#
# Three dielectric heights between edges is the usual rule for keeping
# microstrip-to-microstrip coupling near a percent, and the height is the one
# this board is actually built with rather than a number typed here. What
# makes it matter on this board is that the comparator inputs are tapped
# *ahead* of the ADC filter, so nothing between the connector and the
# comparator removes anything: the TLV3501 has 6 mV of hysteresis and no
# external network, and its output latches the drive off through the trip bus.
SEPARATION_IN_HEIGHTS = 3


# How finely the run below is sampled. It has to be small against the
# separation being measured - a few tenths of a millimetre - and 0.05 mm is a
# third of the narrowest track this board draws.
SAMPLE = 0.05


def _run_alongside(a, b, a_width, b_width, within):
    """
    How far two tracks run within `within` of each other, edge to edge.

    Two changes from the axis-aligned version this replaces, both of which it
    got wrong rather than approximately right.

    It measured **centre to centre** while the limit is stated edge to edge -
    "three dielectric heights between edges" - so it admitted a pair whose
    copper was half of both widths closer than the derivation asks for. And it
    gave up unless both segments were axis-aligned, returning zero, which is
    never a violation: 249 of this board's 1286 segments run on a diagonal,
    including six of the sixty comparator-input ones, and every pair involving
    one of them was unmeasurable.

    Sampling handles any orientation, including two tracks that converge - the
    length reported is the length actually within the distance, which for a
    crossing is short and for a parallel run is the whole of it.
    """
    length = math.dist(a[0], a[1])
    if length == 0.0:
        return 0.0, float("inf")
    gap = (a_width + b_width) / 2
    steps = max(1, int(length / SAMPLE))
    run = best = 0.0
    closest = float("inf")
    for i in range(steps + 1):
        fraction = i / steps
        point = (a[0][0] + (a[1][0] - a[0][0]) * fraction,
                 a[0][1] + (a[1][1] - a[0][1]) * fraction)
        apart = point_to_segment(point, b[0], b[1]) - gap
        # `apart <= 0` is copper that touches or overlaps, the worst case
        # there is, and it used to fall into the else and reset the run -
        # scoring the worst geometry as not-alongside. Unreachable between two
        # nets on one layer because DRC holds them apart, but it was the wrong
        # way round.
        if apart < within:
            run += length / steps
            if run >= best:
                best, closest = run, min(closest, apart)
        else:
            run = 0.0
    return best, closest


def _backward_crosstalk(length, centres, height, swing, edge, velocity):
    """
    Roughly what an aggressor couples backward into a track beside it, in volts.

    The standard microstrip estimate: a coupling coefficient set by how far
    apart the two are compared with their height above the plane,

        Kb = 1 / 4 / (1 + (D / H) ** 2)

    and, for a run shorter than the critical length, a share of it in
    proportion to how much of the edge the run is - `2 * length` against the
    distance the edge travels while it rises.

    Approximate, and it reproduces the one case this board has measured: the
    8.55 mm of FAST4_SENSE that ran 0.55 mm from the RMII's transmit enable
    comes out at about 8 mV against a 6 mV threshold, which is the defect that
    was found and moved.
    """
    coefficient = 0.25 / (1.0 + (centres / height) ** 2)
    share = min(1.0, 2.0 * length / (edge * 1e9 * velocity))
    return coefficient * swing * share


def test_nothing_runs_alongside_a_raw_comparator_input(
    design, segments, board_dir, spec, layer_stack
):
    """
    A track that decides a trip keeps its distance from one that does not.

    The comparator taps are deliberately ahead of the ADC's anti-alias filter,
    so a millivolt coupled onto one of them arrives at the comparator intact.
    The part has 6 mV of hysteresis, nothing external adds any, and its output
    sets a latch that only firmware can clear - so crosstalk here is not an
    error in a reading, it is a drive that stops.

    This found `FAST4_SENSE` running 8.55 mm at 0.55 mm pitch beside the
    RMII's transmit enable on the back layer, with no ground between them. At
    a 1 ns edge that is about 12 mV onto a 6 mV threshold, and it would have
    looked exactly like a real over-current that happened whenever the network
    was busy.
    """
    sys.path.insert(0, str(board_dir.parent / "tools"))
    from mcu_pins import load_source

    description = load_source(board_dir / "layout.py", "cpu1_layout_separation")
    # Each layer sits its own distance from the plane that references it, and
    # that distance is the whole of the coupling coefficient's denominator.
    #
    # **This paragraph used to credit itself with a fix that changes nothing.**
    # It said reading `stack[0]` for every layer was "wrong by a factor of five
    # the moment one is routed on In2 at 0.43". Measured, `layer_stack` on this
    # board is F.Cu 0.1855, In3.Cu 0.175, B.Cu 0.1855 - so `max()` returns
    # 0.1855, which is `stack[0]`, which is exactly the number it replaced. And
    # the failure it named cannot happen: the fixture excludes every poured
    # inner layer, so In2.Cu is not in the dict at all and a tap routed there
    # would raise a KeyError below rather than silently use 0.43.
    #
    # It is kept because it is right in principle - a board with a thicker
    # inner signal layer than its outer prepreg would need it - and the
    # sentence now says what it does rather than what it saved.
    height_of = {layer: micro.height for layer, micro in layer_stack.items()}
    # The geometric net has to be cast at the widest of them, or a run on a
    # layer further from its plane is discarded before it is ever measured.
    wanted = SEPARATION_IN_HEIGHTS * max(height_of.values())

    # What decides it is millivolts, not millimetres. Three dielectric heights
    # is the geometry worth *looking* at; whether a particular run matters is
    # what it couples against what the comparator can tell apart, and a
    # package whose pins are half a millimetre apart forces a millimetre of
    # close running that no rule can remove and that couples a tenth of the
    # hysteresis. The old check compared the length against 1.0 mm, which was
    # not from anywhere and was doing this job badly.
    epsilon = description.BOARD["stack"][0]["epsilon_r"]
    effective = 0.475 * epsilon + 0.67
    velocity = 299.792458 / math.sqrt(effective)        # mm per nanosecond
    edge, _ = spec("trip", "aggressor_edge")            # the fastest, so the worst
    _, swing = spec("rail.3v3", "voltage")
    # The *least* hysteresis any comparator on this board has. `max` was the
    # most permissive part of a mixed set, which is the wrong end for a noise
    # margin - the comparator that trips first is the one with the least to
    # lose. All seven are identical today, so this changes no number.
    hysteresis = min(
        spec(address, "input_hysteresis")[0]
        for address, part in design["parts"].items()
        if part["symbol"].startswith("Comparator:")
    )

    inputs = {
        net for net, nodes in design["nets"].items()
        for address, pad in nodes
        if design["parts"][address]["symbol"].startswith("Comparator:")
        and symbol_pin_names(design["parts"][address]["symbol"]).get(pad) in ("+", "-")
    }

    # An aggressor has to switch. A net that reaches nothing but a DAC output,
    # a reference, a comparator input or a test pad carries a DC level and
    # cannot couple anything into anything - which matters here because the
    # threshold DAC's outputs leave its package on a 0.5 mm pitch, and no
    # routing rule can separate two pins that are 0.5 mm apart. Anything whose
    # family is not on this list counts as switching, so a part nobody thought
    # about is an aggressor rather than an exemption.
    static = ("Analog_DAC:", "Reference_Voltage:", "Comparator:", "Connector:TestPoint")
    quiet = {
        net for net, nodes in design["nets"].items()
        if all(design["parts"][address]["symbol"].startswith(static) for address, _ in nodes)
    }

    # How fast an aggressor can actually switch, which is not the same question
    # as how fast the fastest thing on the board switches.
    #
    # `trip.aggressor_edge` is 1 ns, the sharpest edge anywhere here, and
    # feeding it to every net overstates the ones that physically cannot rise
    # that fast. FAST4 is FAST4_SENSE through a 10 ohm into a 10 nF shunt:
    # its own network holds it to a 220 ns edge, three orders of magnitude off
    # the figure the model was giving it, and that is the difference between
    # 9.2 mV and 42 uV on the 12.4 mm the two run together.
    #
    # This replaces an exemption that said the same thing topologically - two
    # nets bridged by a two-terminal resistor are "the same signal" - and said
    # it far too broadly. Any resistor counted, so a comparator input with a
    # pull-up to a switching net would have been exempted outright, and the
    # arithmetic went on treating the exempted aggressor as the fastest edge
    # on the board while the exemption claimed it was slow. Now the slowness
    # is measured, from the same netlist, and only slows what is slow.
    nets_of: dict[str, list[str]] = {}
    for net, nodes in design["nets"].items():
        for address, _ in nodes:
            nets_of.setdefault(address, []).append(net)

    shunt: dict[str, list[str]] = {}
    series: dict[str, list[str]] = {}
    for address, part in design["parts"].items():
        ends = nets_of.get(address, [])
        if len(ends) != 2:
            continue
        for near, far in (ends, ends[::-1]):
            if part["symbol"] == "Device:C" and far in PLANES:
                shunt.setdefault(near, []).append(address)
            elif part["symbol"] == "Device:R":
                series.setdefault(near, []).append(address)

    # Worked out only for the nets actually asked about, and remembered. The
    # first version read every capacitor's value while building the table,
    # which made a dozen supply bypasses look "read" to the check that hunts
    # declared-but-unread parameters - a value used to answer a question
    # nobody asked is not read, it is touched.
    known: dict[str, float] = {}

    def slowest_edge(net: str) -> float:
        """Seconds: the 10-90 % edge this net's own RC permits."""
        if net not in known:
            if net not in series or net not in shunt:
                known[net] = edge         # nothing slows it; as fast as any
            else:
                resistance = min(spec(a, "resistance")[0] for a in series[net])
                capacitance = sum(spec(a, "capacitance")[1] for a in shunt[net])
                known[net] = max(edge, 2.2 * resistance * capacitance)
        return known[net]

    close = []
    for a_start, a_end, a_layer, a_net, a_width in segments:
        if a_net not in inputs:
            continue
        for b_start, b_end, b_layer, b_net, b_width in segments:
            if (b_layer != a_layer or b_net == a_net or b_net in PLANES
                    or b_net in inputs or b_net in quiet):
                continue
            # Cheap reject before sampling: two segments whose bounding boxes
            # are further apart than the limit cannot be within it.
            #
            # **In the same units the limit is in.** `wanted` is edge to edge
            # and `_run_alongside` subtracts half of both widths before
            # comparing, so a reject measured centre to centre threw away
            # every pair whose copper edges were inside the limit while their
            # centrelines were outside it - which is every violation drawn
            # with normal-width tracks. It hid a 12.5 mm run at 0.425 mm from
            # a comparator input, worth 10.8 mV onto a 6 mV threshold, and it
            # discarded the *longest* runs preferentially, because coupling
            # grows with length while the reject keys on separation.
            reach = wanted + (a_width + b_width) / 2
            if (min(a_start[0], a_end[0]) - max(b_start[0], b_end[0]) > reach
                    or min(b_start[0], b_end[0]) - max(a_start[0], a_end[0]) > reach
                    or min(a_start[1], a_end[1]) - max(b_start[1], b_end[1]) > reach
                    or min(b_start[1], b_end[1]) - max(a_start[1], a_end[1]) > reach):
                continue
            along, apart = _run_alongside(
                (a_start, a_end), (b_start, b_end), a_width, b_width, wanted)
            if along <= 0.0:
                continue
            centres = apart + (a_width + b_width) / 2
            coupled = _backward_crosstalk(along, centres, height_of[a_layer], swing,
                                          slowest_edge(b_net), velocity)
            if coupled > hysteresis:
                close.append(
                    f"  {a_net} on {a_layer} runs {along:.2f} mm alongside "
                    f"{b_net}, {apart:.2f} mm between their edges: about "
                    f"{coupled * 1e3:.1f} mV onto a {hysteresis * 1e3:g} mV threshold"
                )
    assert not close, (
        f"Raw comparator inputs closer than {wanted:.2f} mm "
        f"({SEPARATION_IN_HEIGHTS} x the {max(height_of.values()):g} mm the "
        f"furthest signal layer sits from its plane) to a foreign track:\n"
        + "\n".join(sorted(set(close)))
    )


def test_the_plane_edges_are_stitched(vias, board_dir):
    """
    No long stretch of board edge without a ground via behind it.

    The two ground planes and the supply plane between them are parallel
    plates with open edges, and a cavity 129 by 109 mm resonates at about
    540 MHz along and 640 MHz across in FR4 - inside the window CISPR 32
    measures, and driven by every switching current that flows in a plane.
    Stitching the grounds to each other round the perimeter is what damps it
    and what stops the edge radiating.

    This board had twelve ground vias within 10 mm of the plane's edge and
    **all twelve were on the west side**, by the PHY: one via per hundred and
    nineteen millimetres of perimeter. The ring the layout now generates is on
    a fourteen-millimetre pitch, a twentieth of a wavelength at 500 MHz, and
    skips candidates that land on something - so this asks that no stretch of
    edge is bare, not that every intended via exists.
    """
    sys.path.insert(0, str(board_dir.parent / "tools"))
    from mcu_pins import load_source

    description = load_source(board_dir / "layout.py", "cpu1_layout_stitching")
    pitch = description.STITCH_PITCH
    keepout = description.JACK_KEEPOUT

    # The pour's own outline, not the board's. The planes are inset from the
    # edge and notched around the jack, so walking a rectangle at the board
    # size asks about copper that is not there and misses the notch.
    outline = description._pour_outline()

    # A via damps an edge by being *at* it. This used to accept the nearest
    # ground via anywhere on the board, so a dense field ten millimetres
    # inboard answered for an edge with nothing on it - which is the exact
    # arrangement the check was written to catch.
    #
    # "At" is the ring's own inset plus a via, not one pitch. A pitch is
    # fourteen millimetres here, which let a via ten millimetres inboard go on
    # answering - the sentence above was still not what the code did. The ring
    # is generated at `inset`, so a via belonging to it is within that plus
    # its own diameter of the edge, and nothing else counts.
    at_the_edge = description.STITCH_INSET + description.VIA[0]

    def near_the_edge(point):
        return min(
            point_to_segment(point, a, b)
            for a, b in zip(outline, outline[1:] + outline[:1])
        ) <= at_the_edge

    grounds = [(x, y) for x, y, net in vias if net == GROUND and near_the_edge((x, y))]
    assert grounds, "no ground via within a pitch of the pour's edge"

    # Every edge walked at a fixed step *and* its far end, so the last stretch
    # of each side is sampled whatever the board measures. The old walk went
    # in fives from zero and only reached the far corner because 130 and 110
    # are both multiples of five.
    # How far a point on the edge may be from the nearest stitch. A ring on a
    # pitch of `pitch` puts every edge point within half a pitch of a via
    # along the edge, and `at_the_edge` - the inset plus a via, the furthest
    # from the edge a via can be and still count as on the ring - is the other
    # leg of that triangle. Nothing else goes into it. (This said "the ring's
    # own inset", which is the first term of `at_the_edge` and not the whole
    # of it: 7.16 mm rather than 7.28.)
    #
    # This was `1.5 * pitch` - twenty-one millimetres, three times the
    # spacing the wavelength argument asks for, from a factor that appeared
    # nowhere else and was justified nowhere. It hid an eleven-millimetre
    # bare stretch on the south edge where the generator had skipped two
    # candidates in a row.
    allowed = math.hypot(pitch / 2, at_the_edge)

    # Half a millimetre, not five. The distance to the nearest via changes no
    # faster than the walk moves, so a five-millimetre step could miss a bare
    # patch by two and a half - a third of the whole allowance. It was
    # under-reporting the true worst here by 0.08 mm.
    step = 0.5
    bare = []
    for a, b in zip(outline, outline[1:] + outline[:1]):
        length = math.dist(a, b)
        count = max(1, int(length / step))
        for i in range(count + 1):
            fraction = i / count
            here = (a[0] + (b[0] - a[0]) * fraction, a[1] + (b[1] - a[1]) * fraction)
            if keepout[0] <= here[0] <= keepout[2] and keepout[1] <= here[1] <= keepout[3]:
                continue
            if min(math.dist(here, g) for g in grounds) > allowed:
                bare.append(f"  ({here[0]:.1f}, {here[1]:.1f})")

    assert not bare, (
        f"Pour edge more than {allowed:.1f} mm from a ground via at the "
        f"edge:\n" + "\n".join(sorted(set(bare)))
    )


def _segment_gap(a_start, a_end, b_start, b_end) -> float:
    """Closest approach of two line segments, centreline to centreline."""
    if _crosses(a_start, a_end, b_start, b_end):
        return 0.0
    return min(point_to_segment(a_start, b_start, b_end),
               point_to_segment(a_end, b_start, b_end),
               point_to_segment(b_start, a_start, a_end),
               point_to_segment(b_end, a_start, a_end))


def _crosses(p1, p2, p3, p4) -> bool:
    """Whether two segments properly intersect."""
    def side(a, b, c):
        return ((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]))

    d1, d2 = side(p3, p4, p1), side(p3, p4, p2)
    d3, d4 = side(p1, p2, p3), side(p1, p2, p4)
    return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0))


def test_nothing_sits_on_the_fabricators_floor(vias, segments, board_dir, spec, pcb_text):
    """
    No copper within a fifth of the fabricator's minimum, and no hole inside
    the escape diagonal of the finest package on the board.

    **Two rules, because the two floors are not the same kind of number.** The
    copper clearance is published, so it takes the design margin in
    `routing.clearance_over_floor`. The hole-to-hole figure is not - the fab
    file says so - so holes are held to something the board derives instead,
    and that lands 7 um above the fab's own figure. A real bound, and it does
    catch what it was written for, but it is not "a fifth" and this sentence
    used to claim it was.

    `fab/pcbway.kicad_dru` says it in as many words: "These are the
    fabricator's floor, not a design target. A board that only just clears
    them is one the fab can make, not one that will come back reliably." DRC
    compares against those floors with `min`, so equality passes and the build
    is green and nothing anywhere says the board is sitting on them.

    Four pairs of vias sat at exactly **0.500 mm** hole to hole against a
    0.5 mm floor, and two back-layer tracks at exactly **0.100 mm** from a via
    of another net against a 0.1 mm floor. None was drawn by the stitching
    generator, which does this arithmetic properly - `clear()` works to
    `VIA_TO_VIA` and `COPPER_MARGIN`, both half as generous again. They were
    hand-written coordinates, which nothing held to anything but DRC.

    Both floors are read out of the fab's own rules file rather than repeated
    here, so a fabricator with different capabilities moves this check with
    them.
    """
    import re

    floors = (board_dir.parent / "fab" / "pcbway.kicad_dru").read_text()
    copper = float(re.search(r"\(constraint clearance \(min ([\d.]+)mm\)\)", floors).group(1))
    hole = float(re.search(r"\(constraint hole_to_hole \(min ([\d.]+)mm\)\)", floors).group(1))
    over, _ = spec("routing", "clearance_over_floor")

    sys.path.insert(0, str(board_dir.parent / "tools"))
    from mcu_pins import load_source

    description = load_source(board_dir / "layout.py", "cpu1_layout_margins")
    radius, drill = description.VIA[0] / 2, description.VIA[1]

    # Holes are held to the spacing this board's own generator builds to, not
    # to the fab's floor times a factor.
    #
    # `fab/pcbway.kicad_dru` says of the hole-to-hole figure that it is "not
    # published at the standard tier" and that the value there "predates that
    # reading and has no recorded source", so multiplying the design margin
    # onto it would be inventing twice. The copper clearance beside it does
    # take the margin, because 0.1 mm is published.
    #
    # But the floor plus a thousandth of a millimetre, which is what this
    # asked for two commits, is not a requirement either - it says only "not
    # exactly equal", while the function is called "nothing sits on the
    # fabricator's floor" and its docstring promises a fifth clear of it.
    #
    # What sets it is the finest package on the board. Escaping a footprint
    # whose pads are on a 0.5 mm pitch puts two vias on that pitch's diagonal
    # whatever anybody intends - 0.707 mm centre to centre, 0.507 mm hole to
    # hole once the drill is taken off - and asking for more would be asking
    # the LQFP-144 to have coarser pins. Anything tighter than a package's own
    # escape diagonal is a choice rather than a package, and that is what this
    # catches: the four pairs at exactly 0.500 mm were hand-written
    # coordinates that beat the finest thing the board has to escape.
    #
    # The pitch is not written down here. KiCad puts it in the footprint's own
    # name - `LQFP-144_20x20mm_P0.5mm` - so the board file states it, and a
    # coarser board moves this on its own.
    #
    # Not `VIA_TO_VIA`, which was the previous attempt: that is the separation
    # the *stitching* generator keeps, 0.95 mm centre to centre, and holding
    # the whole board to it condemns sixty-odd perfectly ordinary package
    # escapes. Not `hole + 1e-3` either, which asked only that nothing sit
    # exactly on the floor while the function is called "nothing sits on the
    # fabricator's floor".
    pitches = [float(found) for found in
               re.findall(r'"[^"]*_P([\d.]+)mm[^"]*"', pcb_text)]
    assert pitches, "no footprint on this board states a pad pitch in its name"
    hole_floor = max(hole, min(pitches) * math.sqrt(2) - drill)

    tight = []
    for i, (x1, y1, net1) in enumerate(vias):
        for x2, y2, net2 in vias[i + 1:]:
            apart = math.dist((x1, y1), (x2, y2)) - drill
            if apart < hole_floor - 1e-6:
                tight.append(
                    f"  vias on {net1} and {net2} are {apart:.3f} mm hole to "
                    f"hole at ({x1:g}, {y1:g}), inside the {hole_floor:.3f} mm "
                    f"that escaping this board's finest {min(pitches):g} mm "
                    f"pitch on the diagonal already needs"
                )

    for x, y, net in vias:
        for start, end, _, track, width in segments:
            if track == net:
                continue
            gap = point_to_segment((x, y), start, end) - radius - width / 2
            if gap < copper * over - 1e-9:
                tight.append(
                    f"  a {track} track passes {gap:.3f} mm from a {net} via at "
                    f"({x:g}, {y:g}), against a {copper:g} mm floor"
                )

    # **And track to track, which this never measured.** The sentence at the
    # top says "no copper within a fifth of the fabricator's minimum" and the
    # two loops above cover via-to-via and via-to-track only. The population
    # it was written for - "hand-written coordinates, which nothing held to
    # anything but DRC" - is mostly tracks, and DRC passes anything above the
    # fab's own 0.1 mm, so a pair 12 um above the floor was invisible.
    #
    # Same layer and different nets only: two segments of one net touch by
    # design, and copper on different layers is a stackup question rather
    # than an etch one.
    by_layer: dict[str, list] = {}
    for start, end, layer, track, width in segments:
        by_layer.setdefault(layer, []).append((start, end, track, width))
    for layer, here in by_layer.items():
        for i, (a_start, a_end, a_net, a_width) in enumerate(here):
            for b_start, b_end, b_net, b_width in here[i + 1:]:
                if a_net == b_net:
                    continue
                gap = _segment_gap(a_start, a_end, b_start, b_end) \
                    - a_width / 2 - b_width / 2
                if gap < copper * over - 1e-9:
                    tight.append(
                        f"  {a_net} and {b_net} run {gap:.3f} mm apart on "
                        f"{layer} near ({a_start[0]:g}, {a_start[1]:g}), "
                        f"against a {copper:g} mm floor"
                    )
    assert not tight, (
        f"Copper within {over:g} times the fabricator's floor:\n"
        + "\n".join(sorted(set(tight)))
    )


def test_the_crossing_solver_finds_where_a_track_enters_and_leaves():
    """
    `_edge_crossings` against shapes whose answers are known by inspection.

    It is exercised nowhere else. The island it serves is on B.Cu, which is
    not a reference plane, so the check that uses it returns before reaching
    it - correctly, because a pour on an outer layer strands nobody, but that
    leaves forty lines of geometry that only a break-test ever runs. This is
    the direct test, so the solver is not trusted on the strength of a board
    that happens not to need it.

    The middle case is the one that matters: a track straight through a
    rectangle has **both ends outside it**, which is what the endpoint
    comparison this replaced could never see.
    """
    box = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
    cases = (
        ("in one side and out the other", (-1.0, 5.0), (11.0, 5.0), 2),
        ("entering and stopping inside", (-1.0, 5.0), (5.0, 5.0), 1),
        ("wholly inside", (2.0, 5.0), (8.0, 5.0), 0),
        ("wholly outside and clear", (-5.0, 5.0), (-2.0, 5.0), 0),
        ("a diagonal across a corner", (8.0, -1.0), (11.0, 2.0), 2),
        ("running along an edge", (2.0, 0.0), (8.0, 0.0), 0),
    )
    for what, a, b, expected in cases:
        found = _edge_crossings(box, a, b)
        assert len(found) == expected, (
            f"{what}: {len(found)} crossings, expected {expected} ({found})"
        )

    # And the point it reports is on the boundary, not merely between the ends.
    (x, y), = _edge_crossings(box, (-1.0, 5.0), (5.0, 5.0))
    assert abs(x) < 1e-9 and abs(y - 5.0) < 1e-9, f"crossed at ({x}, {y}), expected (0, 5)"



def test_the_generator_and_drc_resolve_an_overlapping_rule_the_same_way(board_dir, nets):
    """
    Where two rules match one net, the width the generator draws is the width
    DRC will hold that net to.

    **They resolve overlaps by different algorithms.** KiCad applies the
    *last* matching rule in the file - later rules override earlier ones -
    while `layout.py`'s `_width_for` takes the **maximum** over every match.
    Six patterns on this board overlap: `SW*` with `SW_5V`, `TRIP*` with
    `TRIP_LEVEL_*`, `BOARD_ID*` with `*_SENSE`, `USB_*` with the usb pair,
    `ETH_*` with the ethernet pairs, and `PWM*` with the safety chain.

    They agree today only because every later rule happens to be *wider* than
    the earlier one it overlaps, which makes last-match and maximum the same
    number. Nothing held them to that. A rule added or reordered so that a
    later one is narrower would have the generator draw a track wider than
    DRC requires - harmless - or, if the patterns were the other way round,
    draw one DRC then rejects, which is a build that fails a long way from
    its cause.

    This compares the two algorithms over every net actually on the board, so
    the coincidence has to keep holding or say so.
    """
    import fnmatch
    import re as _re

    text = (board_dir / "rules.kicad_dru").read_text()
    ordered: list[tuple[str, float]] = []
    for block in _re.findall(r"\(rule\b.*?\(severity", text, _re.S):
        width = _re.search(r"\(constraint track_width \(min ([\d.]+)mm\)\)", block)
        if not width:
            continue
        for pattern in _re.findall(r"A\.NetName == '([^']+)'", block):
            ordered.append((pattern, float(width.group(1))))
    assert ordered, "no track_width rules to compare"

    disagree = []
    for net in sorted(nets):
        matched = [(pattern, w) for pattern, w in ordered
                   if fnmatch.fnmatchcase(net, pattern)]
        if len(matched) < 2:
            continue
        last = matched[-1][1]                    # what KiCad applies
        widest = max(w for _, w in matched)      # what the generator draws
        if abs(last - widest) > 1e-9:
            disagree.append(
                f"  {net}: matches {[p for p, _ in matched]}; DRC applies the "
                f"last at {last:g} mm and the generator draws the widest at "
                f"{widest:g} mm"
            )
    assert not disagree, (
        "Nets where the rules file and the generator disagree:\n"
        + "\n".join(disagree)
        + "\nKiCad takes the last matching rule; `_width_for` takes the "
          "maximum. Reorder the rules so the two coincide, or narrow the "
          "overlap."
    )
