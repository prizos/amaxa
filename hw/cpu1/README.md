# cpu1 — the control board

The STM32H743ZIT6 board that generates every hard real-time signal, and is later
soldered onto one analog power board. **In progress:** so far only its pin map
exists.

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

A 4-layer stackup and the router extensions an LQFP-144 needs; the MCU core
(crystals, reset, Tag-Connect, VDDA and VREF+); a 9–36 V input with a 100 V-class
buck; the hardware trip chain (external comparators, a latch, and PWM buffers
that are off until firmware deliberately enables them); the ADC input networks;
USB, CAN FD, RS-485 and Ethernet; and 2.54 mm headers to the power board.
