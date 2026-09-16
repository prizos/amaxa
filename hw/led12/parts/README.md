# Parts

One directory per KiCad footprint library. Each holds the footprint file, the
`.ato` that declares the components using it, and a review note.

atopile requires the footprint to sit beside the `.ato` that declares the
component, and takes the library name from the directory. That is why the
directories are named after packages rather than parts, and why several
components can share one: `SOT23` holds both MOSFETs, `R0805` all four
resistors.

## What the review notes are for

The automatic part picker cannot run — atopile's parts server no longer
resolves — so every part here is specified by hand. Nothing checks by machine
that a part number matches the footprint it was given, or that pad 1 is the
pin the datasheet calls pin 1. The note is the record of that check.

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
2. Declare the component in `<DIR>/<DIR>.ato`, deriving from a standard-library
   type (`Resistor`, `Capacitor`, `LED`, `Fuse`, `MOSFET`, `Diode`) where one
   fits. That gives real parameters, a designator prefix and a BOM value.
3. Assert the part's own datasheet values in the component body. A board that
   then asks for something the part cannot do resolves to an `<empty>` spec,
   which `make check` rejects.
4. Write `<DIR>/<DIR>.md`. `make check` fails if it is missing.
