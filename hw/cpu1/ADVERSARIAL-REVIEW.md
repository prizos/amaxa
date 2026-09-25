# cpu1 — how much of this board is proven, and how much is prose

The question this round was asked: *how much of it is real, and simulated to
prove it's real, or mathematically proven, and how much is simply words.*

Five agents each took one area — the safety chain, power, the measurement
path, routing and copper, and the evidence base — and were told to attack
rather than to summarise. Everything below that is a number I re-derived
myself before writing it down; where a figure is an upper bound rather than a
count, it says so.

---

## The answer, in one table

Two denominators matter, and they give different answers, which is itself the
finding.

**The 206 checks**, counted by what each one actually reads. The suite is
**214** now; the eight added since were not re-classified, so the denominator
below is the one the classification was done against:

| | | |
|---|---|---|
| run against a circuit simulator | **22** | 11 % |
| derive a number from the netlist, the routed copper or the stackup | **130** | 64 % |
| assert structure only — this is wired to that, this exists | **72** | 35 % |

**The 843 declared values** the checks compare against, counted by where the
number came from. That figure is **874** now, for the same reason:

| | | |
|---|---|---|
| produced by a simulation | **0** | — |
| a datasheet figure typed into `parts.py` | **777** | 92 % |
| ...of those, on a part with at least one committed evidence crop | **310** | 40 % of the 777, *at best* |
| design intent declared in `cpu1.py` | **66** | 8 % |

So: the machinery that *checks* is largely real. The numbers it checks
against are largely typed. A check that reads 22.22 Ω off the netlist,
multiplies it correctly and compares it to a bound is doing real arithmetic on
a figure nobody verified against a measurement.

---

## 1. What is simulated: almost nothing

*This section described the board before the trip chain was simulated; what it
says about the power path is still true, and the count above has moved from
6 measurements to 27, across six decks. `sim/trip_chain.cir.in`
integrates the chain end to end and gets 33.5 ns where the arithmetic sums to
40.5; `sim/trip_clear.cir.in` runs the AC-coupled clear with its clamp as a
diode; `sim/power_up.cir.in` holds the rails' ordering at every instant and
reproduces `c297e58` when the reference is moved back to the 5 V rail; and
`sim/rmii_transmit.cir.in` drives the RMII's two critical nets as
transmission lines, reproduces ST's own 20 pF test jig beside them, and finds
that the analytic budget was adding the board's copper on top of a figure
already measured into a load. **So comms is no longer unsimulated either.**
See `DESIGN-REVIEW.md` §3 and §8. What follows is the argument that got them
built, and what it says about the power path's **loops** - as opposed to its
ordering - is still true: nothing simulates a control loop, ripple, inrush or
a falling rail.*

Two ngspice decks, `sim/adc_corner.cir.in` and `sim/adc_settling.cir.in`, six
`.meas` statements between them. Both are about one ADC input network.

**Nothing in the safety chain is simulated.** Not the latch, not the trip bus,
not the clear pulse, not the gate kill, not the buffers. The 40.5 ns trip
chain — the number this board exists to make true — is five closed-form terms
summed in Python from datasheet figures and measured copper capacitance. That
is arithmetic, and it is good arithmetic, but no solver has ever integrated
this circuit.

Nothing in the power path is simulated: not the buck loops, not the inrush,
not the reverse-polarity FET, not the TVS. Nothing in comms is.

`led12` — the small proven board — has **three** decks and 18 `.meas`
statements, three times as many as this one. The complicated board is the less
simulated of the two.

### And the one deck that could disagree with a check, cannot

`adc_corner.cir.in` substitutes the source impedance, the series resistor
**and** the shunt capacitor all at `:max`. Its own comment says why: that is
the end that makes the corner lowest, and a corner that is too low is the
dangerous one. The consequence is that the deck only ever evaluates one end of
a two-ended band.

Concretely, with the fitted 4.7 nF the deck reports 1.271 MHz and the check's
band is 1.271–1.728 MHz — the deck reproduces the low end exactly and has
nothing to say about the high one. Substitute a 3.3 nF part and the deck
reports **1.810 MHz, inside the declared 1–2 MHz, and passes**, while the
check computes a high end of **2.460 MHz and rejects it**. The simulation
would sign off a network the design rejects.

That is not a wrong deck; it is a deck doing half the job its header claims
("the second method, and it is worth having only while the two can
disagree"). On the upper corner they cannot disagree.

---

## 2. What is derived, and genuinely binds

This is the part of the board that holds up. 129 of the 205 checks read a real
quantity, and the quantities come from places that move when the board moves:

- **the netlist** — which pad is on which net, walked, not tabulated;
- **the routed copper** — track lengths, via positions, per-net capacitance
  against the planes, measured off `default.kicad_pcb` on every run;
- **the stackup** — impedances computed from prepreg thickness and εr;
- **ST's vendored silicon data** — every pin function and alternate number.

The strongest examples, each of which has been watched to fail:

| what | how it binds |
|---|---|
| the 3V3 rail at 814.4 mA of 850 | every load summed off the netlist by walking to ground |
| the trip chain at 40.5 ns of 50 | five terms, four of them from part figures, one from measured copper |
| every resistor's worst case | a fault model that found a real 174 % overload |
| the decoupling reach | every MCU supply pad matched one-to-one against placed copper |
| the pair impedances | from the stackup, not from a table |

The rule that makes this count for something is that no check may contain a
hand-written table of expected values. That rule has been enforced against
itself: a `POLARITY` table once enforced a backwards reverse-polarity FET, and
that is why it exists.

**72 checks assert structure only.** They are not weak — "no PWM pin reaches
the connector except through a buffer" is the most load-bearing assertion on
the board and it reads no numbers at all — but they cannot catch a wrong
value, only a wrong wire.

---

## 3. What is a datasheet figure taken on trust: most of it

774 of the 839 declared values are parameters of a specific part, typed into
`parts.py` from a datasheet. 257 of the 272 footprints carry an LCSC code that
was verified against the distributor's live API — **which proves the part is
buyable, and nothing whatever about any number attached to it.**

The mechanism this project has for going further is an evidence crop: the
relevant table or figure cut out of the PDF at 200 dpi and committed beside
the part, with the source URL and the PDF's sha256 in a sidecar. There are
**32 crops**, covering 17 of the 41 footprint directories and 21 of the 72
distinct part numbers. At most 307 of the 774 parameters belong to a part that
has any crop at all — and that is an upper bound, not a count, because a crop
covers one table and a part may declare figures from several.

**The two gaps that matter are both in the safety chain:**

- `SOT523` — the gate-kill FET, whose on-resistance, gate charge and thermal
  figures are three of the five terms in the trip budget. **Zero crops.**
- `VSSOP8` — the 74LVC1G74 latch, whose propagation delay is the first term in
  that same budget. **Zero crops.**

Two of the gaps this round named have since been closed, and both were closed
because a number moved onto load-bearing ground rather than because the list
was worked through: the REF3030's whole electrical table
(`SOT23/ref3030_electrical.png`) once every trip threshold became a fraction
of its output, and the MCP4728's absolute maximums
(`MSOP10/absolute_maximum.png`) once the I²C bus had to be held to them. The
first of those also caught a figure read from the wrong column — 50 µA of
quiescent current at 25 °C where the boldface 59 µA over temperature was the
one that applied.

Every passive package is also uncropped, which matters less — a 10 kΩ ±1 %
0402's tolerance is not a figure anyone misreads — but the two above are not
passives, and the chain they time is the reason the board exists.

---

## 4. What is simply words

Prose in this repository is load-bearing: the part `.md` files, the design
comments and `docs/research/` are where the *reasoning* lives, and no check
reads any of it. This round attacked the prose directly and found five
statements that were wrong, unbacked, or both. All five are fixed; three now
have checks that would catch a relapse.

| claim | where it was | what was true | now |
|---|---|---|---|
| the PWM lines arrive "about 200 ns" after the gate line | 3 files, computed in none | 32–39 ns bare, up to 188 ns into 10 pF — the old figure was the loaded end quoted as the figure | derived by a new check, all three files corrected |
| PG5 is "pulled up, so a reset pin does not clear it" | `pinmap.py` | the pull-up is on the *other* side of the coupling capacitor; nothing holds PG5 | note rewritten; a new check holds every pull claim in the pin map to the copper |
| "the DAC comes out of reset at zero" | `parts/SOT23_6/SOT23_6.md` | it powers up at zero and has no reset pin; `cpu1.py` said so and the two contradicted each other | corrected to agree with `cpu1.py` |
| "there is also a watchdog path that cuts PWM" | `docs/research/07` | there is no watchdog net and no watchdog part; the IWDG's timeout is a reset, and `NRST` presets the latch | corrected to describe the path that exists |
| "a 36 V stand-off TVS clamps near 58 V" | `DESIGN-REVIEW.md` §5 | the fitted part is an SMBJ40A: 40 V stand-off, 64.5 V clamp. The old figures were the part the *plan* proposed | corrected |
| "six independent things stop the outputs" | `DESIGN-REVIEW.md` §3 | six mechanisms, five of which meet at the latch. Three are independent | corrected, with the three named |
| 603 vias, 8.3 % tap error, 9.4 ns tap delay | `DESIGN-REVIEW.md` | 602, 8.58 %, 10.6 ns | corrected |

The pattern is worth naming: **every one of these was a number or a mechanism
that had been written down once, believed, and then copied.** None of them
survived being asked "which check reads this?".

---

## 5. Two defects in the checks themselves

**One declaration doing two jobs — and the first fix was wrong.**
`trip.threshold_tolerance` is 12 %. The accuracy check summed the rail, the
comparator and the DAC's offset, gain and nonlinearity to 11.46 % and passed.
The filter-loading check computed the comparator tap's amplitude deficit at
8.58 % and compared it against *the same 12* and passed. That looked like one
budget spent twice, so the two were summed — 20.0 % — and filed as a blocker.

Working the dynamics showed the sum was wrong. The 8.58 % is a fraction of the
*step*; the other five are fractions of the *threshold*. A ramp gets the
delay, a step gets the deficit, and no one signal gets both. And the deficit
does not make a trip late: a lead-lag's output jumps immediately to R/(Rs + R)
of its input, so a fault already 9.38 % over its threshold fires on the
instant.

| a step this far over the threshold | fires after |
|---|---|
| 5.0 % | 69.9 ns |
| **9.4 %** | **0 ns** |
| 300 % | 0 ns |

So the real defect was thinner: one declared name was serving as both a DC
error budget and a dynamic amplitude bound. `trip.prompt_overshoot` — a
quarter — is the declaration that was missing, and the tap's real cost stays
where it belongs, as 10.55 ns of the 20 ns reserved for it in `trip.budget`.

**And the thing that came out of examining it.** The largest remaining term
was the logic rail at 5.00 %, because the MCP4728's full scale *is* its supply
and its supply was 3V3 — while every channel the ADCs convert is ratiometric
to VREF+. Thresholds and measurements were scaled by two different numbers.
The DAC's supply is VREF+ now, its I²C pull-ups with it (Microchip's absolute
maximum is VDD + 0.3 V, and a bus on the logic rail would have been 171 mV
outside it), and the budget is **7.46 % of 12** instead of 11.46 % — 7.06 %
when this was written, before two drift terms were added that it had missed
by counting figures stated at 25 °C and not their temperature coefficients.
It cost
7.74 mA of the reference's 12.9 mA and 0.77 mV of load regulation, both now
derived and checked; the old part note had rejected the idea as "a worse
trade" without measuring it.

**A value that could be zero.** Setting `safety.c_clear.capacitance` to 0 F
left all 203 checks passing. The coupling capacitor is the entire reason the
latch clear is a pulse rather than a level — without it, a firmware pin stuck
low holds the board in a trip-clear-trip oscillation — and the clamp diodes'
junctions were quietly holding the node in the arithmetic. The check now
asserts that the capacitor dominates the junctions; with the capacitor zeroed
it fails.

**And one measurement that was not a defect until it was.** The fabricator's
floor in `fab/pcbway.kicad_dru` is 0.100 mm, and DRC against it was clean: 0
violations, 0 unconnected. This board declared a margin over that floor —
`routing.clearance_over_floor` — so its own target was 0.120 mm, and raising
the DRC rule to 0.120 mm produced **13 violations**, from 0.100 to 0.117 mm.

**Every one of the 13 involved a pad**: a track past a decoupling pad, a via
beside an LQFP pad, `TRIP_SET_N` running 0.100 mm from D7's `NRST` pad. That
was the class of clearance no check here measured — `test_routing.py` measured
track-to-track, found 0.141 mm, and passed its 0.120 mm bound honestly,
because pads are not tracks.

Closed since. `rules.kicad_dru` now carries a clearance rule, so DRC enforces
the board's own margin rather than the fabricator's, and it reports 0
violations against it. Four of the thirteen were unreachable rather than
unfixed — 0.5 mm pitch less an 0402 pad's 0.31 and a signal's 0.075 leaves
0.115 — so the declaration is 1.15 over the floor and
`test_the_clearance_this_board_asks_for_is_one_it_can_reach` derives that
0.115 from the board file and rejects any declaration the package forbids.

---

## 6. What would actually move these numbers

In descending order of what it buys:

1. **Crop the two safety-chain parts.** Four of the five terms in the trip
   budget rest on figures nobody has shown. This is an afternoon, and the two
   crops added since this was written show what it is worth: one of them found
   a figure that had been read off the wrong column.
2. **Give the trip chain a simulation.** Not because the arithmetic is
   suspect, but because it is the one chain on the board whose failure mode is
   a destroyed bridge, and it is currently one method deep.
3. **Make `adc_corner.cir.in` sweep both corners**, so the second method can
   contradict the first in both directions.
4. **Resolve the 12 %.** Four candidates, listed in `BLOCKING`.
5. ~~**Add pad clearance to the checks**, so the board's own margin is
   measured rather than the fabricator's.~~ **Done**, along with 2 and 3 —
   see above and `CHANNEL-REVIEW.md` §10.

None of these is large. The reason to write them down is that the board is at
the point where the remaining risk is concentrated rather than spread, and
that is a better place to be than the one the previous review described.
