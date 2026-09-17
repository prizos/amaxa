# SMB — the input transient suppressor

| | |
|---|---|
| Component | `TVS_40V` |
| Manufacturer | BORN |
| Part number | `SMBJ40A` |
| LCSC | [C152095](https://www.lcsc.com/product-detail/C152095.html) |
| Footprint | `D_SMB` |

Unidirectional TVS, DO-214AA (SMB), 600 W. Stock 8,772, read from JLCPCB's
component API on 2026-09-17.

| | |
|---|---|
| Stand-off voltage | **40 V** |
| Breakdown voltage | 44.4 V minimum, **51.1 V maximum** |
| Clamping voltage | **64.5 V at 9.3 A** |
| Peak power | 600 W, 10/1000 µs |

Stand-off, clamping voltage and peak pulse current are from the SMBJ series
table led12's note traces to, read again here for the 40 V row. BORN's own
listing on LCSC quotes 49.1 V for the breakdown maximum against that table's
51.1 V; the larger figure is the one recorded, because every check that uses it
gets stricter as it rises.

## Why 40 V on a 36 V rail

A TVS has to stand off the top of the rail it protects, and this board's input
is specified to 36.0 V **exactly**. The 36 V part's stand-off equals that, which
is the same defect led12 shipped one size down: above its stand-off voltage a
TVS is in its knee, drawing leakage nobody bounds, and avalanche breakdown has a
positive temperature coefficient — a part that merely leaks when warm conducts
hard when cold.

Narrowing the declared input range to 32 V would have made the 36 V part fit.
Keeping 9 to 36 V — a 24 V industrial supply at +50 % — was worth the higher
clamp.

## What the higher clamp costs

64.5 V rather than 58.1 V, and that number is the constraint everything on the
input rail lives under:

- the buck is a 100 V part, 1.55× the clamp;
- the input capacitors are 100 V, checked against the **breakdown** maximum
  rather than the clamp, because between stand-off and breakdown the TVS does
  nothing at all and the capacitors hold the rail alone;
- the FET's gate clamp has to survive conducting at 64.5 V, which is what
  `test_the_gate_clamp_survives_conducting_through_a_surge` works out.

## Pin mapping

Pad 1 cathode, pad 2 anode. The cathode is the banded end.
**Needs a human eye** against the manufacturer's drawing before fabrication.

**Footprint.** KiCad stock `Diode_SMD:D_SMB`, unmodified. The same library
directory as led12's, which carries the 14 V part.
