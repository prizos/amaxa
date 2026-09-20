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

**"At 0.7 A out" was wrong, and it was the check's number as well.** L1 sits
between the switch node and the 5 V rail, so everything the 3V3 buck draws
goes through it too: the converter delivers **0.887 A**, not the 5 V rail's
own budget. At 36 V in, 391.5 kHz and the inductance's low corner the peak is
**1.095 A against the 1.25 A limit — a 12 % margin**, where the check was
reporting 63 %. The part is still untroubled at 2.5 A of saturation; what this
is about is the converter reaching cycle-by-cycle limit at full budget.

## Why 33 µH stays, at 12 %

Raising the inductance is the obvious way to buy margin and it is blocked by
the winding, from both ends:

- The peak is load plus half the ripple, and the load is 0.887 A of the
  1.095. Twenty per cent of margin needs the ripple down from 0.416 A to
  0.226, which is **61 µH** nominal — nearly twice this part. (It said 76,
  which applies the ±20 % band upward from nominal as well as taking the low
  corner, counting the same tolerance twice.)
- Winding loss is `I² × DCR`, and the loss budget is what the declared
  efficiency leaves over: 0.887 W for the whole conversion, of which
  `test_the_inductors_do_not_spend_the_efficiency_the_design_assumes` allows
  an inductor a third. At 270 mΩ this part spends 212 mW of that 296. A 61 µH
  part in this footprint runs 500 mΩ or more and spends 390 mW against that
  296 mW, which fails.

Raising the switching frequency instead — halving the on-time resistor — would
halve the ripple current and buy the same margin. It also halves the ripple
injected at the feedback pin, which has 29 % of margin above the LM5164's
12 mV minimum and would drop through it. The two constraints pull opposite
ways and 33 µH is where they meet.

**So the margin is 12 % and it is a stacked worst case**: every rail at its
declared maximum at once, the inductance at the bottom of ±20 %, and the input
at 36 V. Reaching the limit folds the output back; it does not damage
anything. It is the first thing to measure at bring-up, and the figure to
revisit if the 3V3 budget grows.

**270 mΩ is the weak figure here.** At 0.7 A it is 130 mW, about a fifth of the
loss the declared 80 % efficiency allows for the whole conversion, and
`test_the_inductors_do_not_spend_the_efficiency_the_design_assumes` holds it to
a third. A lower-resistance 33 µH part in this size exists; this one was chosen
on saturation current and stock. If the 5 V rail's budget grows, this is the
first part to revisit.

**Footprint.** KiCad stock `Inductor_SMD:L_Sunlord_MWSA0603S`, unmodified —
named for this manufacturer's own series, so the land pattern is the part's.
