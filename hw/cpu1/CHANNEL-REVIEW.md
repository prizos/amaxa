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
eighth in `23f4a92`. The board's own mutation tester was run afterwards and
its result is at the end.

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

Now counted, for that one part on that one net. **The general problem stays
open**: a hand-written deck drifts from the board it claims to model, and
nothing but a reader's attention connects `trip_clear.cir.in`'s three RCs or
`power_up.cir.in`'s rail tree to the netlist they are drawn from.

---

## Channel by channel

What each one has, and what it still does not.

| Channel | Coverage | What is not checked |
|---|---|---|
| **Safety chain** | 30 checks, a transient deck, the 50 ns budget derived five ways | nothing found this pass |
| **Trip / thresholds** | 18 checks; the error budget derived and printed at 7.06 % of 12 | the DAC's settling time is not declared and the deck treats it as ideal |
| **ADC / measurement** | 10 checks, two decks, both corners of the band | — |
| **Power** | 31 checks, a sequencing deck, every rail summed off the netlist | no control loop is simulated; inrush and brown-out are prose |
| **Ethernet** | 22 checks including the new RMII one | the MCU's own RMII timing is not vendored, so the budget is half-closed |
| **USB** | 12 checks — one pair, thoroughly | — |
| **CAN / RS-485** | 14 checks after this pass | the V_IO current is out of the rail sum, disclosed with its magnitude |
| **MCU core** | 15 checks — crystals, VCAP, decoupling, reset, thermal | — |
| **Headers** | 8 checks; every connector signal now declares its idle | the aux pin and the ideal-diode OR the plan called for are not fitted |
| **Routing / copper** | 11 checks, DRC clean at the fab floor | **pad-to-track and pad-to-pad clearance**, still |
| **Encoder / Hall** | idle state now declared | no electrical check at all — no series resistance, no clamp, nothing between the connector and an MCU pin |

---

## What is still open

1. **Pad clearance.** DRC is clean against PCBWay's 0.100 mm floor. At this
   board's own declared 0.120 mm there are **13 violations, 0.100 to
   0.117 mm, every one involving a pad** — the class no check here measures.
   Named in `DESIGN-REVIEW.md` §8 and unmoved.
2. **The aux pin and the ideal-diode OR**, dropped from the plan without a
   record. Now recorded; whether to fit them is a spin-2 decision.
3. **A local symbol library**, which would end the stand-in class of problem
   rather than declaring each instance of it.
4. **Deck topology**, above.
5. **Scope-by-what-exists** as a pattern. Two instances were fixed this pass;
   the shape recurs — `assert out` accepts one field bus where the board has
   two, and a fixture keyed on `address.endswith(".transceiver")` cannot see a
   bus whose part is named otherwise.
6. **The eight floating connector inputs.** Declared now, and still floating.
   A power board that is unfitted leaves eight MCU pins at mid-rail; firmware
   is expected to configure an internal pull before it samples them, and
   nothing enforces that because nothing here can.

---

## The mutation sweep

`tools/mutate.py` changes every number the design declares and runs the checks
that read it, which is a different question from whether anything *looks it
up*: a check can read a figure, put it in a message, and compare something
else.

Over the board's declared promises — the intent bands, which are the numbers
this board asserts about itself rather than the ones it read off a datasheet:

> **0 of 67 intent bands change no outcome.**

Every promise this board makes is held to something that fails when the
promise moves. The count was 56 when `mutate.py`'s own headline was written
and has grown with the board — `trip.prompt_overshoot`,
`ethernet.rmii_skew_share`, the four sequencing figures — without anything
falling dead.

**The other half was not re-run.** A full sweep is a pytest run per value,
867 of them, and takes the better part of a day; the last recorded figure is
150 of 677 part parameters unmoved, every one of which fell into one of the
categories `mutate.py` lists — a resistor that dissipates nothing being
unmoved by its power rating, one of seven identical comparators being unmoved
by a check that takes the worst of them. That is worth a night before a spin
rather than an afternoon during a review, and it is the one thing this pass
did not finish.