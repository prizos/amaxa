# HDR1X3 — where each field bus leaves the board

| | |
|---|---|
| Component | `HEADER_1X3` |
| Manufacturer | HCTL |
| Part number | `PZ254-1-03-Z-8.5` |
| LCSC | [C2894926](https://www.lcsc.com/product-detail/C2894926.html) |
| Footprint | `PinHeader_1x03_P2.54mm_Vertical` |

Three pins on 2.54 mm, 3 A, brass, through-hole. Stock 20,245, read from
JLCPCB's component API on 2026-09-17. Two of them: one for CAN, one for RS-485.

## Three pins, and why the third one is there

Two wires and a ground. The ground is not the return — a differential pair is
its own return — it is the reference the two ends have to share before either
transceiver's common-mode range means anything. A pair run without it works on
a bench, where both boards sit on the same supply, and fails between two
machines, which is the only place it was ever needed.

## Figures used

| Figure | Value | Where |
|---|---|---|
| Current rating | 3 A per contact | LCSC's parametric data for C2894926 |
| Pitch | 2.54 mm | same |

The current rating is not there because a CAN bus draws current. It is there
because of what happens when a bus wire touches something: the transceivers are
rated to survive ±58 V and ±18 V respectively, and at those voltages the
termination on this board is a resistor across the fault. `test_buses.py` works
the current out from each transceiver's fault rating and the termination it
finds in the netlist, and holds it under this number — 0.48 A for CAN, 0.15 A
for RS-485. A part that survives a fault on a board that does not is a worse
outcome than neither surviving, because it looks like it worked.

## Which pin is which

Pin 1 is the high side of each pair (`CAN_H`, `RS485_A`), pin 2 the low side
(`CAN_L`, `RS485_B`), pin 3 ground. Nothing in the design declares that; it
falls out of the transceiver pins the nets come from, and `test_buses.py`
rediscovers the pair by asking what a transceiver and its connector have in
common.

**These are pin headers for now.** As with the two big daughter-board
connectors, the plan puts the final connector choice after the board works. A
locking three-way connector on the same 2.54 mm grid is a footprint change and
nothing else.

**Footprint.** KiCad stock
`Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical`, unmodified.
