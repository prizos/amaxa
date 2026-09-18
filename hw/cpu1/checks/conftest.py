"""
Fixtures shared by cpu1's own checks.

Two of them, both about the board as built rather than as designed: the
stackup the layout computes its impedances from, and what each net's copper
actually measured once it was routed.
"""

import json
import sys

import pytest


@pytest.fixture(scope="session")
def stack(board_dir):
    """The dielectric between the outer layers and the plane beside them."""
    sys.path.insert(0, str(board_dir.parent / "tools"))
    from layout_lib import Microstrip
    from mcu_pins import load_source

    board = load_source(board_dir / "layout.py", "cpu1_layout_stack").BOARD
    first = board["stack"][0]
    return Microstrip(height=first["thickness"], epsilon_r=first["epsilon_r"])


@pytest.fixture(scope="session")
def lengths(build_dir):
    """net -> millimetres of copper, written by the layout as it routed."""
    report = build_dir / "lengths.json"
    assert report.is_file(), "no lengths.json; run `make layout` first"
    return json.loads(report.read_text())
