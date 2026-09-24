"""
Shared fixtures for the board design checks.

Two directories of checks run against a board: `hw/checks/`, which apply to
every board, and `hw/<board>/checks/`, which are that board's own. This file sits
above both so they share one set of fixtures.

These read what a build produced — `design.json`, the BOM and the KiCad board —
and assert things about the design. They exist because the design source states
values and nothing more: anything relating two quantities, or anything about
board geometry, has to be checked here. See hw/README.md, "The checks".

Run them with `make -C hw check`, which builds first.
"""

import csv
import types
import json
import re
import sys
from pathlib import Path

import pytest

HW_DIR = Path(__file__).resolve().parent


def pytest_addoption(parser):
    parser.addoption(
        "--board",
        required=True,
        help="Board directory under hw/ to check",
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
            name = re.match(r'\(pad "([^"]*)" (\w+)', pad_block)
            net = re.search(r'\(net \d+ "([^"]*)"\)', pad_block)
            # A non-plated hole has no number and can never carry a net, so it
            # is not a pad to check for one.
            if name and name.group(2) != "np_thru_hole" and name.group(1) != "":
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


# Every (path, name) any check actually looked up, recorded by the `spec` and
# `spec_has` fixtures. A textual scan of this directory cannot stand in for it:
# half the lookups are built from f-strings (`spec(f"{branch}.led", ...)`) or
# from a tuple of candidate parameter names, so grep both misses real reads and
# cannot tell a live one from a mention in a comment.
PARAMETERS_READ: set[tuple[str, str]] = set()


def pytest_collection_modifyitems(config, items):
    """
    Record how many checks were collected, and run the coverage guards last.

    The guards assert on what every other check read, so they have to run after
    them. Sorting on a boolean is stable, so nothing else moves.
    """
    # Checks that will actually execute, not checks that exist. A skipped test
    # is still collected, so counting collection let `@pytest.mark.skip` turn a
    # gate off in one line without the guard noticing — verified: the suite
    # reported "30 passed, 1 skipped" and stayed green.
    config.collected_check_count = sum(
        1
        for item in items
        if not (item.get_closest_marker("skip") or item.get_closest_marker("skipif"))
    )
    guards = {"test_every_declared_parameter_is_read", "test_every_design_intent_is_read_by_something"}
    items.sort(key=lambda item: item.name in guards)


@pytest.fixture(scope="session")
def collected_check_count(pytestconfig) -> int:
    return getattr(pytestconfig, "collected_check_count", 0)


@pytest.fixture(scope="session")
def parameters_read() -> set[tuple[str, str]]:
    """Every (path, name) the checks have looked up so far. Read it last."""
    return PARAMETERS_READ


@pytest.fixture(scope="session")
def board_config(board_dir):
    """
    The board's own declarations for the common checks: `<board>/checks/config.py`.

    Its expected check count, the parameters it deliberately leaves unread and
    why, and the pin mappings still waiting on a person.
    """
    path = board_dir / "checks" / "config.py"
    if not path.is_file():
        pytest.fail(f"no {path}. Every board declares what the common checks need.")
    return _load(path, f"{board_dir.name}_checks_config")


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
        PARAMETERS_READ.add((path, name))
        if key not in values:
            pytest.fail(
                f"{key} is not in design.json. Either the path is wrong, or the "
                "part never states that value."
            )
        low, high = values[key]
        return float(low), float(high)

    return lookup


@pytest.fixture(scope="session")
def unguaranteed(spec, spec_has):
    """
    What to multiply a figure its datasheet declined to bound.

    `unguaranteed("trip.fast1_high")` -> 1.667.

    **The board's own figure was a judgement, and the parts disagree with
    it.** `loads.unguaranteed_margin` adds a flat quarter to anything called
    `*_typical` or `*_at_25c`, and its own comment says so: "a judgement
    rather than a measurement ... there to be replaced by a measurement on
    the first assembled board". It is applied to the comparator's hysteresis,
    which is a term in the trip point's error budget.

    A datasheet that gives no maximum for one row usually gives one for
    others, and **that is the vendor's own statement of how far its parts
    travel from typical.** Where a part declares
    `typical_to_maximum_worst` - the worst ratio its own table publishes -
    that number is used instead.

    Two things keep this from being a way of choosing a smaller number:

      - the house quarter is a **floor**. A part whose own table happens to
        be tight cannot argue its way below it, only above;
      - the ratio is taken from rows of the same *kind*. A datasheet writes a
        mismatch specification with a plus-or-minus - the TLV3501's offset is
        `+-1` typ against `+-6.5` max - and a designed quantity as a plain
        number. Those spread differently and by large factors, and the
        distinction is visible in the datasheet's own notation rather than
        being a reading of it. Each part's declaration names the rows it came
        from.
    """
    def factor(address: str) -> float:
        floor = 1.0 + spec("loads", "unguaranteed_margin")[1]
        if spec_has(address, "typical_to_maximum_worst"):
            return max(floor, spec(address, "typical_to_maximum_worst")[1])
        return floor

    return factor


@pytest.fixture(scope="session")
def spec_has(design):
    """
    Whether a part declares a parameter at all, without failing if it does not.

    `spec` deliberately fails on a missing value, because a check that treats
    "never specified" as "anything" passes for the wrong reason. This is for
    the checks that walk a set of parts and have to ask which of several
    ratings each one carries.
    """
    values = design["values"]

    def has(path: str, name: str) -> bool:
        PARAMETERS_READ.add((path, name))
        return f"{path}.{name}" in values

    return has


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
    return _load(path, f"{board_dir.name}_parts").ALL


def _load(path: Path, name: str):
    """From source, never a cached `.pyc`: see `tools/mcu_pins.py`'s `load_source`."""
    module = types.ModuleType(name)
    module.__file__ = str(path)
    exec(compile(path.read_text(), str(path), "exec"), module.__dict__)
    return module
