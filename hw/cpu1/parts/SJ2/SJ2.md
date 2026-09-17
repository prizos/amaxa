# SJ2 — the jumper that decides whether this board is the end of a bus

| | |
|---|---|
| Component | `SOLDER_JUMPER` |
| Manufacturer | — |
| Part number | `SOLDER-JUMPER-2` |
| LCSC | none: this is copper, not a part |
| Footprint | `SolderJumper-2_P1.3mm_Open_Pad1.0x1.5mm` |

Two pads 1.3 mm apart, closed with a blob of solder. Nothing to buy, nothing to
place, and `lcsc=None` keeps it off the BOM — the part number exists only so
the design has something to call it.

## Why a bus termination is a decision and not a value

A terminated bus wants exactly two terminations, one at each physical end. A
board that is terminated because it was built that way can only ever be an end
of a bus, and two of them in the middle of a working one is the fault that
looks like a cable problem for a day and a half.

There are two of these, one per bus, and both arrive **open**. A board added to
an existing bus is usually not the end of it, so open is right more often than
closed; and a board that needs to be an end needs a soldering iron for two
seconds, which is a smaller thing to ask than desoldering an 0402 in the field.

`test_buses.py` walks from one bus wire to the other through whatever
two-terminal parts it finds, and requires exactly one jumper in that path with
`open` as its value. A part list would not tell those two states apart.

## Figures used

None. It has no electrical parameters: it is two pads, and what matters about
it is its state, which is checked from the design rather than from a datasheet.

**Footprint.** KiCad stock
`Jumper:SolderJumper-2_P1.3mm_Open_Pad1.0x1.5mm`, unmodified. The `Open`
variant has no solder bridge drawn between the pads; the `Bridged` variant of
the same footprint would arrive terminated, which is the opposite of what this
board wants.
