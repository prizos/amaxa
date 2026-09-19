#!/usr/bin/env python3
"""
Fill the copper pours on a board.

`kicad-cli` cannot do this. It runs DRC against whatever fill is already in the
file, so a board whose ground plane has never been filled reports every ground
pad as unconnected — the pour exists as an outline but no copper has been
computed inside it.

KiCad's own Python module does the filling, using the same code pcbnew uses,
so the result is what a person would get by opening the board and pressing B.

    python3 tools/fill_zones.py led12/elec/layout/default/default.kicad_pcb

This runs after tools/layout.py, which writes the pour's outline, and before
DRC, which needs it filled.
"""

import re
import sys
from pathlib import Path

try:
    import pcbnew
except ImportError:
    sys.exit(
        "KiCad's Python module is not available. It ships with KiCad itself;\n"
        "on Debian and Ubuntu the package is python3-pcbnew."
    )


def _nets_in(text: str) -> dict:
    """
    Every via and track in a board file, keyed by where it is, with its net.

    Read out of the file's own text rather than through pcbnew, because the
    rewrite this guards against happens in `LoadBoard`: pcbnew re-resolves
    connectivity as it reads, so a board already loaded has already been
    changed and cannot be compared with itself.
    """
    names = dict(re.findall(r'\(net (\d+) "([^"]*)"\)', text))
    out = {}
    for kind in ("via", "segment"):
        for block in re.findall(rf"\n\t\({kind}\n(?:\t\t[^\n]*\n)+\t\)", text):
            at = re.search(r"\(at ([-\d.]+) ([-\d.]+)\)", block)
            start = re.search(r"\(start ([-\d.]+) ([-\d.]+)\)", block)
            end = re.search(r"\(end ([-\d.]+) ([-\d.]+)\)", block)
            layer = re.search(r'\(layers? "([^"]+)"', block)
            number = re.search(r"\(net (\d+)\)", block)
            if not number:
                continue
            where = at or start
            if not where:
                continue
            key = (kind, layer.group(1) if layer else "",
                   where.group(1), where.group(2),
                   end.group(1) if end else "", end.group(2) if end else "")
            out[key] = names.get(number.group(1), "")
    return out


def _moved(before: dict, after: dict) -> list[str]:
    """Copper whose net changed as the board was loaded and filled."""
    return [
        f"  {kind} at ({x}, {y}) mm on {layer}: {was!r} became {after[key]!r}"
        for key, was in sorted(before.items())
        if key in after and after[key] != was
        for kind, layer, x, y, *_ in [key]
    ]


def main() -> int:
    if len(sys.argv) != 2:
        sys.exit(f"usage: {Path(sys.argv[0]).name} <board.kicad_pcb>")

    path = Path(sys.argv[1]).resolve()
    if not path.is_file():
        sys.exit(f"no board at {path}")

    before = _nets_in(path.read_text())
    board = pcbnew.LoadBoard(str(path))
    zones = list(board.Zones())
    if not zones:
        print("no pours to fill")
        return 0

    filler = pcbnew.ZONE_FILLER(board)
    if not filler.Fill(board.Zones()):
        sys.exit("zone fill failed")

    pcbnew.SaveBoard(str(path), board)

    moved = _moved(before, _nets_in(path.read_text()))
    if moved:
        sys.exit(
            "the zone fill changed what net some copper is on, which it must "
            "never do:\n" + "\n".join(moved) + "\n"
            "Every check in this repository reads the board *after* this step, "
            "so a net pcbnew rewrites here is a net nothing downstream can "
            "disagree with. Fix the layout instead."
        )

    for zone in zones:
        print(
            f"filled {zone.GetNetname() or '<no net>'} on "
            f"{board.GetLayerName(zone.GetFirstLayer())}: "
            f"{zone.GetFilledArea() / 1e12:.1f} mm2"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
