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


# --- reading atopile's resolved specs ----------------------------------------

_PREFIX = {
    "p": 1e-12, "n": 1e-9, "u": 1e-6, "µ": 1e-6, "μ": 1e-6, "m": 1e-3,
    "": 1.0, "k": 1e3, "K": 1e3, "M": 1e6, "G": 1e9,
}
_UNITS = ("Ω", "V", "A", "W", "F", "H", "s", "cd", "Hz")
_NUMBER = r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?"


class UnconstrainedSpec(Exception):
    """The parameter was never given a value, so nothing can be computed from it."""


def _magnitude(text: str, fallback_suffix: str = "") -> float:
    """Turn `680Ω`, `125mW`, `2.4` (with a fallback suffix) into a number in SI units."""
    text = text.strip()
    match = re.fullmatch(rf"({_NUMBER})\s*(.*)", text)
    if not match:
        raise ValueError(f"cannot read a number from {text!r}")
    value, suffix = float(match.group(1)), match.group(2).strip() or fallback_suffix

    for unit in _UNITS:
        if suffix.endswith(unit):
            prefix = suffix[: -len(unit)]
            if prefix in _PREFIX:
                return value * _PREFIX[prefix]
            break
    if suffix in _PREFIX:  # bare prefix, no unit
        return value * _PREFIX[suffix]
    raise ValueError(f"unknown unit in {text!r}")


def _suffix_of(text: str) -> str:
    match = re.fullmatch(rf"{_NUMBER}\s*(.*)", text.strip())
    return match.group(1).strip() if match else ""


def parse_spec(spec: str | None) -> tuple[float, float]:
    """
    An atopile spec string as an inclusive (low, high) range in SI units.

    Handles the four shapes it emits: a single value `125mW`, a tolerance
    `680Ω ±1%`, a range `2-2.4V` or `90-110nF`, and the unconstrained `{ℝ+}A`.
    Raises UnconstrainedSpec for the last, because a check that silently treats
    "never specified" as "zero to infinity" passes for the wrong reason.
    """
    if spec is None or "ℝ" in spec or spec == "<empty>":
        raise UnconstrainedSpec(f"no usable value: {spec!r}")

    text = spec.strip()

    tolerance = re.fullmatch(rf"(.+?)\s*±\s*({_NUMBER})\s*%", text)
    if tolerance:
        centre = _magnitude(tolerance.group(1))
        fraction = float(tolerance.group(2)) / 100.0
        return centre * (1 - fraction), centre * (1 + fraction)

    # A range: the unit may appear only on the upper bound, as in `2-2.4V`.
    range_match = re.fullmatch(rf"({_NUMBER}\s*\S*?)\s*-\s*({_NUMBER}\s*\S*)", text)
    if range_match:
        low_text, high_text = range_match.group(1), range_match.group(2)
        high = _magnitude(high_text)
        low = _magnitude(low_text, fallback_suffix=_suffix_of(high_text))
        return low, high

    single = _magnitude(text)
    return single, single


@pytest.fixture(scope="session")
def spec(variables):
    """
    Look up one parameter's resolved range: `spec("leds[0].resistor", "resistance")`.

    Fails the test rather than returning something made up if the parameter is
    missing or was never constrained.
    """
    index = {(v["path"], v["name"]): v["spec"] for v in variables}

    def lookup(path: str, name: str) -> tuple[float, float]:
        if (path, name) not in index:
            pytest.fail(f"No parameter {path}.{name} in the variable report")
        try:
            return parse_spec(index[(path, name)])
        except UnconstrainedSpec as exc:
            pytest.fail(
                f"{path}.{name} cannot be checked: {exc}. "
                "Assert it in the part definition, from the datasheet."
            )

    return lookup


@pytest.fixture(scope="session")
def net_members(footprints) -> dict[str, set[tuple[str, str]]]:
    """
    Net name -> {(source address, pad)}.

    Addresses like `power.fuse` rather than designators like `F1`, because
    designators are assigned by the build and shift when a part is added.
    """
    out: dict[str, set[tuple[str, str]]] = {}
    for fp in footprints:
        address = fp["properties"].get("atopile_address", fp["designator"])
        for pad, net in fp["pads"].items():
            if net:
                out.setdefault(net, set()).add((address, pad))
    return out


@pytest.fixture(scope="session")
def net_parts(net_members) -> dict[str, set[str]]:
    """Net name -> the set of source addresses it touches, ignoring which pad."""
    return {net: {addr for addr, _ in members} for net, members in net_members.items()}


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
        fp["properties"].get("atopile_address"): (fp["x"], fp["y"])
        for fp in footprints
    }

    def lookup(address: str) -> tuple[float, float]:
        if address not in index:
            pytest.fail(f"no part at address {address}")
        return index[address]

    return lookup
