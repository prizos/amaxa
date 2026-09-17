# HDR2X15 — the analog connector to the power board

| | |
|---|---|
| Component | `HEADER_2X15` |
| Manufacturer | HCTL |
| Part number | `PZ254-2-15-Z-8.5` |
| LCSC | [C3012255](https://www.lcsc.com/product-detail/C3012255.html) |
| Footprint | `PinHeader_2x15_P2.54mm_Vertical` |

30 pins, 2.54 mm, through-hole, 3 A per contact. Stock 821, read from JLCPCB's
component API on 2026-09-17. The same family as the digital connector, and a
pin header for the same reason: the real connector gets chosen when there is a
power board to connect to.

## What crosses it

Seventeen signals and thirteen grounds, laid out by the same generator the
digital header uses — two signals, then a ground, all the way along.

Fourteen of the seventeen come *in*: three phase currents, the DC link, three
phase voltages, an auxiliary fast channel, four slow ones and two board-identity
divider taps. Every one of them is **raw**. The comparators watch these nets
directly and the anti-alias filter between each one and the MCU's own ADC pin is
a later block, because a filter slow enough to be worth having on a 1 MSPS ADC
costs hundreds of nanoseconds and the trip budget is fifty.

Three go *out*: VREF+, so the power board's sensors can be ratiometric to the
same reference the ADCs use, and two pins of 5VA for them to run from.

## VREF+ leaves this board unbuffered

Straight off the REF3030, which can source 25 mA and is specified with no
output capacitor required. What it is not specified for is a metre of cable,
and the plan asks for an op-amp buffer here.

Until that exists, **the power board's sensors must draw next to nothing from
this pin**, and the reference's own load regulation — 100 µV/mA — is the number
that says what "next to nothing" buys. A sensor bridge pulling a milliamp costs
a tenth of a millivolt, which is nothing; a resistive divider to ground on the
far end of the cable is a different matter.

## 5VA is a bead, not a regulator

The 5 V rail through a 600 Ω ferrite, which is what VDDA gets and for the same
reason. A low-noise LDO would be better and is what the plan asks for; the bead
is what this block needs to name the rail and get the pin onto the connector,
and replacing it later changes one part.

**Footprint.** KiCad stock `Connector_PinHeader_2.54mm:PinHeader_2x15_P2.54mm_Vertical`,
unmodified.
