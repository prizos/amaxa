# amaxa firmware

Bare-metal firmware for the STM32H743, built with GCC through Bazel, with a Makefile front end. Everything except `make` is downloaded and pinned by checksum. That covers the build tool, the cross compiler, ST's HAL and the Renode emulator, so a fresh Linux machine gets identical builds.

The first app, `hello_hw`, is a bring-up test for a motor/inverter controller on a **NUCLEO-H743ZI2**.

## Quick start

Needs Linux (x86_64 or aarch64) with `make`, `curl`, `tar` and `sha256sum`.

```sh
make              # fetch tools on first run, build hello_hw into out/
make sim          # run it in the Renode emulator, no board needed
make sim-check    # run it and assert how it behaved
make flash        # program a board over its ST-LINK
make monitor      # console, 115200 8N1 (PORT=/dev/ttyACM0)
make help         # all targets and variables
```

The first build downloads Bazel, the toolchain and the ST sources (about 250 MB), which takes a few minutes. Later builds are incremental and take seconds.

## What is pinned

| Component | Version | Where |
|---|---|---|
| Bazelisk | v1.29.0 | `Makefile` (sha256) |
| Bazel | 9.2.0 | `.bazelversion` |
| Arm GNU Toolchain (`arm-none-eabi-gcc`) | 15.2.rel1 (GCC 15.2.1), x86_64 and aarch64 hosts | `MODULE.bazel` (sha256) |
| rules_cc / platforms | 0.2.25 / 1.1.0 | `MODULE.bazel` (Bazel Central Registry) |
| Arm CMSIS-Core | 5.9.0 | `MODULE.bazel` (sha256) |
| ST CMSIS device H7 | v1.10.7 | `MODULE.bazel` (sha256) |
| ST STM32H7 HAL driver | v1.11.6 | `MODULE.bazel` (sha256) |
| Renode (only for `make sim`) | 1.17.0 portable | `Makefile` (sha256) |

To upgrade a component, change its URL and checksum. For a new GCC release, also update `GCC_VERSION` in `toolchain/arm_gnu_toolchain.BUILD`.

## Layout

```
firmware/
├── Makefile                  front end: build, flash, monitor, sim, clean
├── MODULE.bazel              toolchain + vendor source downloads
├── .bazelrc / .bazelversion  --config=stm32 selects the STM32H743 platform
├── platforms/                target platform: armv7e-mf, no OS
├── toolchain/                arm-none-eabi cc_toolchain (flags, multilib files)
├── tools/firmware.bzl        ELF -> .bin/.hex, disassembly, size report
├── third_party/              BUILD overlays for CMSIS and the ST HAL
├── bsp/nucleo_h743zi2/       HAL config, pin map, linker script
├── apps/hello_hw/            the bring-up app
└── renode/                   emulator board description and start script
```

Build outputs land in `out/`: `hello_hw.elf`, `.bin`, `.hex`, `.lst` (disassembly) and `.size.txt`.

Running Bazel directly works too:

```sh
.tools/bazelisk-v1.29.0-linux-* build --config=stm32 //apps/hello_hw:hello_hw   # or `bazel`, if installed
```

Build modes are selected with `make MODE=opt|dbg|fastbuild`: `-O2 -g`, `-Og -g3` and `-O1 -g`. App code builds with `-Wall -Wextra -Wshadow -Werror`.

## hello_hw

It exercises the parts of the chip a motor/inverter controller depends on:

- **Clock tree:** the 8 MHz ST-LINK reference through PLL1 gives 400 MHz. Timers run at 200 MHz.
- **Three-phase PWM on TIM1:**
  - 20 kHz, centre-aligned, 50 Hz sine modulation
  - complementary outputs with 1 µs hardware dead-time
  - active-low break input that latches all outputs off until re-armed
- **20 kHz control-loop interrupt**, with execution time, period jitter and overrun counts measured by the DWT cycle counter.
- **ADC3** reads the die temperature and VDDA, using the internal reference and the factory calibration.
- **Safety chain:**
  - independent watchdog, with reset cause reported at boot
  - core lockup and flash/RAM double-ECC errors routed in hardware to the TIM1 break
- **Board I/O:** LEDs, a button interrupt, and a console on the ST-LINK virtual COM port.

### NUCLEO-H743ZI2 pins

| Signal | Pin | Notes |
|---|---|---|
| Phase A high / low | PE9 / PE8 | TIM1_CH1 / CH1N |
| Phase B high / low | PE11 / PE10 | TIM1_CH2 / CH2N |
| Phase C high / low | PE13 / PE12 | TIM1_CH3 / CH3N |
| Break input | PE15 | active low, internal pull-up. Ground it to trip |
| Console | PD8 / PD9 | USART3 → ST-LINK VCP |
| LD1 green | PB0 | fast blink: PWM on; slow blink: PWM off |
| LD2 yellow | PE1 | modulation above 0 % |
| LD3 red | PB14 | outputs off (break) |
| B1 button | PC13 | cycles modulation 0 / 30 / 60 / 90 % |

### Console commands

| Key | Action |
|---|---|
| `?` | help |
| `s` | status line now (one is printed every second anyway) |
| `+` / `-` | modulation ±10 % |
| `b` | software break: outputs go to their safe (low) state |
| `r` | re-arm after a break (refused while PE15 is still low) |
| `w` | stop feeding the watchdog → IWDG reset after 2 s |
| `l` | fault inside HardFault → core lockup → TIM1 break → IWDG reset |

### What to check on a real board
1. **Boot:** the banner shows 400 MHz SYSCLK, `rev V`, the unique ID, and `pwm TIM1 3-phase ... DTG 0xa4`.
2. **PWM on a scope:** at 0 % modulation, PE9 and PE8 are complementary 50 % squares at 20 kHz, with about 1 µs where both are low. Press B1 and the duty cycle swings sinusoidally at 50 Hz. An RC low-pass on PE9 shows the sine.
3. **Status line:** `isr` reads 20000/s. `max` is the handler time in µs, and `jitter` is the period error in CPU cycles around 20000.
4. **Break:** ground PE15. All six outputs go low within tens of nanoseconds, LD3 lights and `breaks` increments. Release it and press `r`.
5. **Watchdog:** press `w` and the chip resets within 2 s. The next banner says `reset cause independent watchdog (IWDG1)`.
6. **Lockup:** press `l`. The outputs drop straight away (hardware break), then the watchdog resets the chip.

These checks are what the firmware is written to do. It has only run in the emulator so far; nobody has confirmed them on a board yet.

## Emulation (`make sim`)

`make sim` builds the app and boots the ELF in Renode 1.17.0 on its Nucleo-144 H7 model. It runs for `SIM_SECONDS` of virtual time (default 5), types `SIM_KEYS` into the console, and prints the console output:

```sh
make sim SIM_SECONDS=3 SIM_KEYS="+ + s b s w"
```

On this setup that run shows the banner and status lines, the replies to `+`, `s` and `b`, and then `w` starving the watchdog. Renode's IWDG model resets the machine and the firmware boots again. `l` goes through HardFault into lockup and is also recovered by the watchdog.

### `make sim-check`, and what it is for

`make sim` prints a console; `make sim-check` reads one and holds it to what
the safety story claims. CI built both board support packages and stopped
there, so every property the hardware is designed around - "an unprogrammed
board is inert", the trip latch, the buffers - was firmware behaviour that
nothing checked, on a repository where the board next door carries 188 derived
checks.

It asserts that the firmware got far enough to configure TIM1 as a three-phase
centre-aligned timer with a dead-time, that the main loop reported more than
once, that the break input sits where its pull-up puts it, and - the one that
matters - that **the outputs never drove without being asked**. Re-arming is
not asking: `r` on the console re-arms after a break and the outputs stay off.

It is a smoke test and not a proof. Renode models the STM32, not the board
around it, so what it can see is the firmware's own account of itself: the
timer it set up, whether it is driving, what it believes the break input is
doing. It cannot see a buffer, a latch, or a gate driver.

### What the Renode model covers

| Covered | Not modelled (the firmware output reflects it) |
|---|---|
| Boot, SystemInit, newlib, HAL init | TIM1 main-output enable and break: status always shows `pwm OFF`, and `r` is refused |
| Clock tree (reports 400 MHz) | Actual PWM waveforms and dead-time |
| Console input and output | RCC reset-cause flags: always `power-on` |
| GPIO, LEDs, button interrupt | DBGMCU ID register: `dev 0x000 rev ?` |
| TIM1 update interrupt (control-loop path runs) | PWR supply-config register: clock step reports `(-1)` |
| Independent watchdog resets | ADC3: replaced by a stub, because Renode 1.17.0's H7 ADC model aborts the emulator when VREFINT is sampled |
| HardFault and lockup recovery | GPIO pull-ups: the script holds PE15 high; DWT cycle counts, so jitter numbers are meaningless |

That matches how emulation is used on this project: it checks firmware logic, boot and reset behaviour and console I/O, while PWM timing and analog behaviour are covered by physics simulation and real hardware. Each Renode workaround is commented in `renode/nucleo_h743zi2.repl` and `renode/nucleo_h743zi2.resc`.

## Continuous integration

`.github/workflows/firmware.yml` runs on every push and pull request that touches `firmware/`. It can also be started by hand from the Actions tab. On an `ubuntu-24.04` runner it:

1. Restores cached downloads (Bazelisk, the toolchain, vendor sources) and Bazel's action cache.
2. Runs `make build MODE=dbg`, then `make build MODE=opt`. Warnings are errors, so both builds must be clean.
3. Adds the release size report to the job summary.
4. Uploads `hello_hw.elf/.bin/.hex` as a build artifact, kept for 14 days.

CI points Bazel's caches at those directories through `user.bazelrc`, which `.bazelrc` imports if present. You can use the same file locally, for example for a remote cache; git ignores it.

## Adding things

- **Another app:** create `apps/<name>/BUILD.bazel` modelled on `apps/hello_hw`, with a `cc_binary` that depends on `//bsp/nucleo_h743zi2:bsp` and passes the linker script, plus a `firmware_image`. Build it with `make APP=<name>`.
- **Another H7 board:**
  - Copy `bsp/nucleo_h743zi2`.
  - Change the `STM32H743xx` define, the HSE value in `stm32h7xx_hal_conf.h`, the memory map in the linker script, and the startup file in `third_party/cmsis_device_h7.BUILD`.
- **Another Cortex-M core:**
  - Add a platform with the right CPU constraint.
  - Set the `cpu`/`fpu_flags` of the toolchain config.
  - Change `MULTILIB` in `toolchain/arm_gnu_toolchain.BUILD` to the matching library directory, e.g. `thumb/v7e-m+fp/hard` for a Cortex-M4F.

## Licences of fetched sources

CMSIS-Core and ST's CMSIS device files are Apache-2.0. The ST HAL is BSD-3-Clause. `bsp/nucleo_h743zi2/stm32h7xx_hal_conf.h` is derived from ST's HAL configuration template (BSD-3-Clause) and keeps its header.
