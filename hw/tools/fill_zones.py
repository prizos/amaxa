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

import sys
from pathlib import Path

try:
    import pcbnew
except ImportError:
    sys.exit(
        "KiCad's Python module is not available. It ships with KiCad itself;\n"
        "on Debian and Ubuntu the package is python3-pcbnew."
    )


def main() -> int:
    if len(sys.argv) != 2:
        sys.exit(f"usage: {Path(sys.argv[0]).name} <board.kicad_pcb>")

    path = Path(sys.argv[1]).resolve()
    if not path.is_file():
        sys.exit(f"no board at {path}")

    board = pcbnew.LoadBoard(str(path))
    zones = list(board.Zones())
    if not zones:
        print("no pours to fill")
        return 0

    filler = pcbnew.ZONE_FILLER(board)
    if not filler.Fill(board.Zones()):
        sys.exit("zone fill failed")

    pcbnew.SaveBoard(str(path), board)

    for zone in zones:
        print(
            f"filled {zone.GetNetname() or '<no net>'} on "
            f"{board.GetLayerName(zone.GetFirstLayer())}: "
            f"{zone.GetFilledArea() / 1e12:.1f} mm2"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
