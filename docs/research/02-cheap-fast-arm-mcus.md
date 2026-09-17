# Cheap, fast Arm MCUs (shortlist)

> **Superseded by a decision.** The project uses the **STM32H743ZIT6**, which
> this file ranks behind its two recommendations on unit price. See the decision
> in [README.md](README.md#decision). The research below is unchanged.

Every part here can run field-oriented motor control, a PFC front end and comms on a single core. The Cortex-M7 parts leave the most headroom for doing everything in software.

## Recommendation
- **Cheap, fast and already emulated: NXP i.MX RT1062.**
  - Cortex-M7 at 600 MHz, $7.97 each at 1,200 units.
  - Renode already models the RT1064, which is the same chip with flash inside the package.
- **Cheapest fast Arm, if we build the emulator model ourselves: GigaDevice GD32H759** (China).
  - Cortex-M7 at 600 MHz, with more motor and CAN hardware than the RT1062.
  - No Renode, QEMU or upstream Zephyr support yet.
- **What decides between them:** production volume. The GD32H759's per-unit saving has to pay back the one-time work of writing its emulator platform.

## Comparison

| Part | Core | Motor PWM / ADC | Comms | Emulation today | Price (DigiKey, 2026-09-15) |
|---|---|---|---|---|---|
| **NXP i.MX RT1062** | M7, 600 MHz | 4 motor PWM modules with fault inputs [U]; 2× 12-bit ADC [U] | 2× Ethernet, 3× CAN (1 FD) [U] | Renode RT1064 model (Ethernet, ADC, PWM; no CAN). Zephyr: yes | $13.04 (1); $7.97 (1,200). No stock; 240 due 2027-01-07 |
| **GigaDevice GD32H759** | M7, 600 MHz | 2 advanced timers + high-res timer; 2× 14-bit + 1× 12-bit ADC | 1× Ethernet, 3× CAN FD | None. Zephyr: no | Not verified (not on DigiKey or Findchips) |
| ST STM32H743 | M7, 480 MHz [U] | 2 advanced timers; 3× 16-bit ADC [U] | Ethernet, 2× CAN FD [U] | Renode: best (flash, CAN FD, Ethernet). Zephyr: yes | $16.67 (1) |
| ST STM32H723 | M7, 550 MHz [U] | 2 advanced timers; 3 ADCs [U] | Ethernet, CAN FD [U] | Renode: generic H7 model only. Zephyr: yes [U] | $13.76 (1) |
| NXP i.MX RT1021 | M7, 500 MHz | [U] | [U] | No Renode model (RT1064 model is a starting point) | $6.17 (420, marketplace); DAG5B $9.63 (1) |
| GigaDevice GD32F470 | M4F, 240 MHz | 2 advanced timers + high-res timer; 3× 12-bit ADC | Ethernet, 2× CAN 2.0B | Renode: none. Zephyr: yes | Not verified |
| Artery AT32F437 | M4F, 288 MHz | 3 advanced timers with dead-time; 3× 12-bit 5.33 MSPS ADC | Ethernet (IEEE 1588), 2× CAN 2.0B | None. Zephyr: no | Not verified (not on Findchips) |
| ST STM32F405 | M4F, 168 MHz [U] | 2 advanced timers; 3× 12-bit ADC [U] | 2× CAN 2.0, no Ethernet (F407 adds it) [U] | Renode: good. QEMU runs the CPU. Zephyr: yes | $12.50 (1) |
| ST STM32G474 | M4F, 170 MHz [U] | high-res timer (184 ps, 12 outputs), op-amps, comparators, 5 ADCs [U] | 3× CAN FD, no Ethernet [U] | Renode: none. Zephyr: yes [U] | $10.00 (1) |

- Rows marked [U] in the spec columns come from general knowledge; those datasheets weren't fetched this session.
- GigaDevice and Artery specs come from the vendor product pages.
- Emulator and Zephyr status for the GigaDevice and Artery rows was checked against the Renode and Zephyr repos (see [03](03-emulation.md)).

## Part details

### NXP i.MX RT1062 (leading candidate)
- **Core:** Cortex-M7 at 600 MHz.
- **Flash:** none inside the chip. It runs from external QSPI flash, which is cheap. The RT1064 is the same die with 4 MB of flash in the package.
- **Emulation:**
  - Renode's `imxrt1064` platform models Ethernet, ADC and eFlexPWM (compare interrupts only; dead-time not modelled).
  - It has no CAN model. Renode's `NXP_FlexCAN` model, written for the S32K3, is the likely starting point [U effort].
- **Software:** strong Zephyr support, including MCUboot and networking.
- **Price and availability:**
  - `MIMXRT1062DVL6B`: $13.04 at qty 1, $7.9746 at 1,200.
  - DigiKey had 0 in stock, with 240 expected on 2027-01-07. Check other distributors.

### GigaDevice GD32H759 (cheapest fast Arm)
Source: [GigaDevice GD32H759](https://www.gigadevice.com/product/mcu/high-performance-mcus/gd32h7xx-series/gd32h759)
- **Core and memory:** Cortex-M7 at 600 MHz. Flash 1,024 / 2,048 / 3,840 KB; SRAM 1,024 KB.
- **Timers:** 2× 16-bit advanced timers (complementary outputs, dead-time, break), 1× high-resolution timer (HRTM), 4× 32-bit and 12× 16-bit general-purpose timers.
- **ADCs:** 2× 14-bit (16 or 20 channels) and 1× 12-bit (12 or 17 channels).
- **Comms:** 3× CAN FD, 1× Ethernet, 2× USB 2.0 OTG (full-speed and high-speed).
- **Packages:** LQFP176 (121 I/O), BGA176 (134 I/O).
- **Temperature:** −40 to 85 °C; −40 to 125 °C on selected variants.
- **Not claimed:** no functional-safety or pin-compatibility claims on the page.
- **Emulation:** no Renode platform, no QEMU machine, and no upstream Zephyr board (GigaDevice's Zephyr boards are GD32F4/E1/E5/A5/L2/F3 class).
- **Sourcing:** through Chinese distributors. Not stocked by DigiKey.

### GigaDevice GD32F470
Source: [GigaDevice GD32F470](https://www.gigadevice.com/product/mcu/high-performance-mcus/gd32f4xx-series/gd32f470)
- **Core and memory:** Cortex-M4F at 240 MHz. Flash up to 3,072 KB; SRAM up to 768 KB.
- **Timers:** 2× 16-bit advanced timers (complementary, dead-time, break), 1× high-resolution timer, 2× 32-bit and 8× 16-bit general-purpose timers, 2× 16-bit capture/PWM timers.
- **ADCs:** 3× 12-bit (16–24 channels depending on package).
- **Comms:** 2× CAN 2.0B, Ethernet, USB FS+HS OTG, up to 8 U(S)ART, 6 SPI, 3 I2C.
- **Temperature and packages:** −40 to 85 °C. LQFP100/144, BGA100/176.
- **Emulation:** upstream Zephyr boards exist (`gd32f470i_eval`, `gd32f450i_eval`/`v_start`/`z_eval`). No Renode platform.

### Artery AT32F437
Source: [Artery AT32F437](https://www.arterychip.com/en/product/AT32F437.jsp)
- **Core and memory:** Cortex-M4F at 288 MHz. Flash 256–4,032 KB; SRAM 384 KB (configurable to 512 KB).
- **Timers:** 3× 16-bit advanced timers with dead-time; 2× 32-bit and 8× 16-bit general-purpose timers.
- **Analog:** 3× 12-bit 5.33 MSPS ADCs (up to 24 channels), 2× 12-bit DACs.
- **Comms:** 2× CAN 2.0B (no CAN FD), 10/100 Ethernet MAC with IEEE 1588, 2× USB FS OTG, 2× QSPI, SDRAM controller.
- **Temperature:** −40 to 105 °C.
- **Emulation:** no Renode platform and no Zephyr support (no Artery vendor directory upstream).

### ST STM32H743 / STM32H723
- **Emulation:** the best-emulated MCUs found.
  - Renode 1.17 models flash erase/program (so update flows run), CAN FD and Ethernet.
  - Zephyr CAN and PTP tests run in Renode.
  - The H743 has its own Renode platform file. The H723 would use the generic `stm32h7` platform [U fit].
- **Price:** the highest here per unit (qty-1 prices above).

### ST STM32F405 / STM32G474
- **STM32F405:** a proven cheap motor-control part (VESC and ODrive v3 use the F405 class [U]). Renode's `stm32f4` platform is mature. Its qty-1 price is high for its speed.
- **STM32G474:** a motor and digital-power MCU with rich analog. It has no Renode platform.

## Ruled out: too small for one board covering every power-board type

| Part | Why it's out |
|---|---|
| GigaDevice GD32M531 (announced 2026-03-10) | Cortex-M33 at 180 MHz, 128–256 KB flash, **32 KB SRAM**, no CAN or Ethernet listed. It does have strong motor hardware: 2 advanced timers for dual-motor FOC, hardware over-current shutdown, up to 5 simultaneous samples, 4 comparators. [Source](https://www.gigadevice.com/product/mcu/specific-mcus/gd32m531-series/gd32m531) |
| Artery AT32M416 | Cortex-M4 at 180 MHz, up to 128 KB flash, **16 KB SRAM**, 1 advanced timer (4 complementary pairs), 2× 12-bit 2.5 MSPS ADC, 2 comparators, 4 op-amps, 1× CAN FD, no Ethernet. [Source](https://www.arterychip.com/en/product/AT32M416.jsp) |

## Price verification notes
- **Qty 1 vs volume:** DigiKey single-unit prices are far above volume. The RT1062 drops 39% at 1,200 units.
- **Chinese parts:**
  - LCSC blocked automated lookups (`lcsc.com` renders prices with JavaScript; `wmsc.lcsc.com` and `so.szlcsc.com` returned access denied).
  - Findchips had no listings for GD32H759IMK6 or AT32F437VMT7, and timed out on GD32F470VIT6. OEMsecrets returned 403.
  - **To do:** check LCSC by hand for GD32H759IMK6, GD32F470VIT6, AT32F437VMT7, and the APM32F407 (Geehy, not researched).
- **Not researched:**
  - Geehy APM32, Nations N32, MindMotion MM32 (the Geehy product page URL wasn't found).
  - HPMicro and WCH were left out because their fast parts are RISC-V, not Arm.

## Sources
- DigiKey: [RT1062](https://www.digikey.com/en/products/result?keywords=MIMXRT1062DVL6B), [RT1021](https://www.digikey.com/en/products/result?keywords=MIMXRT1021DAG5A), [STM32H743](https://www.digikey.com/en/products/result?keywords=STM32H743VIT6), [STM32H723](https://www.digikey.com/en/products/result?keywords=STM32H723VGT6), [STM32F405](https://www.digikey.com/en/products/result?keywords=STM32F405RGT6), [STM32G474](https://www.digikey.com/en/products/result?keywords=STM32G474RET6)
- Renode platform list: https://github.com/renode/renode/tree/master/platforms/cpus
- Zephyr GigaDevice boards: https://github.com/zephyrproject-rtos/zephyr/tree/main/boards/gd
