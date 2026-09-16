"""
Shared fixtures for the board design checks.

These read what a build produced — the variable report, the BOM and the KiCad
board — and assert things about the design. They exist because atopile's own
assertions only intersect intervals on a single parameter: anything relating
two quantities, or anything about board geometry, has to be checked here.
See hw/README.md, "What atopile's assertions actually check".

Run them with `make -C hw check`, which builds first.
"""

import csv
import json
import re
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
    d = board_dir / "build" / "builds" / "default"
    if not d.is_dir():
        pytest.fail(f"No build output in {d}. Run `make -C hw build` first.")
    return d


@pytest.fixture(scope="session")
def variables(build_dir) -> list[dict]:
    """
    Every parameter in the design, flattened.

    Each entry is {path, name, spec, actual, meetsSpec, type}, where `path` is
    the instance path like `leds[0].resistor` and `spec` is the resolved
    constraint as atopile prints it, e.g. `680Ω ±1%` or `<empty>`.
    """
    data = json.loads((build_dir / "default.variables.ato.json").read_text())
    out: list[dict] = []

    def walk(node: dict):
        for var in node.get("variables", []):
            out.append(
                {
                    "path": node["path"],
                    "type": node.get("typeName"),
                    "name": var["name"],
                    "spec": var.get("spec"),
                    "actual": var.get("actual"),
                    "meets_spec": var.get("meetsSpec"),
                }
            )
        for child in node.get("children", []):
            walk(child)

    for node in data["nodes"]:
        walk(node)
    return out


@pytest.fixture(scope="session")
def bom(build_dir) -> list[dict]:
    """The BOM as a list of rows, with `designators` split out of the first column."""
    with (build_dir / "default.bom.csv").open() as fh:
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
    `Partnumber`, `resistance`, and `atopile_address`, the path back to the
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
