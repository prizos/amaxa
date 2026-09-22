# cpu1 — what this board is, and what it does

A design review written after the adversarial round that closed `BLOCKING`.
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
firmware has deliberately allowed it, and several independent things can take
that permission away in tens of nanoseconds.**

---

## 2. What is actually on it

| | |
|---|---|
| MCU | STM32H743ZIT6, LQFP-144, 400 MHz |
| Board | 130 × 110 mm, 6 layers, 272 footprints, 603 vias, 1327 track segments |
| Stackup | F / **In1 GND** / In2 3V3 / **In3 signal** / In4 GND / B, 0.1855 mm outer prepreg |
| Input | 9–36 V, fused, reverse-polarity FET, TVS |
| Rails | 5 V (LM5164, 100 V-class), 3V3 (TPS562200), 3V3A (TLV70233 LDO), VREF+ 3.0 V |
| To the power board | digital 2×26 (52 pins), analog 2×15 (30 pins) |
| Comms | USB-C device, CAN FD, RS-485, 100BASE-TX Ethernet |
| Checks | 203, all passing; DRC 0 violations, 0 unconnected |

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

Six independent things stop the outputs, and they compose rather than
alternate.

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
2. **Their thresholds come from an MCP4728 DAC that powers up at zero.** An
   unprogrammed board therefore reads every phase current as over its
   high-side threshold and **trips as it powers up**, rather than switching.
3. **A hardware latch** (74LVC1G74 used as a set-reset, clock and data tied
   low) holds the trip. Only PG5 clears it, and only as an AC-coupled
   *pulse* — a pin stuck low cannot hold the clear asserted, because the
   coupling capacitor lets go in 7.6 µs.
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
about 200 ns later, through their 10 kΩ pull-downs. That is the Infineon MADK
convention, and until recently this board had never said so.

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
| tap error | 8.3 % amplitude against 12 % of threshold tolerance |
| tap delay | 10.6 ns of the 20 the trip budget allows |

The settling argument is worth stating because it is not the textbook one:
**ST's Equation 1 rejects every value that works here.** That equation asks
how long a source takes to charge the whole input capacitance from nothing,
which is right when there is no capacitor at the pin. Here there is one, it
stays charged between conversions, and the only charge that moves is what the
4 pF sampling capacitor takes at each sample. The check does the charge
sharing instead, and says so.

Measurements are ratiometric to a 3.0 V series reference that leaves the board
on its own connector pin, so what the power board measures and what this board
converts are scaled by the same number.

---

## 5. Power

```
9–36 V ─ fuse ─ P-FET ─ TVS ─┬─ LM5164 ─ 5 V ─┬─ TPS562200 ─ 3V3 ─ bead ─ VDDA
                             │                ├─ TLV70233 ─ 3V3A ─→ analog header
                             │                └─ comparators, CAN
                             └─ (100 V-class, because a 36 V TVS clamps near 58)
```

The 100 V buck is not overkill. A 36 V stand-off TVS clamps near 58 V, and a
60 V part would have about 3 % of margin against that — which is the
regulator defect this project already made once on `led12`.

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
LEM-class 5 V sensors makes its own 5 V from the 12–15 V aux it already has,
and scales the output to this rail.

---

## 7. What the checks are, and what they are for

203 of them. The distribution is the interesting part:

| file | checks | |
|---|---|---|
| `test_power.py` | 30 | rails, converters, ratings, the resistor fault model |
| `test_safety.py` | 26 | the trip chain end to end |
| `test_ethernet.py` | 21 | the one block with an external standard to satisfy |
| `test_trip.py` | 17 | thresholds, the DAC, what a trip is worth |
| `test_core.py` | 15 | the MCU against its own datasheet |
| `test_buses.py` | 13 | CAN and RS-485 |
| `test_usb.py` | 12 | one differential pair, thoroughly |
| `test_routing.py` | 11 | what the copper does that the netlist cannot say |
| `test_adc.py` | 10 | the measurement path |
| others | 48 | pin map, parts, geometry, build gates |

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

`BLOCKING` is empty, which means nothing known is unfinished. That is not the
same as nothing being uncertain.

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

**Not covered by anything:** pad-to-track and pad-to-pad clearance are
measured by no check here — only by DRC, against the fabricator's floor rather
than against this board's own margin.

---

## 9. The honest summary

The board is finished in the sense that matters — drawn, routed, checked,
reproducible, and buildable with the network unplugged — and every claim it
makes about itself is now cashed by something that reads the board rather than
a comment. The five `BLOCKING` entries it started this round with are gone,
and the last one went by building the fault model it said was missing, which
immediately found a real defect: a gate-kill drain resistor at 174 % of its
derated rating, in a part I had added myself six commits earlier.

What it has not had is a power board to talk to, or a reflow oven. Every
number in section 8 is waiting on those two things.
