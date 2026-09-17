# HDR2X20 — the digital connector to the power board

| | |
|---|---|
| Component | `HEADER_2X20` |
| Manufacturer | HCTL |
| Part number | `PZ254-2-20-Z-8.5` |
| LCSC | [C2894981](https://www.lcsc.com/product-detail/C2894981.html) |
| Footprint | `PinHeader_2x20_P2.54mm_Vertical` |

40 pins, 2.54 mm, through-hole, 3 A per contact. Stock 906, read from JLCPCB's
component API on 2026-09-17.

## A pin header, deliberately

The connector to the power board is not chosen yet, and choosing it before there
is a power board to connect to would be guessing. Plain 0.1-inch pins are what
a bench harness and a logic analyser both take, and swapping them later changes
one line of `parts.py` and the footprint under it.

**Stock is the thinnest on this board** at 906 pieces. It is also the part whose
substitution matters least.

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
  phase. It looks arbitrary on the connector and it is what lets twenty-five
  tracks cross the board without crossing each other. A cable made to this
  pinout is made from the table.

## Pin mapping

Pins 1 and 2 are the first position, 3 and 4 the second, odd on one row and even
on the other — KiCad's `Conn_02x20_Odd_Even`, which is the numbering the
footprint's pads carry.

**Footprint.** KiCad stock `Connector_PinHeader_2.54mm:PinHeader_2x20_P2.54mm_Vertical`,
unmodified.
