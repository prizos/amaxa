# VSSOP8 — the trip latch

| | |
|---|---|
| Component | `LATCH_DFF` |
| Manufacturer | Texas Instruments |
| Part number | `SN74LVC1G74DCUR` |
| LCSC | [C70285](https://www.lcsc.com/product-detail/C70285.html) |
| Footprint | `VSSOP-8_2.3x2mm_P0.5mm` |

Single D flip-flop with asynchronous preset and clear, 1.65 to 5.5 V.
Stock 5,300, read from JLCPCB's component API on 2026-09-17.

## What it is doing here

Not counting anything. Its clock and data are tied to ground and never move; the
only inputs that do anything are the preset and the clear, which makes it a
set-reset latch with one input per direction and no way to reach an undefined
state from the outside.

Preset wins the board's power-on, because NRST is low then and NRST is what the
preset sees. So the board comes out of every reset — power-on, watchdog,
debugger — with its outputs already off, and firmware has to clear the latch
deliberately before anything can switch. A flip-flop with no preset would come
up in whichever state it settled into, which is the wrong answer half the time.

## Figures used from the datasheet

TI's *SN74LVC1G74*, SCES794E (October 2009, revised January 2015), served by
LCSC for C70285. At V_CC = 3.3 V, −40 to +85 °C.

| Figure | Value | Where |
|---|---|---|
| Supply voltage | 1.65 to 5.5 V | §7.3 |
| Preset or clear to output | 1.7 to 5.9 ns | §7.7 |
| Input thresholds | V_IH 2.0 V, V_IL 0.8 V | §7.3 |
| Output current | ±24 mA at 3 V | §7.3 |

**V_IL is the number the Schottky diodes were chosen against.** Three things
pull the trip bus low, each through a diode of its own so none of them is wired
to the others, and each reaches 0.8 V only if its own low level plus the diode's
forward drop stays under it. A silicon diode's 0.7 V would spend the entire
budget; `test_the_trip_bus_reaches_a_valid_low_through_its_diodes` is the check.

Both low at once — a fault while firmware is clearing — drives both outputs
high, which the datasheet calls a nonstable condition. It resolves to whichever
input is released last, so a fault that persists keeps the latch tripped when
the clear is released. That is the behaviour wanted, and it is worth knowing it
comes from a footnote rather than from the circuit.

## Pin mapping

Pin 1 CLK, 2 D, 3 Q̄, 4 GND, 5 Q, 6 CLR, 7 PRE, 8 V_CC, read from the
datasheet's Pin Functions table.

The symbol is KiCad's `74xGxx:74AUP1G74`, which carries exactly that numbering —
checked pin by pin against the table above. No library has a 74LVC1G74 symbol,
and the AUP part of the same function is pin-identical.

**Footprint.** KiCad stock `Package_SO:VSSOP-8_2.3x2mm_P0.5mm`, unmodified.
The DCU package is 2.3 × 2.0 mm on a 0.5 mm pitch.
