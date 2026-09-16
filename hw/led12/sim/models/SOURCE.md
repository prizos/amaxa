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

## The low-side switch

Not a model. The 2N7002 is represented by its datasheet on-resistance of 7.5 Ω
at V_GS = 10 V, as a plain resistor, because in this circuit it is either fully
on or fully off and nothing depends on its switching behaviour. Where the gate
network's timing matters, `debounce.cir.in` models the RC directly and does not
involve the FET at all.
