"""
Write `<board>/review/README.md`: the board as pictures and tables, for GitHub.

Every number in it is read from the board file, from `build/design.json` and
from the DRC report. Nothing is typed in by hand, because a review document
that is maintained by hand is a review document that is wrong - the same
reasoning the checks are built on, applied to the thing a person actually
looks at.

The prose - what each block is for, what each layer shows, what a picture of
this board cannot tell you - comes from `<board>/review.py`, which sits beside
the board because it is about that board.

Run through `make review BOARD=<board>`, which plots the layers first.

Deliberately dependency-free so it runs under the system Python, like
everything else in `tools/`.
"""

import json
import re
import sys
from pathlib import Path

HW_DIR = Path(__file__).resolve().parent.parent


def load_module(path: Path, name: str):
    import importlib.util

    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def block_of(address: str, blocks) -> str:
    root = address.split(".")[0]
    for name, keys, _ in blocks:
        for key in keys:
            if root == key or (key.endswith("_") and root.startswith(key)):
                return name
    return "Other"


def board_facts(pcb_text: str) -> dict:
    """Counted off the board file, not off the log that wrote it."""
    # In the order the board's layer table lists them, which is the order they
    # are stacked. Sorted alphabetically, B.Cu would come first and the document
    # would describe the board from the bottom up.
    copper, seen = [], set()
    for name in re.findall(r'"((?:F|B|In\d+)\.Cu)" signal', pcb_text):
        if name not in seen:
            seen.add(name)
            copper.append(name)
    xs, ys = [], []
    for match in re.finditer(
        r"\(gr_line\s*\(start ([-\d.]+) ([-\d.]+)\)\s*\(end ([-\d.]+) ([-\d.]+)\)", pcb_text
    ):
        xs += [float(match.group(1)), float(match.group(3))]
        ys += [float(match.group(2)), float(match.group(4))]
    return {
        "layers": copper,
        "width": max(xs) - min(xs) if xs else 0.0,
        "height": max(ys) - min(ys) if ys else 0.0,
        "footprints": len(re.findall(r"\n\t\(footprint ", pcb_text)),
        "tracks": len(re.findall(r"\n\t\(segment", pcb_text)),
        "vias": len(re.findall(r"\n\t\(via", pcb_text)),
        "zones": len(re.findall(r"\n\t\(zone", pcb_text)),
    }


def zone_fills(pcb_text: str) -> list[tuple[str, str]]:
    """(net, layer) for each filled zone, in the order the board lists them."""
    out = []
    for block in re.finditer(r"\n\t\(zone\b(.{0,600})", pcb_text, re.S):
        net = re.search(r'\(net_name "([^"]*)"\)', block.group(1))
        layer = re.search(r'\(layers? "([^"]*)"\)', block.group(1))
        if net and layer and net.group(1):
            out.append((net.group(1), layer.group(1)))
    return out


def table(headings: list[str], rows: list[list[str]], align: str = "") -> str:
    align = align or "l" * len(headings)
    sep = {"l": "---", "r": "--:", "c": ":-:"}
    lines = ["| " + " | ".join(headings) + " |",
             "|" + "|".join(sep[a] for a in align) + "|"]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join(lines)


def details(summary: str, body: str) -> str:
    return f"<details>\n<summary>{summary}</summary>\n\n{body}\n\n</details>"


def main(board: str) -> None:
    board_dir = HW_DIR / board
    review_dir = board_dir / "review"
    design = json.loads((board_dir / "build" / "design.json").read_text())
    pcb_text = (board_dir / "elec/layout/default/default.kicad_pcb").read_text()
    prose = load_module(board_dir / "review.py", f"{board}_review")

    facts = board_facts(pcb_text)
    parts, nets = design["parts"], design["nets"]
    pending = design.get("pending", {})

    drc_path = board_dir / "elec/layout/default/drc.json"
    drc = json.loads(drc_path.read_text()) if drc_path.is_file() else {}
    violations = len(drc.get("violations", []))
    unrouted = len(drc.get("unconnected_items", []))

    routing = "complete"
    board_mk = board_dir / "board.mk"
    if board_mk.is_file() and "ROUTING := incomplete" in board_mk.read_text():
        routing = "incomplete"

    # --- the document --------------------------------------------------------
    out: list[str] = []
    out.append(f"# {prose.TITLE}\n")
    out.append(prose.LEDE + "\n")

    out.append(table(
        ["", ""],
        [["**Size**", f"{facts['width']:g} × {facts['height']:g} mm"],
         ["**Stackup**", f"{len(facts['layers'])} layers — " + " / ".join(facts["layers"])],
         ["**Footprints**", str(facts["footprints"])],
         ["**Nets**", f"{len(nets)}" + (f", of which {len(pending)} pending" if pending else "")],
         ["**Routing**", f"{facts['tracks']} track segments, {facts['vias']} vias, "
                         f"{facts['zones']} zones"],
         ["**DRC**", f"{violations} violations, {unrouted} connections not yet routed"
                     f" (`ROUTING := {routing}`)"]],
    ) + "\n")

    if routing == "incomplete":
        out.append(
            "> [!IMPORTANT]\n"
            "> **Routing is deliberately incomplete.** Read the plots with that in\n"
            "> mind, and see *What these pictures are not*, at the end.\n"
        )

    # --- layers --------------------------------------------------------------
    out.append("## The copper, one layer at a time\n")
    out.append(
        "Plotted separately rather than stacked: a stacked plot of a board with\n"
        f"{facts['zones']} filled zones is a solid rectangle. The layer list is read from\n"
        "the board file rather than written down here, for the same reason the gerber\n"
        "list is — a fixed `F.Cu,B.Cu` list silently leaves a 4-layer board's planes out.\n"
    )
    fills = zone_fills(pcb_text)
    for layer in facts["layers"]:
        stem = layer.replace(".", "_")
        if not (review_dir / f"{stem}.svg").is_file():
            continue
        on_it = [net for net, where in fills if where == layer]
        out.append(f"### `{layer}`\n")
        out.append(prose.LAYERS.get(stem, "") + "\n")
        if on_it:
            out.append("Zones on this layer: " + ", ".join(f"`{n}`" for n in on_it) + "\n")
        out.append(f"![{layer} plot]({stem}.svg)\n")

    if (review_dir / "assembly.svg").is_file():
        out.append("### Assembly\n")
        out.append(prose.LAYERS.get("assembly", "") + "\n")
        out.append("![Assembly drawing](assembly.svg)\n")

    # --- renders -------------------------------------------------------------
    renders = [(side, cap) for side, cap in prose.RENDERS.items()
               if (review_dir / f"{side}.png").is_file()]
    if renders:
        out.append("## Renders\n")
        out.append(table(
            [cap.split(" - ")[0] for _, cap in renders],
            [[f"![{side}]({side}.png)" for side, _ in renders],
             [cap.split(" - ", 1)[-1].rstrip(".") for _, cap in renders]],
        ) + "\n")

    # --- blocks and parts ----------------------------------------------------
    grouped: dict[str, list] = {}
    for address, part in sorted(parts.items()):
        grouped.setdefault(block_of(address, prose.BLOCKS), []).append((address, part))
    unplaced = grouped.pop("Other", [])

    out.append("## What is on the board\n")
    out.append(
        "Every part belongs to one block, named by the address it is built under in\n"
        f"`{board}.py` — so this grouping is the design's own, not a reading of the\n"
        "schematic after the fact.\n"
    )
    out.append(table(
        ["Block", "Parts", "What it is"],
        [[name, str(len(grouped[name])), desc]
         for name, _, desc in prose.BLOCKS if name in grouped],
        align="llr"[0] * 2 + "l",
    ) + "\n")
    if unplaced:
        out.append("Parts in no block (a gap in `review.py`): "
                   + ", ".join(f"`{a}`" for a, _ in unplaced) + "\n")

    body = []
    for name, _, _ in prose.BLOCKS:
        if name not in grouped:
            continue
        body.append(f"#### {name}\n")
        body.append(table(
            ["Ref", "Address", "Value", "Part number", "LCSC", "Footprint"],
            [[f"`{p['ref']}`", f"`{a}`", p.get("value", ""), p.get("mpn", "") or "—",
              p.get("lcsc") or "—", f"`{p.get('footprint', '').split(':')[-1]}`"]
             for a, p in grouped[name]],
        ) + "\n")
    out.append(details(f"<strong>Every footprint</strong> — all {len(parts)}, by block",
                       "\n".join(body)) + "\n")

    # --- nets ----------------------------------------------------------------
    out.append("## Nets\n")
    if pending:
        out.append(
            f"{len(pending)} of the {len(nets)} nets are ERC waivers: each has exactly one\n"
            "connection, because the block at its other end is not drawn yet. A check\n"
            "requires that to stay true, so when the block lands the waiver has to go.\n"
        )
        by_reason: dict[str, list[str]] = {}
        for net, reason in sorted(pending.items()):
            by_reason.setdefault(reason, []).append(net)
        out.append(table(
            ["Waiting on", "Nets"],
            [[reason, ", ".join(f"`{n}`" for n in names)]
             for reason, names in sorted(by_reason.items())],
        ) + "\n")
    out.append(details(
        f"<strong>Every net</strong> — all {len(nets)}, by size",
        table(["Net", "Nodes", "Status"],
              [[f"`{net}`", str(len(nodes)), "pending" if net in pending else ""]
               for net, nodes in sorted(nets.items(), key=lambda kv: (-len(kv[1]), kv[0]))],
              align="lrl"),
    ) + "\n")

    # --- caveats -------------------------------------------------------------
    out.append("## What these pictures are not\n")
    for heading, text in prose.CAVEATS:
        out.append(f"**{heading}.** {text.strip()}\n")

    out.append(
        "---\n\n"
        f"Generated by `make review BOARD={board}` from "
        f"`{board}/elec/layout/default/default.kicad_pcb` and `{board}/build/design.json`.\n"
        "Not edited by hand: if this disagrees with the board file, the board file is\n"
        "right, and the fix is to regenerate.\n"
    )

    target = review_dir / "README.md"
    target.write_text("\n".join(out))
    print(f"wrote {target.relative_to(HW_DIR)}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "cpu1")
