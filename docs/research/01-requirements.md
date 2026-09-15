# Requirements

## Project brief (current)
- **Product:** a mechatronics driver board for inverters and single- or three-phase motors. The range runs from small motors to servos to compressors, and potentially high-power stages.
- **Architecture:**
  - One digital control board design generates every hard real-time signal: PWM, sensor sampling in sync with the PWM, hardware fault trip, and the control loops.
  - Each built unit carries exactly **one** power board soldered directly onto the digital board.
  - Power boards are **purely analog**: MOSFETs/IGBTs, gate drivers, current and voltage sensing, analog amplifiers. They carry no MCU, ADC or other digital logic.
  - There are N power-board types (50 mA to 300 A, AC or DC). The digital board must cover the most demanding single type.
- **Silicon:** a cheap Arm MCU with a fast core. Most of the control runs in real-time software on a single core. Chinese parts are in scope.
- **Comms:** flexible. Any protocol is fine; EtherCAT was only an example.
- **Simulation:** firmware code, firmware updates, networking and system integration must run in an emulator or VM. PWM, ADC timing and fault paths do not need emulator fidelity, because they are simulated separately with physics models.

## How the brief changed (2026-09-15)

| Round | What the research assumed | Correction from the user |
|---|---|---|
| 1 | EtherCAT preferred; considered putting MCUs on the power boards | Any comms protocol is fine. Power boards are purely analog. |
| 2 | One board driving N power boards at once; emulator fidelity for PWM, ADC and fault paths | One power board per digital board. Emulate software only. |
| 3 | Sized for GaN at MHz, dual active bridges and multilevel inverters, which led to an FPGA SoC pick | This is a motor/inverter mechatronics board. |
| 4 | Automotive MCUs and evaluation boards costing $60–$2,200 | Cheap, fast Arm cores in single-core software, including Chinese parts. |

## Signal spec for a motor/inverter driver board
Power level changes the power board, not the digital board. A 300 A IGBT inverter and a small servo need the same set of signals.

| Signal group | Worst case across the power boards |
|---|---|
| PWM | 6 for a 3-phase bridge, +1 brake chopper, +2 for a compressor's PFC front end. Complementary pairs with hardware dead-time. Typically 4–20 kHz, where normal timer resolution is enough. |
| Current sensing | 2–3 phase currents sampled at the same instant, in sync with the PWM, plus PFC current. 12-bit. |
| Voltage and temperature | DC-link voltage; 3 phase voltages for sensorless start; AC line voltage; module, heatsink and motor temperatures |
| Servo feedback | Quadrature encoder, Hall sensors, resolver, RS-485 for serial absolute encoders (BiSS-C, EnDat) |
| Protection | Hardware over-current trip, DC-link over-voltage, gate-driver fault input, 2-channel Safe Torque Off, brake and pre-charge relay outputs |
| Control rates | Current loop 8–20 kHz; speed and position loops 1–4 kHz |

Right-sized counts for DC, single-phase AC and 3-phase motor boards switching up to ~50 kHz:
- 6–8 PWM outputs at normal resolution
- 6–8 fast analog inputs, 12-bit, with 2–3 sampled simultaneously in sync with the PWM
- ~4 slow analog inputs and 1 power-board ID input
- ~4 comparators (3 phase over-current + DC-link over-voltage) and 2 fault inputs

## Gate signals by power-board type

| Power board | Gate signals | Fast sense channels | Needs high-res PWM? |
|---|---|---|---|
| DC buck, one direction | 2 | inductor current, output voltage | only above ~100 kHz |
| H-bridge: brushed DC motor, bidirectional DC, single-phase AC | 4 | current, DC-link voltage, AC voltage | no |
| 3-phase motor or 3-phase AC | 6 (7 with a brake chopper) | 2–3 phase currents, DC-link voltage (+3 phase voltages for sensorless or grid sync) | no |
| High-current DC by interleaving (e.g., 4-phase 300 A buck) | 8 | 4 phase currents, input and output voltage | only at high frequency |
| Isolated DC/DC (dual active bridge) | 8 | transformer current, output current, 2 voltages | yes, at 100 kHz+ |
| 3-level inverter (high-voltage drives, grid) | 12 | 3 currents, 2 DC-link halves, 3 phase voltages | no |

- **Current doesn't add signals:** paralleled MOSFETs for 300 A share one gate signal.
- **Waveform doesn't add signals:** sine, square and DC outputs all come from varying the duty cycle on the same legs.

### Why a 3-phase bridge takes 6 PWM signals, not 3
- Each phase is a leg of two switches, high-side and low-side. Each switch needs its own gate signal.
- The two signals are complementary, with a short dead-time where both are off so the leg never shorts the supply.
- **Getting down to 3:** a gate driver can take one PWM input per leg and generate the complement and dead-time itself (e.g., IR2104, or TI DRV8323 in 3-input mode). The costs:
  - Dead-time is fixed on the power board, so firmware can't adjust or calibrate it.
  - The two switches in a leg can't be controlled independently. Some modes need that:
    - pre-charging bootstrap supplies
    - braking by turning all low sides on
    - leaving a phase floating in 6-step commutation (unless the driver has a per-leg enable)
    - diode emulation at light load in DC/DC
- **Recommendation:** route 2 signals per leg on the digital board. Power boards with single-input drivers just use one of each pair.

## What each spec means
- **High-resolution PWM.** A timer moves a PWM edge in whole ticks; a normal MCU timer ticks every ~5–20 ns.
  - At 20 kHz the period is 50 µs, so a 10 ns tick gives 5,000 duty steps (~12 bits). That's enough.
  - At 500 kHz the period is 2 µs, so the same tick gives 200 steps. On a 48 V input the output moves in ~0.24 V jumps, and the control loop hunts between them.
  - High-res PWM places edges to 100–300 ps. It only matters for high-frequency converters.
  - Rule of thumb: duty-cycle resolution should be at least as fine as the ADC's effective resolution on the regulated quantity, otherwise the loop limit-cycles.
- **Simultaneous sampling.** Motor-control maths assumes the phase currents were captured at the same instant.
  - At 20 kHz, ~1 µs alignment is fine.
  - 100 ns alignment only matters for fast SiC/GaN stages.
- **Resolution and rate.** 12-bit is standard for motors. 16-bit adds headroom for precise low-current boards. A 20 kHz motor needs ~20–40 kSPS per channel (1–2 samples per PWM period).
- **Slow analog.** Temperatures and supply rails, read every few milliseconds.
- **Comparators with programmable thresholds.** These are hardware over-current and over-voltage trips that cut the PWM in tens of nanoseconds.
  - A shorted switch survives only a few microseconds, too fast for firmware to react.
  - Thresholds are programmable because each power-board type scales its sensors differently. The digital board sets trip levels at boot from the board ID.
- **Fault inputs.** Signal lines from the power board's gate drivers (short-circuit or desaturation detection), over-temperature switches and supply monitors. Any of them disables the PWM in hardware.
- **ID inputs.** Each power-board type has a resistor divider that an ADC reads at boot, so firmware loads that type's settings. One input distinguishing 16 types is probably enough.

## Superseded: the combined worst case across all topologies
Round 3 combined every topology above, including multilevel inverters, dual active bridges and GaN switching up to 1 MHz:
- 16 PWM outputs, 12 or more high-res at 150–300 ps
- 12 fast analog inputs, 16-bit, ≥200 kSPS, aligned within 100 ns
- 8 slow analog inputs
- 8 comparators, 4 fault inputs, 2 ID inputs

That spec is **not** needed for motors and inverters. It is kept here only because files 04–06 were researched against it.
