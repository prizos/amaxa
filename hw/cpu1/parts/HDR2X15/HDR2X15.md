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

Fourteen of the seventeen come *in*: eight fast channels, four slow ones and
two board-identity divider taps. What each one measures is the power board's
business — this board knows only how fast it has to be read and whether a
comparator watches it. Every one of them is **raw**. The comparators watch these nets
directly and the anti-alias filter between each one and the MCU's own ADC pin is
a later block, because a filter slow enough to be worth having on a 1 MSPS ADC
costs hundreds of nanoseconds and the trip budget is fifty.

Three go *out*: VREF+, so the power board's sensors can be ratiometric to the
same reference the ADCs use, and two pins of 3V3A for them to run from.

## VREF+ leaves this board unbuffered

Straight off the REF3030, which can source 25 mA and is specified with no
output capacitor required. What it is not specified for is a metre of cable,
and the plan asks for an op-amp buffer here.

Until that exists, **the power board's sensors must draw next to nothing from
this pin**, and the reference's own load regulation — 100 µV/mA — is the number
that says what "next to nothing" buys. A sensor bridge pulling a milliamp costs
a tenth of a millivolt, which is nothing; a resistive divider to ground on the
far end of the cable is a different matter.

## The sensor supply is 3.3 V, and that is an interface decision

It was 5 V through a 600 Ω ferrite. The sense lines come back into TT_xx
analog pins that ST's Table 20 caps at **4.0 V absolute** with no
positive-injection allowance, and a sensor's op-amp rails to its own supply
during exactly the over-current the trip chain exists for — so a 5 V supply
out of this connector was a 5.25 V fault this board had no way to clamp.

A TLV70233 regulates it to 3.3 V instead, and at the top corner of its 2 %
accuracy a sensor can rail to 3.366 V, which the pins take. See
`parts/SOT23_5/SOT23_5.md`.

**What a power board gives up:** sensors that need 5 V — an ACS724, a LEM
module — cannot run from this pin. They run from the gate-drive supply every
power board already has, **on the power board's own side**, and their output
is scaled to this rail. That is the trade, and it is stated here because it is
the connector's business rather than the regulator's.

It said "from the 12–15 V aux on the digital header" and there is no such pin.
The digital header is 2×26 and carries 3V3 and nothing else that is a
supply.

**Footprint.** KiCad stock `Connector_PinHeader_2.54mm:PinHeader_2x15_P2.54mm_Vertical`,
unmodified.
