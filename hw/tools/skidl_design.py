"""
The one tool module that knows SKiDL exists.

A board's design source (`<board>/<board>.py`) builds its circuit out of
`part()` calls and hands the result to `run()`, which checks it and writes what
the rest of the pipeline reads: `build/design.json`, in a schema we own, and a
KiCad netlist. Nothing downstream reads SKiDL's own output, so changing design
tool again means changing this file and each board's circuit, and nothing else.

Unlike the other tools this one needs the design virtualenv, because it imports
SKiDL. It is only ever imported by a board's design source.

`design.json`:

    board    the board's name
    parts    address -> ref, value, symbol, footprint, manufacturer, mpn, lcsc
    values   "address.parameter" -> [low, high], in SI units. Design intent that
             belongs to no part uses a path whose owner is not a part address.
    nets     net name -> [[address, pad], ...]
"""

import json
import os
from pathlib import Path

os.environ.setdefault("KICAD9_SYMBOL_DIR", "/usr/share/kicad/symbols")

import skidl  # noqa: E402
from skidl import ERC, KICAD9, Part, generate_netlist, set_default_tool  # noqa: E402
from skidl.logger import erc_logger  # noqa: E402

set_default_tool(KICAD9)

# A symbol library that cannot be found is an error, not a fallback. Left on,
# SKiDL quietly loads the `<board>_sklib.py` it cached on the previous run
# instead, so a board whose symbols moved or were deleted keeps building from a
# copy nobody is looking at - and did exactly that, when SKiDL happened to be
# imported before the library path above was set.
skidl.config.query_backup_lib = False

_addresses: dict[str, Part] = {}


def part(spec, address: str, ref: str) -> Part:
    """
    One instance of a part, tagged with the address the rest of the tree uses.

    The address is passed to SKiDL as the instance tag too. Left to itself SKiDL
    invents a random tag per part and writes it into the netlist, which makes two
    builds of the same design differ.

    Designators are pinned rather than assigned: auto-assignment makes the
    mapping from a physical board to its bill of materials a function of source
    order, so a part added next year would renumber a board already built.
    """
    if address in _addresses:
        raise ValueError(f"address {address!r} used twice")
    made = Part(
        *spec.symbol.split(":"),
        footprint=spec.footprint,
        value=spec.value,
        ref=ref,
        tag=address,
    )
    made.fields["address"] = address
    made.fields["Manufacturer"] = spec.manufacturer
    made.fields["Partnumber"] = spec.mpn
    if spec.lcsc:
        made.fields["LCSC"] = spec.lcsc
    made.spec = spec
    made.address = address
    _addresses[address] = made
    return made


def design(circuit, board: str, intent: dict[str, tuple[float, float]]) -> dict:
    """The circuit as data: what each part is, what it does, and what joins it."""
    components = {}
    values = dict(intent)

    for address, made in sorted(_addresses.items()):
        spec = made.spec
        components[address] = {
            "ref": made.ref,
            "value": spec.value,
            "symbol": spec.symbol,
            "footprint": spec.footprint,
            "manufacturer": spec.manufacturer,
            "mpn": spec.mpn,
            "lcsc": spec.lcsc,
        }
        for name, (low, high) in spec.params.items():
            values[f"{address}.{name}"] = [low, high]

    nets = {}
    for net in circuit.nets:
        nodes = sorted(
            (pin.part.address, str(pin.num))
            for pin in net.pins
            if hasattr(pin.part, "address")
        )
        if nodes:
            nets[net.name] = [list(node) for node in nodes]

    return {
        "board": board,
        "parts": components,
        "values": {key: list(value) for key, value in sorted(values.items())},
        "nets": dict(sorted(nets.items())),
    }


def run(build, board_dir: Path, intent: dict[str, tuple[float, float]]) -> int:
    """
    Build a board's circuit, check it, and write what the pipeline reads.

    `build` assembles the circuit and returns any one of its nets.

    Warnings fail the build as well as errors. SKiDL calls an unconnected passive
    pin a warning, which is precisely the mistake worth catching. A warning that
    appears later has to be silenced deliberately — `do_erc = False` on the net
    or pin that earns it — which is a line in a diff rather than a message
    nobody reads.
    """
    board = board_dir.name
    out = board_dir / "build"
    out.mkdir(exist_ok=True)

    circuit = build().circuit
    ERC()
    errors = erc_logger.error.count
    warnings = erc_logger.warning.count
    generate_netlist(file_=str(out / f"{board}.net"))

    data = design(circuit, board, intent)
    (out / "design.json").write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")

    print(f"{len(data['parts'])} parts, {len(data['nets'])} nets, {len(data['values'])} values")
    if errors or warnings:
        print(f"\nERC: {errors} errors, {warnings} warnings. Both fail the build.")
        return 1
    return 0
