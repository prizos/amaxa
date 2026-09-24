# cpu1 — what this board is, and what it does

A design review written after the adversarial round that closed `BLOCKING`,
then corrected twice: once by the round that found four wrong numbers on this
page, and once by the round that found the first correction had itself been
wrong about the trip point. See
[`ADVERSARIAL-REVIEW.md`](ADVERSARIAL-REVIEW.md) for how much of what follows
is proven and how much is prose.
Everything here is measured off the generated board and `build/design.json`
rather than recalled; where a number is an assumption rather than a
measurement it says so.

For the block-by-block part list see [`review/README.md`](review/README.md),
which is generated. For the build gates see [`README.md`](README.md). This
document is the thing neither of those is: an account of what the board *is*.

---

## 1. The one-paragraph version

cpu1 is the digital half of a two-board motor controller. It carries an
STM32H743ZIT6 and generates every hard real-time signal — PWM for two
three-phase bridges, ADC sampling synchronised to it, and a hardware trip that
stops the outputs without firmware — then hands all of it across two pin
headers to a purely analog power board that does not exist yet. It is
130 × 110 mm, six copper layers, 272 parts, 197 nets. The whole board exists
to make one guarantee cheap to believe: **nothing reaches a gate driver unless
firmware has deliberately allowed it, and three independent things can take
that permission away in tens of nanoseconds.** (Three, not six — §3 says which
three, and why the other count was the wrong way to read the diagram.)

---

## 2. What is actually on it

| | |
|---|---|
| MCU | STM32H743ZIT6, LQFP-144, 400 MHz |
| Board | 130 × 110 mm, 6 layers, 272 footprints, 602 vias, 1327 track segments |
| Stackup | F / **In1 GND** / In2 3V3 / **In3 signal** / In4 GND / B, 0.1855 mm outer prepreg |
| Input | 9–36 V, fused, reverse-polarity FET, TVS |
| Rails | 5 V (LM5164, 100 V-class), 3V3 (TPS562200), 3V3A (TLV70233 LDO), VREF+ 3.0 V |
| To the power board | digital 2×26 (52 pins), analog 2×15 (30 pins) |
| Comms | USB-C device, CAN FD, RS-485, 100BASE-TX Ethernet |
| Checks | 207 and 22 simulated measurements, all passing; DRC 0 violations, 0 unconnected |

The part count is dominated by the safety chain (59) and the MCU core (39) —
which is the right shape for what this board is for.

### The layer choice is the interesting one

Two ground planes, In1 and In4, sandwiching a 3V3 plane and a nearly-empty
inner signal layer. That means **a signal crossing from front to back keeps
its reference**: 267 of the 279 layer changes on this board hand their return
to a ground via beside them, and only 12 reach for a plane-tying capacitor.
The 5 V island lives on B.Cu, not on an inner layer, so it references solid
ground and splits nothing.

---

## 3. The safety chain, which is the point of the board

Six mechanisms stop the outputs. They are **not** six independent ones, and
the difference is the honest way to read the diagram: five of the six meet at
the latch. A latch that failed would take the comparators, the DAC's
thresholds, the buffers' second enable and the gate kill with it.

What is genuinely independent is three things: that latch chain;
`PWM_ENABLE_N`, which the MCU drives straight into the buffers' first enable
and which touches no part of the latch; and the pull-down on every buffered
output at the connector, which is passive and needs nothing on this board to
be alive.

```
 comparator ──┐
 gate fault ──┤                    ┌── OE2 ─→ both '541 buffers ─→ high-Z
 NRST      ──┴─→ TRIP_SET_N ─→ latch ─┤
 power good                        └── Q ──→ Q2 gate ─→ GATE_ENABLE_OUT low
                                           (3.4 ns)
 PWM_ENABLE_N ────────────────────────→ OE1 ─→ both buffers
```

1. **Seven external comparators** — TLV3501, 7 ns — watch three phase
   currents at two thresholds each plus the DC link. They run from 5 V so
   their common-mode range covers the whole signal swing.
2. **Their thresholds come from an MCP4728 DAC that powers up at zero**, and
   that runs from **VREF+ rather than the logic rail**. An unprogrammed board
   therefore reads every phase current as over its high-side threshold and
   **trips as it powers up**, rather than switching — and a programmed one
   compares a sensor scaled to the 3.0 V reference against a threshold that
   is a fraction of the same 3.0 V reference. See §4.
3. **A hardware latch** (74LVC1G74 used as a set-reset, clock and data tied
   low) holds the trip. Only PG5 clears it, and only as an AC-coupled
   *pulse* — a pin stuck low cannot hold the clear asserted, because the
   coupling capacitor lets go. `sim/trip_clear.cir.in` runs that: with PG5
   driven low and **left there**, the clear is a valid low for **9.22 µs**
   against a closed form of 9.33, the latch comes out of its trip 12 ns in,
   and 280 µs later the node is back at the rail with the pin still low. The
   deck is there for the clamp, which is the only nonlinear thing in the
   circuit — take D13 out and the release overshoot is **6.59 V** against an
   absolute maximum of 6.5 on an input that has no clamp of its own.
4. **Two octal buffers** with both enables used: one from the MCU, one from
   the latch. Either one high is high-impedance. Reset floats the pins, which
   turns the buffers off *and* presets the latch.
5. **A gate-kill FET** pulls `GATE_ENABLE_OUT` low in 3.4 ns, independently of
   the buffers letting go.
6. **Every buffered output has a pull-down** at the connector, so an unfitted
   power board is not a command.

### The trip budget, measured

`trip.budget` is 50 ns — how long a half bridge survives a shoot-through. The
chain, printed on every test run:

| term | ns |
|---|---|
| latch preset, and the slower buffer disabling | 14.7 |
| comparator, at its datasheet's own load | 7.0 |
| 137 pF of trip bus — 12 Schottky junctions and the copper | 5.0 |
| the ADC filter's lead-lag on the comparator tap | 10.6 |
| pulling the gate line below 0.8 V once Q2 is on | 3.4 |
| **total** | **40.5 of 50** |

### And the same thing simulated

`sim/trip_chain.cir.in` builds that chain - the tap, the comparator, twelve
Schottky junctions, the latch, the buffer and the gate-kill transistor - and
runs a fault current ramping into it. One excitation, one number:

| | the sum above | the deck |
|---|---|---|
| comparator output falls | 17.6 ns | **13.2** |
| trip bus at a valid low | 22.6 | **21.7** |
| `TRIPPED` high | 28.5 | **27.6** |
| **gate line below 0.8 V** | **40.5** | **33.5** |

Both are inside the 50 ns budget and **the arithmetic is 21 % conservative**,
which is the direction to be wrong in. Two things account for most of it:

- **the tap.** The check sums both of FAST4_SENSE's shunt capacitors as
  though both sat on the sense node, when one is behind 22 Ω and the other
  behind 1 kΩ. In the deck they are where the board puts them.
- **the bus.** The check extrapolates the comparator's Figure 5 to 137 pF,
  past the 100 pF the straight line was fitted from, and counts each Schottky
  junction at the datasheet's 10 pF — which is its value at 1 V of reverse
  bias, where the bus sits nearer 1.6 and the junctions are 8.5 pF.

Neither is a defect. Both are the kind of conservatism that is worth knowing
the size of, because 9.5 ns of spare and 16.5 ns of spare are different
boards.

**And the models are checked before they are believed.** Two of them are
calibrated rather than derived, so the deck rebuilds the datasheet's own test
circuit beside the board and measures it: the comparator's 13 pF reference
load returns **7.030 ns** against a declared 7.000, and the latch's 50 pF with
500 Ω returns **5.900** against 5.900. Halve the latch's declared drive and
that second measurement moves to 7.22 ns and fails, which is what stops a
fitted constant going quietly wrong. `sim/models/SOURCE.md` says what each
model does and does not represent.

The two terms worth knowing about: the **tap** was for a long time a
*reservation* — 40 % of the budget held back for "a filter this board has not
drawn" — when the filter had been fitted all along as the ADC's own capacitor
on the node the comparator watches. And the **gate kill** exists because no
resistor could do the job: the budget wanted a pull-down under 600 Ω and the
3V3 rail wanted over 1.4 kΩ, and that window is empty.

### What the interface promises

This is the part a power board has to read. `GATE_ENABLE` is the signal the
trip's timing rests on — **the power board must disable every gate driver
from that one pin.** The fourteen PWM lines are a second layer that arrives
**32–39 ns later with nothing attached, and up to 188 ns later** into the
10 pF a gate driver's input pin may present, through their 10 kΩ pull-downs.
Both ends are derived by
`test_the_pwm_lines_really_are_the_second_layer_the_interface_promises`; the
"about 200 ns" that stood in three files was the loaded end, quoted as though
it were the figure and computed nowhere. That is the Infineon MADK convention,
and until recently this board had never said so.

---

## 4. The measurement path

Eight fast channels, four slow, two board-ID straps and one extra network
that feeds the MCU's own comparator — each an RC between the connector and a
pin, with an external comparator watching the unfiltered side of the fast
ones.

The fast network — **22 Ω and 4.7 nF** — is where three constraints meet, and
none of them can be relaxed without breaking another:

| | |
|---|---|
| corner | 1.27–1.73 MHz, inside the declared 1–2 MHz |
| settling | 0.37 LSB left in a 236 ns window, of the half-LSB allowed |
| tap error | 8.58 % off a step, which is 9.38 % of overshoot, not a threshold error |
| tap delay | 10.6 ns of the 20 the trip budget allows |

**The tap error is not a threshold error, and for one round this document
said it was.** Two checks looked as though they were spending one 12 %
declaration — the accuracy sum at 11.46 % and this tap term at 8.58 % — so the
two were added, giving 20.0 %, and the result was filed as a blocker. That was
wrong. The 8.58 % is a fraction of the *step*; the other five are fractions of
the *threshold*; and a ramp gets the delay while a step gets the deficit, so
no one signal gets both.

More to the point, the deficit does not make a trip late. A lead-lag's output
jumps immediately to R/(Rs + R) of its input, so a fault already 9.38 % over
its threshold fires on the instant, with nothing added. What the deficit sets
is **how far over a fault has to be** to get that, and `trip.prompt_overshoot`
— a quarter — is what this board now promises about it. The tap's real cost is
10.55 ns of the 20 ns reserved for it, in §3's table with the rest.

The settling argument is worth stating because it is not the textbook one:
**ST's Equation 1 rejects every value that works here.** That equation asks
how long a source takes to charge the whole input capacitance from nothing,
which is right when there is no capacitor at the pin. Here there is one, it
stays charged between conversions, and the only charge that moves is what the
4 pF sampling capacitor takes at each sample. The check does the charge
sharing instead, and says so.

Measurements are ratiometric to a 3.0 V series reference that leaves the board
on its own connector pin, so what the power board measures and what this board
converts are scaled by the same number — **and so is every trip threshold**,
since the MCP4728's full scale is its supply pin and its supply pin is that
reference.

### What the trip point is worth

| term | share |
|---|---|
| the DAC's offset, 20 mV at a 0.750 V threshold | 2.67 % |
| the comparator's offset and hysteresis | 1.87 % |
| the DAC's nonlinearity, 13 LSB | 1.27 % |
| the DAC's gain error | 1.25 % |
| **VREF+ itself**, the REF3030's ±0.2 % at 25 °C | 0.20 % |
| the reference drifting over 25 °C of ambient | 0.19 % |
| the comparator drifting over the same 25 °C | 0.02 % |
| the reference's line regulation, from 3V3 | 0.004 % |
| **total** | **7.46 % of 12 declared** |

The last three rows are newer than the rest and this table read **7.06 %**
without them. Two figures above are stated at one temperature — the
comparator's offset under a header saying "At T_A = 25 °C", the
reference's accuracy under one saying the same — and the budget counted
the figures and not the drift. The DAC's three terms do **not** have that
gap: Microchip's header states −40 to +125 °C outright, so its maxima
already cover it.

The comparator's row moved for a second reason. Its hysteresis has a
figure under TYP and **nothing under MIN or MAX**, and it was declared
`exact` and used as a bound. It carries `loads.unguaranteed_margin` now —
the quarter this board adds to any figure a datasheet did not guarantee,
which is what the PHY's supply current already does.

The 5.00 % row that is missing is the interesting one. The DAC ran from 3V3 until
recently, and then the top row of this table was the **logic rail at 5.00 %** —
the largest single term, and a number the board was spending on nothing,
because the thresholds it scaled were being compared against sensors scaled to
a different reference entirely.

Moving the supply to VREF+ replaced it with the reference's own accuracy and
its line regulation, which together are 0.204 %, and took the budget from
11.46 % to 7.46 %. It cost 7.74 mA of the 12.9 mA the reference's headroom
allows, worth 0.77 mV of load regulation, and it cost the I²C pull-ups moving
to VREF+ as well — Microchip's absolute maximum for every pin on that part is
VDD + 0.3 V, and a bus idling on the logic rail would have been 171 mV outside
it. There is no quad 12-bit I²C DAC with a real reference pin in stock
anywhere; `parts/MSOP10/MSOP10.md` lists the five that were priced.

---

## 5. Power

```
9–36 V ─ fuse ─ P-FET ─ TVS ─┬─ LM5164 ─ 5 V ─┬─ TPS562200 ─ 3V3 ─ bead ─ VDDA
                             │                ├─ TLV70233 ─ 3V3A ─→ analog header
                             │                └─ comparators, CAN
                             └─ (100 V-class: the SMBJ40A clamps at 64.5 V)
```

The 100 V buck is not overkill. The TVS fitted is an **SMBJ40A**: 40 V
stand-off, 51.1 V breakdown, and **64.5 V of clamping voltage at its peak
pulse current**, all three read off its datasheet and held by a check. A 60 V
buck would be *under* that clamp, not merely close to it — which is the
regulator defect this project already made once on `led12`.

An earlier draft of this page said "a 36 V stand-off TVS clamps near 58 V".
That was the part the plan proposed, not the part on the board.

### The rails, derived from the netlist

Neither figure is typed any more; both are summed off the board on every run.

| | derived | band |
|---|---|---|
| 3V3 | 814.4 mA, 54 loads | 850 mA |
| 5 V | 173.8 mA, 11 loads | 200 mA |

The 3V3 band is 850 rather than 900 because the binding part is the **LM5164
upstream**, which carries this rail reflected through the 3V3 buck's
efficiency *plus* the 5 V rail's own budget: at 850 that is 930 mA of its
1.0 A, and at 900 it would be 973.

Two of that sum's largest terms are not guaranteed, and the sum says so
rather than hiding it. The PHY's 102 mA is a **typical** — the LAN8742A
datasheet has no maximum supply current anywhere — and the comparators' 5 mA
is a 25 °C figure. `loads.unguaranteed_margin` adds a quarter to any figure
whose name says the datasheet did not guarantee it, which is what takes 785 mA
of measured load to 814.

---

## 6. The interface to the power board

Everything this board asks of the far side, in one place:

| promise | value | why |
|---|---|---|
| `analog.input_voltage_max` | 3.366 V | the analog rail's own top corner — a sensor running from this board cannot exceed it |
| `header.source_impedance` | 2 Ω | what makes the comparator tap a lead-lag; at zero the whole error disappears |
| `header.gate_line_capacitance` | 10 pF | the far side of every gate line |
| `header.gate_line_low` | 0.8 V | what a gate driver calls a low |
| `header.supply_current` | 100 mA at 3V3 | what the connector may draw |
| `analog.supply_current` | 50 mA at 3V3A | what the sensors may draw |
| `vref.supply_current` | 5 mA | everything the reference supplies, on-board and off |
| idle states | per signal, in `pinmap.py` | an unfitted board must not read as permission |

**The analog supply is 3.3 V and that is a real constraint on every future
power board.** It used to be 5 V through a ferrite, and the sense lines come
back into TT_xx pins ST caps at 4.0 V absolute with no positive-injection
allowance — so an op-amp railing to its own supply during the over-current the
trip chain exists for was a 5.25 V fault this board could not clamp. Clamps do
not fit; three positions were tried. Regulating instead makes the fault
impossible rather than survivable. A power board that wants ACS724- or
LEM-class 5 V sensors makes its own 5 V on its own side, from the gate-drive
supply it already has —  **not from this connector, which has no aux pin** —
and scales the output to this rail.

---

## 7. What the checks are, and what they are for

215 of them. The distribution is the interesting part:

| file | checks | |
|---|---|---|
| `test_power.py` | 31 | rails, converters, ratings, the resistor fault model |
| `test_safety.py` | 29 | the trip chain end to end |
| `test_ethernet.py` | 23 | the one block with an external standard to satisfy |
| `test_core.py` | 19 | the MCU against its own datasheet |
| `test_trip.py` | 18 | thresholds, the DAC, what a trip is worth |
| `test_buses.py` | 14 | CAN and RS-485 |
| `test_usb.py` | 12 | one differential pair, thoroughly |
| `test_routing.py` | 12 | what the copper does that the netlist cannot say |
| `test_adc.py` | 10 | the measurement path |
| others | 47 | pin map, parts, geometry, build gates |

They are not regression tests. The rule they are written under is that a check
**derives** what it expects — from the netlist, the routed board, the stackup,
or a datasheet figure recorded with a committed evidence crop — and never
from a table of beliefs. The reason is on the record: a hand-written polarity
table once enforced a backwards reverse-polarity FET on this project.

The gates that keep them honest:

- **`EXPECTED_CHECKS`** — a ratchet, so a check cannot quietly stop running.
- **every declared parameter must be read** by something, or be listed with
  the reason it cannot be.
- **`tools/mutate.py`** — perturbs every declared number to zero and to
  something absurd, and reports which change no outcome.
- **every change lands with a break-test**: the thing is deliberately broken
  and the new check is watched to catch it.

### The measurement that says the checks bite

Setting every resistor's power rating to zero, one at a time, and re-running
the suite:

| | survivors |
|---|---|
| before this round | 36 of 101 |
| after fixing the pull-up model | 20 of 101 |
| after the fault model | **0 of 101** |

---

## 8. What I would not yet bet on

`BLOCKING` is empty. It held one entry for part of this round — the trip point
at 20.0 % against a 12 % declaration — and that entry was a mistake of mine
rather than a defect of the board's: two checks were not spending one budget,
they were measuring two different things. §4 has it. The reference-supplied
DAC that came out of examining it is a real improvement and went in anyway.

Everything below is uncertain in the weaker sense: nothing is known to be
wrong, and nothing has been measured.

**What the rails do on the way up**, which was four sentences of prose until
`sim/power_up.cir.in` ran them. Every figure behind it is declared now, and
one of the sentences was wrong: the 3V3 converter's UVLO is 3.45–4.05 V and
`cpu1.py` said "about 4.1".

| | |
|---|---|
| 5 V to 3V3 | **576 µs** |
| VREF+ above VDDA, worst instant | **0 V** — ST's Table 86 allows none |
| the DAC below its 2.7 V minimum, with 3V3 already up | **53 µs** |
| 3V3A's ceiling at any instant | **3.303 V** against a 4.0 V pin limit |

The third of those is a number nobody had: a window in which the latch and
both buffers are alive at 1.65 V and every trip threshold is undefined. It is
harmless — firmware has not run, so nothing is enabling a buffer — and it is
now bounded rather than unmentioned.

Put the reference back on the 5 V rail, which is the defect `c297e58` fixed,
and the deck reports VREF+ **2.99 V above VDDA** and fails. That is the
historical defect reproduced, and it is why `docs/research/09` no longer lists
power-up sequencing among the things no pipeline can catch. Inrush still is.

**Assumptions carried deliberately, each declared in one place and each
wanting a measurement on the first assembled board:**

- `capacitors.bias_derating` — what DC bias takes off a Class II ceramic. No
  maker publishes a per-part curve in a document `make offline` can reach;
  Samsung's, Murata's and TDK's were all fetched and read. The model is
  proportional to the field, which is the right shape and is what made the fix
  a voltage rating rather than a bigger pile of parts.
- `loads.unguaranteed_margin` — a quarter on any load figure the datasheet
  did not guarantee. Two of the 3V3 rail's largest terms are in that category.
- `header.source_impedance`, `header.gate_line_capacitance` — the far side of
  a connector, on a board that does not exist.
- The crystals' stray capacitance, which the LSE's own copper has nearly used
  up.

**Things that are tight rather than uncertain:** the tightest track-to-track
gap is 0.141 mm against a 0.120 mm bound; six via pairs sit exactly on the
escape-grid floor; the nearest via to a mounting hole is 3.54 mm against a
3.5 mm keep-out. These are facts about a densely packed board, and they are
measured on every run.

**Two checks that cannot fail, both disclosed in their own docstrings:** the
Ethernet centre-tap proximity check (53 capacitors tie 3V3 to ground, and the
bound is the jack's own 20.7 mm span), and the pair's plane-reference check
(every routable layer on this stackup is backed by ground). Both are kept
because they are the assertions that *would* fail on a different stackup.

**Pad clearance, which this said was covered by nothing, now is.** The board
declared `routing.clearance_over_floor` and then never wrote a clearance rule,
so DRC only ever compared against the fabricator's 0.100 mm floor, and the one
check that measured clearance looked at vias and tracks and never at pads. The
gap between the two figures was thirteen places, 0.100 to 0.117 mm, every one
of them involving a pad.

`rules.kicad_dru` now carries the board's first clearance rule and DRC enforces
the declared margin. Nine of the thirteen moved; the other four did not,
because they cannot: a decoupling capacitor sits on its supply pin's line and
the next pin along escapes down its own line 0.5 mm away, so an 0402 pad's
0.31 mm and a signal's 0.075 mm leave **0.115 mm** between two parallel lines
whatever anybody places where. The declared margin is 1.15 × the floor rather
than 1.2 for that reason — the same argument this board already makes about
the hole floor, where asking for more would be asking the LQFP-144 to have
coarser pins.

`test_the_clearance_this_board_asks_for_is_one_it_can_reach` now derives that
0.115 from the footprint pitch in the board file, the fitted decoupling pad,
and the narrowest track width in the rules file, and rejects any declaration
the geometry forbids. Set the declaration back to 1.2 and it fails with the
arithmetic printed.

---

## 9. The honest summary

The board is finished in the sense that matters — drawn, routed, checked,
reproducible, and buildable with the network unplugged. The five `BLOCKING`
entries it started the previous round with are gone, and the last one went by
building the fault model it said was missing, which immediately found a real
defect: a gate-kill drain resistor at 174 % of its derated rating, in a part I
had added myself six commits earlier.

The sentence that used to end this paragraph — "every claim it makes about
itself is now cashed by something that reads the board" — was not true, and
the round after it proved that by finding a "200 ns" in three files that
nothing computed, a pull-up in the pin map that is on a different net, a DAC
"reset" that is a power-up, a watchdog path with no net, and four wrong
figures on this page. Those are fixed and three of them now have checks.
[`ADVERSARIAL-REVIEW.md`](ADVERSARIAL-REVIEW.md) counts what is still prose.

What it has not had is a power board to talk to, or a reflow oven. Every
number in section 8 is waiting on those two things.
