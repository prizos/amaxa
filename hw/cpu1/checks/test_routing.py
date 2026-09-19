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
    """Every track as ((x1, y1), (x2, y2), layer, net)."""
    out = []
    for block in re.findall(r"\n\t\(segment\n(?:\t\t[^\n]*\n)+\t\)", pcb_text):
        start = re.search(r"\(start ([-\d.]+) ([-\d.]+)\)", block)
        end = re.search(r"\(end ([-\d.]+) ([-\d.]+)\)", block)
        layer = re.search(r'\(layer "([^"]+)"\)', block)
        net = re.search(r"\(net (\d+)\)", block)
        if start and end and layer and net:
            out.append(((float(start.group(1)), float(start.group(2))),
                        (float(end.group(1)), float(end.group(2))),
                        layer.group(1), net_names.get(net.group(1), "")))
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
    back = [(a, b) for a, b, layer, _ in segments if layer == "B.Cu"]

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
    return {plane["net"]: plane["outline"] for plane in planes}


@pytest.fixture(scope="module")
def stitchers(pcb_text, design) -> list[tuple[float, float]]:
    """
    Where the ground plane and the supply planes are tied together.

    A capacitor with one pad on ground and the other on a rail. These are the
    only places a return current can cross between the two inner layers, so
    they are what a track changing layer has to stay near.
    """
    pad_net = {tuple(node): net for net, nodes in design["nets"].items() for node in nodes}
    out = []
    for block in pcb_text.split("\n\t(footprint ")[1:]:
        address = re.search(r'\(property "address" "([^"]+)"', block)
        at = re.search(r"\n\t\t\(at ([-\d.]+) ([-\d.]+)", block)
        if not (address and at):
            continue
        sides = {pad_net.get((address.group(1), pad)) for pad in ("1", "2")}
        if GROUND in sides and sides & {"3V3", "5V"}:
            out.append((float(at.group(1)), float(at.group(2))))
    assert out, "no capacitor ties the ground plane to a supply plane"
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
        if net not in plane_outlines:
            continue
        if not _inside(plane_outlines[net], (x, y)):
            lost.append(f"  {net} via at ({x:g}, {y:g}) is outside the {net} plane")
    assert not lost, (
        "Vias reaching for a plane that is not underneath them:\n" + "\n".join(lost)
    )


def test_every_layer_change_has_a_way_back_for_its_return_current(
    spec, vias, stitchers
):
    """
    Each signal that changes layer, against the nearest tie between the planes.

    A track on the front is referenced to the ground plane below it; one on the
    back is referenced to the supply islands. A via between them moves the
    signal and leaves its return current to find its own way across, and the
    only crossings are the decoupling capacitors. How far the return has to
    detour is the loop it makes, and the loop is what radiates.

    This is the check that is easiest to satisfy by accident and hardest to
    notice failing: nothing about a long detour is visible in the layout, in
    DRC, or on a working bench.
    """
    _, allowed = spec("routing", "reference_change_distance")
    far = []
    for x, y, net in vias:
        if net in PLANES:
            continue                      # a plane via is the return path
        detour = min(math.dist((x, y), tie) for tie in stitchers)
        if detour > allowed:
            far.append(f"  {net} changes layer at ({x:g}, {y:g}), {detour:.1f} mm "
                       "from the nearest tie between the planes")
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
    return {"order": order, "planes": {plane["layer"] for plane in planes},
            "island": next(p["layer"] for p in planes if p["net"] == "5V")}


def test_no_signal_beside_a_supply_island_crosses_its_edge(
    pcb_text, net_names, plane_outlines, plane_layers
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

    order, planes = plane_layers["order"], plane_layers["planes"]
    at = order.index(plane_layers["island"])
    facing = {
        order[n] for n in (at - 1, at + 1)
        if 0 <= n < len(order) and order[n] not in planes
    }
    assert facing, (
        f"the islands are on {plane_layers['island']} with a plane on both "
        "sides, so no signal references them - which makes this check vacuous "
        "rather than passing"
    )

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
        if _inside(island, a) != _inside(island, b):
            crossing.append(f"  {name} on {layer.group(1)} crosses the island edge "
                            f"between ({a[0]:g}, {a[1]:g}) and ({b[0]:g}, {b[1]:g})")
    assert not crossing, (
        f"Tracks on {sorted(facing)} changing what they are referenced to:\n"
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
    for a, b, _, net in segments:
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
