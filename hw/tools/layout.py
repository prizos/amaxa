#!/usr/bin/env python3
"""
Apply a board's placement and routing to the KiCad file tools/board.py wrote.

The board writer decides what is connected to what; it leaves every footprint at
the origin and the board unrouted. This takes a placement and a set of routes
written as data — see hw/led12/layout.py — and writes them in.

Two properties make it safe to run on every build:

  - It is idempotent. Everything it writes is tagged, and a second run removes
    what the first wrote before writing again. Positions and tracks therefore
    come from the description, never from accumulated edits.
  - It is deterministic. Object UUIDs are derived from what the object is, not
    from randomness, so a rebuild that changes nothing produces no diff.

Routes name pads symbolically, as `power.q_rpp:3` — the part's address and the
pad number — so moving a part in the placement table moves the tracks that
reach it. Literal coordinates are for the corners in between.

Every layer a route, via or plane names must exist on the board. A route on
In1.Cu of a two-layer board is refused, not written into a layer KiCad will
quietly drop.

    python3 tools/layout.py led12
"""

import argparse
import json
import math
import re
import sys
import uuid
from pathlib import Path

HW_DIR = Path(__file__).resolve().parent.parent

# Marks every object this script owns, so it can take them away again. KiCad
# has nowhere to put a custom attribute on a track, so the mark goes in the one
# field every object has: the first block of its UUID. Anything carrying it was
# written by this script and is safe to remove.
TAG = "amaxa-layout"
MARK = "a1a2a3a4"
NAMESPACE = uuid.UUID("6f3a1c2e-0b7d-4f8a-9c1d-2e5b7a9c4d10")


def stable_uuid(*parts) -> str:
    """A UUID that is the same for the same object every run, and recognisable."""
    digest = uuid.uuid5(NAMESPACE, "|".join(str(p) for p in parts)).hex
    return f"{MARK}-{digest[:4]}-{digest[4:8]}-{digest[8:12]}-{digest[12:24]}"


# --- reading the board -------------------------------------------------------


def sexp_blocks(text: str, head: str, start: int = 0) -> list[tuple[int, int]]:
    """(start, end) spans of every `(head ...)` block, outermost first."""
    spans = []
    for match in re.finditer(rf"\({re.escape(head)}[\s(]", text[start:]):
        i = start + match.start()
        if any(a <= i < b for a, b in spans):
            continue
        depth = 0
        for j in range(i, len(text)):
            if text[j] == "(":
                depth += 1
            elif text[j] == ")":
                depth -= 1
                if depth == 0:
                    spans.append((i, j + 1))
                    break
    return spans


class Board:
    def __init__(self, path: Path):
        self.path = path
        self.text = path.read_text()
        self.nets = {
            name: int(num)
            for num, name in re.findall(r'\(net (\d+) "([^"]*)"\)', self.text)
        }
        table = re.search(r"\(layers\n([\s\S]*?)\n\t\)", self.text)
        self.copper = re.findall(r'\(\d+ "([^"]+)" signal\)', table.group(1)) if table else []

    def require_layer(self, layer: str, what: str) -> None:
        """Refuse copper on a layer this board does not have."""
        if layer not in self.copper:
            sys.exit(f"{what} is on {layer}, but this board's copper layers are {self.copper}")

    def footprints(self) -> dict[str, dict]:
        """part address -> {span, origin, rotation, pads}."""
        out = {}
        for start, end in sexp_blocks(self.text, "footprint"):
            block = self.text[start:end]
            props = dict(re.findall(r'\(property "([^"]+)" "([^"]*)"', block))
            address = props.get("address")
            if not address:
                continue
            at = re.search(r"\(at ([-\d.]+) ([-\d.]+)(?: ([-\d.]+))?\)", block)
            pads: dict[str, tuple[float, float]] = {}
            boxes: list[tuple[float, float, float, float]] = []
            for pad_start, pad_end in sexp_blocks(block, "pad"):
                pad = block[pad_start:pad_end]
                name = re.match(r'\(pad "([^"]*)"', pad).group(1)
                pad_at = re.search(r"\(at ([-\d.]+) ([-\d.]+)", pad)
                # Several footprints repeat a pad number (a switch's two poles,
                # a regulator's tab). The first is the one routes anchor to.
                pads.setdefault(name, (float(pad_at.group(1)), float(pad_at.group(2))))
                size = re.search(r"\(size ([\d.]+) ([\d.]+)\)", pad)
                boxes.append((
                    float(pad_at.group(1)), float(pad_at.group(2)),
                    float(size.group(1)) if size else 0.9,
                    float(size.group(2)) if size else 0.9,
                ))
            # Each silkscreen line as the box it occupies, in the same frame.
            # Its own outline is not something a part's label has to dodge -
            # that is where a designator belongs - but a neighbour's is.
            silk = []
            for line_start, line_end in sexp_blocks(block, "fp_line"):
                line = block[line_start:line_end]
                if '"F.SilkS"' not in line:
                    continue
                ends = re.findall(r"\((?:start|end) ([-\d.]+) ([-\d.]+)\)", line)
                if len(ends) != 2:
                    continue
                (x0, y0), (x1, y1) = ((float(a), float(b)) for a, b in ends)
                silk.append(((x0 + x1) / 2, (y0 + y1) / 2, abs(x1 - x0), abs(y1 - y0)))
            out[address] = {
                "span": (start, end),
                "reference": props.get("Reference"),
                "origin": (float(at.group(1)), float(at.group(2))),
                "rotation": float(at.group(3) or 0),
                "pads": pads,
                # Every pad as (x, y, w, h) in the footprint's own frame,
                # including the repeats `pads` drops: a label has to dodge a
                # switch's second pole as much as its first.
                "pad_boxes": boxes,
                "silk_boxes": silk,
            }
        return out


# --- writing it back ---------------------------------------------------------


def strip_generated(text: str) -> str:
    """Remove every object a previous run wrote."""
    for head in ("segment", "via", "zone", "gr_line", "gr_arc"):
        while True:
            spans = [
                (a, b)
                for a, b in sexp_blocks(text, head)
                if f'(uuid "{MARK}-' in text[a:b]
            ]
            if not spans:
                break
            a, b = spans[0]
            end = b
            while end < len(text) and text[end] in "\n\t ":
                end += 1
            start = a
            while start > 0 and text[start - 1] in "\t ":
                start -= 1
            text = text[:start] + text[end:]
    return text


def _part_rects(footprints: dict, placement: dict, address: str, key: str) -> list:
    """One part's pads, or its silkscreen, as (x0, y0, x1, y1) in board millimetres."""
    x, y, *rest = placement[address]
    turn = math.radians(-(rest[0] if rest else 0))
    out = []
    for px, py, w, h in footprints[address].get(key, ()):
        ax = x + px * math.cos(turn) - py * math.sin(turn)
        ay = y + px * math.sin(turn) + py * math.cos(turn)
        # A turned pad's width and height swap; for anything but a right angle
        # the bounding box is the safe answer and no board here needs better.
        wide = abs(w * math.cos(turn)) + abs(h * math.sin(turn))
        tall = abs(w * math.sin(turn)) + abs(h * math.cos(turn))
        out.append((ax - wide / 2, ay - tall / 2, ax + wide / 2, ay + tall / 2))
    return out


def _clear(box, obstacles, margin: float) -> bool:
    x0, y0, x1, y1 = box
    return not any(
        x0 - margin < ox1 and ox0 < x1 + margin and y0 - margin < oy1 and oy0 < y1 + margin
        for ox0, oy0, ox1, oy1 in obstacles
    )


# Where a designator is tried, in order: above, below, either side, then the
# four corners, each at a growing distance. Above first because that is where a
# reader looks, and because a board read in one direction is easier than one
# whose labels are scattered by the search that placed them.
LABEL_STEPS = (0.0, 0.5, 1.1, 1.8, 2.6, 3.5, 4.5, 5.6, 6.8)
LABEL_SIDES = ((0, -1), (0, 1), (-1, 0), (1, 0), (-1, -1), (1, -1), (-1, 1), (1, 1))


def label(text: str, footprints: dict, placement: dict, labels: dict, font: dict) -> str:
    """
    Put each reference designator where it can be read.

    A stock footprint puts them on top of the part they name, which puts
    silkscreen over pads - the fab clips it away and the board comes back with
    unlabelled parts. A fixed offset instead puts them on top of each other:
    cpu1 had twenty-six pairs of designators printed one over the other and a
    hundred and eleven over a neighbour's outline, and a silkscreen that cannot
    be read is the same as no silkscreen at all.

    So the offset is searched for rather than assumed, the way the plane vias
    are: above the part first, then below, either side, the corners, each at a
    growing distance, and the first place that clears every pad on the board
    and every designator already placed is the one it takes.

    A board's own `LABELS` is the first candidate rather than the last word: a
    hand-chosen side that still works is kept, and one that a later part moved
    under is replaced instead of being printed over.

    Offsets are in board millimetres and are converted into the footprint's own
    frame, so a part that is turned around keeps its label upright and on the
    same side.
    """
    size = font["size"]
    pads = {
        address: _part_rects(footprints, placement, address, "pad_boxes")
        for address in placement
    }
    silk = {
        address: _part_rects(footprints, placement, address, "silk_boxes")
        for address in placement
    }
    everything = [rect for rects in pads.values() for rect in rects]
    taken: list = []

    chosen: dict[str, tuple[float, float]] = {}
    # Biggest parts first: they have the fewest places to put a label and the
    # most pads of their own to dodge, and a small part beside one has room
    # left over either way.
    for address in sorted(placement, key=lambda a: (-len(footprints[a].get("pad_boxes", ())), a)):
        reference = footprints[address].get("reference") or address
        half_w = (len(reference) * size * 0.72 + 0.3) / 2
        half_h = (size + 0.3) / 2
        own = pads[address]
        x, y, *_ = placement[address]
        reach_x = max((x1 - x for _, _, x1, _ in own), default=0.4)
        reach_y = max((y1 - y for _, _, _, y1 in own), default=0.4)
        # Its own outline is where a designator belongs; every other part's is
        # something to step over.
        others = [rect for other, rects in silk.items() if other != address for rect in rects]
        fixed = labels.get(address, labels.get("*"))
        candidates = ([fixed] if fixed is not None else []) + [
            (sx * (reach_x + half_w + 0.35 + step), sy * (reach_y + half_h + 0.35 + step))
            for step in LABEL_STEPS
            for sx, sy in LABEL_SIDES
        ]
        chosen[address] = candidates[0]
        # Three passes, each dropping a constraint the one before it kept. A
        # designator over an outline is untidy and still legible; one over a
        # pad gets clipped by the fab; one over *another designator* leaves two
        # parts unlabelled at once, which is the worst of the three. So the
        # last pass keeps only the other labels: a part with nowhere good left
        # lands somewhere untidy rather than on top of a neighbour's name.
        for obstacles in (everything + others, everything, []):
            for dx, dy in candidates:
                box = (x + dx - half_w, y + dy - half_h, x + dx + half_w, y + dy + half_h)
                if _clear(box, obstacles, 0.15) and _clear(box, taken, 0.15):
                    chosen[address] = (dx, dy)
                    break
            else:
                continue
            break
        dx, dy = chosen[address]
        taken.append((x + dx - half_w, y + dy - half_h, x + dx + half_w, y + dy + half_h))

    for address in sorted(placement, key=lambda a: -footprints[a]["span"][0]):
        start, end = footprints[address]["span"]
        block = text[start:end]
        dx, dy = chosen[address]

        # Board offset into the footprint's frame: the inverse of the turn
        # absolute_pad() applies. The signs of the sine terms matter only for
        # parts turned by 90 or 270 degrees, which is why a board of parts at 0
        # and 180 never showed them wrong.
        rotation = math.radians(placement[address][2] if len(placement[address]) > 2 else 0)
        local_x = dx * math.cos(rotation) - dy * math.sin(rotation)
        local_y = dx * math.sin(rotation) + dy * math.cos(rotation)

        def fix(match: re.Match) -> str:
            body = match.group(0)
            body = re.sub(
                r"\(at [-\d.]+ [-\d.]+(?: [-\d.]+)?\)",
                f"(at {local_x:g} {local_y:g} 0)",
                body,
                count=1,
            )
            body = re.sub(
                r"\(size [\d.]+ [\d.]+\)",
                f'(size {font["size"]:g} {font["size"]:g})',
                body,
            )
            body = re.sub(
                r"\(thickness [\d.]+\)", f'(thickness {font["thickness"]:g})', body
            )
            # Centred on the offset, rather than pushed off to one side.
            return re.sub(r"\n\s*\(justify[^)]*\)", "", body)

        block = re.sub(
            r'\(property "Reference"[\s\S]*?\n\t\t\)', fix, block, count=1
        )
        text = text[:start] + block + text[end:]
    return text


def place(text: str, footprints: dict, placement: dict) -> str:
    """Move each named footprint, working from the end so spans stay valid."""
    missing = set(placement) - set(footprints)
    if missing:
        sys.exit(f"placement names parts that are not on the board: {sorted(missing)}")
    unplaced = set(footprints) - set(placement)
    if unplaced:
        sys.exit(
            "every part must be placed deliberately; these are not in the "
            f"placement table: {sorted(unplaced)}"
        )

    for address in sorted(placement, key=lambda a: -footprints[a]["span"][0]):
        x, y, *rest = placement[address]
        rotation = rest[0] if rest else 0
        start, end = footprints[address]["span"]
        block = text[start:end]
        new_at = f"(at {x:g} {y:g} {rotation:g})" if rotation else f"(at {x:g} {y:g})"
        block = re.sub(r"\(at [-\d.]+ [-\d.]+(?: [-\d.]+)?\)", new_at, block, count=1)
        block = _turn_pads(block, rotation)
        block = _move_zones(block, x, y, rotation)
        text = text[:start] + block + text[end:]
    return text


def _turn_pads(block: str, rotation: float) -> str:
    """
    Turn each pad with its footprint.

    KiCad stores a pad's angle *absolutely*, not relative to the footprint it
    is in: rotating a footprint in pcbnew rewrites every pad's `(at x y angle)`
    to carry the new orientation. Setting only the footprint's own angle
    therefore rotates where the pads are and not which way they face, and a
    rectangular pad ends up lying across its neighbours.

    Nothing notices until a rotated part has pads longer than their pitch. The
    USB ESD array was the first: a SOT-23-6 turned a quarter turn, whose
    1.325 mm pads sat on a 0.95 mm pitch, so DRC found four pairs of shorted
    pads in a footprint that is fine at every other angle. Every 0402 on this
    board had been turned the same way and never overlapped anything.
    """
    if not rotation:
        return block

    def turn(match: re.Match) -> str:
        x, y, angle = match.group(1), match.group(2), match.group(3)
        turned = (float(angle or 0) + rotation) % 360
        return f"(at {x} {y} {turned:g})" if turned else f"(at {x} {y})"

    chunks = block.split("\n\t\t(pad ")
    return chunks[0] + "".join(
        "\n\t\t(pad " + re.sub(r"\(at ([-\d.]+) ([-\d.]+)(?: ([-\d.]+))?\)",
                               turn, chunk, count=1)
        for chunk in chunks[1:]
    )


def _move_zones(block: str, x: float, y: float, rotation: float) -> str:
    """
    Carry a footprint's own zones with it.

    KiCad stores a zone inside a footprint - a keepout under a Tag-Connect's pogo
    pins, say - in board coordinates, not the footprint's. The board writer
    copies it from the library file, where it sits around (0, 0), so unless it
    moves and turns with the footprint it stays at the board's origin: over
    whatever part is there, forbidding things that were never near the footprint
    it belongs to.
    """
    angle = math.radians(-rotation)

    def move(match: re.Match) -> str:
        lx, ly = float(match.group(1)), float(match.group(2))
        ax = x + lx * math.cos(angle) - ly * math.sin(angle)
        ay = y + lx * math.sin(angle) + ly * math.cos(angle)
        return f"(xy {ax:g} {ay:g})"

    out = []
    last = 0
    for zone_start, zone_end in sexp_blocks(block, "zone"):
        out.append(block[last:zone_start])
        out.append(re.sub(r"\(xy ([-\d.]+) ([-\d.]+)\)", move, block[zone_start:zone_end]))
        last = zone_end
    out.append(block[last:])
    return "".join(out)


def absolute_pad(footprints: dict, placement: dict, reference: str) -> tuple[float, float]:
    """`address:pad` -> absolute (x, y) after placement."""
    address, _, pad = reference.partition(":")
    if address not in footprints:
        sys.exit(f"route names an unknown part: {address}")
    if pad not in footprints[address]["pads"]:
        sys.exit(
            f"route names pad {pad} of {address}, which has "
            f"{sorted(footprints[address]['pads'])}"
        )
    local_x, local_y = footprints[address]["pads"][pad]
    x, y, *rest = placement[address]
    rotation = math.radians(-(rest[0] if rest else 0))
    return (
        x + local_x * math.cos(rotation) - local_y * math.sin(rotation),
        y + local_x * math.sin(rotation) + local_y * math.cos(rotation),
    )


def resolve(point, footprints, placement) -> tuple[float, float]:
    return (
        absolute_pad(footprints, placement, point)
        if isinstance(point, str)
        else (float(point[0]), float(point[1]))
    )


def route(board: Board, footprints: dict, placement: dict, routes: list,
          lengths: dict | None = None) -> list[str]:
    """
    Turn each route into track segments, and total the copper laid per net.

    The totals are what a skew check reads. Measured here rather than recovered
    from the board afterwards because this is where a route's points are known
    to belong to that route; two nets crossing on the same layer are
    indistinguishable in the finished file.
    """
    objects = []
    for net_name, width, layer, points in routes:
        if net_name not in board.nets:
            sys.exit(f"route names an unknown net: {net_name}")
        board.require_layer(layer, f"a {net_name} route")
        net = board.nets[net_name]
        resolved = [resolve(p, footprints, placement) for p in points]
        for (x1, y1), (x2, y2) in zip(resolved, resolved[1:]):
            if (x1, y1) == (x2, y2):
                continue
            if lengths is not None:
                lengths[net_name] = round(
                    lengths.get(net_name, 0.0) + math.dist((x1, y1), (x2, y2)), 4
                )
            objects.append(
                f'\t(segment\n'
                f'\t\t(start {x1:g} {y1:g})\n'
                f'\t\t(end {x2:g} {y2:g})\n'
                f'\t\t(width {width:g})\n'
                f'\t\t(layer "{layer}")\n'
                f'\t\t(net {net})\n'
                f'\t\t(uuid "{stable_uuid(TAG, net_name, x1, y1, x2, y2, layer)}")\n'
                f'\t)'
            )
    return objects


def stitch(board: Board, footprints: dict, placement: dict, vias: list) -> list[str]:
    """
    A via from a pad down to the ground plane, plus the stub that reaches it.

    Surface-mount pads live only on the top layer, so every one of them that
    belongs to the plane needs its own way down.

    Each entry is `(pad, (x, y), net, via size, drill)`, with an optional sixth
    field for the stub's width. The position may also be an `address:pad`
    reference, for a via that sits on a pad. It defaults to 0.5 mm, which suits an 0805 pad
    and would short a 0.5 mm-pitch QFP pad to both of its neighbours.

    A pad of `None` is a free via, with no stub: where a route changes layer, or
    where a track already reaches the via's position.

    Two vias asked for at the same point on the same net are one hole. That
    happens whenever a route branches at a layer change - each branch asks for
    the via it needs and neither knows about the other - and the board file
    happily took both. The drill file then carried the same coordinate twice,
    which a fab either merges silently or queries. The stub is not
    deduplicated with it: two pads may legitimately reach the same via.
    """
    objects = []
    drilled: set = set()
    top, bottom = board.copper[0], board.copper[-1]
    for entry in vias:
        pad_ref, where, net_name, size, drill, *rest = entry
        # A via may be asked for at a pad rather than at a point - that is what
        # a route changing layer on top of one looks like - so it is resolved
        # the same way a route's points are.
        via_x, via_y = resolve(where, footprints, placement)
        stub = rest[0] if rest else 0.5
        if net_name not in board.nets:
            sys.exit(f"via names an unknown net: {net_name}")
        net = board.nets[net_name]
        if pad_ref is not None:
            pad_x, pad_y = absolute_pad(footprints, placement, pad_ref)
            objects.append(
                f'\t(segment\n'
                f'\t\t(start {pad_x:g} {pad_y:g})\n'
                f'\t\t(end {via_x:g} {via_y:g})\n'
                f'\t\t(width {stub:g})\n'
                f'\t\t(layer "F.Cu")\n'
                f'\t\t(net {net})\n'
                f'\t\t(uuid "{stable_uuid(TAG, "stub", pad_ref, via_x, via_y)}")\n'
                f'\t)'
            )
        if (round(via_x, 4), round(via_y, 4), net) in drilled:
            continue
        drilled.add((round(via_x, 4), round(via_y, 4), net))
        objects.append(
            f'\t(via\n'
            f'\t\t(at {via_x:g} {via_y:g})\n'
            f'\t\t(size {size:g})\n'
            f'\t\t(drill {drill:g})\n'
            f'\t\t(layers "{top}" "{bottom}")\n'
            f'\t\t(net {net})\n'
            f'\t\t(uuid "{stable_uuid(TAG, "via", via_x, via_y)}")\n'
            f'\t)'
        )
    return objects


def board_outline(spec: dict) -> list[str]:
    """
    The board edge: four straight sides joined by four corner arcs.

    Drawn here rather than by the board writer because it is geometry, and all
    the other geometry lives in this file. The arcs' endpoints have to land
    exactly on the straight segments' endpoints or KiCad rejects the outline as
    unclosed.
    """
    width, height = spec["size"]
    radius = spec["corner_radius"]
    x, y = width / 2, height / 2
    inner_x, inner_y = x - radius, y - radius

    objects = []
    sides = [
        ((-inner_x, -y), (inner_x, -y)),   # top
        ((x, -inner_y), (x, inner_y)),     # right
        ((inner_x, y), (-inner_x, y)),     # bottom
        ((-x, inner_y), (-x, -inner_y)),   # left
    ]
    for (x1, y1), (x2, y2) in sides:
        objects.append(
            f"\t(gr_line\n"
            f"\t\t(start {x1:g} {y1:g})\n"
            f"\t\t(end {x2:g} {y2:g})\n"
            f"\t\t(stroke\n\t\t\t(width 0.05)\n\t\t\t(type solid)\n\t\t)\n"
            f'\t\t(layer "Edge.Cuts")\n'
            f'\t\t(uuid "{stable_uuid(TAG, "edge", x1, y1, x2, y2)}")\n'
            f"\t)"
        )

    diagonal = radius * math.sqrt(0.5)
    corners = [
        ((inner_x, -y), (inner_x + diagonal, -inner_y - diagonal), (x, -inner_y)),
        ((x, inner_y), (inner_x + diagonal, inner_y + diagonal), (inner_x, y)),
        ((-inner_x, y), (-inner_x - diagonal, inner_y + diagonal), (-x, inner_y)),
        ((-x, -inner_y), (-inner_x - diagonal, -inner_y - diagonal), (-inner_x, -y)),
    ]
    for (sx, sy), (mx, my), (ex, ey) in corners:
        objects.append(
            f"\t(gr_arc\n"
            f"\t\t(start {sx:g} {sy:g})\n"
            f"\t\t(mid {mx:g} {my:g})\n"
            f"\t\t(end {ex:g} {ey:g})\n"
            f"\t\t(stroke\n\t\t\t(width 0.05)\n\t\t\t(type solid)\n\t\t)\n"
            f'\t\t(layer "Edge.Cuts")\n'
            f'\t\t(uuid "{stable_uuid(TAG, "edge-arc", sx, sy, ex, ey)}")\n'
            f"\t)"
        )
    return objects


def ground_plane(board: Board, plane: dict) -> str:
    """
    A filled copper pour, so the return path is a plane and not a track.

    Two pours may share a layer if one has the higher `priority`: KiCad fills
    that one first and the other keeps clear of it. That is how a rail gets an
    island inside another rail's plane without either outline having to be
    drawn around the other.
    """
    board.require_layer(plane["layer"], f'the {plane["net"]} plane')
    net = board.nets[plane["net"]]
    corners = "\n".join(f"\t\t\t\t\t(xy {x:g} {y:g})" for x, y in plane["outline"])
    priority = plane.get("priority", 0)
    return (
        f'\t(zone\n'
        f'\t\t(net {net})\n'
        f'\t\t(net_name "{plane["net"]}")\n'
        f'\t\t(layers "{plane["layer"]}")\n'
        f'\t\t(uuid "{stable_uuid(TAG, "zone", plane["net"], plane["layer"])}")\n'
        f'\t\t(name "{TAG}")\n'
        + (f'\t\t(priority {priority})\n' if priority else "")
        + f'\t\t(hatch edge 0.5)\n'
        f'\t\t(connect_pads\n'
        f'\t\t\t(clearance {plane["pad_clearance"]:g})\n'
        f'\t\t)\n'
        f'\t\t(min_thickness {plane["min_thickness"]:g})\n'
        f'\t\t(filled_areas_thickness no)\n'
        f'\t\t(fill\n'
        f'\t\t\t(thermal_gap {plane["thermal_gap"]:g})\n'
        f'\t\t\t(thermal_bridge_width {plane["thermal_bridge"]:g})\n'
        f'\t\t)\n'
        f'\t\t(polygon\n'
        f'\t\t\t(pts\n{corners}\n'
        f'\t\t\t)\n'
        f'\t\t)\n'
        f'\t)'
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("board", help="board directory under hw/, e.g. led12")
    args = parser.parse_args()

    board_dir = HW_DIR / args.board
    pcb_path = board_dir / "elec" / "layout" / "default" / "default.kicad_pcb"
    if not pcb_path.is_file():
        sys.exit(f"no board at {pcb_path}. Run `make -C hw build` first.")

    sys.path.insert(0, str(board_dir))
    try:
        description = __import__("layout")
    except ModuleNotFoundError:
        sys.exit(f"no layout description at {board_dir / 'layout.py'}")

    board = Board(pcb_path)
    board.text = strip_generated(board.text)
    footprints = board.footprints()

    board.text = place(board.text, footprints, description.PLACEMENT)
    footprints = board.footprints()  # spans moved
    board.text = label(
        board.text,
        footprints,
        description.PLACEMENT,
        getattr(description, "LABELS", {}),
        getattr(description, "LABEL_FONT", {"size": 0.9, "thickness": 0.15}),
    )
    footprints = board.footprints()

    lengths: dict[str, float] = {}
    objects = board_outline(description.BOARD)
    objects += route(board, footprints, description.PLACEMENT, description.ROUTES, lengths)
    objects += stitch(board, footprints, description.PLACEMENT, description.VIAS)
    planes = getattr(description, "PLANES", None) or [description.PLANE]
    objects += [ground_plane(board, plane) for plane in planes]

    closing = board.text.rstrip().rfind(")")
    board.text = (
        board.text[:closing] + "\n".join(objects) + "\n" + board.text[closing:]
    )
    pcb_path.write_text(board.text)

    # What each net's copper measures, for the checks that care about matching.
    # Written beside design.json rather than into it: design.json is what the
    # circuit is, and this is what the layout made of it.
    report = board_dir / "build" / "lengths.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(dict(sorted(lengths.items())), indent=1) + "\n")

    tracks = sum(1 for o in objects if o.lstrip().startswith("(segment"))
    vias = sum(1 for o in objects if o.lstrip().startswith("(via"))
    edges = sum(1 for o in objects if o.lstrip().startswith(("(gr_line", "(gr_arc")))
    print(
        f"placed {len(description.PLACEMENT)} parts, "
        f"{tracks} track segments, {vias} vias, {edges} outline segments, "
        f"{len(planes)} plane{'s' if len(planes) != 1 else ''}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
