# cpu1 — the control board

The STM32H743ZIT6 board that generates every hard real-time signal, and is later
soldered onto one analog power board. **In progress,** and built one block at a
time.

What exists: the pin map; the MCU itself on a 4-layer board, with every used pin
on its own named net, every unused pin marked no-connect, and its ground pads
stitched to a solid ground plane on In1. It builds, passes ERC and every check,
and DRC finds no violations — with the 3.3 V rail's pins not yet routed, because
nothing supplies them until the power block lands. 94 nets are *pending*, each
naming the block that will connect it (`_MILESTONES` in [`cpu1.py`](cpu1.py)).

| | |
|---|---|
| Stackup | PCBWay's published regular 4-layer build: 1 oz copper throughout, 7628 prepreg, 1.03 mm core, 1.51 mm finished |
| Layers | F.Cu signal, In1.Cu solid ground, In2.Cu supply islands (to come), B.Cu signal |
| Size | 100 × 80 mm, provisional until the blocks and power-board headers are placed |
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

## Still to come

The router extensions a dense board needs — routes that change layer and
generated fan-out and decoupling; the MCU core
(crystals, reset, Tag-Connect, VDDA and VREF+); a 9–36 V input with a 100 V-class
buck; the hardware trip chain (external comparators, a latch, and PWM buffers
that are off until firmware deliberately enables them); the ADC input networks;
USB, CAN FD, RS-485 and Ethernet; and 2.54 mm headers to the power board.
