# cpu1 — the control board

The STM32H743ZIT6 board that generates every hard real-time signal, and is later
soldered onto one analog power board. Built one block at a time, and now
**fully routed**: every net is drawn, `board.mk` says `ROUTING := complete`, and
DRC runs in the mode that demands every connection.

The encoder and Hall inputs now reach the digital connector too, which is why
this board is six layers rather than four: see
[`docs/research/16-cpu1-motion-feedback.md`](../../docs/research/16-cpu1-motion-feedback.md)
for the arithmetic. What the encoder *is* — single-ended, RS-422, open
collector — is still the power board's decision; cpu1 carries pins.

**What is on it, and how much of it is drawn, is in
[`review/README.md`](review/README.md)** — the board plotted layer by layer,
every footprint and every net, with the counts read from the board file rather
than written down. `make review BOARD=cpu1` regenerates it. This file is about
*how* the board is built; that one is about what it currently is, and it cannot
go stale.

Nets still waiting for later blocks are *pending*, each naming the block that
will connect it (`_MILESTONES` in [`cpu1.py`](cpu1.py)); the review lists them.

| | |
|---|---|
| Stackup | 6 layers, 1 oz copper throughout. The outer prepreg is PCBWay's published 7628 build, 0.1855 mm — unchanged from the 4-layer spin, so the controlled-impedance pairs are unchanged. The inner cores and middle prepreg are **provisional**: see `layout.py` |
| Layers | F.Cu signal, In1.Cu ground, In2.Cu signal, In3.Cu ground, In4.Cu supply islands, B.Cu signal |
| Size | 130 × 110 mm — grown from 100 × 80 to hold the Ethernet jack |
| MCU | STM32H743ZIT6, LCSC C114408 — **zero stock at JLCPCB** on 2026-09-17; see [its review note](parts/LQFP144/LQFP144.md) |

## The pin map

[`pinmap.py`](pinmap.py) is the single table of what every MCU pin does. It is
checked against ST's own description of the part, vendored in
[`../silicon/STM32H743ZITx/`](../silicon/STM32H743ZITx/SOURCE.md), and it
generates the firmware's
[`board_pins.h`](../../firmware/bsp/amaxa_cpu1/board_pins.h). Edit the table,
never the header.

```sh
make pins BOARD=cpu1           # check the pin map against the silicon
make pins-write BOARD=cpu1     # regenerate the firmware header
```

`make pins` fails if a pin cannot carry the signal it is used for, a digital
function has no alternate-function number, a pin or name is used twice, a
peripheral is used in part (a UART with one line, RMII with eight of nine
signals, a bridge leg with a high side and no low side), a pair meant to be
sampled simultaneously is not on ADC1 and ADC2, ST's data and KiCad's symbol
disagree about the part, or the committed header is not what the table
generates.

88 of the package's 114 I/O pins are used. Three conflicts shaped the layout,
and the table's docstring records them: Ethernet's CRS_DV and TIM8_CH1N want the
same pin, no 32-bit timer is free for the encoder, and keeping TIM1 where the
NUCLEO has it costs COMP2's external inputs.

## How the MCU core is laid out

Most of it is computed from the netlist and the footprint, not written as
coordinates ([`layout.py`](layout.py), with helpers in
[`../tools/layout_lib.py`](../tools/layout_lib.py)):

- **Supply pins take their plane vias inward.** An LQFP-144 has an 18 mm square
  of empty board inside its pad ring, where no signal will ever escape. Outside
  the ring, vias on neighbouring 0.5 mm-pitch pins collide; inside, they stagger
  in rings — ground at 9.3 mm from the centre, 3V3 at 8.5 mm, and 7.7 mm for a 3V3
  pin beside another.
- **Each supply pin's capacitor goes outward**, turned so its first pad faces the
  pin, with its ground via beyond. Capacitors on neighbouring pins spread apart.

VDDA's filter, both crystals, debug, the indicators and the button are placed by
hand, near the pins they serve.

## What the checks establish

[`checks/test_core.py`](checks/test_core.py) derives everything from ST's
datasheet figures and the parts' own:

| Check | From |
|---|---|
| Every supply pin has its **own** 100 nF within 3 mm, matched one to one | ST pin data, netlist, placed board |
| Bulk: 4.7 µF on 3V3, 1 µF on 3V3 and on VDDA | Datasheet Figure 13 |
| One 2.2 µF on each VCAP pin | Datasheet Table 24 |
| Each crystal sees its specified load, at every corner | Crystal load, capacitor tolerance, declared stray |
| **Oscillator gain margin at least 5**, both crystals | Datasheet Tables 43–44, crystal ESR and C0 |
| Indicators visibly lit and inside the LED's and the pin's ratings | LED and resistor tolerances, pin limit |
| NRST's 100 nF, BOOT0 and button pull-downs, VDDA fed only through a ferrite | Datasheet Figure 21, netlist |

The gain-margin check chose the crystals. Every in-stock 8 MHz part in 3225 or
HC-49S, and the common 12.5 pF 32 kHz parts, fail it — the latter at a margin of
1.8. Each would start on the bench and might not start cold.

**Four things need a person** before ordering, tracked by `make check`: which
supply pin each of the datasheet's decoupling values belongs to (the figure is a
drawing), the 32 kHz crystal's pad roles, the LEDs' cathode pad, and the
Tag-Connect pinout against Tag-Connect's own drawing. ST's AN4938 hardware guide
could not be fetched and has not been read.

## Still to come

- The ordering codes still marked **unverified**, and the pinouts in
  `checks/config.py` that need a person with a datasheet open.
- Confirming the inner stackup with PCBWay.
