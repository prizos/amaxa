# amaxa

A mechatronics driver board for motors and inverters — small motors, servos,
compressors, and up through high-power drives.

The architecture is one **digital control board** that generates every hard
real-time signal, soldered onto **one analog power board** at a time. There are
N power-board types, from a few tens of milliamps to hundreds of amps, AC or
DC; the control board is the same in each case. It does the control in real-time
software on a single fast Arm core rather than in dedicated hardware, which is
what keeps the silicon cheap.

Nothing here is finished. What exists is the groundwork: the research that chose
the parts, a firmware build that runs in an emulator, and a board design
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

It is worth the detour because of what the gates caught on something this
simple: a 6.3 V capacitor on a 12 V rail, a FET whose gate rating was exceeded
in normal operation, series resistors dissipating 104 % of their rating, a
regulator rated below the voltage its own protection clamps at, and a TVS fitted
backwards. Five defects, five different tiers of checking, on a board with
twenty-eight parts.

Each gate has also been made to fail on purpose at least once. A gate that has
never failed is not a gate.

## The principle that has cost the most to learn

**Do not let a tool's output format become your internal interface.**

The hardware pipeline was built on atopile, whose authors abandoned the
open-source project partway through — no public commits since March 2026, every
service except telemetry switched off, and a successor that is a sign-in-only
browser product. Moving to SKiDL took six steps and produced an identical board,
to the coordinate and to the simulated digit, because the work that mattered —
placement, routing, checks, simulation — was never written against atopile's
output in the first place. The one place it was, we replaced with a schema we
own.

A build here reaches nothing over the network. No parts service, no registry, no
account. `make tools` fetches a pinned toolchain; after that, nothing.

## Getting started

Both halves are self-contained and pin everything they use by checksum.

```sh
make -C firmware          # build the firmware
make -C firmware sim      # run it under Renode

make -C hw tools          # pinned uv, Python and the design virtualenv
make -C hw outputs        # build the board, check it, simulate it, render it
```

`hw/` also needs KiCad 9 and ngspice from your package manager; `hw/README.md`
says why the version matters.
