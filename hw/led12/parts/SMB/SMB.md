# SMB — SMB transient-voltage suppressor

| | |
|---|---|
| Component | ``TvsSmbj12A`` |
| Manufacturer | Brightking |
| Part number | `SMBJ12A/TR13` |
| LCSC | [C111091](https://www.lcsc.com/product-detail/C111091.html) |
| Footprint | `D_SMB` |

Unidirectional TVS, DO-214AA (SMB). Stock 15,880, $0.0557 at qty 100. Extended —
there is no Basic-library SMB TVS at all.

| | |
|---|---|
| Stand-off voltage | 12 V |
| Breakdown voltage | 14.7 V |
| Clamping voltage | **19.9 V at 30.2 A** |
| Peak power | 600 W, 10/1000 µs |

**Why not Littelfuse.** LCSC's Littelfuse SMBJ12A listing (C151251) carries
13 V / 15.9 V / 21.5 V / 28 A, which are the **SMBJ13A** numbers. Five other
manufacturers of the same part number list the correct 12 V figures. Either the
listing is mis-parameterised or the stock is the wrong part; not worth the risk
for a few cents.

**Pin mapping.** Pad 1 cathode, pad 2 anode. The cathode is the banded end.
**Needs a human eye** against the manufacturer drawing before fabrication.

**Footprint.** KiCad stock `Diode_SMD:D_SMB`, unmodified.

**Design note.** The 19.9 V clamping voltage is the constraint the rest of the
12 V rail has to live with. Nothing on that rail may have an absolute maximum
below it.
