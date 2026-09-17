# SOT23 — the voltage reference

| | |
|---|---|
| Component | `VREF_3V0` |
| Manufacturer | Texas Instruments |
| Part number | `REF3030AIDBZR` |
| LCSC | [C38423](https://www.lcsc.com/product-detail/C38423.html) |
| Footprint | `SOT-23` |

3.000 V series reference, ±0.2 %, 75 ppm/°C, 50 µA quiescent, SOT-23-3.
Stock 15,700, read from JLCPCB's component API on 2026-09-17.

## Why a reference at all

Everything this board measures — phase currents, DC-link voltage — is a ratio
of VREF+. Deriving it from the 3V3 rail would make every measurement a
measurement of the switching regulator, and the MCU's own VREFBUF is specified
in percent, not in parts per million. This part's 0.2 % initial error and
75 ppm/°C drift are the board's measurement accuracy, and they are the two
numbers to quote when anyone asks what the current sensing is worth.

3.0 V and not 3.3: VREF+ may not exceed VDDA, and VDDA is the logic rail less
the drop across its ferrite. A 3.3 V reference on a 3.3 V rail has no headroom
at all, and `test_the_reference_is_below_the_analog_supply_it_sits_under`
compares the reference's highest against the rail's lowest.

## Figures used from the datasheet

TI's *REF3012, 3020, 3025, 3030, 3033, 3040*, SBVS032F (March 2002, revised
August 2008), served by LCSC for C38423.

| Figure | Value | Where |
|---|---|---|
| Output voltage | 2.994 / 3.0 / 3.006 V | Electrical characteristics, 3.0 V |
| Supply voltage | V_OUT + 1 mV to 5.5 V | Electrical characteristics, power supply |
| Absolute maximum supply | 7.0 V | Absolute maximum ratings |
| Output current | 25 mA | Features |
| Drift | 75 ppm/°C maximum, −40 to +125 °C | Features |
| Supply bypass | 0.47 µF recommended | Application information |

**No output capacitor is required**, and one is allowed: the datasheet's only
caution about capacitive loading is against low-ESR capacitance on the 1.25 V
member of the family, which it bounds at 10 µF. The 1 µF and 100 nF on VREF+
are the MCU's decoupling, not this part's.

## Pin mapping

Pin 1 IN, pin 2 OUT, pin 3 GND, read from the package drawing on page 1 of the
datasheet, which is text and not an image. KiCad's `Reference_Voltage:REF3030`
inherits the same numbering from `REF3012`. Two sources, agreeing: no doubt
here.

**Footprint.** KiCad stock `Package_TO_SOT_SMD:SOT-23`, unmodified.
