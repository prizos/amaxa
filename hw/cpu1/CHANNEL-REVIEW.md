# cpu1 — an adversarial pass over every channel

The question: what is wrong with each channel and feature of this board, as
opposed to how much of the board is proven, which is
[`ADVERSARIAL-REVIEW.md`](ADVERSARIAL-REVIEW.md).

Method: for each block, read what the netlist actually is, read every check
that touches it, and look for the four things this repository keeps finding —
a claim no check reads, a check whose scope is whatever happened to be
declared, a number typed rather than derived, and a feature with no check at
all. Datasheets were re-read where a claim rested on one.

**Seven findings, all fixed in `9b3e7f6` except where marked open**, plus an
eighth in `23f4a92` and three more from a second pass over the same ground.
The eleventh is the one that mattered: a check that measured the wrong
quantity on the only 50 MHz bus on the board, and a budget that turned out to
have **nine picoseconds of margin in a thousand**. The board's own mutation
tester was run afterwards and its result is at the end.

---

## The findings

| # | Channel | What was wrong | Status |
|---|---|---|---|
| 1 | **Headers** | Six documents promise a 12–15 V aux pin the connector does not carry | fixed |
| 2 | **Headers** | Eight of eighteen connector signals declared no idle state, and the check's scope was the ten that did | fixed |
| 3 | **CAN** | The design said the transceiver boots "listening"; the datasheet says the receiver is off | fixed |
| 4 | **CAN** | Its mode pin was checked by nothing — the check looks for a pin called `RE` | fixed |
| 5 | **CAN / symbols** | The netlist reports a part driving the 3V3 rail, because a stand-in symbol types a supply input as an output | fixed |
| 6 | **Ethernet** | The RMII — nine single-ended signals at 50 MHz — had no timing or length check | fixed |
| 7 | **Simulation** | A deck's values come from the build; its topology is typed | narrowed |
| 9 | **Trip / thresholds** | The error budget counted two figures stated at 25 °C and never their drift | fixed |
| 10 | **Routing** | The board declared a clearance margin and wrote no rule enforcing it | fixed |
| 11 | **Ethernet** | The RMII check measured the difference between clock and data where the transmit path is limited by their **sum**; the board was over budget | fixed |

---

## 1. The connector promises a pin it does not have

**The worst of the seven, because it is a contract with somebody else.**

`docs/research/07-power-board-interface.md` is the document a power-board
designer reads. It said, under *Supplies*: "3.3 V, 5 V analog, a reference
output, and **12–15 V auxiliary** for the gate-drive DC/DC."

The digital header carries **52 pins across 35 nets, and 3V3 is the only
supply on it.** There is no auxiliary pin, no 5 V analog pin, and nothing that
supplies this board from the power board at all.

The plan called for both the pin and an ideal-diode OR behind it, so that a
power board could feed the digital one instead of its own terminal block.
Neither was built, and nothing recorded the drop. `power_block()` is terminal
→ fuse → P-FET → TVS and stops.

It had spread. Five more files repeated it, and one of them used it as the
**justification for a design decision**: `SOT23_5.md` explains the move to a
regulated 3V3A analog rail and offers, as the mitigation, that "a power board
wanting 5 V sensors makes 5 V from the 12–15 V aux pin it already has on the
digital header".

The substance of that mitigation survives — a board generating gate drive has
a 12–15 V rail whether or not it crosses the joint — but it was being
described as something *this connector provides*, and it is not. All six
corrected, and research 07 now states plainly that nothing supplies this board
but its own terminal.

**Still open, and a decision rather than a fix:** whether a second spin should
fit the aux pin and the ideal-diode OR. A system built on this pair currently
needs two supplies or a wire.

---

## 2. A check whose scope was whoever had filled the field in

`test_every_connector_signal_is_defined_with_nothing_attached` asserted

```python
assert len(expected) >= 10, (
    f"only {len(expected)} pins declare an idle rail; this check is about "
    f"the connector signals and there are ten of them")
```

Ten pins declared an `idle`, so ten was what it checked — permanently. The
assertion cannot notice a signal that never declared one.

The digital connector carries **eighteen** signals that reach an MCU pin. The
eight nobody had filled in:

```
ENC_A  ENC_B  ENC_Z  ENC_SERIAL_RX  ENC_SERIAL_TX  HALL_1  HALL_2  HALL_3
```

Nothing on the board holds any of them. Every other connector signal has a
pull — the fault lines up, the safe-torque-off feedback down, the straps up,
the relays down — and these eight have nothing.

They are **not a hazard**, which is why it went unnoticed: they are feedback
and not permission, and a floating quadrature input enables nothing. The
buffers still need `PWM_ENABLE_N` low and the latch cleared. But "nothing
holds this, and here is why" is a sentence the board should have to write.

`idle="float"` is where it writes it now. The scope comes from the netlist —
every net that touches the connector and reaches an MCU pin — and a `float`
the copper contradicts fails as loudly as a rail that does. `HALL_1` carries
the one thing that is true of it and not of the others: PB4 is NJTRST and has
an internal reset pull-up, which is inside the MCU and not on the board.

---

## 3 & 4. CAN comes up asleep, and nothing checked the pin that decides it

`cpu1.py` said: "The CAN part's standby pin has an integrated pull-up, so it
comes out of reset **listening** rather than talking."

TI's Table 8-4 and §8.4.3: STB high is standby, where *"the CAN driver and
main receiver are switched off and bi-directional CAN communication is not
possible"*. Only a low-power wake receiver runs, and RXD sits recessive until
a valid wake-up pattern arrives — **indistinguishable from an idle bus**.

So the board boots unable to receive CAN, not merely unable to transmit.
Firmware must drive PD3 low first. The hardware is in the safe state either
way; the comment was wrong in the direction that costs a bring-up day, and
the pin map now says so.

**And nothing was checking that pin.**
`test_every_receiver_enable_is_tied_to_the_state_that_listens` looks for a pin
named `RE` or `~{RE}`. The TCAN1044V has none — its mode pin is `Rs` on the
symbol and `STB` on the part. So the check found the RS-485 transceiver,
asserted `found` was non-zero, and skipped the other bus entirely. Half the
field-bus coverage behind an assertion that one thing was found.

A new check covers any transceiver control pin, found by elimination rather
than by name: anything that is not a supply, a ground, a bus line or a data
line.

---

## 5. The netlist reports a part driving the 3V3 rail

`test_power.py` decides which rail holds up a resistor chain by asking which
parts *drive* the net it starts on, and "drives" is a **pin type** rather than
a connection. That distinction exists because the earlier version asked only
whether a part powered from a rail touched the net, and charged the 3V3
feedback divider to both rails at once.

The types come from the symbol. This board's CAN transceiver is a TCAN1044V
drawn with an **SN65HVD230's symbol** — same package, same eight pins in the
same order, which is what makes it usable — and pin 5 differs: a reference
**output** on the drawn part, a supply **input** on the fitted one. The board
wires it to 3V3, correctly, and `cpu1.py` says so.

So the netlist reports a part that drives 3V3, and it is the only part on this
board that reports driving 3V3 at all. **The one mechanism built to stop a
connection being read as a drive is the one a stand-in breaks first.**

It changes no answer today, because 3V3 is a declared rail and the rail check
short-circuits on those before it consults the drivers. That is luck.

`PartSpec.symbol_misnames` makes a stand-in machine-readable rather than a
sentence a reader has to notice, and two checks read it: one that no pin typed
as an output sits on a rail unless the spec says why, and one that a declared
misnaming still describes its symbol, so the exemption cannot outlive the
problem.

**Already disclosed, and confirmed still true:** the same stand-in means the
transceiver's V_IO current — 300 µA maximum — is in no rail's sum, because the
sum attributes a figure by pin name and the symbol calls that pin V_REF.
`parts.py` states the omission and its magnitude against the 3V3 rail's 35 mA
of margin. **The structural fix is a local symbol library**, which this
repository does not have; that is a decision, not an oversight.

---

## 6. The RMII had no timing check of any kind

Twenty-one Ethernet checks. Six of them are about the two differential pairs
to the jack — impedance, coupling, skew, what runs beside them, what plane
returns them, whether a plane runs under the cable end.

The **RMII** is nine single-ended signals at 50 MHz running about 90 mm from
the PHY to the MCU, and it is the only 50 MHz bus on the board. It was checked
for being wired to the right pins and for nothing else.

Table 5.12 of the PHY's datasheet, REF_CLK Out mode — the mode this board uses
— is declared now:

| | |
|---|---|
| `tclkp` clock period | 20 ns |
| `toval` RXD valid after an edge | 7.0 ns max |
| `toinvld` still valid after the next | 3.0 ns min |
| `tsu` TXD setup at the PHY | 7.5 ns min |
| `tihold` TXD hold | 2.0 ns min |

Measured off the routed copper, the worst clock-to-data skew is **ETH_RXD1 at
10.3 mm from ETH_REF_CLK — 63 ps, 0.31 % of a clock period.** Comfortable.

Two assertions, doing different jobs. The **physical** one: skew must be under
the tighter of the two windows the datasheet leaves — 10.5 ns, what a period
has left after the PHY's own setup and hold. The **ratchet**: 0.5 % of a
period, just above what this placement achieves, in the same sense as
`ethernet.coupled_fraction`, so a change that lets one of the nine wander has
to be argued for rather than found on a bench. Detour one line 30 mm and it
reports 733 ps and fails.

**What it does not do**, and says so: close the real budget. That needs the
MCU's own RMII output delay and setup window, and the pages of ST's datasheet
vendored here do not state them. What is bounded is the copper's share, which
is the share the board controls.

---

## 7. A deck's values come from the build; its topology does not

This is about work from the same day, and it is the honest half of it.

Every number in `sim/trip_chain.cir.in` is an `@path:end@` the build resolves.
That is what stops a deck being a second copy of the design. The **netlist**
it substitutes them into is written out by hand.

Twelve Schottky junctions face `TRIP_SET_N` on this board and the deck
instantiates twelve — and nothing made those two numbers the same one. Add a
seventh dual diode and the design check's loading term grows, the deck's does
not, and **both go on passing**, because both are banded against the whole
50 ns budget and neither would notice two nanoseconds of divergence.

Now counted for that one part on that one net — and then generalised.
`test_every_deck_carries_the_parts_that_load_the_nets_it_models` takes the
same argument over every deck: wherever one reaches for a net's measured
copper, which is the only way a deck can name a net, every part the netlist
puts on that net must appear in the deck, either as a named placeholder or as
a model from `sim/models/` whose name is inside the part's own value or MPN.
Connectors and the MCU are exempt by symbol library, because a deck
represents those as its excitation rather than modelling them.

**It found one.** `trip_clear.cir.in` modelled `TRIPPED` as its copper and a
pull-up and left off the two buffer enables and the gate-kill transistor's
gate — the three loads on the latch's single output, which are the whole
subject of the trip budget's `max(buffer_off, turn_on)` term and which
`trip_chain.cir.in` models correctly. Adding them moved `t_clear_to_q` from
12.09 to 12.20 ns inside a band three orders wider, which is why no band
caught it, and is the point: **a deck is not verified by its bands.**

What stays open is the half a machine cannot reach — the node *names* and the
connections between them are still typed, so a deck can put the right parts in
the wrong order. Only a reader catches that.

---

## 10. The margin that was declared and then enforced by nothing

`routing.clearance_over_floor` has been declared since the board was drawn,
and until this pass **nothing ever asked DRC for it**. `rules.kicad_dru` had
track widths, via sizes and a hole floor, and no clearance rule at all — so
DRC fell back to the fabricator's 0.100 mm, the board passed, and the one
check that measured clearance — `test_nothing_sits_on_the_fabricators_floor`
— walked vias and track segments and never looked at a pad.

Three reviews listed the consequence — thirteen places between 0.100 and
0.117 mm, every one involving a pad — and each of them listed it again rather
than fixing it, because the finding as written had no owner: it named a
number without saying whether the number was reachable.

It was not, quite. Four of the thirteen are forced by the package: a
decoupling capacitor sits on its supply pin's line, the next pin along escapes
down its own line half a millimetre away, and 0.5 − 0.31 − 0.075 = **0.115**
is what is left between two parallel lines no matter who places what. So the
declaration was wrong by 0.005 mm, and the nine that *were* movable had been
hidden behind it.

Fixed on both sides: `rules.kicad_dru` carries the board's first clearance
rule, six coordinates in `layout.py` moved, DRC reports **0 violations**
against the board's own margin rather than the fabricator's, and
`test_the_clearance_this_board_asks_for_is_one_it_can_reach` derives that
0.115 from the footprint pitch, the fitted decoupling pad and the narrowest
track width in the rules file — so a declaration the geometry forbids now
fails a check instead of sitting in a review.

---

## 11. The clock goes one way and the data goes the other

The RMII is the only 50 MHz bus on this board and until the last pass it had
no timing check at all. The one added then measured **the difference** between
each line's length and the clock's — 47 ps, 0.24 % of a period — and held it
to a window. That is the right quantity for the receive path and the wrong one
for transmit, and transmit is the path with no margin.

The PHY sources REF_CLK out of its `nINT/REFCLKO` pin. So the clock travels
PHY → MCU and the transmit data travels MCU → PHY, and at the PHY's own
sampling edge the data has taken **the clock's flight time plus the MCU's
output delay plus its own flight time**. Those add. A check on their
difference can read zero while the sum is two nanoseconds and the bus does not
work.

**What made the wrong check possible was a missing half of the budget.** Its
docstring said closing the real one "needs the MCU's own RMII output delay and
setup window, and the pages of ST's datasheet vendored here do not state
them". The second clause was true and the first was a conclusion drawn from
it. ST states all six figures in Table 111, page 193 — the same document, two
pages from a table already cropped for the analog pins. The fix was to vendor
the page, not to narrow the check.

With both halves present the arithmetic is unforgiving:

| | |
|---|---|
| RMII period | 20.0 ns |
| MCU `td(TXD)` maximum | 11.5 ns |
| PHY `tsu` minimum | 7.5 ns |
| **left for the clock's copper and the data's, together** | **1.0 ns** |
| what the board had | 1.004 ns |

**The board was over its transmit budget by four picoseconds, and no check on
it could ever have said so.** Both parts sit at the pessimistic end of the
RMII envelope, and 19 of the 20 ns are gone before any copper is drawn.

Fixed by taking 1.6 mm off the clock's detour south of the analog header and
0.15 mm off each transmit lane — the most the geometry allows, bounded by a
`VREF+` track crossing the strip on the back layer and by the PHY reset line's
own crossing. The margin is now **+9 ps of 1000**, which is not comfort; it is
the finding restated. Real margin needs the PHY nearer the MCU or REF_CLK-In
mode with an oscillator, and both are spin-2.

Two more things came out of it:

- **`toinvld` is back.** It was declared, read into a receive window the board
  was two hundred times inside, and withdrawn when `make mutate` reported that
  no value of it changed an answer. That was right about the check and wrong
  about the part: the receive window was open at the hold end only because the
  MCU's own `tih(RXD)` was not declared either. Both are now, they are 3.0 ns
  each, and the margin between them is exactly how much longer RXD is than the
  clock — 51 ps. Setting `toinvld` to 2.9 fails the check.
- **A firmware constraint nothing could hold.** Table 111 is measured at
  `OSPEEDRy[1:0] = 10` with a 20 pF load. At the reset default ST does not
  specify the delay at all — not a slower number, an absent one — and the
  documented symptom is CRC errors at the PHY. The pin map records it beside
  the Hall inputs' own, and a second check holds the copper to the 20 pF the
  figures were taken into: the worst RMII net carries 7.9 pF, leaving 12.1 for
  the two pins.

---

## Channel by channel

What each one has, and what it still does not.

| Channel | Coverage | What is not checked |
|---|---|---|
| **Safety chain** | 30 checks, a transient deck, the 50 ns budget derived five ways | nothing found this pass |
| **Trip / thresholds** | 19 checks; the error budget at 7.46 % of 12, and the I²C bus that carries the thresholds now has an electrical check | the trip deck still drives the comparator references from ideal sources |
| **ADC / measurement** | 10 checks, two decks, both corners of the band | — |
| **Power** | 31 checks, a sequencing deck, every rail summed off the netlist | no control loop is simulated; inrush and brown-out are prose |
| **Ethernet** | 23 checks; the RMII budget closed at both ends from both datasheets | nothing found this pass, and the transmit margin is 9 ps of 1000 |
| **USB** | 12 checks — one pair, thoroughly | — |
| **CAN / RS-485** | 14 checks after this pass | the V_IO current is out of the rail sum, disclosed with its magnitude |
| **MCU core** | 15 checks — crystals, VCAP, decoupling, reset, thermal | — |
| **Headers** | 8 checks; every connector signal now declares its idle | the aux pin and the ideal-diode OR the plan called for are not fitted |
| **Routing / copper** | 12 checks, DRC clean at the board's own margin | nothing found this pass |
| **Encoder / Hall** | idle state now declared | no electrical check at all — no series resistance, no clamp, nothing between the connector and an MCU pin |

---

## What is still open

1. **The aux pin and the ideal-diode OR**, dropped from the plan without a
   record. Now recorded; whether to fit them is a spin-2 decision. Both
   headers are fully assigned — 52 pins as 34 signals and 18 grounds, 30 as
   17 and 13 — so there is no spare pin, and a supply pin without the OR is
   two sources back-feeding each other. It is one change or neither.
2. **A local symbol library**, which would end the stand-in class of problem
   rather than declaring each instance of it. Less urgent than it was: the
   three stand-ins are declared, the one that costs something has its
   misnaming carried into `design.json`, and the rail sum reads it.
3. **Deck node names.** The parts in a deck are now held to the netlist; the
   nodes and the order they are wired in are still typed.
4. **The RMII's nine picoseconds.** Not a defect and not fixable in copper:
   ST's 11.5 ns and Microchip's 7.5 ns take 19 of the 20 ns period before any
   track is drawn. Real margin needs the PHY nearer the MCU or REF_CLK-In
   mode with an oscillator, and both are spin-2.
5. **The eight floating connector inputs.** Declared now, and still floating.
   A power board that is unfitted leaves eight MCU pins at mid-rail; firmware
   is expected to configure an internal pull before it samples them, and
   nothing enforces that because nothing here can.

---

## The mutation sweep

`tools/mutate.py` changes every number the design declares and runs the checks
that read it, which is a different question from whether anything *looks it
up*: a check can read a figure, put it in a message, and compare something
else.

Run over everything, with the tool's reader map fixed first — see below:

| | |
|---|---|
| intent bands that change no outcome | **0 of 67** |
| part parameters | **68 of 799** |
| — unmoved by every check that reads them | 39 |
| — read only by a simulation deck, which it does not run | 13 |
| — read by no check's call phase at all | 16 |

Every promise this board makes about itself is held to something that fails
when the promise moves. The intent count was 56 when `mutate.py`'s headline
was written and has grown with the board — `trip.prompt_overshoot`,
`ethernet.rmii_skew_share`, the four sequencing figures — without anything
falling dead.

The 39 fall into the categories `mutate.py` itself names as legitimate: one of
six identical dual diodes unmoved by a check that takes the worst of all six,
one of seven identical comparators likewise, a bypass capacitor whose value
nothing states a requirement for. Three were re-tested against the **whole**
suite by hand and were quiet there too.

### And the tool was overstating it

The first run of this sweep reported **164** of 800, and one of them was
`safety.r_gate_kill_drain.resistance` — which, set to zero, makes
`test_the_gate_kill_stays_inside_its_ratings` fail. It is noticed, loudly, and
it was on the list.

The plugin that records who reads what took a set difference against
`PARAMETERS_READ`, which is **one cumulative set for the whole session**. That
difference is non-empty only for the *first* test to read a value; every later
reader registers nothing. So the map held one reader per parameter and the
sweep probed that one. Re-measured with a plugin that empties the set around
each test: **116 of the 164 had other readers that were never asked.**

That is the failure the module exists to catch — a figure read, put in a
message, and compared against something else — occurring in the module. Fixed
in `d2ea237`: every reader is recorded and all of them are probed together,
and parameters read only by a simulation deck are reported as that rather than
as dead weight.

**What it still cannot see:** only the readers the plugin recorded. A check
reaching a figure some way the recorder misses would be missed too. Running
the whole suite per probe would be exact and is the next thing to try.
