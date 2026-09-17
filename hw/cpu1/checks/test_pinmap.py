"""
The pin map against the silicon.

Research rated this the highest-value custom check a board with an MCU can
have: a wrong pin number on a 144-pin part, a peripheral on a pin that cannot
carry it, or a wrong alternate-function number in firmware all build, route and
pass DRC, and are found on the bench.

These need no build, only `pinmap.py` and ST's vendored data, so `make pins`
runs them on their own.
"""

import sys
from pathlib import Path

import pytest

HW_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HW_DIR / "tools"))

import mcu_pins as pm  # noqa: E402
from stm32 import Silicon  # noqa: E402


@pytest.fixture(scope="module")
def board():
    return Path(__file__).resolve().parents[1].name


@pytest.fixture(scope="module")
def module(board):
    return pm.load(board)


@pytest.fixture(scope="module")
def silicon(module):
    return Silicon(module.PART)


def _fail_if(problems: list[str], headline: str):
    assert not problems, headline + ":\n" + "\n".join(f"  {p}" for p in problems)


def test_every_signal_is_on_a_pin_that_carries_it(module, silicon):
    """The part can actually do, on that pin, what the board uses it for."""
    _fail_if(pm.unknown_signals(module.PINS, silicon), "Signals the silicon cannot carry")


def test_every_alternate_function_has_its_number(module, silicon):
    """
    Every digital function has the `GPIO_AFn` value that selects it.

    The firmware cannot configure a pin without it, and the number is the part
    of a pin assignment most often copied wrongly by hand.
    """
    _fail_if(
        pm.missing_alternate_functions(module.PINS, silicon),
        "Alternate functions with no number",
    )


def test_no_pin_or_name_is_used_twice(module):
    _fail_if(pm.duplicates(module.PINS), "Pin map conflicts")


def test_peripherals_are_complete(module):
    """A UART has both lines, RMII all nine, and every bridge leg both switches."""
    _fail_if(pm.incomplete_peripherals(module.PINS), "Peripherals used in part")


def test_simultaneous_pairs_are_really_simultaneous(module):
    """Pairs sampled at one instant are on ADC1 and ADC2, which dual mode locks together."""
    _fail_if(
        pm.bad_simultaneous_pairs(module.PINS, getattr(module, "SIMULTANEOUS", [])),
        "ADC pairs that cannot be sampled simultaneously",
    )


def test_st_and_kicad_agree_about_the_part(module, silicon):
    """
    ST's data and KiCad's symbol describe the same pins in the same positions.

    The symbol is what the board is drawn with and ST's data is what the pins are
    checked against, so if they ever diverge, a pin can pass here and be wired
    somewhere else.
    """
    _fail_if(pm.sources_disagree(silicon, module.SYMBOL), "ST and KiCad disagree")


def test_firmware_header_matches_the_pin_map(board, module, silicon):
    """
    The committed firmware header is exactly what the pin map generates.

    Generated rather than written, so the firmware cannot use a pin the board
    does not, or an alternate-function number nobody checked.
    """
    path = pm.header_path(module)
    expected = pm.render_header(board, module, silicon)
    assert path.is_file(), f"{path} does not exist. Run `make -C hw pins-write BOARD={board}`."
    assert path.read_text() == expected, (
        f"{path.relative_to(pm.REPO_DIR)} differs from what {board}/pinmap.py generates. "
        f"Edit the pin map, not the header, then run `make -C hw pins-write BOARD={board}`."
    )
