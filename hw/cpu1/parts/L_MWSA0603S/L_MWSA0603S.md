# L_MWSA0603S — the 100 V buck's inductor

| | |
|---|---|
| Component | `IND_33U` |
| Manufacturer | Sunlord |
| Part number | `MWSA0603S-330MT` |
| LCSC | [C408454](https://www.lcsc.com/product-detail/C408454.html) |
| Footprint | `L_Sunlord_MWSA0603S` |

33 µH ±20 %, shielded, 7.0 × 6.6 mm. Stock 9,247, read from JLCPCB's component
API on 2026-09-17.

| | |
|---|---|
| Saturation current | 2.5 A |
| Rated (heating) current | 2.0 A |
| DC resistance | 270 mΩ |

## Why these numbers

**Saturation current is chosen against the converter, not the load.** At 0.7 A
out the peak inductor current is under an amp, and a 1.2 A part would look
generous. But an inductor that saturates before the converter's current limit
acts takes the decision away from the part that has a limit, a fold-back and a
comparator for exactly this case: the current rises without bound inside one
switching cycle and nothing sees a slope to act on. The LM5164's peak limit is
1.25 A at its lowest, so the inductor has to clear that — which is what
`test_the_inductors_are_never_the_first_thing_to_give_way` compares.

**270 mΩ is the weak figure here.** At 0.7 A it is 130 mW, about a fifth of the
loss the declared 80 % efficiency allows for the whole conversion, and
`test_the_inductors_do_not_spend_the_efficiency_the_design_assumes` holds it to
a third. A lower-resistance 33 µH part in this size exists; this one was chosen
on saturation current and stock. If the 5 V rail's budget grows, this is the
first part to revisit.

**Footprint.** KiCad stock `Inductor_SMD:L_Sunlord_MWSA0603S`, unmodified —
named for this manufacturer's own series, so the land pattern is the part's.
