#!/usr/bin/env python3
"""
led12 — the 12 V LED board, as a circuit.

    12V in ──[fuse 1A]──┬──[P-FET reverse polarity]──┬── 12V
                        │                            │
                       TVS                    47uF + 100nF
                                                     │
      button ──[10k]──┬── N-FET gate                 ├── 4 x (2k2 + LED)
                      │                              │       cathodes
                 1uF ─┤ 100k                         └── LDO 3V3 ── 3k3 load
                      └── GND              N-FET drain sinks LED_RETURN

Press the button: the gate charges through the debounce network, the N-FET
turns on and the LEDs light. Release: the 100k discharges the gate.

This is the only file in the repository that knows SKiDL exists. It writes
`design.json`, which everything downstream reads — the board writer, the
checks, the simulation. That indirection is deliberate: the previous design
tool's output format had become our internal interface, and every place we read
it was a place that tool could hurt us. Change design source again and one file
changes.

Two conventions carry the whole pipeline:

  **Addresses.** Every instance has a stable name like `power.q_rpp` or
  `leds[0].resistor`, independent of its designator. Placement, routing,
  topology checks and simulation decks are all written in terms of them, so
  they must not drift. They are also passed to SKiDL as instance tags, which
  is what makes its output deterministic — left to itself it invents a random
  tag per part and writes it into the netlist.

  **Designators are pinned, not assigned.** Every `ref=` below is explicit.
  Auto-assignment makes the mapping from a physical board to its bill of
  materials a function of source ordering, so a part added next year would
  renumber the silkscreen of a board already in a drawer.

Run it with `make -C hw build`.
"""

import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
os.environ.setdefault("KICAD9_SYMBOL_DIR", "/usr/share/kicad/symbols")
sys.path.insert(0, str(HERE))

from skidl import ERC, KICAD9, POWER, Net, Part, SubCircuit  # noqa: E402
from skidl.logger import erc_logger  # noqa: E402
from skidl import generate_netlist  # noqa: E402
from skidl import set_default_tool  # noqa: E402

import parts  # noqa: E402

set_default_tool(KICAD9)

# Parameters that describe the design rather than any one component: what the
# board expects at its input, and what its regulator is designed to deliver.
# The checks and the simulation decks read these by the same paths as any part
# parameter.
INTENT: dict[str, tuple[float, float]] = {
    "power.out.voltage": (10.8, 13.2),
    "rail.power_out.voltage": (3.234, 3.366),
}

_addresses: dict[str, object] = {}


def part(spec: parts.PartSpec, address: str, ref: str) -> Part:
    """One instance of a part, tagged with the address the rest of the tree uses."""
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


# --- the blocks --------------------------------------------------------------


@SubCircuit
def power_input(raw_hv, rail, gnd):
    """Screw terminal, fuse, reverse-polarity FET and input bulk capacitance."""
    terminal = part(parts.SCREW_TERM_2, "power.terminal", "J1")
    fuse = part(parts.FUSE_1A, "power.fuse", "F1")
    q_rpp = part(parts.PFET_RPP, "power.q_rpp", "Q1")
    r_gate = part(parts.RES_100K, "power.r_gate", "R5")
    tvs = part(parts.TVS_12V, "power.tvs", "D5")
    c_bulk = part(parts.CAP_BULK, "power.c_bulk", "C1")
    c_hf = part(parts.CAP_100N, "power.c_hf", "C2")

    # Terminal, then fuse, then the P-FET. The FET conducts only when the
    # supply is the right way round; reversed, its body diode blocks.
    raw_hv += terminal[1], fuse[1]
    gnd += terminal[2]
    Net("VIN_FUSED").connect(fuse[2], q_rpp["S"])
    rail += q_rpp["D"]

    # The gate sits at ground through the 100k, so V_gs is the whole rail once
    # it comes up — which is why this part must be rated for it.
    Net("RPP_GATE").connect(q_rpp["G"], r_gate[1])
    gnd += r_gate[2]

    # Surge clamp across the protected rail, then bulk and decoupling.
    # Named pins, not a chain: a diode bridged anode-to-cathode across a rail
    # conducts at 0.7 V and shorts the supply.
    rail += tvs[1]      # cathode, to the rail it protects
    gnd += tvs[2]       # anode
    rail += c_bulk[1], c_hf[1]
    gnd += c_bulk[2], c_hf[2]


@SubCircuit
def debounced_switch(rail, gnd, gate, switched):
    """Push button, RC debounce, and the low-side switch it drives."""
    button = part(parts.BUTTON_6MM, "switch.button", "SW1")
    r_series = part(parts.RES_10K, "switch.r_series", "R8")
    r_pulldown = part(parts.RES_100K, "switch.r_pulldown", "R7")
    c_debounce = part(parts.CAP_1U, "switch.c_debounce", "C5")
    q_switch = part(parts.NFET_SWITCH, "switch.q_switch", "Q2")

    rail += button[1]
    Net("BTN").connect(button[2], r_series[1])

    # The gate node: series resistor, pulldown, capacitor and FET all meet.
    gate += r_series[2], r_pulldown[1], c_debounce[1], q_switch["G"]
    gnd += r_pulldown[2], c_debounce[2], q_switch["S"]

    switched += q_switch["D"]


@SubCircuit
def led_branch(rail, switched, index):
    """One series resistor and LED, between the rail and the switched return."""
    resistor = part(parts.RES_2K2, f"leds[{index}].resistor", f"R{index + 1}")
    led = part(parts.LED_RED, f"leds[{index}].led", f"D{index + 1}")

    # Named explicitly rather than left to be de-duplicated: four branches
    # cannot all carry the same name, and the numbering should be ours.
    rail += resistor[1]
    Net(f"LED{index + 1}_A").connect(resistor[2], led[2])   # LED pin 2 is the anode
    switched += led[1]                                       # pin 1 is the cathode


@SubCircuit
def rail_3v3(rail, gnd, out):
    """12 V to 3.3 V, with a fixed load so the rail can be measured."""
    ldo = part(parts.LDO_3V3, "rail.ldo", "U1")
    c_in = part(parts.CAP_1U, "rail.c_in", "C3")
    c_out = part(parts.CAP_10U, "rail.c_out", "C4")
    r_load = part(parts.RES_3K3, "rail.r_load", "R6")

    rail += ldo["VI"], c_in[1]
    out += ldo["VO"], c_out[1], r_load[1]
    gnd += ldo["GND"], c_in[2], c_out[2], r_load[2]


# --- the board ---------------------------------------------------------------


def build() -> Net:
    """Assemble the board. Returns one of its nets, which carries the circuit."""
    rail = Net("12V")
    gnd = Net("GND")
    v3v3 = Net("3V3")
    raw = Net("VIN_RAW")
    gate = Net("GATE")
    switched = Net("LED_RETURN")

    # The supply arrives through a screw terminal, whose pins are passive, so
    # nothing on the board drives these nets and ERC would report every part
    # hanging off them as undriven. Saying so explicitly is the true statement:
    # they are driven, from outside the board.
    raw.drive = POWER
    rail.drive = POWER
    gnd.drive = POWER
    v3v3.drive = POWER

    power_input(raw, rail, gnd, tag="power")
    debounced_switch(rail, gnd, gate, switched, tag="switch")
    rail_3v3(rail, gnd, v3v3, tag="rail")
    for index in range(4):
        led_branch(rail, switched, index, tag=f"leds[{index}]")

    # Test points on every rail plus the gate, so the board can be probed.
    # Designators follow the board that already exists rather than the order
    # they are written in.
    for address, ref, net in (
        ("tp_12v", "TP2", rail),
        ("tp_3v3", "TP1", v3v3),
        ("tp_gnd", "TP4", gnd),
        ("tp_gate", "TP3", gate),
    ):
        net += part(parts.TEST_PAD, address, ref)[1]

    return rail


# --- what the rest of the pipeline reads -------------------------------------


def design(circuit) -> dict:
    """The circuit as data: what each part is, what it does, and what joins it."""
    components = {}
    values = dict(INTENT)

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
        "board": "led12",
        "parts": components,
        "values": {key: list(value) for key, value in sorted(values.items())},
        "nets": dict(sorted(nets.items())),
    }


def main() -> int:
    circuit = build().circuit

    # Warnings fail the build as well as errors. SKiDL calls an unconnected
    # passive pin a warning, which is precisely the mistake worth catching, and
    # this board sits at zero of both. A warning that appears later has to be
    # silenced deliberately - `do_erc = False` on the net or pin that earns it -
    # which is a line in a diff rather than a message nobody reads.
    ERC()
    errors = erc_logger.error.count
    warnings = erc_logger.warning.count
    generate_netlist(file_=str(HERE / "build" / "led12.net"))
    data = design(circuit)
    (HERE / "build" / "design.json").write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    )

    print(
        f"{len(data['parts'])} parts, {len(data['nets'])} nets, "
        f"{len(data['values'])} values"
    )
    if errors or warnings:
        print(
            f"\nERC: {errors} errors, {warnings} warnings. Both fail the build; "
            "see the note in main()."
        )
        return 1
    return 0


if __name__ == "__main__":
    (HERE / "build").mkdir(exist_ok=True)
    sys.exit(main())
