# Device models

Where each model came from, and how far it can be trusted. A simulation is only
worth the models under it, and a fitted model that nobody wrote down becomes a
measurement nobody can question.

Every figure below is already declared in `parts.py`, so a model follows the
part when the part changes. Nothing here introduces a number the design does
not state — with one exception, `lvc1g74.lib`'s `tfit`, and that one carries a
measurement in the deck to catch it drifting.

**The rule these were built under.** Where the design checks *approximate* a
mechanism, the model carries the mechanism and lets the simulator work out what
it costs. Where no mechanism is available and the datasheet simply states a
figure, the model states the figure. Nothing is modelled as a delay that a
check computes as a delay — otherwise the deck restates the check and agrees
with it by construction.

---

## `bat54a.lib` — LRC LBAT54ALT1G

**Fitted, not vendor.** LRC publishes no SPICE model.

`IS` and `N` are solved from the two lowest of the three forward-voltage
maxima in `parts.py`:

    N  = (0.32 - 0.24) / (Vt * ln 10)  = 1.34327
    IS = 1e-4 / exp(0.24 / (N * Vt))   = 1.000e-7 A

**`RS` is zero because the fit leaves nothing for it**, and that is a fact
about the datasheet rather than about the part. Probed:

| I_F | datasheet max | model | residual |
|---|---|---|---|
| 100 µA | 0.240 V | 0.240037 V | +0.04 mV |
| 1 mA | 0.320 V | 0.320004 V | +0.00 mV |
| 10 mA | 0.400 V | 0.400000 V | +0.00 mV |

The three maxima lie on one ideal-diode line to under a microvolt. They came
out of one equation, so **the third point is not an independent check on the
first two** and this model is not validated by reproducing it. It is
interpolation dressed as agreement, and it is recorded here so nobody mistakes
it for a fit that survived a test.

`CJO` is set so the model gives the declared `total_capacitance` of 10 pF at
the 1 V reverse bias the datasheet states it at. `VJ = 0.6` and `M = 0.5` are
conventional Schottky values, **not fitted**. Probed:

| V_R | model |
|---|---|
| 0 V | 16.34 pF |
| **1 V** | **10.000 pF** ← the declared point |
| 1.6 V | 8.53 pF ← where the trip bus sits |
| 3 V | 6.67 pF |

That 1.6 V row is the one that matters: the design checks use 10 pF flat, so
twelve junctions are 120 pF to a check and 102 pF here. **The check is about
15 % conservative on the trip bus**, and it is conservative in the safe
direction.

**What it does not represent:** temperature. `forward_voltage_tempco` is
declared and read by the checks; `EG` and `XTI` here are conventional Schottky
values and the decks run at one temperature, so nothing downstream depends on
them. Reverse leakage is the diode equation's own, not the datasheet's
FIG.2 curve, which the checks read separately.

---

## `tlv3501.lib` — TI TLV3501AIDBVR

**Behavioural, not vendor.** Four declared figures: `input_offset_voltage` +
half `input_hysteresis` as a static shift, `propagation_delay_max` 7 ns,
`delay_load_reference` 13 pF, `output_swing_from_rail` 50 mV at 1 mA giving
50 Ω, and `output_short_circuit_current` 74 mA.

**The load-dependent delay is deliberately absent.** `parts.py` reduces the
datasheet's Figure 5 to a straight line — 40.23 ps per picofarad past a 13 pF
reference — and the trip budget extrapolates that to 137 pF, past the 100 pF
the fit was taken from. Putting the slope in the model would make the deck
restate the check. What is here is the mechanism the slope is a fit *of*: a
resistance and a current ceiling.

**The 7 ns is measured into the datasheet's own 13 pF**, so the intrinsic
delay is that figure less what this output stage takes to drive 13 pF to half
a swing — `rout * cref * ln 2`. The current ceiling makes the first volt of
the edge a ramp rather than an exponential, so the correction is approximate
and the residual is measured: **7.029 ns at 13 pF against a datasheet 7.000**,
0.4 % high.

**And then it was checked against a figure it was not built from.** Probed
against load:

| C_L | model | model increment from 13 pF |
|---|---|---|
| 13 pF | 7.03 ns | — |
| 100 pF | 10.26 ns | **3.23 ns** |
| 137 pF | 11.64 ns | **4.61 ns** |

Figure 5's own increment over the same 13→100 pF span is 8.2 − 4.7 = **3.5 ns**.
The model reproduces it to **7.7 %** from two figures — 50 mV at 1 mA and a
74 mA short circuit — that have nothing to do with Figure 5. That is the one
genuine independent validation in this file.

At 137 pF the check's linear fit gives 4.99 ns against this model's 4.61, so
**the extrapolation past the fit's endpoint is 8.2 % pessimistic** — again the
safe direction, and now a number rather than a worry.

**What it does not represent:** hysteresis as state. The offset and half the
hysteresis are a static threshold shift, which is right for a monotonic
crossing and wrong for a signal that dithers around the threshold — so this
model says nothing about chatter. Also no supply-current draw, no common-mode
limit, no shutdown pin, and no temperature.

**`output_short_circuit_current` is an absolute maximum**, not a guaranteed
drive. A model bounded by it is optimistic rather than conservative about how
fast the output moves a capacitive load. Given the Figure 5 agreement above,
that optimism appears to be small; it is not zero.

---

## `lvc1g74.lib` — TI SN74LVC1G74DCUR

**Behavioural, not vendor.** The board ties D and C low and uses only `~PRE`
and `~CLR`, so what is modelled is the two cross-coupled gates those reach:
no clock, no data path, no setup or hold.

**Cross-coupled rather than a delayed follower**, because the state is the
point — a model that followed `~PRE` would come out of a trip the moment the
comparator released, which is the failure the latch exists to prevent. Probed:
`~PRE` pulsed low for 20 ns, then released, and Q holds at 3.293 V of a 3.3 V
rail 200 ns later, with `~Q` at zero.

**`tfit` is solved, not derived, and it is the one number here the design does
not state.** Most of the datasheet's 5.9 ns is the datasheet's own load: Figure
3 measures it into 50 pF with 500 Ω to ground at V_M = 1.5 V, and driving 50 pF
to 1.5 V at 24 mA is 3.1 ns on its own. But the gate's ramp and the output
stage's charging **overlap rather than add** — the analytic correction
`tpre - cref*vmeas/ilim` gives 2.775 ns of intrinsic delay, which comes out at
3.36 ns in the jig and not 5.9. `tfit = 6.6653 ns` was found by bisection
against the jig, and reproduces **5.90000 ns**.

A fitted constant goes quietly wrong when something upstream moves — change
`ilim` and this is silently mis-calibrated. So `trip_chain.cir.in` builds the
datasheet's load circuit beside the real board and measures it, banded against
the declared `preset_to_output_max`. **If the fit drifts, the deck says so
before anything downstream of it is believed.**

**What it does not represent:** the clock and data path, setup and hold, the
metastable window, power-up state, or supply current. The output stage is
current-limited at `output_current_max` with no near-rail resistance declared
anywhere, so it holds its rail exactly rather than to a V_OL.

---

## `lvc541.lib` — TI SN74LVC541APWR

**Behavioural, not vendor.** Only the output-enable half: an enable that puts
the output into high impedance after `disable_time_max` (7 ns), and a
current-limited output stage at `output_current_max` (24 mA) while it is not.

**Letting go is the whole contribution.** What happens next — the line falling
through its pull-down, or through the gate-kill transistor — is not this part's
doing and is deliberately not modelled here. `cpu1.py:1281` makes the point
that "the '541 going high-impedance is not the same event as the gate line
going low", and a model that discharged the line itself would hide exactly
that.

**What it does not represent:** the data path and its 5.1 ns propagation delay,
per-channel skew, input thresholds, and the enable's own asymmetry — `t_PHZ`
and `t_PLZ` are given separately and this uses the one figure for both.
`disable_time_max` is measured in the same jig as the latch's figure, at 0.3 V
from the rail under 500 Ω; that jig's contribution is **not** subtracted here,
so this model lets go slightly later than the part does. Conservative.

---

## `dmg1012t.lib` — Diodes Incorporated DMG1012T-7

**Behavioural, not vendor.** `gate_threshold_max` 1.0 V, `on_resistance_at_2v5`
0.5 Ω at `on_resistance_gate_voltage` 2.5 V, and `gate_charge_gate_source` +
`gate_charge_gate_drain` = 210.2 pC.

**Charge, not capacitance**, following `parts.py`, which declines to declare
C_iss and says why: it is a lone typical measured at V_DS = 16 V, where a
MOSFET's input capacitance is at its smallest. The gate is presented as
`qg/vgs_rds` = 84.1 pF, which is the same charge over the same swing. Probed:
the gate reaches 2.5 V in **8.763 ns** at 24 mA, against the check's
`(Q_gs + Q_gd)/24 mA` = 8.758 ns — 0.06 %.

So this is **not** a second opinion on the charge. It is a second opinion on
who pays it: the check divides the charge by the latch's full 24 mA, and on
this board that same 24 mA is also holding two buffer enables and 4.5 pF of
copper. Here they share one source.

Channel, probed: **0.5012 Ω at V_GS = 2.5 V** against a declared 0.5, and
202 Ω at V_GS = 1.0 V, which is off.

**What it does not represent:** the two declared points are the ends of a ramp
in conductance and there is nothing between them, so the shape there is an
assumption and not a reading. No body diode, no C_rss, no drain-voltage
dependence, no temperature, and no avalanche. `drain_current_max` and
`drain_source_voltage_max` are ratings the checks hold it to and are not in the
model.

---

## What none of these represent

- **Supply current, and therefore supply collapse.** Every model here takes its
  rail as given. A deck of the trip chain says nothing about what the chain
  does to the 3V3 rail while it fires.
- **Temperature.** The decks run at ngspice's default 27 °C. The design checks
  cover the declared 0 to 45 °C ambient separately, and the Schottky's
  forward-voltage tempco is read there and not here.
- **Part-to-part spread.** Each model sits at one corner of its declared band,
  chosen by the deck through `@path:end@`. Nothing here is a Monte Carlo.
- **Anything on the way down.** Brown-out, the rails decaying, the window in
  which the comparators are below their minimum supply while the buffers are
  still driving — `cpu1.py:937` describes it and no model here has a rail that
  can fall.
