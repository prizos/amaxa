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
