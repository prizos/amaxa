# MSOP10 — the threshold DAC

| | |
|---|---|
| Component | `THRESHOLD_DAC` |
| Manufacturer | Microchip Tech |
| Part number | `MCP4728T-E/UN` |
| LCSC | [C478093](https://www.lcsc.com/product-detail/C478093.html) |
| Footprint | `MSOP-10_3x3mm_P0.5mm` |

Quad 12-bit DAC, I²C, MSOP-10. Stock 21,498, read from JLCPCB's component API
on 2026-09-17.

Four channels for three thresholds - over-current in each direction, and the
DC link's over-voltage - with one spare on a test pad. All three phases share
one pair of current thresholds, which is what a symmetric limit means.

## Two things about this part that are not ideal

**Its reference is its supply.** The MCP4728 can use its own 2.048 V reference
or VDD, and neither is VREF+. The trip thresholds are therefore ratiometric to
the 3V3 rail while everything the ADCs measure is ratiometric to VREF+, so the
rail's ±5 % lands directly on every trip point.

That is acceptable for a protective limit — you set it well above the working
maximum anyway — and it is checked rather than assumed:
`checks/test_trip.py::test_the_trip_thresholds_are_as_accurate_as_they_claim`
works the rail band through to a tolerance and compares it against what the
board declares. Powering the DAC from VREF+ instead would make the ratio exact
and put I²C switching currents into the ADC reference, which is a worse trade.

**Its power-up value comes from EEPROM.** Microchip ships the part with the
factory default loaded, and this board depends on that default being zero - it
is what makes an unprogrammed board trip as it powers up. **Firmware must never
write the EEPROM**, only the input registers, or the board's power-up state
changes silently and permanently.

**Needs a human eye.** The datasheet for this part is a scanned-font PDF that no
text extraction here could read, so the factory default and the EEPROM write
sequence were not confirmed from it. Read §4.1 and §5.5 before ordering. The
safety argument does not rest on it — NRST presets the trip latch regardless —
but the second line of defence does.

## Pin mapping

Pin 1 VDD, 2 SCL, 3 SDA, 4 LDAC, 5 RDY/BSY, 6–9 VOUTA–VOUTD, 10 VSS.

Taken from **two independent sources that agree**: KiCad's `Analog_DAC:MCP4728`
symbol, and LCSC's own symbol data for C478093. Neither is the manufacturer's
drawing, which is the same gap as the factory default above.

LDAC is tied low, so a write reaches the output when it lands; nothing here
needs four thresholds to change at one instant. RDY/BSY reports an EEPROM write
in progress and is deliberately left unconnected, because there will not be one.

**Footprint.** KiCad stock `Package_SO:MSOP-10_3x3mm_P0.5mm`, unmodified.
