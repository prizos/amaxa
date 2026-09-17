# LQFP144 — the MCU

| | |
|---|---|
| Component | `MCU_H743` |
| Manufacturer | STMicroelectronics |
| Part number | `STM32H743ZIT6` |
| LCSC | [C114408](https://www.lcsc.com/product-detail/C114408.html) |
| Footprint | `LQFP-144_20x20mm_P0.5mm` |

Cortex-M7 at 480 MHz, 2 MB flash, 1 MB RAM, 114 I/O, LQFP-144 20 × 20 mm,
−40 to +85 °C, supply 1.62 to 3.6 V.

| Qty | $ each |
|---|---|
| 1–9 | 11.06 |
| 10–29 | 9.92 |
| 30–99 | 9.18 |
| 100+ | 8.48 |

Read from JLCPCB's component API on 2026-09-17 and cross-checked against
LCSC's product page for C114408, which states `STM32H743ZIT6`, `LQFP-144`,
`2MB`, `1MB` and `480MHz`.

## Stock: zero

**JLCPCB listed no stock of this part on 2026-09-17.** Every other part on the
project's boards so far had thousands. An assembled order needs either stock to
return, a consigned reel, or hand-fitting the MCU. This has to be resolved
before ordering, not discovered at checkout.

## Figures used from the datasheet

ST's datasheet, *STM32H743xI*, DocID030538 Rev 3 (October 2017), served by LCSC
for C114408. ST's own site did not respond to automated requests, so AN4938 —
ST's hardware development guide for the part — was not read.

| Figure | Value | Where |
|---|---|---|
| Supply voltage | 1.62 to 3.6 V | Table 23 |
| VCAP capacitor CEXT | 2.2 µF per VCAP pin, ESR < 100 mΩ | Table 24 |
| HSE maximum critical gm | 1.5 mA/V | Table 43 |
| HSE load capacitors | 5 to 25 pF typical | Section 6.3.8 |
| LSE maximum critical gm | 0.5 / 0.75 / 1.7 / 2.7 µA/V by drive | Table 44 |
| I/O pin current | 20 mA absolute maximum | Table 21 |
| NRST capacitor | 100 nF, internal pull-up 30–50 kΩ | Figure 21, Table 62 |
| Supply decoupling | N × 100 nF + 1 × 4.7 µF on VDD; "100 nF + 1 x 1 µF" pairs | Figure 13 |

**Needs a human eye.** Figure 13 is a drawing, and its extracted text gives the
decoupling values without saying which supply pin each belongs to: "100 nF",
"100 nF + 1 x 1 µF" and "4.7 µF" appear beside VDDA, VREF+, VDD33USB and VBAT in
no recoverable order. The board gives every supply pin its 100 nF, and both 3V3
and VDDA a 1 µF, which covers the likely reading — but read the figure, and
AN4938, before ordering.

## Why this part

Recorded in [`docs/research/README.md`](../../../../docs/research/README.md#decision).

## Pin mapping

Not taken from a datasheet page, and not in need of a human eye, because it is
checked by machine. The symbol is KiCad's `MCU_ST_STM32H7:STM32H743ZITx`, and
`hw/cpu1/checks/test_pinmap.py` requires every one of its 144 pin positions and
every I/O pin's function list to match ST's own data for the part, vendored in
`hw/silicon/STM32H743ZITx/`. The footprint's pads are numbered 1–144 and
`hw/checks/test_symbols.py` requires them to match the symbol's pins.

What that does not establish is that pad 1 of the stock footprint sits where
ST's package drawing puts pin 1. The footprint is KiCad's standard LQFP-144 with
pin 1 top left and numbering counter-clockwise, which is the JEDEC convention
ST's LQFP packages follow; confirming it against the package drawing is part of
the gerber review before ordering.

**Footprint.** KiCad stock `Package_QFP:LQFP-144_20x20mm_P0.5mm`, unmodified.
