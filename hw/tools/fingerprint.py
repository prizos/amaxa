#!/usr/bin/env python3
"""
Reduce a KiCad board to the design it describes, ignoring how it was written.

Two builds from identical sources produce files that differ on hundreds of
lines, because filling the copper pours goes through KiCad's own code and it
reassigns object identifiers on save. None of that is the design. Every part is
in the same place, every track runs between the same points, and the pour covers
the same copper.

So the board cannot be compared byte for byte, but it can be compared as a
design. This prints, or compares, exactly that: where each part sits, what
copper joins what, and what the nets are called.

    python3 tools/fingerprint.py board.kicad_pcb              # print it
    python3 tools/fingerprint.py before.kicad_pcb after.kicad_pcb   # compare

Comparing exits 1 and says what moved if the two designs differ.
"""

import re
import sys
from pathlib import Path


def blocks(text: str, head: str) -> list[str]:
    out = []
    for match in re.finditer(rf"\({re.escape(head)}[\s(]", text):
        i = match.start()
        depth = 0
        for j in range(i, len(text)):
            if text[j] == "(":
                depth += 1
            elif text[j] == ")":
                depth -= 1
                if depth == 0:
                    out.append(text[i : j + 1])
                    break
    return out


def fingerprint(path: Path) -> dict[str, set[str]]:
    """The design, as sorted sets of plain strings."""
    text = path.read_text()

    parts = set()
    for block in blocks(text, "footprint"):
        props = dict(re.findall(r'\(property "([^"]+)" "([^"]*)"', block))
        at = re.search(r"\(at ([-\d.]+) ([-\d.]+)(?: ([-\d.]+))?\)", block)
        lib = re.search(r'\(footprint "([^"]+)"', block)
        parts.add(
            f"{props.get('Reference')} {props.get('address')} "
            f"{lib.group(1)} at ({at.group(1)}, {at.group(2)}) "
            f"rot {at.group(3) or '0'} = {props.get('Value')} "
            f"[{props.get('LCSC') or 'no supplier part'}]"
        )

    nets = {f"{num} {name}" for num, name in re.findall(r'\(net (\d+) "([^"]*)"\)', text)}

    tracks = {
        f"net {net} {layer} ({x1}, {y1}) -> ({x2}, {y2}) width {w}"
        for x1, y1, x2, y2, w, layer, net in re.findall(
            r"\(segment\s*\(start ([-\d.]+) ([-\d.]+)\)\s*\(end ([-\d.]+) ([-\d.]+)\)"
            r'\s*\(width ([\d.]+)\)\s*\(layer "([^"]+)"\)\s*\(net (\d+)\)',
            text,
        )
    }

    vias = {
        f"({x}, {y}) size {size} drill {drill}"
        for x, y, size, drill in re.findall(
            r"\(via\s*\(at ([-\d.]+) ([-\d.]+)\)\s*\(size ([\d.]+)\)\s*\(drill ([\d.]+)\)",
            text,
        )
    }

    zones = set()
    for block in blocks(text, "zone"):
        net = re.search(r'\(net_name "([^"]*)"\)', block)
        layers = re.search(r'\(layers? "([^"]+)"\)', block)
        points = len(re.findall(r"\(xy ", block))
        zones.add(
            f"{net.group(1) if net else '?'} on "
            f"{layers.group(1) if layers else '?'}: {points} points"
        )

    return {"parts": parts, "nets": nets, "tracks": tracks, "vias": vias, "zones": zones}


def main() -> int:
    if len(sys.argv) not in (2, 3):
        sys.exit(f"usage: {Path(sys.argv[0]).name} <board> [<other board>]")

    first = fingerprint(Path(sys.argv[1]))

    if len(sys.argv) == 2:
        for section, entries in first.items():
            print(f"\n# {section} ({len(entries)})")
            for entry in sorted(entries):
                print(f"  {entry}")
        return 0

    second = fingerprint(Path(sys.argv[2]))
    differences = []
    for section in first:
        for entry in sorted(first[section] - second[section]):
            differences.append(f"  -{section}: {entry}")
        for entry in sorted(second[section] - first[section]):
            differences.append(f"  +{section}: {entry}")

    if differences:
        print("The two boards describe different designs:")
        print("\n".join(differences[:40]))
        if len(differences) > 40:
            print(f"  ... and {len(differences) - 40} more")
        return 1

    counts = ", ".join(f"{len(v)} {k}" for k, v in first.items())
    print(f"Same design: {counts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
