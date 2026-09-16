# led12 — 12 V LED board

A deliberately small board with no processor. Its job is to prove the design
pipeline end to end — declarative source, generated layout, rule checks,
simulation and CI gates — before any of it is trusted with the STM32H743
control board.

Press the button, four LEDs light. That is the whole function. Everything
interesting is in what had to be true for it to be correct.

| Top | Bottom |
|---|---|
| ![Top side](docs/board-top.png) | ![Bottom side](docs/board-bottom.png) |

50 × 40 mm, two layers, 30 parts, 68 track segments, 13 stitching vias, and a
ground pour on the back. **KiCad DRC reports no errors**, against both the fab
limits and the board's own rules. Nine warnings remain: seven
`lib_footprint_mismatch`, and two on one test point's silkscreen label.

The mismatch explanation here used to say it was because we add part identity to
the footprints. That was wrong. The count moved from four to seven when three
parts were rotated, and there are now exactly seven rotated parts on the board —
R1 to R4, Q1, D6 and D7. The cause is `pcbnew` re-normalising a rotated
footprint when it fills the pours, not anything about the design.

The silkscreen warnings were four and are now two: `tp_gnd`'s label sat on its
own pad outline and on `tp_12v`'s label, and moving it to the side fixed that
much. The remaining two are not positional — every offset tried leaves exactly
those two — and cannot be chased from the DRC report, whose JSON gives a
reference field's position as twice the offset actually written.

## How it works

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

**Q1's drain faces the supply.** A P-MOSFET's body diode has its anode on the
drain, so that is the orientation in which it blocks a reversed input. Source to
the supply reads more naturally, is how a high-side load switch is drawn, works
perfectly on the bench — and leaves the board completely unprotected. D6 and D7
are 15 V Zeners holding each FET's gate below its ±20 V rating during a clamp
event, which the TVS's 23.2 V would otherwise walk straight through.

## What is checked, and what that caught

Forty-four checks, thirteen simulated measurements, electrical rule checking on the
circuit itself, and DRC against both the PCBWay fab limits and the board's own
design rules. Each gate has been made to
fail on purpose at least once — a gate that has never failed is not a gate.

Eight real defects have been caught so far. The first five came from the gates
as they were built; the last three came from an adversarial review that went
looking for what the gates could **not** see, and every one of them is now
covered by a check that fails on it.

| Found | By |
|---|---|
| Bulk capacitor was a **6.3 V part on a 12 V rail**, and 100 µF at 25 V does not exist in 1210 at all | Verifying every part against the distributor |
| Reverse-polarity FET rated **±8 V gate-source** in a circuit that puts 13.2 V across it in normal operation | The same |
| LED series resistors dissipating **104 % of their rating** at nominal, 137 % at the corner — 680 Ω is a 5 V habit on a 12 V rail | `checks/test_electrical.py` |
| Regulator rated **15 V against a TVS that clamps at 19.9 V** — the protection would have destroyed what it protects | `checks/test_electrical.py` |
| **TVS fitted backwards.** `out.hv ~> tvs ~> out.lv` reads perfectly and bridges anode-to-cathode, shorting the rail through a forward-biased diode | KiCad DRC, once the board was routed |
| **The reverse-polarity FET was wired backwards** — source to the supply, so its body diode conducted under reverse polarity. With the TVS on the protected rail that is a two-diode short from ground to the reversed input, simulated at 69 A | Adversarial review. Now `test_reverse_polarity_fet_faces_the_supply`, which derives the answer from the netlist instead of a table |
| **The TVS stood off 12 V on a rail specified to 13.2 V**, so the protection conducted in normal operation at high line, and sooner when cold | Adversarial review. Now `test_tvs_stands_off_the_rail_it_protects` |
| **Neither FET's gate survived the clamp** — 23.2 V on a ±20 V gate, the Si2301 defect one layer down, with the rating recorded nowhere a check could reach | Adversarial review. Now `test_fet_gates_survive_the_tvs_clamp` |

And two defects in the *pipeline itself*:

- The generated rules file lived in a directory the build deletes, so any DRC
  run outside `make drc` checked the board against **no custom rules** — and
  changed the copper, producing a different ground pour.
- The design source named `Device:Q_NMOS_GSD` and `Device:Q_PMOS_GSD`, which
  exist in no KiCad library. Nothing noticed for months, because the old tool
  never resolved symbols at all. `checks/test_symbols.py` catches it now.
- The silkscreen rules policed every layer despite being named for silkscreen,
  so they fired on fabrication-layer text that is never printed.

## Bill of materials

Every part verified against LCSC — manufacturer, part number, supplier code,
stock and price — with a review note in `parts/<LIB>/<LIB>.md` recording the
datasheet it was read from and what a human confirmed.

| Ref | Value | Part | LCSC |
|---|---|---|---|
| C1 | 47 µF 25 V 1210 | Chinocera HGC1210R5476M250NSVK | C7432791 |
| C2 | 100 nF 50 V | YAGEO CC0805KRX7R9BB104 | C49678 |
| C3, C5 | 1 µF 50 V | Samsung CL21B105KBFNNNE | C28323 |
| C4 | 10 µF 25 V | Samsung CL21A106KAYNNNE | C15850 |
| D1–D4 | red LED, Vf 2.0–2.4 V | Everlight 17-21SURC/S530-A3/4T | C2943978 |
| D5 | TVS, 14 V standoff, 23.2 V clamp | BORN SMBJ14A | C152106 |
| D6, D7 | 15 V Zener gate clamp | Jiangsu Changjing BZT52C15 | C2104 |
| F1 | 1 A slow-blow | Littelfuse 0468001.NRHF | C45157 |
| J1 | 2-pole 5.08 mm terminal | Ningbo Kangnex WJ500V-5.08-2P | C8465 |
| Q1 | P-FET, −30 V, ±20 V gate | Alpha & Omega AO3407A | C15155 |
| Q2 | N-FET, 60 V, logic level | onsemi 2N7002LT1G | C16338 |
| R1–R4 | 2.2 k 1 % | Yageo RC0805FR-072K2L | C114561 |
| R5, R7 | 100 k 1 % | Yageo RC0805FR-07100KL | C96346 |
| R6 | 3.3 k 1 % | Yageo RC0805FR-073K3L | C114531 |
| R8 | 10 k 1 % | Yageo RC0805FR-0710KL | C84376 |
| SW1 | 6 mm tactile | Korean Hroparts K2-1102DP-C4SW-04 | C110153 |
| U1 | 3.3 V LDO, 44 V max in | Gainsil GS2401C-33CTR3 | C6283798 |
| TP1–TP4 | test pads | bare copper, deliberately off the BOM | — |

## The port off atopile

The design source has been moved off **atopile**, whose authors abandoned the
open-source project — no commits since 2026-03-11, every service except
telemetry switched off, the successor a sign-in-only browser product. The
replacement is **SKiDL**: MIT, maintained since 2016, with no company behind it
and nothing to switch off. `../README.md` has the evidence.

Only the design source changed. The layout engine, the checks, the simulation
and CI all stayed, and the board came out the same — same parts at the same
coordinates, same copper, same simulated numbers to every digit.

| | |
|---|---|
| **S0** Spike, and freeze the reference | **done** |
| **S1** Parts as Python data, symbol checks | **done** |
| **S2** The board as `@SubCircuit` blocks | **done** |
| **S3** The board writer, as text s-expressions | **done** |
| **S4** Re-point the checks and simulation | **done** |
| **S5** Remove atopile | **done** |
| **S6** The gates SKiDL makes possible | **done** |

The port is complete. One new gate came of it — electrical rule checking, which
runs in the design source before anything is placed and fails the build on any
message, warnings included. An unconnected pin is caught there now, rather than
surviving to DRC or to the board. Schematic generation was tried and rejected;
`../README.md` says why.

`reference/` holds the board as atopile last built it, frozen before the port
began: the fingerprint, the pad-level netlist, the BOM, the DRC report, the
placement file and the rendered simulation decks. The SKiDL board reproduces
them, with three deltas that were chosen rather than discovered — the four LED
anode nets are named `LED1_A`…`LED4_A` instead of being de-duplicated, net
numbering is alphabetical, and the `Value` strings are human (`47uF`, `red`)
rather than carrying the unconstrained-parameter notation the old tool leaked
into a silkscreen-adjacent field.

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
| `reference/` | the frozen golden set the port is measured against |

Everything else — how to build it, what each gate does, and what was learned
about the tools — is in [`../README.md`](../README.md).
