#!/usr/bin/env python3
"""
A board's MCU pin map: one table, checked against the silicon, rendered for the
firmware.

A board with an MCU keeps `<board>/pinmap.py`, declaring:

    PART        the ST part, e.g. "STM32H743ZITx", matching hw/silicon/<PART>/
    SYMBOL      the KiCad symbol, "Library:Name"
    FIRMWARE    the generated header, relative to the repository root
    PINS        a list of Pin
    SIMULTANEOUS  optional (master, slave) name pairs sampled in dual mode

The same table wires the MCU in the design source and generates the firmware's
pin header, so the board and the firmware cannot disagree about a pin without
one of them failing to build or a check failing. The checks themselves live in
the board's `checks/test_pinmap.py` and call the functions here.

    python3 tools/mcu_pins.py cpu1            # regenerate the firmware header
"""

import re
import sys
import types
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

HW_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = HW_DIR.parent
sys.path.insert(0, str(HW_DIR / "tools"))

from stm32 import Silicon, kicad_pins  # noqa: E402

KICAD_SYMBOL_DIR = Path("/usr/share/kicad/symbols")


@dataclass(frozen=True)
class Pin:
    """One MCU pin, what it is used for, and what the board calls it."""

    pin: str
    """Port and number as ST writes it: `PE9`, `PC2_C`."""

    signal: str
    """ST's signal name: `TIM1_CH1`, `ADC1_INP2`, `DEBUG_JTMS-SWDIO`, or `GPIO`."""

    name: str
    """What the board calls it. Becomes the net name and the firmware macro."""

    direction: str = ""
    """For `GPIO` only: `in` or `out`."""

    net: str = ""
    """
    The copper node, when it is not this pin's own name.

    Two pins can share one node - both timers' break inputs come from one latch
    output - and then each still needs its own name, because the firmware
    header has a macro per pin. This is what keeps those two facts apart.
    """

    idle: str = ""
    """
    For a connector signal, the rail it must be pulled to with nothing
    attached: `3V3` or `GND`.

    An unfitted or unplugged power board must not read as permission, and
    which rail that means is a property of the *signal*, not of the copper -
    a fault line is active low so it idles high, a safe-torque-off feedback
    idles low, a strap floats to the code that means "no board". It lives
    here because the pin map is where what a signal means is written down;
    `checks/test_safety.py` held the same ten facts as a dictionary of its
    own, which is a table of beliefs inside the thing that was supposed to be
    checking them.
    """

    note: str = ""

    @property
    def net_name(self) -> str:
        return self.net or self.name


# --- loading ------------------------------------------------------------------


def load(board: str):
    path = HW_DIR / board / "pinmap.py"
    if not path.is_file():
        raise FileNotFoundError(f"{board} has no pinmap.py")
    return load_source(path, f"{board}_pinmap")


def load_source(path: Path, name: str):
    """
    Import a board's data file from its source, never from a cached `.pyc`.

    Python trusts a cached compile if the source's size and modification time
    (to the second) are unchanged. Edit a file and put it back within a second —
    or change `STM32H743ZITx` to `STM32H743IITx`, which is the same length — and
    the checks read the edited version while the file on disk says otherwise.
    That happened while these checks were being break-tested.
    """
    module = types.ModuleType(name)
    module.__file__ = str(path)
    code = compile(path.read_text(), str(path), "exec")
    exec(code, module.__dict__)
    return module


# --- what can be wrong with a pin map --------------------------------------------


def unknown_signals(pins: list[Pin], silicon: Silicon) -> list[str]:
    """Every pin exists on this package and carries the signal it is used for."""
    out = []
    for p in pins:
        if p.pin not in silicon.pins:
            out.append(f"{p.name}: {p.pin} is not a pin of {silicon.part}")
        elif silicon.pins[p.pin].type != "I/O":
            out.append(f"{p.name}: {p.pin} is a {silicon.pins[p.pin].type} pin, not I/O")
        elif not silicon.has(p.pin, p.signal):
            out.append(f"{p.name}: {p.pin} cannot carry {p.signal}")
    return out


def missing_alternate_functions(pins: list[Pin], silicon: Silicon) -> list[str]:
    """Every digital alternate function has the `GPIO_AFn` value that selects it."""
    return [
        f"{p.name}: {p.signal} on {p.pin} is a digital alternate function with no "
        "GPIO_AF value in ST's modes file"
        for p in pins
        if silicon.has(p.pin, p.signal)
        and silicon.needs_af(p.signal)
        and silicon.af(p.pin, p.signal) is None
    ]


def duplicates(pins: list[Pin]) -> list[str]:
    """No pin used twice, no name used twice, and every name a C identifier."""
    out = []
    for attribute in ("pin", "name"):
        seen = defaultdict(list)
        for p in pins:
            seen[getattr(p, attribute)].append(p)
        for value, users in seen.items():
            if len(users) > 1:
                out.append(f"{attribute} {value} used by {', '.join(u.name for u in users)}")
    out += [
        f"{p.name}: not usable as a net or macro name"
        for p in pins
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", p.name)
    ]
    out += [
        f"{p.name}: a GPIO needs a direction, in or out"
        for p in pins
        if p.signal == "GPIO" and p.direction not in ("in", "out")
    ]
    return out


# Signals that are no use on their own. Each tuple is a set that must be used
# all together or not at all, per peripheral instance.
_TOGETHER = [
    (r"USART(\d+)_(TX|RX)$", ["TX", "RX"]),
    (r"UART(\d+)_(TX|RX)$", ["TX", "RX"]),
    (r"FDCAN(\d+)_(TX|RX)$", ["TX", "RX"]),
    (r"I2C(\d+)_(SCL|SDA)$", ["SCL", "SDA"]),
    (r"USB_OTG_FS_(DM|DP)$", ["DM", "DP"]),
    (r"RCC_OSC_(IN|OUT)$", ["IN", "OUT"]),
    (r"RCC_OSC32_(IN|OUT)$", ["IN", "OUT"]),
    (r"DEBUG_(JTMS-SWDIO|JTCK-SWCLK)$", ["JTMS-SWDIO", "JTCK-SWCLK"]),
    (
        r"ETH_(REF_CLK|MDIO|MDC|CRS_DV|RXD0|RXD1|TX_EN|TXD0|TXD1)$",
        ["REF_CLK", "MDIO", "MDC", "CRS_DV", "RXD0", "RXD1", "TX_EN", "TXD0", "TXD1"],
    ),
]


def incomplete_peripherals(pins: list[Pin]) -> list[str]:
    """
    Peripherals whose signals only make sense together are used together.

    Serial ports need both lines, RMII needs all nine, an oscillator needs both
    ends. And a timer driving complementary outputs drives them for every
    channel it uses: a half bridge with a high side and no low side is a board
    that shoots through or never switches.
    """
    used = {p.signal for p in pins}
    out = []
    for pattern, members in _TOGETHER:
        groups = defaultdict(set)
        for signal in used:
            match = re.match(pattern, signal)
            if match:
                key = match.group(1) if match.re.groups > 1 else ""
                groups[key].add(match.groups()[-1])
        for key, present in groups.items():
            missing = [m for m in members if m not in present]
            if missing:
                label = re.sub(r"\(.*", key, pattern).rstrip("_")
                out.append(f"{label}: has {sorted(present)} but not {missing}")

    timers = defaultdict(lambda: {"CH": set(), "CHN": set()})
    for signal in used:
        match = re.match(r"TIM(\d+)_CH(\d)(N?)$", signal)
        if match:
            timers[match.group(1)]["CHN" if match.group(3) else "CH"].add(match.group(2))
    for timer, channels in sorted(timers.items()):
        if not channels["CHN"]:
            continue  # not a complementary-output timer on this board
        highs, lows = channels["CH"], channels["CHN"]
        for channel in sorted(lows - highs):
            out.append(f"TIM{timer}: CH{channel}N has no CH{channel}")
        for channel in sorted((highs & {"1", "2", "3"}) - lows):
            out.append(f"TIM{timer}: CH{channel} drives a bridge leg with no CH{channel}N")
    return out


def bad_simultaneous_pairs(pins: list[Pin], pairs: list[tuple[str, str]]) -> list[str]:
    """
    Each pair sampled at the same instant is on ADC1 and ADC2, in that order.

    Dual regular simultaneous mode ties ADC2 to ADC1: ADC1 is the master and
    ADC2 converts on its trigger. ADC3 can share a trigger but is not locked to
    it, so a pair involving ADC3 is not simultaneous and must not be called so.
    """
    by_name = {p.name: p for p in pins}
    out = []
    for master, slave in pairs:
        for role, name, adc in (("master", master, "ADC1"), ("slave", slave, "ADC2")):
            p = by_name.get(name)
            if p is None:
                out.append(f"({master}, {slave}): no pin named {name}")
            elif not re.match(rf"{adc}_INP\d+$", p.signal):
                out.append(f"({master}, {slave}): {role} {name} is {p.signal}, needs {adc}_INPn")
    return out


def sources_disagree(silicon: Silicon, symbol: str) -> list[str]:
    """ST's data and KiCad's symbol agree on every pin's positions and functions."""
    library, _, name = symbol.partition(":")
    kicad = kicad_pins(KICAD_SYMBOL_DIR / f"{library}.kicad_sym", name)
    out = []
    for pin, info in sorted(silicon.pins.items()):
        if pin not in kicad:
            out.append(f"{pin}: in ST's data, not in {symbol}")
            continue
        numbers, alternates = kicad[pin]
        if sorted(numbers) != sorted(info.positions):
            out.append(f"{pin}: ST puts it at {sorted(info.positions)}, KiCad at {sorted(numbers)}")
        if info.type == "I/O":
            st_functions = {s for s in info.signals if s != "GPIO"}
            if st_functions != alternates:
                out.append(
                    f"{pin}: only ST has {sorted(st_functions - alternates)}, "
                    f"only KiCad has {sorted(alternates - st_functions)}"
                )
    out += [f"{pin}: in {symbol}, not in ST's data" for pin in sorted(set(kicad) - set(silicon.pins))]
    return out


# --- the firmware header ------------------------------------------------------------


def render_header(board: str, module, silicon: Silicon) -> str:
    """The pin header, as C. Deterministic, so a committed copy can be compared."""
    lines = [
        "/*",
        f" * {board} pin map for the {silicon.part} ({silicon.package}).",
        " *",
        f" * GENERATED from hw/{board}/pinmap.py by hw/tools/mcu_pins.py. Do not edit:",
        " * a check fails if this file differs from what the pin map generates.",
        " * Regenerate with `make -C hw pins-write BOARD=" + board + "`.",
        " */",
        f"#ifndef {board.upper()}_BOARD_PINS_H",
        f"#define {board.upper()}_BOARD_PINS_H",
        "",
    ]
    for p in module.PINS:
        port, number = re.match(r"P([A-K])(\d+)", p.pin).groups()
        what = p.signal if p.signal != "GPIO" else f"GPIO {p.direction}put"
        comment = f"{what} on {p.pin}, pin {silicon.position(p.pin)}"
        if p.note:
            comment += f". {p.note}"
        lines.append(f"/* {p.name}: {comment} */")
        lines.append(f"#define PIN_{p.name}_PORT GPIO{port}")
        lines.append(f"#define PIN_{p.name}_PIN GPIO_PIN_{number}")
        af = silicon.af(p.pin, p.signal)
        if af:
            lines.append(f"#define PIN_{p.name}_AF {af}")
        adc = re.match(r"(ADC\d)_INP(\d+)$", p.signal)
        if adc:
            lines.append(f"#define PIN_{p.name}_ADC {adc.group(1)}")
            lines.append(f"#define PIN_{p.name}_ADC_CHANNEL ADC_CHANNEL_{adc.group(2)}")
        lines.append("")
    lines.append(f"#endif /* {board.upper()}_BOARD_PINS_H */")
    return "\n".join(lines) + "\n"


def header_path(module) -> Path:
    return REPO_DIR / module.FIRMWARE


def main() -> int:
    if len(sys.argv) != 2:
        sys.exit(f"usage: {Path(sys.argv[0]).name} <board>")
    board = sys.argv[1]
    module = load(board)
    silicon = Silicon(module.PART)
    path = header_path(module)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_header(board, module, silicon))
    print(f"wrote {path.relative_to(REPO_DIR)}: {len(module.PINS)} pins")
    return 0


if __name__ == "__main__":
    sys.exit(main())
