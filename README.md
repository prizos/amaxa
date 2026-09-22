# amaxa

A mechatronics driver board for motors and inverters — small motors, servos,
compressors, and up through high-power drives.

The architecture is one **digital control board** that generates every hard
real-time signal, soldered onto **one analog power board** at a time. There are
N power-board types, from a few tens of milliamps to hundreds of amps, AC or DC;
the control board is the same in each case. It does the control in real-time
software on a single fast Arm core rather than in dedicated hardware, which is
what keeps the silicon cheap.

**Nothing here is finished.** What exists is the groundwork: the research that
chose the parts, a firmware build that runs in an emulator, and a board design
pipeline proven end to end on a deliberately trivial board.

## What is here

| | |
|---|---|
| [`docs/research/`](docs/research/README.md) | Why the MCU, the power-board interface and the design toolchain are what they are |
| [`firmware/`](firmware/README.md) | Bare-metal STM32H743, GCC through Bazel, running under Renode in CI |
| [`hw/`](hw/README.md) | Boards designed as code: SKiDL, KiCad, ngspice, all gated in CI |

## The boards

### `hw/cpu1` — the control board

[`hw/cpu1`](hw/cpu1/README.md) is the real one: an STM32H743ZIT6 that
generates every hard real-time signal — PWM for two three-phase bridges, ADC
sampling synchronised to it, and a hardware trip that stops the outputs
without firmware — and hands all of it to a power board across two pin
headers. 130 × 110 mm, six layers, 272 parts.

![cpu1](hw/cpu1/review/top.png)

It is drawn, routed and checked: 203 checks, DRC clean with nothing
unconnected, gerbers for all six layers, and a build that reaches nothing over
the network. Its trip chain measures 40.5 ns against a 50 ns budget, and every
figure in that sum is derived from the netlist, the routed copper or a
datasheet page committed as an evidence crop.

**[`DESIGN-REVIEW.md`](hw/cpu1/DESIGN-REVIEW.md) is the account of what it is
and does**, including a section on what is assumed rather than measured. What
it has not had is a power board to talk to, or a reflow oven.

### `hw/led12` — the board that proved the pipeline

[`hw/led12`](hw/led12/README.md) is a 12 V LED board with no processor. Press a
button, four LEDs light. Its only purpose was to prove the pipeline before the
control board depended on it.

![led12](hw/led12/docs/board-top.png)

Neither board has been fabricated. What is proven is the pipeline.

## Getting started

Both halves are self-contained and pin everything they use by checksum.

```sh
make -C firmware          # build the firmware
make -C firmware sim      # run it under Renode

make -C hw tools          # pinned uv, Python and the design virtualenv
make -C hw check          # build the board and run the design checks
```

`hw/` also needs KiCad 9 and ngspice from your package manager;
[`hw/README.md`](hw/README.md) says why the version matters.
