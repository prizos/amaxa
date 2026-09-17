# STM32H743ZITx — pin data

What each pin of the STM32H743ZIT6 (LQFP-144) can do, and the alternate-function
number that selects it. `tools/stm32.py` reads these; the pin-map checks for any
board built on this part are only as good as they are.

| File | What it is |
|---|---|
| `STM32H743ZITx.xml` | Every pin: its position, its type, and the signals it can carry |
| `GPIO-STM32H747_gpio_v1_0_Modes.xml` | The `GPIO_AFn_*` value that selects each signal on each pin. The H743 shares this GPIO IP with the H747 — the MCU file names it |
| `LICENSE` | BSD 3-Clause, STMicroelectronics |

## Where it came from

[STMicroelectronics/STM32_open_pin_data](https://github.com/STMicroelectronics/STM32_open_pin_data),
commit `7d1f1514ed5583ec5007ad91236b4e1d377295b1`, fetched 2026-09-17. It is the
data STM32CubeMX is built on.

| File | Upstream path | sha256 |
|---|---|---|
| `STM32H743ZITx.xml` | `mcu/STM32H743ZITx.xml` | `ac4c5375cf52cb170e7296442abd7ca7dc9f4926acc98ed2c735fa2b12ef2e68` |
| `GPIO-STM32H747_gpio_v1_0_Modes.xml` | `mcu/IP/GPIO-STM32H747_gpio_v1_0_Modes.xml` | `49f51ae2508a11df6b385b86ed21172ea43478c4d314314db465e0f8d278c246` |
| `LICENSE` | `LICENSE` | `2e80479026d27db007f8bdd190860e4b0452ca30d622ef4c04084b064418a096` |

Copied verbatim, not trimmed, so each file can be compared byte for byte against
upstream at that commit.

## Why it is vendored rather than fetched

A build reaches nothing over the network, and the pin checks run on every build.

## Why this and not only the KiCad symbol

KiCad's `MCU_ST_STM32H7:STM32H743ZITx` symbol lists the same functions per pin,
but carries **no alternate-function numbers**, and the firmware cannot configure
a pin without one. It is kept as a second source anyway: a check requires the
two to agree on every pin's position and function list. On the day this was
vendored they agreed on all 114 I/O pins, which is unsurprising — KiCad
generates its STM32 symbols from ST's data — so the check is a guard against
either changing underneath us, not a discovery.

## Updating it

Fetch the same two paths at a newer commit, record the commit and hashes here,
and run `make pins`. Every board on this part is re-checked against the new data.
