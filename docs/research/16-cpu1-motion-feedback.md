# Bringing cpu1's motion feedback out, and what it cost

Eight MCU pins — three encoder lines, three Hall inputs and a serial pair —
were reserved by the plan and connected to nothing. They now reach the digital
connector. Getting them there took a sixth and fifth copper layer, and this
note is the arithmetic that says why, because four layers did not fail for
want of effort.

| net | pin | package pad | edge |
|---|---|---|---|
| `ENC_A` | PD12 | 81 | east |
| `ENC_B` | PD13 | 82 | east |
| `ENC_Z` | PD14 | 85 | east |
| `HALL_1` | PB4 | 134 | north |
| `HALL_2` | PB5 | 135 | north |
| `HALL_3` | PB0 | 46 | south |
| `ENC_SERIAL_TX` | PB13 | 92 | east |
| `ENC_SERIAL_RX` | PB12 | 91 | east |

The motor's wires land on the power board, so **that** board decides what the
encoder is — single-ended, RS-422, open collector — and cpu1 carries pins
rather than a commitment. J3 grows from 2x20 to 2x26, which fits all eight on
the same ground-every-two pattern: 34 signals, 18 grounds, 52 pins exactly.

## What moved besides the layer count

- **The serial encoder moved from USART1 (PB6/PB7) to UART5 (PB13/PB12).**
  USART1's only free pair on this part is PB6/PB7, on the north edge beside
  the Hall inputs and forty millimetres from the connector. UART5's PB13/PB12
  are the first two pins of the east edge, five pins from the encoder's own.
  Four signals in the package's worst corner became two. This was worth doing
  on its own and would have been worth doing even if the routing had failed.
- **`HEADER_DIGITAL` split into named groups.** The layout used to find out
  which buffer a signal belonged to by indexing that list at 11 and 18, which
  stops being true the moment anything is added to the end of it.
- **The connector's pin count is now counted, not written.** `cpu1.py` takes
  it from the symbol's own pin list and the checks take it from the pads on
  the board, so growing the connector again is one line.

## Why four layers could not do it

Everything below was measured on the routed four-layer board.

### Three walls between the package and the connector

The connector's new rows are in the south-east. Between them and the MCU:

1. **The buffered PWM outputs, on the front.** Seven horizontals from x 2.25
   to x 25.64 across y 16 to 20. Nothing crosses them on that layer, anywhere
   in that span.
2. **The 5 V spine, on the back.** The width of the board at y 21, then the
   length of it at x 36.5. Signals must cross one arm or the other.
3. **The 5 V island**, x -9 to 33, y 24.5 to 36.5. A back-layer track that
   crossed its edge handed its return current from one plane to the other
   halfway along, which a check refuses. The crossing had to be made on the
   front.

### And one window, which was already full

Crossing the spine needed a via between the buffered outputs' southernmost
line (y 19.89) and the spine itself (y 21.0). That is 1.11 mm, and a via needs
0.475 either side — so the window was 0.16 mm of y, and it only existed where
both lines existed. Worse, the buffer enable's own back-layer row sat at
y 20.5, inside it, from x 1.5 to x 24.3.

Moving those two apart — the spine to y 22.2 and the enable's row to y 21.3 —
opened a real window, and that part worked. What it opened onto did not:

| x band | what is there |
|---|---|
| < 24.3 | the buffer enable's row, until it was moved |
| 24.3 – 27.0 | `safety.buffer1`'s west pads: a via needs 0.65 mm from a pad edge and there is 0.6 mm |
| 27.0 – 29.4 | **clear — room for four vias at the spacing hole-to-hole demands** |
| 29.4 – 31.4 | the 3V3 buck's feedback column, then the buffer's east pads |
| 31.4 – 36.8 | the buffered outputs' own front-layer rows, at y 19.89 and 20.55 |
| > 36.5 | the far side of the spine's other arm |

**Four via positions where eight were needed.** That is the measurement the
decision turned on. Everything else — the crowded descent from x 15 to 25,
the corridor south across the island, the 3V3 buck sitting in exactly the
quadrant the new rows wanted — only made it worse.

## What six layers changed

PCBWay builds 1 to 14 layers on the same standard process, with the same
0.15 mm drill and 0.1 mm track and spacing, so `fab/pcbway.kicad_dru` did not
change and neither did any existing track.

The order is **F.Cu / In1 ground / In2 signal / In3 ground / In4 supply
islands / B.Cu**, and the middle two are placed deliberately:

- The new signal layer goes **between the two grounds**, not beside the
  supplies. It is the one layer with no way out — a track there cannot be
  taken round the other side of an obstruction the way one on an outer layer
  can — so it gets a solid reference above and below, and its return current
  never has to find its way around an island's edge.
- B.Cu keeps exactly the reference it had on four layers: the islands, one
  prepreg away. So every track on it is unchanged, and the check that
  polices island crossings still has something to police. Moving the islands
  away from B.Cu would have made that check vacuous, which is not the same as
  making the board better.
- The outer prepreg is unchanged — PCBWay's published 7628 build, 0.1960
  pressed to 0.1855. Every impedance-controlled track on this board is on
  F.Cu over In1, so fixing that one dielectric keeps the USB and Ethernet
  pair geometry exactly as it was, and `pair_geometry` solves it from these
  numbers rather than from a width someone remembered.

**Confirmed since:** the build above is PCBWay's own, from their standard
stackup table — the 1.6 mm 1 oz-inner entry, with 0.43 mm cores and a 7628
middle prepreg at 0.175. That entry was picked out of the table precisely
because its outer prepreg is the same 7628 at the same 0.1855 as the 4-layer
spin, which is what makes the "impedance pairs unchanged" claim above true
rather than hoped for. PCBWay's *default* 6-layer 1.6 mm build uses 2116 at
0.1195 for the outer prepreg, and choosing that one would have moved every
controlled-impedance pair on the board.

## How the eight actually run

All eight leave the package on the front, drop to In2.Cu, run south in their
own column and east in their own row. Two rules keep the fan-out planar, and
both are properties of the geometry rather than preferences:

- **A row can only cross a column that has already turned**, so the
  westernmost column takes the southernmost row — and `HEADER_FEEDBACK` is
  therefore in the order the tracks *arrive*, which is the reverse of the
  order the pins leave the package.
- West of the package there is **exactly one column clear of plane vias from
  the north edge to the connector**: x -5.0, between the 5 V buck's ground
  vias at -5.6 and the DC-link comparator's tap at -4.5. `HALL_2` takes it.
  `HALL_3` drops level with its own pin and so misses everything north of it.
  `HALL_1` comes south at x -2.25, which is the x of one of the MCU's own 3V3
  vias, so it steps clear of that via on In2.Cu before its column starts.

The result is 0 DRC violations and 0 unconnected items with DRC in the mode
that demands every connection.
