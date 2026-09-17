"""
Make a KiCad SVG plot readable on a web page, in place.

Two things are in the way. The file opens with an SVG 1.1 DOCTYPE pointing at a
DTD on w3.org: a network fetch nobody asked for, and a file some renderers
refuse outright. And the plot is black lines on a transparent ground, so on a
dark page - GitHub renders these in whichever theme the reader is using - it is
black on black, which looks exactly like an empty layer.

And the <title> carries the wall-clock time of the plot, so a file regenerated
from an unchanged board is a diff - which makes a committed plot churn, and
makes "regenerate and check nothing moved" useless as a gate.

So: drop the DOCTYPE, drop the timestamp, and put an opaque sheet behind the
drawing.

    python3 tools/svg_sheet.py <file.svg>
"""

import re
import sys
from pathlib import Path

SHEET = "#ffffff"
MARK = "<!-- sheet -->"


def main(path: Path) -> None:
    original = path.read_text()
    text = re.sub(r"\s*<!DOCTYPE[^>]*>\s*", "\n", original, count=1)
    text = re.sub(r"(<title>SVG Image created as \S+) date [^<]*</title>",
                  r"\1</title>", text, count=1)

    if MARK in text:  # the sheet is already there; the target is safe to re-run
        if text != original:
            path.write_text(text)
        return
    opening = re.search(r"<svg\b[^>]*>", text)
    if not opening:
        raise SystemExit(f"{path}: no <svg> element")
    box = re.search(r'viewBox="([-\d.]+) ([-\d.]+) ([-\d.]+) ([-\d.]+)"', opening.group(0))
    if not box:
        raise SystemExit(f"{path}: no viewBox to size the sheet from")
    x, y, w, h = box.groups()
    sheet = (f'{MARK}\n<rect x="{x}" y="{y}" width="{w}" height="{h}" '
             f'fill="{SHEET}" stroke="none"/>')
    path.write_text(text[: opening.end()] + "\n" + sheet + text[opening.end():])


if __name__ == "__main__":
    main(Path(sys.argv[1]))
