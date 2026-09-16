# SW6MM — 6 mm tactile switch

| | |
|---|---|
| Component | `BUTTON_6MM` |
| Manufacturer | Korean Hroparts Elec |
| Part number | `K2-1102DP-C4SW-04` |
| LCSC | [C110153](https://www.lcsc.com/product-detail/C110153.html) |
| Footprint | `SW_PUSH_6mm` |

6 × 6 × 5 mm, 4 leads, through hole, 12 V / 50 mA, 2.5 N actuation, 100 k cycles.
Stock 88,870, $0.0485 at qty 100. Extended.

**Why not the Alps part.** SKHHAKA010 is real (C139754, $0.0746, 1 M cycles) but
stock is only 2,317. Same 6 × 6 × 5 mm 4-pin outline, so it remains a drop-in
second source if the cheaper part goes away.

**Pin arrangement — note this, it is the opposite of the obvious guess.** The
two leads **6.5 mm apart** are internally connected to each other. The two
independent poles are the leads **4.5 mm apart**. KiCad numbers the four holes
1, 1, 2, 2 accordingly: pad 1 at (0, 0) and (6.5, 0), pad 2 at (0, 4.5) and
(6.5, 4.5). Two independent sources agree — the KiCad footprint and the
LCSC/EasyEDA symbol, which wires pin 1 to pin 2 and pin 3 to pin 4.

The design uses pin 1 and pin 2, which are therefore the two poles.

**Footprint.** KiCad stock `Button_Switch_THT:SW_PUSH_6mm`, unmodified. Its
holes are 1.1 mm against LCSC's 1.3 mm; either accommodates the real leads,
which are about 0.7 × 0.3 mm.
