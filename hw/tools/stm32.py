"""
What an STM32 package's pins can do, from ST's own data.

Two files per part, vendored under `hw/silicon/<part>/` with their provenance:

- the MCU file, which is the authority on what exists: every pin, its position,
  its type, and the signals *this package* bonds out;
- the GPIO modes file, which supplies the `GPIO_AFn_*` value selecting each
  digital alternate function. It describes a whole family, so it names signals
  a given package does not have. It is only ever asked for a number, never
  whether a signal exists.

Pin names in both files carry decorations — `PA13 (JTMS/SWDIO)`,
`PH0-OSC_IN (PH0)` — so every name is reduced to its port and number first.

Dependency-free, like everything in tools/ that the checks import.
"""

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

HW_DIR = Path(__file__).resolve().parent.parent
_NS = {"st": "http://dummy.com"}

# Signals that are not selected through an alternate-function number: analog
# inputs and outputs, the oscillators, and a pin's plain GPIO role. Anything
# else is a digital alternate function and must have a `GPIO_AFn_*` value.
_ADDITIONAL_FUNCTIONS = re.compile(
    r"^(GPIO|ADC\d+_(INP|INN)\d+|DAC\d+_OUT\d+|COMP\d+_(INP|INM)|OPAMP\d+_\w+|"
    r"RCC_OSC(32)?_(IN|OUT)|USB_OTG_FS_VBUS|PWR_WKUP\d+)$"
)


def base_name(name: str) -> str:
    """`PA13 (JTMS/SWDIO)` -> `PA13`; `PC2_C` stays `PC2_C`; `VDD` stays `VDD`."""
    match = re.match(r"^(P[A-K]\d+(?:_C)?)", name)
    return match.group(1) if match else name.split(" ")[0]


@dataclass
class PinInfo:
    name: str
    positions: list[str]
    type: str
    signals: set[str] = field(default_factory=set)


class Silicon:
    """One STM32 part's pins, as ST describes them."""

    def __init__(self, part: str, directory: Path | None = None):
        self.part = part
        directory = directory or HW_DIR / "silicon" / part
        mcu = ET.parse(directory / f"{part}.xml").getroot()

        self.package = mcu.get("Package")
        self.pins: dict[str, PinInfo] = {}
        gpio_ip = None
        for node in mcu.findall("st:Pin", _NS):
            name = base_name(node.get("Name"))
            info = self.pins.setdefault(name, PinInfo(name, [], node.get("Type")))
            info.positions.append(node.get("Position"))
            info.signals |= {s.get("Name") for s in node.findall("st:Signal", _NS)}
        for ip in mcu.findall("st:IP", _NS):
            if ip.get("Name") == "GPIO":
                gpio_ip = ip.get("Version")
        if gpio_ip is None:
            raise ValueError(f"{part}: the MCU file names no GPIO IP")

        modes = ET.parse(directory / f"GPIO-{gpio_ip}_Modes.xml").getroot()
        self._af: dict[tuple[str, str], str] = {}
        for gpio in modes.findall("st:GPIO_Pin", _NS):
            name = base_name(gpio.get("Name"))
            for signal in gpio.findall("st:PinSignal", _NS):
                values = [v.text for v in signal.findall(".//st:PossibleValue", _NS)]
                if values:
                    self._af[(name, signal.get("Name"))] = values[0]

    @property
    def io_pins(self) -> dict[str, PinInfo]:
        return {name: info for name, info in self.pins.items() if info.type == "I/O"}

    def has(self, pin: str, signal: str) -> bool:
        info = self.pins.get(pin)
        return info is not None and signal in info.signals

    def af(self, pin: str, signal: str) -> str | None:
        """The `GPIO_AFn_*` value for a signal on a pin, or None if it takes none."""
        return self._af.get((pin, signal))

    @staticmethod
    def needs_af(signal: str) -> bool:
        """Whether a signal is a digital alternate function, selected by number."""
        return not _ADDITIONAL_FUNCTIONS.match(signal)

    def position(self, pin: str) -> str:
        return self.pins[pin].positions[0]


def kicad_pins(symbol_file: Path, symbol: str) -> dict[str, tuple[list[str], set[str]]]:
    """
    A KiCad symbol's pins: base pin name -> (pin numbers, alternate functions).

    KiCad's STM32 symbols are generated from the same ST data, and are kept here
    as an independent second source rather than trusted as the first.
    """
    text = symbol_file.read_text()
    start = text.find(f'(symbol "{symbol}"')
    if start < 0:
        raise KeyError(f"{symbol} not in {symbol_file}")
    block = _balanced(text, start)
    out: dict[str, tuple[list[str], set[str]]] = {}
    for match in re.finditer(r"\(pin \w+ \w+\s", block):
        pin = _balanced(block, match.start())
        name = base_name(re.search(r'\(name "([^"]*)"', pin).group(1))
        number = re.search(r'\(number "([^"]*)"', pin).group(1)
        alternates = set(re.findall(r'\(alternate "([^"]*)"', pin))
        numbers, signals = out.setdefault(name, ([], set()))
        numbers.append(number)
        signals |= alternates
    return out


def _balanced(text: str, start: int) -> str:
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return text[start:]
