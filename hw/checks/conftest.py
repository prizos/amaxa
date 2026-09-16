"""
Shared fixtures for the board design checks.

These read what a build produced — `design.json`, the BOM and the KiCad board —
and assert things about the design. They exist because the design source states
values and nothing more: anything relating two quantities, or anything about
board geometry, has to be checked here. See hw/README.md, "The checks".

Run them with `make -C hw check`, which builds first.
"""

import csv
import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

HW_DIR = Path(__file__).resolve().parent.parent


def pytest_addoption(parser):
    parser.addoption(
        "--board",
        default="led12",
        help="Board directory under hw/ to check (default: led12)",
    )


@pytest.fixture(scope="session")
def board_dir(pytestconfig) -> Path:
    board = HW_DIR / pytestconfig.getoption("--board")
    if not board.is_dir():
        pytest.fail(f"No such board: {board}")
    return board


@pytest.fixture(scope="session")
def build_dir(board_dir) -> Path:
    d = board_dir / "build"
    if not d.is_dir():
        pytest.fail(f"No build output in {d}. Run `make -C hw build` first.")
    return d


@pytest.fixture(scope="session")
def design(build_dir) -> dict:
    """
    The design, as the board's own source wrote it.

    `design.json` is our schema, not a tool's output format: parts by address,
    parameter ranges as plain numbers, and the nets joining them. Keeping it
    ours is the lesson from the design tool this replaced, whose printed output
    had quietly become the interface half the pipeline read.
    """
    return json.loads((build_dir / "design.json").read_text())


@pytest.fixture(scope="session")
def bom(build_dir) -> list[dict]:
    """The BOM as a list of rows, with `designators` split out of the first column."""
    with (build_dir / "bom.csv").open() as fh:
        rows = list(csv.DictReader(fh))
    for row in rows:
        row["designators"] = [d.strip() for d in row["Designator"].split(",")]
    return rows


@pytest.fixture(scope="session")
def pcb_text(board_dir) -> str:
    pcb = board_dir / "elec" / "layout" / "default" / "default.kicad_pcb"
    if not pcb.is_file():
        pytest.fail(f"No board file at {pcb}")
    return pcb.read_text()


def _address(footprint: dict) -> str:
    """
    A part's stable instance name, as the board writer recorded it.

    Addresses name a role — `power.q_rpp` — while designators name a physical
    part. Only one of those survives adding a component.
    """
    return footprint["properties"].get("address") or footprint["designator"]


def _sexp_blocks(text: str, head: str) -> list[str]:
    """Every top-level `(head ...)` block in a KiCad file, as raw text."""
    blocks = []
    for match in re.finditer(rf"\({re.escape(head)}\s", text):
        start = match.start()
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "(":
                depth += 1
            elif text[i] == ")":
                depth -= 1
                if depth == 0:
                    blocks.append(text[start : i + 1])
                    break
    return blocks


@pytest.fixture(scope="session")
def footprints(pcb_text) -> list[dict]:
    """
    Every placed footprint: designator, library id, position, properties, pads.

    atopile writes each part's identity and every resolved parameter into the
    board file as footprint properties, keyed per instance — `Value`, `LCSC`,
    `Partnumber`, `resistance`, and `address`, the path back to the
    source. That makes the board file, not the BOM, the place to check what was
    actually specified: the BOM merges rows that share a part number, which
    hides exactly the mistake we most want to catch.

    Positions are in millimetres, in the board file's own coordinate system.
    """
    out = []
    for block in _sexp_blocks(pcb_text, "footprint"):
        lib_id = re.search(r'\(footprint "([^"]+)"', block)
        at = re.search(r"\(at ([-\d.]+) ([-\d.]+)", block)
        props = dict(re.findall(r'\(property "([^"]+)" "([^"]*)"', block))

        pads = {}
        for pad_block in _sexp_blocks(block, "pad"):
            name = re.match(r'\(pad "([^"]*)"', pad_block)
            net = re.search(r'\(net \d+ "([^"]*)"\)', pad_block)
            if name:
                pads[name.group(1)] = net.group(1) if net else None

        out.append(
            {
                "designator": props.get("Reference"),
                "lib_id": lib_id.group(1) if lib_id else None,
                "x": float(at.group(1)) if at else None,
                "y": float(at.group(2)) if at else None,
                "properties": props,
                "pads": pads,
            }
        )
    return out


@pytest.fixture(scope="session")
def nets(footprints) -> dict[str, set[tuple[str, str]]]:
    """Net name -> set of (designator, pad) it connects."""
    out: dict[str, set[tuple[str, str]]] = {}
    for fp in footprints:
        for pad, net in fp["pads"].items():
            if net:
                out.setdefault(net, set()).add((fp["designator"], pad))
    return out


def pytest_collection_modifyitems(config, items):
    """Record how many checks were collected, for the check-count guard."""
    config.collected_check_count = len(items)


@pytest.fixture(scope="session")
def collected_check_count(pytestconfig) -> int:
    return getattr(pytestconfig, "collected_check_count", 0)


@pytest.fixture(scope="session")
def spec(design):
    """
    One parameter's range: `spec("leds[0].resistor", "resistance")` -> (low, high).

    Fails rather than inventing a value, because a check that silently treats
    "never specified" as "anything" passes for the wrong reason.
    """
    values = design["values"]

    def lookup(path: str, name: str) -> tuple[float, float]:
        key = f"{path}.{name}"
        if key not in values:
            pytest.fail(
                f"{key} is not in design.json. Either the path is wrong, or the "
                "part never states that value."
            )
        low, high = values[key]
        return float(low), float(high)

    return lookup


@pytest.fixture(scope="session")
def board_outline(pcb_text) -> tuple[float, float, float, float]:
    """(min_x, min_y, max_x, max_y) of the board edge, in millimetres."""
    xs: list[float] = []
    ys: list[float] = []
    for head in ("gr_line", "gr_arc", "gr_rect"):
        for block in _sexp_blocks(pcb_text, head):
            if '(layer "Edge.Cuts")' not in block:
                continue
            for x, y in re.findall(r"\((?:start|end|mid) ([-\d.]+) ([-\d.]+)\)", block):
                xs.append(float(x))
                ys.append(float(y))
    if not xs:
        pytest.fail("the board has no Edge.Cuts outline")
    return min(xs), min(ys), max(xs), max(ys)


@pytest.fixture(scope="session")
def position(footprints):
    """`position("power.c_bulk")` -> that part's (x, y) on the board."""
    index = {
        _address(fp): (fp["x"], fp["y"])
        for fp in footprints
    }

    def lookup(address: str) -> tuple[float, float]:
        if address not in index:
            pytest.fail(f"no part at address {address}")
        return index[address]

    return lookup


@pytest.fixture(scope="session")
def net_members(footprints) -> dict[str, set[tuple[str, str]]]:
    """
    Net name -> {(source address, pad)}.

    Addresses like `power.fuse` rather than designators like `F1`, because
    designators name a physical part while addresses name its role, and only
    one of those is stable when a part is added.
    """
    out: dict[str, set[tuple[str, str]]] = {}
    for fp in footprints:
        address = _address(fp)
        for pad, net in fp["pads"].items():
            if net:
                out.setdefault(net, set()).add((address, pad))
    return out


@pytest.fixture(scope="session")
def net_parts(net_members) -> dict[str, set[str]]:
    """Net name -> the set of source addresses it touches, ignoring which pad."""
    return {net: {addr for addr, _ in members} for net, members in net_members.items()}


@pytest.fixture(scope="session")
def parts(board_dir):
    """The board's part list, loaded from its own `parts.py`."""
    path = board_dir / "parts.py"
    if not path.is_file():
        pytest.fail(f"no {path}")
    spec = importlib.util.spec_from_file_location(f"{board_dir.name}_parts", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.ALL
