# L_SWPA4030S — the 3V3 buck's inductor

| | |
|---|---|
| Component | `IND_3U3` |
| Manufacturer | Sunlord |
| Part number | `SWPA4030S3R3MT` |
| LCSC | [C15269](https://www.lcsc.com/product-detail/C15269.html) |
| Footprint | `L_Sunlord_SWPA4030S` |

3.3 µH ±20 %, shielded, 4.0 × 4.0 mm. Stock 11,618, read from JLCPCB's
component API on 2026-09-17.

| | |
|---|---|
| Saturation current | 3.6 A |
| Rated (heating) current | 2.4 A |
| DC resistance | 52 mΩ |

## Why these numbers

3.3 µH is the middle of the TPS562200 datasheet's Table 2 row for a 3.3 V
output, which is not a suggestion: this converter has no external compensation
and the inductor is half of the filter its control scheme is built around.

The current ratings are against the converter's own limit again — 2.5 A at its
lowest — rather than against the 0.8 A the rail is budgeted. At 650 kHz the
ripple is about 0.7 A peak to peak, which a part chosen on load current alone
would not have allowed for.

**Footprint.** KiCad stock `Inductor_SMD:L_Sunlord_SWPA4030S`, unmodified —
named for this manufacturer's own series, so the land pattern is the part's.
