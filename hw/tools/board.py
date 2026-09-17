#!/usr/bin/env python3
"""
Turn a design into a KiCad board.

KiCad has no headless way to import a netlist into a board — `kicad-cli` only
does drc, export and render, and the Python bindings expose no netlist reader
at all. "Update PCB from Schematic" is a menu item. So every tool in this space
has to write the board itself, and this is ours.

It reads `design.json` — parts, nets and parameters, written by the board's own
source — and emits a `.kicad_pcb` with every footprint placed at the origin and
every pad on its net. `tools/layout.py` then moves them and draws the copper.

Written as text rather than through KiCad's `pcbnew` module, which warns on
import that it is deprecated and will be removed. Footprint bodies are copied
from their `.kicad_mod` files verbatim, so pads, courtyards, silkscreen and 3D
model references all survive exactly as the footprint author wrote them.

Three details carry more weight than their size suggests:

  **Pad numbers repeat.** A tactile switch has four holes numbered 1, 1, 2, 2
  for two poles; a SOT-223's tab shares its number with the pin it is bonded
  to. The netlist has one node per *pin*, so every pad bearing that number has
  to be given the net, not just the first one found.

  **Indentation is load-bearing.** `tools/layout.py` finds each reference
  designator with a regex that ends on a literal newline-tab-tab-paren. Indent
  differently and it silently matches nothing, every label stays on top of its
  pads, and the board comes back from the fab unlabelled. Nothing else notices:
  the fingerprint reads no silkscreen.

  **The project file is not decoration.** Every track-width rule is conditioned
  on a netclass, and netclasses live in the `.kicad_pro`. It also sets a
  copper-to-edge clearance stricter than the fab rules ask for. Without it DRC
  runs, passes, and has checked rather less than it appears to.

    python3 tools/board.py led12
"""

import argparse
import importlib.util
import json
import re
import shutil
import sys
import uuid
from pathlib import Path

HW_DIR = Path(__file__).resolve().parent.parent

# Distinct from tools/layout.py's marker: that one tags objects it may later
# strip and rewrite, and footprints are not among them.
MARK = "b0a12d00"
NAMESPACE = uuid.UUID("3d9c17ab-5e21-4a6f-8b03-1c7f2e6a9d45")


def stable_uuid(*parts) -> str:
    """Same object, same UUID, every run — so a rebuild produces no diff."""
    digest = uuid.uuid5(NAMESPACE, "|".join(str(p) for p in parts)).hex
    return f"{MARK}-{digest[:4]}-{digest[4:8]}-{digest[8:12]}-{digest[12:24]}"


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- the board's fixed parts -------------------------------------------------

def copper_layers(board: dict) -> list[str]:
    """Copper layer names, top to bottom: F.Cu, In1.Cu ... B.Cu."""
    count = board.get("copper_layers", 2)
    if count < 2 or count % 2:
        sys.exit(f"copper_layers must be an even number of at least 2, not {count}")
    return ["F.Cu"] + [f"In{i}.Cu" for i in range(1, count - 1)] + ["B.Cu"]


def layer_id(name: str) -> int:
    """KiCad 9's numbering: F.Cu 0, B.Cu 2, then In1.Cu 4, In2.Cu 6 and so on."""
    if name == "F.Cu":
        return 0
    if name == "B.Cu":
        return 2
    return 2 * int(name[2:-3]) + 2


_USER_LAYERS = """\t\t(9 "F.Adhes" user "F.Adhesive")
\t\t(11 "B.Adhes" user "B.Adhesive")
\t\t(13 "F.Paste" user)
\t\t(15 "B.Paste" user)
\t\t(5 "F.SilkS" user "F.Silkscreen")
\t\t(7 "B.SilkS" user "B.Silkscreen")
\t\t(1 "F.Mask" user)
\t\t(3 "B.Mask" user)
\t\t(17 "Dwgs.User" user "User.Drawings")
\t\t(19 "Cmts.User" user "User.Comments")
\t\t(21 "Eco1.User" user "User.Eco1")
\t\t(23 "Eco2.User" user "User.Eco2")
\t\t(25 "Edge.Cuts" user)
\t\t(27 "Margin" user)
\t\t(31 "F.CrtYd" user "F.Courtyard")
\t\t(29 "B.CrtYd" user "B.Courtyard")
\t\t(35 "F.Fab" user)
\t\t(33 "B.Fab" user)"""


def layers(board: dict) -> str:
    """The layer table: the board's copper, then KiCad's fixed user layers."""
    # Physical order, top to bottom, as KiCad itself writes them. The IDs are
    # not in that order - B.Cu is 2, In1.Cu 4 - and listing B.Cu second, by ID,
    # loads as a board with one copper layer fewer than it has.
    copper = copper_layers(board)
    rows = "\n".join(f'\t\t({layer_id(name)} "{name}" signal)' for name in copper)
    return f"\t(layers\n{rows}\n{_USER_LAYERS}\n\t)"


def _dielectrics(board: dict) -> list[dict]:
    """
    What sits between each pair of copper layers, top to bottom.

    A two-layer board is one core, as it always was. Anything thicker says so in
    `BOARD["stack"]`: one entry per gap, each with a type (`core` or
    `prepreg`), a thickness and its dielectric constant, taken from the fab's
    published stackup rather than from KiCad's defaults.
    """
    count = board.get("copper_layers", 2)
    if count == 2 and "stack" not in board:
        return [{"type": "core", "thickness": board["core_thickness"], "epsilon_r": 4.5}]
    stack = board["stack"]
    if len(stack) != count - 1:
        sys.exit(f"{count} copper layers need {count - 1} dielectrics in BOARD['stack'], not {len(stack)}")
    return stack


def stackup(board: dict) -> str:
    """The physical construction, from the board's own description."""
    copper = copper_layers(board)
    outer = board["copper_thickness"]
    inner = board.get("inner_copper_thickness", outer)
    rows = [
        '\t\t\t(layer "F.SilkS"\n\t\t\t\t(type "Top Silk Screen")\n\t\t\t)',
        '\t\t\t(layer "F.Paste"\n\t\t\t\t(type "Top Solder Paste")\n\t\t\t)',
        f'\t\t\t(layer "F.Mask"\n\t\t\t\t(type "Top Solder Mask")\n'
        f'\t\t\t\t(color "{board["mask_colour"]}")\n\t\t\t\t(thickness 0.01)\n\t\t\t)',
    ]
    for index, name in enumerate(copper):
        thickness = outer if name in ("F.Cu", "B.Cu") else inner
        rows.append(
            f'\t\t\t(layer "{name}"\n\t\t\t\t(type "copper")\n'
            f"\t\t\t\t(thickness {thickness:g})\n\t\t\t)"
        )
        if index < len(copper) - 1:
            gap = _dielectrics(board)[index]
            rows.append(
                f'\t\t\t(layer "dielectric {index + 1}"\n'
                f'\t\t\t\t(type "{gap["type"]}")\n'
                f'\t\t\t\t(thickness {gap["thickness"]:g})\n'
                f'\t\t\t\t(material "FR4")\n'
                f'\t\t\t\t(epsilon_r {gap["epsilon_r"]:g})\n'
                f"\t\t\t\t(loss_tangent 0.02)\n\t\t\t)"
            )
    rows += [
        f'\t\t\t(layer "B.Mask"\n\t\t\t\t(type "Bottom Solder Mask")\n'
        f'\t\t\t\t(color "{board["mask_colour"]}")\n\t\t\t\t(thickness 0.01)\n\t\t\t)',
        '\t\t\t(layer "B.Paste"\n\t\t\t\t(type "Bottom Solder Paste")\n\t\t\t)',
        '\t\t\t(layer "B.SilkS"\n\t\t\t\t(type "Bottom Silk Screen")\n\t\t\t)',
        f'\t\t\t(copper_finish "{board["finish"]}")',
    ]
    return (
        "\t(setup\n\t\t(stackup\n"
        + "\n".join(rows)
        + "\n\t\t)\n\t\t(pad_to_mask_clearance 0)\n"
        "\t\t(allow_soldermask_bridges_in_footprints no)\n\t)"
    )


# --- footprints --------------------------------------------------------------


def indent(text: str) -> str:
    """Shift a footprint body one level deeper, as it sits inside the board."""
    return "\n".join(("\t" + line if line.strip() else line) for line in text.splitlines())


def property_block(name: str, value: str, address: str, hide: bool) -> str:
    """A footprint property, on the fabrication layer unless it is shown."""
    hidden = "\n\t\t\t(hide yes)" if hide else ""
    return (
        f'\t\t(property "{name}" "{value}"\n'
        f"\t\t\t(at 0 0 0)\n"
        f'\t\t\t(unlocked yes)\n'
        f'\t\t\t(layer "F.Fab"){hidden}\n'
        f'\t\t\t(uuid "{stable_uuid("prop", address, name)}")\n'
        f"\t\t\t(effects\n"
        f"\t\t\t\t(font\n"
        f"\t\t\t\t\t(size 1 1)\n"
        f"\t\t\t\t\t(thickness 0.15)\n"
        f"\t\t\t\t)\n"
        f"\t\t\t)\n"
        f"\t\t)"
    )


def embed(address: str, part: dict, source: str, pad_nets: dict[str, tuple[int, str]]) -> str:
    """
    One footprint, ready to drop into a board.

    The body is the `.kicad_mod` as written, with the library-qualified name,
    a position, a UUID, our own properties, and a net on every pad.
    """
    library, _, name = part["footprint"].partition(":")

    body = source.strip()
    body = re.sub(r'^\(footprint "[^"]*"', f'(footprint "{library}:{name}"', body)
    body = re.sub(r"\n\t\(version \d+\)", "", body)
    body = re.sub(r'\n\t\(generator[^\n]*\)', "", body)

    # Reference and Value become the real ones; the stock footprint's own
    # placeholders would otherwise read REF** on every part.
    body = re.sub(r'(\(property "Reference" )"[^"]*"', rf'\1"{part["ref"]}"', body, count=1)
    body = re.sub(r'(\(property "Value" )"[^"]*"', rf'\1"{part["value"]}"', body, count=1)

    # Give every element its own stable identity.
    seen = [0]

    def add_uuid(match: re.Match) -> str:
        seen[0] += 1
        return f'{match.group(0)}\n\t\t(uuid "{stable_uuid(address, "el", seen[0])}")'

    body = re.sub(r'^\t\((?:fp_\w+|pad|model|property) ', lambda m: m.group(0), body, flags=re.M)

    body = indent(body)

    # Position and identity, straight after the layer line.
    body = body.replace(
        '\t\t(layer "F.Cu")',
        f'\t\t(layer "F.Cu")\n'
        f'\t\t(uuid "{stable_uuid("fp", address)}")\n'
        f"\t\t(at 0 0)",
        1,
    )

    # Our own fields, so the board carries part identity the BOM can be built
    # from and the checks can key on.
    extra = [property_block("address", address, address, hide=True)]
    for field, key in (("Manufacturer", "manufacturer"), ("Partnumber", "mpn")):
        extra.append(property_block(field, part[key], address, hide=True))
    if part["lcsc"]:
        extra.append(property_block("LCSC", part["lcsc"], address, hide=True))

    closing = body.rstrip().rfind(")")
    body = body[:closing] + "\n".join(extra) + "\n" + body[closing:]

    # Every pad of a given number gets the net, not only the first: pad numbers
    # repeat, for switch poles and for a regulator's tab.
    def net_pad(match: re.Match) -> str:
        number = match.group(1)
        if number not in pad_nets:
            return match.group(0)
        code, net_name = pad_nets[number]
        return f'{match.group(0)}\n\t\t\t(net {code} "{net_name}")'

    body = re.sub(r'\t\t\(pad "([^"]*)"[^\n]*', net_pad, body)
    return body


# --- assembling the board ----------------------------------------------------


def write(board_dir: Path) -> Path:
    design_path = board_dir / "build" / "design.json"
    if not design_path.is_file():
        sys.exit(f"no design at {design_path}. Run the board's own source first.")
    design = json.loads(design_path.read_text())

    layout = load_module(board_dir / "layout.py", f"{board_dir.name}_layout")
    board_spec = layout.BOARD

    # Net numbers are ours to choose; sorted, so they are stable and reviewable.
    net_codes = {name: i for i, name in enumerate(sorted(design["nets"]), start=1)}

    # address -> {pad number: (code, net name)}
    by_part: dict[str, dict[str, tuple[int, str]]] = {}
    for net_name, nodes in design["nets"].items():
        for address, pad in nodes:
            by_part.setdefault(address, {})[pad] = (net_codes[net_name], net_name)

    footprints = []
    for address, part in sorted(design["parts"].items()):
        library, _, name = part["footprint"].partition(":")
        source = board_dir / "parts" / library / f"{name}.kicad_mod"
        if not source.is_file():
            sys.exit(f"{address}: no footprint at {source}")
        footprints.append(
            embed(address, part, source.read_text(), by_part.get(address, {}))
        )

    nets = "\n".join(
        f'\t(net {code} "{name}")'
        for name, code in sorted(net_codes.items(), key=lambda kv: kv[1])
    )

    text = (
        "(kicad_pcb\n"
        "\t(version 20241229)\n"
        '\t(generator "amaxa")\n'
        '\t(generator_version "9.0")\n'
        "\t(general\n"
        f'\t\t(thickness {board_spec["thickness"]:g})\n'
        "\t\t(legacy_teardrops no)\n"
        "\t)\n"
        '\t(paper "A4")\n'
        f"{layers(board_spec)}\n"
        f"{stackup(board_spec)}\n"
        '\t(net 0 "")\n'
        f"{nets}\n"
        + "\n".join(footprints)
        + "\n)\n"
    )

    out_dir = board_dir / "elec" / "layout" / "default"
    out_dir.mkdir(parents=True, exist_ok=True)
    pcb = out_dir / "default.kicad_pcb"
    pcb.write_text(text)

    # KiCad resolves a footprint's library id through this table.
    libraries = sorted({part["footprint"].partition(":")[0] for part in design["parts"].values()})
    (out_dir / "fp-lib-table").write_text(
        "(fp_lib_table\n\t(version 7)\n"
        + "\n".join(
            f'\t(lib\n\t\t(name "{lib}")\n\t\t(type "KiCad")\n'
            f'\t\t(uri "${{KIPRJMOD}}/../../../parts/{lib}")\n'
            f'\t\t(options "")\n\t\t(descr "amaxa: {lib}")\n\t)'
            for lib in libraries
        )
        + "\n)\n"
    )

    # Netclasses and the stricter clearances DRC actually enforces.
    shutil.copyfile(board_dir / "board.kicad_pro", out_dir / "default.kicad_pro")

    write_bom(board_dir, design)

    print(
        f"wrote {pcb.relative_to(HW_DIR)}: "
        f"{len(footprints)} footprints, {len(net_codes)} nets"
    )
    return pcb


def write_bom(board_dir: Path, design: dict) -> None:
    """
    What to order, grouped the way an assembler expects.

    Parts with no supplier code are absent by construction rather than sitting
    on the BOM unorderable: a test pad is bare copper and nobody sells one.
    """
    groups: dict[tuple[str, str], list[str]] = {}
    detail: dict[tuple[str, str], dict] = {}
    for part in design["parts"].values():
        if not part["lcsc"]:
            continue
        key = (part["mpn"], part["value"])
        groups.setdefault(key, []).append(part["ref"])
        detail[key] = part

    def sort_key(ref: str) -> tuple[str, int]:
        letters = "".join(c for c in ref if c.isalpha())
        digits = "".join(c for c in ref if c.isdigit())
        return letters, int(digits or 0)

    rows = [
        "Designator,Footprint,Quantity,Value,Manufacturer,Partnumber,LCSC Part #"
    ]
    for key in sorted(groups, key=lambda k: sort_key(sorted(groups[k], key=sort_key)[0])):
        refs = sorted(groups[key], key=sort_key)
        part = detail[key]
        designators = ", ".join(refs)
        rows.append(
            ",".join(
                f'"{field}"' if "," in field else field
                for field in (
                    designators, part["footprint"], str(len(refs)), part["value"],
                    part["manufacturer"], part["mpn"], part["lcsc"],
                )
            )
        )
    (board_dir / "build" / "bom.csv").write_text("\n".join(rows) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("board", help="board directory under hw/, e.g. led12")
    args = parser.parse_args()
    write(HW_DIR / args.board)
    return 0


if __name__ == "__main__":
    sys.exit(main())
