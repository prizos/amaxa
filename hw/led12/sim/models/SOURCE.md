# Device models

Where each model came from, and how far it can be trusted. A simulation is only
worth the models under it, and a fitted model that nobody wrote down becomes a
measurement nobody can question.

## `led_red.lib` — Everlight 17-21SURC/S530-A3/4T

**Fitted, not vendor.** Everlight publishes no SPICE model for this part, and
the datasheet's electrical table is an image, so the curve could not be read.

Fitted to the one number that is legible and specified: **forward voltage 2.0 to
2.4 V at 20 mA**. The model puts 2.2 V — the midpoint — at 20 mA, using N = 1.8
and RS = 8 Ω, which are ordinary for a red AlGaInP emitter. IS was then solved
for that point.

What this means in practice:

- At 20 mA it is as accurate as the datasheet.
- At the 4 to 5 mA this board runs, it predicts about 2.0 V. That is the right
  shape and about the right value, but it is extrapolation, not data.
- It carries no temperature or binning behaviour beyond the default diode
  equation, so it says nothing about part-to-part spread. The design checks in
  `hw/checks/` cover that, using the datasheet's stated 2.0 to 2.4 V band.

If a vendor model ever appears, keep the 20 mA point and expect the low-current
end to move.

## `ldo_3v3.lib` — Gainsil GS2401C-33CTR3

**Behavioural, not vendor.** Gainsil publishes no SPICE model. This is three
datasheet numbers wired together: the regulated output, the pass-element
resistance implied by the dropout point (260 mV at 40 mA → 6.5 Ω), and the
150 mA rated output current.

It is deliberately more than a voltage source. A model that simply held 3.3 V
would make `rail3v3.cir.in` a tautology — it would report the setpoint under
every condition, including conditions the real part cannot survive. Both other
mechanisms are live and were verified by probing the model directly:

- **Dropout.** Drive the input down and the output follows it minus the drop
  across 6.5 Ω. At the board's 1 mA that is 6.5 mV, so the model regulates to
  within a few millivolts of its input — which is correct behaviour for a CMOS
  LDO at light load, and why 260 mV at 40 mA does not translate into 260 mV here.
- **Current limit.** Ask for more than 150 mA and the output folds back to
  whatever that current produces across the load. A 20 Ω load gives exactly
  3.000 V, which is 0.15 A × 20 Ω.

What it does **not** represent, and what therefore stays on the bring-up list:

- **Startup.** There is no soft-start, no enable pin and no error-amplifier
  pole, so the model reaches regulation instantly. Inrush into the 10 µF output
  capacitor at switch-on is not simulated by anything.
- **Stability.** The part is a CMOS LDO with no minimum-ESR requirement
  (`parts/SOT223/SOT223.md`), so the usual ceramic-output hazard does not
  apply — but that is read from a datasheet, not demonstrated here. There is no
  loop in this model to be stable or unstable.
- **Line and load transient response, ripple rejection, and temperature.** None
  of these exist in the model, so the deck says nothing about them.
- **Quiescent current.** Modelled as zero; the datasheet's 1.3 µA is well under
  the measurement resolution of anything the deck checks.

## The low-side switch

Not a model. The 2N7002 is represented by its datasheet on-resistance of 7.5 Ω
at V_GS = 10 V, as a plain resistor, because in this circuit it is either fully
on or fully off and nothing depends on its switching behaviour. Where the gate
network's timing matters, `debounce.cir.in` models the RC directly and does not
involve the FET at all.
