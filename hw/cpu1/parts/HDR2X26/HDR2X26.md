# HDR2X26 — the digital connector to the power board

| | |
|---|---|
| Component | `HEADER_2X26` |
| Manufacturer | HCTL |
| Part number | `PZ254-2-40-Z-8.5`, cut to 26 positions |
| LCSC | [C2906029](https://www.lcsc.com/product-detail/C2906029.html) |
| Footprint | `PinHeader_2x26_P2.54mm_Vertical` |

52 pins, 2.54 mm, through-hole, 3 A per contact.

**Grown from 2x20.** The board reserved eight pins for motion feedback - three
encoder lines, three Hall inputs and a serial pair - and had nowhere to put
them. Six more positions at the far end carry all eight with the same
ground-every-two pattern, and the connector grew southwards so every pin that
already existed kept its position and every track that already reached one was
left alone.

**There is no 2x26 male header to buy.** The number this note used to carry,
`PZ254-2-26-Z-8.5`, followed HCTL's own series pattern and does not exist:
JLCPCB's component API returns nothing for it, and the only 2x26 male headers
LCSC list at all are kinghelm's `KH-2.54PH180-2X26P-L11.5` (C19630954) and its
SMT sibling (C19630992), **both at zero stock**. The 2x26 part that is stocked,
C22440848, is a female socket.

So the board orders the **2x40 of the same series and cuts it**:
`PZ254-2-40-Z-8.5`, LCSC C2906029, HCTL, 80 positions, 2.54 mm, dual row,
through hole, −40 to +105 °C, **3453 in stock** (LCSC, read 2026-09-19).
Snapping a 2.54 mm strip to length is ordinary bench practice, and this is the
same family, pitch and 8.5 mm pin as the `PZ254-2-20-Z-8.5` the connector grew
from. The board's footprint is still 52 positions; only the thing in the box is
longer.

## A pin header, deliberately

The connector to the power board is not chosen yet, and choosing it before there
is a power board to connect to would be guessing. Plain 0.1-inch pins are what
a bench harness and a logic analyser both take, and swapping them later changes
one line of `parts.py` and the footprint under it.

**Stock is no longer the thinnest on this board.** The 2x20 it grew from had
906 pieces; the 2x40 it is cut from has 3453.

## The pinout is generated

`pinmap.py` holds an ordered list of signals; `header_pins()` lays them out two
at a time with a ground between, and `cpu1.py` wires the connector from the
result. Nothing here is drawn by hand, and
`test_the_connector_carries_what_the_pin_map_says_it_does` compares the
generated table against the netlist.

Two things follow from that, and both are on purpose:

- **Every signal has a ground within one pin.** A ribbon cable to a gate driver
  with its grounds bunched at one end is an antenna with a connector on it.
  `test_every_connector_signal_sits_next_to_a_ground` checks the pattern rather
  than the drawing.
- **The order is the order the signals leave the package**, not a grouping by
  phase. It looks arbitrary on the connector and it is what lets thirty-three
  tracks cross the board without crossing each other. A cable made to this
  pinout is made from the table.

## Pin mapping

Pins 1 and 2 are the first position, 3 and 4 the second, odd on one row and even
on the other — KiCad's `Conn_02x26_Odd_Even`, which is the numbering the
footprint's pads carry.

**Footprint.** KiCad stock `Connector_PinHeader_2.54mm:PinHeader_2x26_P2.54mm_Vertical`,
unmodified.
