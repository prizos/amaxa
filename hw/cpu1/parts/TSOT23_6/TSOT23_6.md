# TSOT23_6 — the 3V3 buck

| | |
|---|---|
| Component | `BUCK_3V3` |
| Manufacturer | Texas Instruments |
| Part number | `TPS562200DDCR` |
| LCSC | [C49757](https://www.lcsc.com/product-detail/C49757.html) |
| Footprint | `TSOT-23-6` |

4.5 to 17 V in, 2 A out, 650 kHz, D-CAP2 control. Stock 8,489, read from
JLCPCB's component API on 2026-09-17.

## Why this part and not the TPS562201

Because KiCad has a symbol for this one, and the family's pinout is not
constant: `TPS562200` is GND, SW, VIN, VFB, EN, VBST, while `TPS562202` — a
different datasheet — is VIN, SW, GND, VBST, EN, VFB. Using a symbol named for
a sibling would have put every pin of this board's 3V3 rail somewhere else.

The '201 was the first choice on stock and price. It is the same silicon in the
same order but its own datasheet, and nothing here needed the difference.

## Figures used from the datasheet

TI's *TPS562200, TPS563200*, SLVSCB0B (January 2014, revised August 2014),
served by LCSC for C49757.

| Figure | Value | Where |
|---|---|---|
| Input voltage | 4.5 to 17 V | §7.3 |
| Feedback threshold | 758 / 765 / 772 mV, continuous conduction | §7.5 |
| Switching frequency | 650 kHz in continuous conduction | §8.4.1 |
| Current limit | 2.5 / 3.2 / 4.3 A | §7.5 |
| Bootstrap capacitor | 0.1 µF | §9.2.1.2.4 |
| Input capacitance | 10 µF ceramic, plus an optional 0.1 µF | §9.2.1.2.3 |
| Inductor, 3.3 V out | 2.2 / 3.3 / 4.7 µH | Table 2 |
| Output capacitance, 3.3 V out | 20 to 68 µF | Table 2 |
| Divider, 3.3 V out | R2 33.2 kΩ, R3 10.0 kΩ | Table 2 |

**765 mV, not 768.** The 768 mV figure belongs to another member of this
family; this part's electrical table gives 758 / 765 / 772 mV in continuous
conduction and 772 mV in Eco-mode. The divider fitted is TI's own Table 2 row
and `test_the_3v3_feedback_divider_holds_the_rail_inside_its_band` works it
through both ends of that band and the resistors' tolerance.

## The output capacitance is the whole rail

This converter has no external compensation: the double pole of its output
filter has to sit where D-CAP2's internal zero expects it, which is what
Table 2's range of L and C means. The MCU's decoupling is on the same net and
is therefore part of that filter whether it was chosen to be or not, so
`test_the_3v3_output_filter_is_the_one_the_datasheet_specifies` sums every
capacitor on the rail — about 50 µF against a 20 to 68 µF window. **Adding
decoupling moves this**, and the check is what says so.

## Pin mapping

KiCad's `Regulator_Switching:TPS562200`. Its pin numbers — GND 1, SW 2, VIN 3,
VFB 4, EN 5, VBST 6 — match the datasheet's Pin Functions table exactly, which
was read in full. No doubt here.

**Footprint.** KiCad stock `Package_TO_SOT_SMD:TSOT-23-6`, unmodified.
