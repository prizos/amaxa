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

## The board so far

[`hw/led12`](hw/led12/README.md) is a 12 V LED board with no processor. Press a
button, four LEDs light. Its only purpose is to prove the pipeline before the
control board depends on it.

![led12](hw/led12/docs/board-top.png)

It has never been fabricated. What is proven is the pipeline, not the board.

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
