# led12 — 12 V LED board

A deliberately small board with no processor. Press the button, four LEDs light.
That is the whole function. Its job is to prove the design pipeline end to end
before any of it is trusted with the STM32H743 control board.

| Top | Bottom |
|---|---|
| ![Top side](docs/board-top.png) | ![Bottom side](docs/board-bottom.png) |

50 × 40 mm, two layers, 30 parts, and a ground pour on the back. **It has never
been fabricated.**

## The circuit

```
                       D ┌────┐ S
  12V in ──[fuse 1A]─────┤ Q1 ├────┬───────┬── 12V
                         └─┬──┘    │       │
                           G      TVS   47uF + 100nF
                    100k ──┤ D6           │
                     GND ──┴──┘           ├── 4 x (2k2 + LED) cathodes
                                          │
  button ──[10k]──┬── N-FET gate          └── LDO 3V3 ── 3k3 load
                  │
             1uF ─┤ 100k ──┤ D7   N-FET drain sinks LED_RETURN
                  └── GND ──┘
```

The input is fused, reverse-polarity protected by a P-FET, and clamped by a TVS.
Pressing the button charges the gate of a low-side N-FET through an RC network,
which sinks the return of four LED branches. A linear regulator provides a 3.3 V
rail with a fixed load so it can be measured. Four test pads expose 12 V, 3.3 V,
ground and the gate.

Three things are less obvious than they look:

- **Q1's drain faces the supply.** A P-MOSFET's body diode has its anode on the
  drain, so that is the orientation in which it blocks a reversed input. Source
  to the supply reads more naturally, is how a high-side load switch is drawn,
  works perfectly on the bench — and leaves the board unprotected.
- **D6 and D7 are 15 V Zeners clamping each FET's gate.** The TVS clamps at
  23.2 V, and both FETs are ±20 V gate-source, so without these a surge takes
  each gate past its rating. 15 V is the only window: above the 13.2 V the rail
  may reach, below the 20 V the FETs allow.
- **The TVS stands off 14 V, not 12.** The rail is specified to 13.2 V, and a
  TVS above its stand-off voltage leaks — more so cold, because avalanche
  breakdown has a positive temperature coefficient. A 12 V part made the
  protection a load at high line.

## Bill of materials

Generated at `build/bom.csv` by `make build`, and published with every CI run.
Every part is verified against the distributor, with a review note in
`parts/<LIB>/<LIB>.md` recording the datasheet it was read from, what was
rejected and why, and what still needs a person to confirm.

**Four of those notes are still marked "Needs a human eye"**, all of them pin
mappings taken from footprint geometry or distributor symbol data rather than
from a manufacturer drawing. One says in plain words that the board may short
3V3 to GND if its assumption is wrong. `checks/test_parts.py` tracks the list;
clearing it is a precondition for ordering.

## What the gates caught

Eight real defects so far, and the split is the interesting part.

**Five came from the gates as they were built:** a bulk capacitor that was a
6.3 V part on a 12 V rail; a reverse-polarity FET rated ±8 V gate-source in a
circuit that puts 13.2 V across it; LED series resistors dissipating 104 % of
their rating, because 680 Ω is a 5 V habit; a regulator rated 15 V behind a TVS
clamping at 19.9 V; and the TVS itself fitted backwards.

**Three came from an adversarial review** that went looking for what the gates
could *not* see — and all three were in the board, not the checks. The
reverse-polarity FET was wired source-to-supply, so its body diode conducted
under reverse polarity: a two-diode short from ground to the reversed input,
simulated at 69 A. The TVS stood off 12 V on a 13.2 V rail. And neither FET's
gate survived the clamp.

The lesson worth carrying is the second one. The check meant to catch a part
fitted backwards was *holding the FET backwards*, because its expected value was
a hand-written table of what we believed. Correcting the board turned that check
red. Expected values are derived from the netlist now, wherever they can be.

## DRC

Zero errors, against both the PCBWay fab limits and the board's own rules. Nine
warnings remain, and neither group is about the design:

- **Seven `lib_footprint_mismatch`**, one per rotated footprint — R1–R4, Q1, D6,
  D7. `pcbnew` re-normalises a rotated footprint when it fills the pours. The
  count moved from four to seven when three parts were rotated, which is how the
  cause was established.
- **Two silkscreen**, on `tp_gnd`'s reference. Two more were fixed by moving the
  label off its own pad outline; these last two are not positional — every
  offset tried leaves exactly them — and cannot be chased from the DRC report,
  whose JSON gives a reference field's position as twice the offset written.

## The files

| | |
|---|---|
| `led12.py` | the circuit — the only file that knows SKiDL |
| `parts.py` | every part as data — symbol, footprint, part number, datasheet figures |
| `layout.py` | the board: size, placement, routing, vias and the ground pour |
| `board.kicad_pro` | netclasses and the clearances DRC enforces |
| `rules.kicad_dru` | design intent: track widths, clearances |
| `sim/` | ngspice decks, device models and the bands each measurement must meet |
| `parts/<LIB>/` | footprint, and the review note recording what a human checked |
| `reference/` | the board as the previous design source last built it, frozen |

How to change any of it, and what each gate does, is in
[`../README.md`](../README.md).
