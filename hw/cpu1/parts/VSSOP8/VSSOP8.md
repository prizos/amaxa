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

## The clear is AC-coupled, so a stuck pin cannot hold it

PG5 reaches this part's clear through a 1 k and a 4.7 nF, with the 10 k pull-up
on the far side. Driving the pin low puts the clear at 3.135 x 1/11 = 0.29 V,
under V_IL, and it recovers through (1 k + 10 k) x 4.7 nF = 57 us: asserted for
about 11 us, a valid high again by 53 us, whatever the pin does afterwards.

Without it, a pin driven low and then abandoned - a handler spinning while it
still feeds the watchdog, or a debugger halt with the IWDG frozen - holds the
clear asserted for ever, and a permanently cleared latch is worse than no latch.
A trip presets it, the outputs go off, the current decays, the comparator
releases the preset, and the latch immediately clears itself and turns the
outputs back on. The board then sits in sustained over-current at the trip
threshold, and because both inputs low puts Q-bar high, the MCU's break input
reads *no trip* the whole time.

`test_the_clear_reaches_a_valid_low_and_lets_go_by_itself` does this arithmetic
from the three part values, and `test_the_latch_can_only_be_cleared_by_the_mcu`
asserts that every path from the MCU to this pin crosses a capacitor.

## Clearing the latch hides the break input while it happens

With `~PRE` and `~CLR` both low the datasheet's nonstable condition drives
**both** Q and Q-bar high. Q-bar is `TRIP_N`, which is the board's only trip
status signal and both timers' break input — so for as long as firmware holds
the clear asserted, the break input reads *no trip* whatever the trip bus is
doing.

That is a trap for the rearm sequence, and the firmware had it: `pwm_rearm()`
refuses to rearm while `pwm_break_input_active()`, and that function reads the
same pin. Clear and rearm in one breath, with a fault still asserting, and the
board reports "rearmed" every time.

`pwm_clear_trip_latch()` in `firmware/apps/hello_hw/pwm.c` is the sequence
that does not have the trap: it releases `~CLR` **before** anything is read,
so what gets read is the state after the latch has settled. A trip source that
is still asserting sets the latch again as soon as `~CLR` goes high, and the
break input goes back low, which is the answer the caller wanted.

Nothing called the clear yet when this was written, which is the reason to put
the correct sequence in before something does.
