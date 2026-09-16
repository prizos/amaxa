# SMB — SMB transient-voltage suppressor

| | |
|---|---|
| Component | `TVS_14V` |
| Manufacturer | BORN |
| Part number | `SMBJ14A` |
| LCSC | [C152106](https://www.lcsc.com/product-detail/C152106.html) |
| Footprint | `D_SMB` |

Unidirectional TVS, DO-214AA (SMB). Stock 17,941, $0.0658 at qty 1–99.
Extended — there is no Basic-library SMB TVS at all.

| | |
|---|---|
| Stand-off voltage | **14 V** |
| Breakdown voltage | 17.2 V (**maximum** of the band) |
| Clamping voltage | **23.2 V at 25.9 A** |
| Peak power | 600 W, 10/1000 µs |

Read from JLCPCB's component API and cross-checked against LCSC's own product
page for C152106, which states `SMBJ14A`, `DO-214AA(SMB)`, `14V`, `17.2V`,
`23.2V` and `600W`.

## Why this part replaced the SMBJ12A

**The stand-off voltage was below the rail.** The SMBJ12A stands off 12.0 V, and
this board's input is specified at 10.8 to 13.2 V. A TVS above its stand-off
voltage is in its knee, drawing leakage the datasheet does not bound and heating
itself — and because avalanche breakdown has a **positive** temperature
coefficient, a part that merely leaks at room temperature is in full conduction
when it is cold. At −40 °C the 12 A part's breakdown falls by roughly 0.8 V,
which puts a 13.2 V rail straight through it.

So the protection device was a load, in normal operation, at the top of the
range the board is specified to accept. The SMBJ14A's 14 V stand-off clears
13.2 V with 0.8 V to spare.

`hw/checks/test_electrical.py::test_tvs_stands_off_the_rail_it_protects` is the
check that enforces this. It did not exist while the SMBJ12A was fitted;
`reverse_working_voltage` was recorded in the design and compared against
nothing.

**The cost is a higher clamp.** 23.2 V rather than 19.9 V, and that number is
the constraint everything else on the rail lives under. It is what forced D6 and
D7: at 23.2 V the reverse-polarity FET's gate-source voltage and the low-side
FET's divider both exceed ±20 V. See `parts/SOD123/SOD123.md`.

## `v_breakdown_max`, not `v_breakdown_min`

The previous entry recorded 14.7 V for the SMBJ12A under the name
`v_breakdown_min`. **14.7 V is the top of that part's breakdown band**, not the
bottom — the SMBJ12A's V_BR is specified 13.3 to 14.7 V. The figure was right
and the name was wrong, which is worse than not recording it, because a check
written against the name would have reasoned from the wrong end.

Distributors quote a single V_BR figure and do not say which end it is. This
entry is named for what the number is.

## Why not Littelfuse

LCSC's Littelfuse SMBJ12A listing (C151251) carried 13 V / 15.9 V / 21.5 V /
28 A, which are the **SMBJ13A** numbers. Either the listing is
mis-parameterised or the stock is the wrong part. The same caution applies at
14 V: check the figures on the listing you actually order from.

## Pin mapping

Pad 1 cathode, pad 2 anode. The cathode is the banded end.
**Needs a human eye** against the manufacturer drawing before fabrication.

## Design note

The 23.2 V clamping voltage is the constraint the rest of the 12 V rail has to
live with. Nothing on that rail may have an absolute maximum below it, and
`test_rail_parts_survive_the_tvs_clamp` now derives the list of what is on that
rail **from the netlist** rather than from a hand-written list — the hand-written
one named six addresses while the rail actually reached twelve.

The bulk capacitor's 25 V rating is now the tightest thing on the rail, with
1.8 V of margin over the clamp. A part swap there needs checking against this
number, not against the 12 V the rail normally sits at.

**Footprint.** KiCad stock `Diode_SMD:D_SMB`, unmodified.
