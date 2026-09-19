# Bringing cpu1's motion feedback out, and what stops it

cpu1 is routed: every net drawn, DRC demanding every connection and finding
nothing. Eight MCU pins are the exception, and they are not unrouted so much as
*unconnected* — the encoder and Hall inputs were reserved by the plan and never
given anywhere to go:

| net | pin | package pad | edge |
|---|---|---|---|
| `ENC_A` | PD12 | 81 | east |
| `ENC_B` | PD13 | 82 | east |
| `ENC_Z` | PD14 | 85 | east |
| `HALL_1` | PB4 | 134 | north |
| `HALL_2` | PB5 | 135 | north |
| `HALL_3` | PB0 | 46 | south |
| `ENC_SERIAL_TX` | PB6 | 136 | north |
| `ENC_SERIAL_RX` | PB7 | 137 | north |

The decision taken was to carry them through the digital connector: the motor's
wires land on the power board, so that board decides what the encoder is —
single-ended, RS-422, open collector — and cpu1 carries pins rather than a
commitment. J3 grows from 2x20 to 2x26, which fits all eight with the same
ground-every-two pattern (34 signals, 18 grounds, 52 pins exactly).

**The design side of that works. The routing does not, and this note is about
why, because the reason is a placement decision and not a routing one.**

## What was built and then reverted

- J3 as a 2x26, grown at the end so every pin that already existed kept its
  position and every track that already reached one was left alone.
- `HEADER_DIGITAL` split into named groups. The layout used to find out which
  buffer a signal belonged to by indexing that list at 11 and 18, which stops
  being true the moment anything is added to the end of it.
- The serial encoder moved from **USART1 (PB6/PB7) to UART5 (PB13/PB12)**. This
  part is worth keeping whatever happens next. USART1's only free pair on this
  part is PB6/PB7, on the north edge beside the Hall inputs and forty
  millimetres from the connector; UART5's PB13/PB12 are the first two pins of
  the east edge, five pins from the encoder's own. Four signals in the
  package's worst corner become two.

All of it reverted, because a board with eight unrouted connections is worse
than one with eight pins that were never asked to go anywhere.

## Why the eight do not fit

Everything below was measured on the routed board, not estimated.

### Three walls between the package and the connector

The connector's new rows are in the south-east. Between them and the MCU:

1. **The PWM fan, on the front.** Seven horizontals from x 2.25 to x 25.64
   across y 16 to 20. Nothing crosses them on that layer, anywhere in that
   span.
2. **The 5 V spine, on the back.** The width of the board at y 21, then the
   length of it at x 36.5. Signals must cross one arm or the other.
3. **The 5 V island**, x -9 to 33, y 24.5 to 36.5 on In2. A back-layer track
   that crosses its edge hands its return current from one plane to the other
   halfway along, which a check refuses. The crossing has to be made on the
   front.

### And one window, which is already full

Crossing the spine needs a via between the PWM fan's southernmost line
(y 19.89) and the spine itself (y 21.0). That is 1.11 mm, and a via needs 0.475
either side — so the window is 0.16 mm of y, and it only exists where both
lines exist. Worse, the buffer enable's own back-layer row sits at y 20.5,
inside it, from x 1.5 to x 24.3.

Moving those two apart — the spine to y 22.2 and the enable's row to y 21.3 —
opens a real window, and that part was tried and worked. What it opens onto is
the problem:

| x band | what is there |
|---|---|
| < 24.3 | the buffer enable's row, until it was moved |
| 24.3 – 27.0 | `safety.buffer1`'s west pads: a via needs 0.65 mm from a pad edge and there is 0.6 mm |
| 27.0 – 29.4 | **clear — room for four vias at the spacing hole-to-hole demands** |
| 29.4 – 31.4 | the 3V3 buck's feedback column, then the buffer's east pads |
| 31.4 – 36.8 | the buffered outputs' own front-layer rows, at y 19.89 and 20.55 |
| > 36.5 | the far side of the spine's other arm |

Four places, eight signals.

The same arithmetic repeats south of it. The descent from the package to that
window has to pass x 15 to 25, which holds the console pair's escape, the trip
latch at (26, 9) and its ground vias, and two decoupling stubs. The corridor
south across the island is 18 to 25 and holds a test point. The approach to the
connector from the west is closed by the 3V3 buck, which occupies x 26 to 42,
y 19 to 33 — exactly the quadrant the new rows sit in.

## What it would take

One of these, and all of them are placement:

- **Move the 3V3 buck.** It is the single part standing between the buffered
  fan and the empty south-east. It cannot simply go south: its input capacitors
  need vias into the 5 V island, and the island stops at y 36.5. So the island
  grows with it, and the 3V3 vias now inside it move out — including the
  power-good stitch capacitor that was put at (0, 40.5) precisely because it
  was outside.
- **Move the safety chain east.** The buffers and the latch own x 25 to 32.
  Moving them opens the one window, and costs the buffered fan its geometry.
- **Give the feedback its own connector** on the west or south edge, close to
  the pins, and accept that cpu1 has then chosen single-ended feedback.

## What is true today

The eight pins are reserved and connected to nothing. That is what the plan
said would happen — *"the encoder type decision (pins are reserved, not
committed)"* — and the board is otherwise finished. The cost of leaving them is
eight MCU pins and a connector that does not carry motion feedback. The cost of
taking them is re-planning the east half of the board.

The measurement that decides it is the one in the table above: **four via
positions where eight are needed.** Everything else follows from that.
