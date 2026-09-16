# Parts

One directory per KiCad footprint library. Each holds the footprint file and a
review note. What the parts *are* — symbol, part number, supplier code and the
datasheet figures — lives in [`../parts.py`](../parts.py).

The directories are named after packages rather than parts, so several parts
can share one: `SOT23` holds both MOSFETs, `R0805` all four resistors. KiCad
takes the library name from the directory, and `tools/board.py` writes an
`fp-lib-table` pointing at them.

## What the review notes are for

Every part is specified by hand. Two things are now checked by machine — that
the symbol exists, and that its pin numbers match the footprint's pads — but
nothing checks that the part number matches the package it was given, or that
pin 1 is the pin the *datasheet* calls pin 1. The note is the record that a
person looked.

Each note records the part, why it was chosen, what was rejected, the pin
mapping and how it was established, and what is still unconfirmed.

## Status of the review

The part data was verified against LCSC's product-detail API and, where the
PDFs were machine-readable, the manufacturer datasheets. That found three parts
that were simply wrong for the job — a 6.3 V capacitor on a 12 V rail, a FET
whose gate rating was exceeded in normal operation, and a fast-acting fuse
chosen to be slow-blow.

**It is not a substitute for a human reading the datasheets.** Several pin
mappings could only be taken from footprint geometry or distributor symbol
data, because the relevant datasheet pages are images. Those are marked
**Needs a human eye** in the notes, and they are the ones that turn a board
into scrap if wrong:

| Part | What needs confirming |
|---|---|
| `LED0805` | Pad 1 is the cathode |
| `SMB` | Pad 1 is the cathode (banded end) |
| `SOT23` | AO3407A pinout is 1 = G, 2 = S, 3 = D |

The 2N7002 pinout, the AMS1117 pinout and the tactile switch's pole
arrangement were each confirmed from two independent sources and need no
further check.

## Adding a part

1. Copy the footprint from the KiCad library into a directory named after the
   package. Do not edit it; if the stock footprint is unsuitable, pick a
   different stock one and say why in the note.
2. Add a `PartSpec` to [`../parts.py`](../parts.py): the KiCad symbol, the
   footprint, the manufacturer and part number, the supplier code, and the
   datasheet figures the checks and simulations reason about. Use `lcsc=None`
   for something deliberately not bought, which keeps it off the BOM.
3. Check the symbol's pin numbers against the footprint's pads yourself, and
   against the datasheet. `make check` verifies the first pairing; only you can
   verify the second.
4. Write `<DIR>/<DIR>.md`, naming the part number. `make check` fails if the
   note is missing, and fails again if it still names a part that was replaced.
