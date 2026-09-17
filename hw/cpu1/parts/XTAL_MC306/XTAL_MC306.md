# XTAL_MC306 — 32.768 kHz crystal

| | |
|---|---|
| Component | `XTAL_32K` |
| Manufacturer | Seiko Epson |
| Part number | `Q13MC30620006` |
| LCSC | [C83979](https://www.lcsc.com/product-detail/C83979.html) |
| Footprint | `Crystal_SMD_SeikoEpson_MC306-4Pin_8.0x3.2mm` |

32.768 kHz, **6 pF load**, 8.0 × 3.2 mm. Extended, stock 22,497, $0.32. Listing
from JLCPCB's API on 2026-09-17; from Epson's MC-306 datasheet, served by LCSC:
**ESR 50 kΩ maximum, shunt capacitance 0.85 pF typical**.

## Chosen on gain margin

The H743's LSE offers at most 2.7 µA/V, at its highest drive setting
(LSEDRV = 11, datasheet Table 44). With the common 12.5 pF parts that is a
margin barely above one — it would start on the bench and not reliably cold. A
6 pF load and this ESR give a margin of **6.8** at the datasheet's maximum ESR.
Firmware must select high drive.

The Abracon ABS07 (C1985240), in a smaller two-pad package, leaves its shunt
capacitance blank in its datasheet, so its margin could not be shown.

## Pins

Epson's datasheet: terminals #2 and #3 are internally connected and **must not
be connected to anything external**. The crystal is between #1 and #4. KiCad's
`Device:Crystal_GND23` symbol matches: pins 1 and 4 are the crystal, 2 and 3
are left unconnected in the design.

**Needs a human eye.** Epson's package drawing is an image, and the extracted
text gives the pin positions only as "#4 | #1 #2 | #3". KiCad's footprint puts
pad 1 bottom-left and pad 4 top-left — both crystal terminals at one end — which
fits that reading. Confirm against the drawing: if the crystal were between #1
and #2 instead, this footprint would join one of its ends to nothing.

**Footprint.** KiCad stock `Crystal:Crystal_SMD_SeikoEpson_MC306-4Pin_8.0x3.2mm`,
unmodified.
