# TSSOP20 — the PWM buffers

| | |
|---|---|
| Component | `BUF_OCTAL` |
| Manufacturer | Texas Instruments |
| Part number | `SN74LVC541APWR` |
| LCSC | [C113281](https://www.lcsc.com/product-detail/C113281.html) |
| Footprint | `TSSOP-20_4.4x6.5mm_P0.65mm` |

Octal buffer, two output enables, 1.65 to 3.6 V, ±24 mA. Stock 3,792, read from
JLCPCB's component API on 2026-09-17. Two of them on the board.

## Why LVC, and why a '541 rather than a '244

**The '541 has two enables that both have to be low.** That is the whole
circuit: one from the MCU, one from the trip latch, in series in silicon. A
'244 has two enables as well, but each controls four outputs, so using it here
would mean wiring both of them to both sources and losing the independence.

**LVC because the interesting number is how fast it stops.** The trip budget is
tens of nanoseconds, and this part's disable time is 7 ns of it. The same
function in HC is four times that at 3.3 V, which would leave nothing for the
comparators.

## Figures used from the datasheet

TI's *SN54LVC541A, SN74LVC541A*, SCAS298N (January 1993, revised June 2014),
served by LCSC for C113281. At V_CC = 3.3 V ± 0.3 V, −40 to +85 °C.

| Figure | Value | Where |
|---|---|---|
| Supply voltage | 1.65 to 3.6 V | §7.3 |
| Propagation delay, A to Y | 1.5 to 5.1 ns | §7.7 |
| Enable time, OE to Y | 1.5 to 7 ns | §7.7 |
| Disable time, OE to Y | 1.5 to 7 ns | §7.7 |
| Output-to-output skew | 1 ns | §7.7 |
| Input thresholds | V_IH 2.0 V, V_IL 0.8 V | §7.3 |
| Output current, recommended | 24 mA per output at V_CC = 3 V | §7.3 |
| Output current, absolute maximum | ±50 mA per output | §7.1 |
| Package current, absolute maximum | ±100 mA through V_CC or GND | §7.1 |

The 1 ns skew is why a bridge's high and low sides go through the *same*
package: between two parts the bound is each one's own 1.5 to 5.1 ns window,
which is nearly four nanoseconds of shoot-through that dead time has to cover.
`checks/test_safety.py::test_complementary_pwm_outputs_go_through_the_same_buffer`
is what holds the channel assignment to that.

## Pin mapping

Pin 1 OE1, pins 2–9 A1–A8, pin 10 GND, pins 11–18 Y8–Y1, pin 19 OE2, pin 20
V_CC, read from the datasheet's Pin Functions table in full.

The symbol is KiCad's `74xx:74AHC541`, because no library carries an LVC541A.
**Every pin number matches**; only the names differ, KiCad counting A0..A7 and
Y0..Y7 where TI counts A1..A8 and Y1..Y8. This is the same substitution led12
makes for its LDO, and for the same reason: the footprint and the numbering are
what the board is built from.

**Footprint.** KiCad stock `Package_SO:TSSOP-20_4.4x6.5mm_P0.65mm`, unmodified.


## The package current was recorded as half what it is

This note used to read "25 mA per output, 50 mA per part". Neither figure was
right and the second was wrong in a way that mattered: §7.1 gives ±50 mA as
the continuous current *per output* and ±100 mA as the continuous current
through V_CC or GND, which is the package total. The 50 was the per-output
number read as a package one.

It was load-bearing while the trip budget was being closed with resistors: the
gate-line pull-downs were briefly taken from 10 k to 1.2 k, and the floor that
stopped them going lower was "eight outputs on one package against half of
50 mA" - a floor drawn against a per-output rating mistaken for a package one.
The resistor route turned out to be a dead end for other reasons (see
`parts/R0402/R0402.md`) and the fall is now done by a transistor, so the
number is no longer holding a value in place. It is still the number every
check uses, which is why it had to be right. See
`evidence/lvc541a_current_ratings.png`.

The per-output figure is what bounds Q2's drain resistor: 3.465 V across
33 + 150.5 ohm is 19 mA from the one output that fights it, against the 24 mA
§6.7 recommends for a guaranteed level, and well inside the ±50 mA §7.1
allows.
