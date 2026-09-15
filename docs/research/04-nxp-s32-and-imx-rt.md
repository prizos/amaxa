# NXP S32K3, S32K39x and related NXP parts

**Status:** evaluated in rounds 1–3. The S32K3 was the user's original reference. It is now mostly outside the cheap, fast Arm direction because of cost and a slower core, but it remains the automotive-grade (ASIL D) option. The cheap NXP picks, i.MX RT1062 and RT1021, are in [02](02-cheap-fast-arm-mcus.md).

## S32K3 general-purpose lineup
Source: S32K3xx Data Sheet Rev. 14 (2026-04-10), https://www.nxp.com/docs/en/data-sheet/S32K3xx.pdf

**Common to all:** Cortex-M7, AEC-Q100, −40 to 125 °C, HSE_B security engine, 12-bit SAR ADCs, 16-bit eMIOS timers (24 channels per instance), up to 2 LCUs, BCTU (triggers ADC conversions from timers), all CAN ports CAN FD, Ethernet with AVB/TSN.

| Part | Cores @ MHz | Flash / RAM | Ethernet | CAN FD | ADCs | ASIL |
|---|---|---|---|---|---|---|
| S32K310 | 1× M7 @120 | 512K / 112K | – | 3 | 2 | B |
| S32K311 | 1× @120 | 1M / 128K | – | 3 | 2 | B |
| S32K312 | 1× @120 | 2M / 192K | – | 6 | 2 | B |
| S32K322 | 2× @160 | 2M / 256K | 100M | 4 | 2 | B |
| S32K341 / K342 | 1× lockstep @160 | 1M or 2M / 256K | 100M | 4 | 2 | D |
| S32K314 / K324 | 1× or 2× @160 | 4M / 512K | 100M | 6 | 3 | B |
| **S32K344** | 1× lockstep @160 | 4M / 512K | 100M | 6 | 3 | D |
| S32K328 / K338 | 2× or 3× @240 | 8M / 1152K | 1G | 8 | 3 | B |
| S32K348 / K358 / K356 | lockstep, or lockstep + 1, @240 | 8M or 6M / 1152K | 1G | 8 | 3 | D |
| **S32K388** | multi-core with lockstep @320 | 8M / 1152K | 1 or 2× 1G | 8 | 3 | D |
| S32K389 | same as K388 | 12M / 2304K | 1 or 2× 1G | 12 | 3 | D |

- **PWM:** there is no FlexPWM on the general-purpose parts. PWM comes from eMIOS, with the LCU adding complementary outputs and dead-time. There is no high-resolution PWM.
- **Comparators:** at most 3, with 8-bit DACs.
- **Ethernet:** every derivative has "no Ethernet" ordering variants.
- **Motor use:** fine for motors at normal switching frequencies. Too coarse for GaN-class switching.
- **Discrepancy:** SEGGER lists 14 MB of code flash on the S32K389, where NXP says 12 MB.

## S32K39x / S32K37x / S32K36x (motor-control variants)
These are shipping ("Active") parts. Sources: [product page](https://www.nxp.com/products/S32K39-37-36), [AN14301](https://www.nxp.com/docs/en/application-note/AN14301.pdf), [S32K396 data sheet Rev. 5](https://www.nxp.com/docs/en/data-sheet/S32K396.pdf) (June 2026).

- **Cores:** 4× Cortex-M7 at 320 MHz, configured as 2 lockstep pairs or 1 lockstep pair + 2 split cores. Plus a CoolFlux DSP for sigma-delta post-processing.
- **PWM:** 2× eFlexPWM with NanoEdge high-resolution edges, **195 ps typical** step. The "312 ps" figure in some sources is from older Kinetis parts.
  - The S32K396 has 16 NanoEdge outputs (8 pairs), plus 64 eTPU and 24 eMIOS channels at normal resolution.
  - Sources disagree on eFlexPWM channel count per module: 8 in AN14301, 12 on the product page.
- **eTPU:** 2 engines at 320 MHz (64 channels) on the S32K39x only. The S32K37x has none.
- **ADCs:** 7 SAR ADCs (12-bit effective [U], up to 69 inputs, 7 independent sample-and-holds), 4 sigma-delta ADCs, 2× 10-bit sine generators for resolver excitation. The S32K36x has fewer ADCs.
- **Comparators:** only 2 on-chip, with 8-bit DACs.
- **Memory:** 4 or 6 MB flash, 800 KB RAM. Packages: 289 MAPBGA, 176 LQFP-EP.
- **Comms:** 1× 10/100 Ethernet with TSN (no Gigabit), 6 CAN FD, HSE_B.
- **Positioning:** NXP's training deck says it can drive "one 6-phase or two 3-phase motors over 200 kHz control loops". The S32K36x is positioned for a single traction motor.

## Other NXP parts found

| Part | Summary | Status |
|---|---|---|
| **i.MX RT1180** | M7 @800 MHz + M33 @300 MHz, **integrated EtherCAT slave controller**, Gigabit TSN switch, 16-bit ADCs, PWM, delta-sigma demodulators, −40 to 125 °C. Industrial grade, not ASIL; external flash. Reference servo design with EtherCAT + dual PMSM ([App Code Hub](https://github.com/nxp-appcodehub/rd-motion-control-slave-servo-mimxrt1180)); [AN14155](https://www.nxp.com/docs/en/application-note/AN14155.pdf) covers TwinCAT | Active |
| MCX E31 | Industrial S32K3-like part: M7 @160 MHz, 4 MB flash, 10/100 TSN, 6 CAN FD, motor-control subsystem, SIL2 targeted ([fact sheet](https://www.nxp.com/docs/en/fact-sheet/MCXE31FS.pdf)). Zephyr board `frdm_mcxe31b` | Active |
| S32K5 | M7 + R52 cores at 200–800 MHz, NPU, up to 41 MB MRAM, 2.5G/1G/100M/10BASE-T1S switch, CAN-XL, HSE2. Synopsys VDK confirmed. Zephyr board `s32k5xxcvb` | Pre-production (sampling since Q3 2025) |
| S32Z2 / S32E2 | Real-time processors | Not researched in depth |

## Development boards (prices found 2026-09-15)

| Board | Price | Notes |
|---|---|---|
| FRDM-A-S32K344 | $60 (NXP) | Arduino form factor |
| S32K3X4EVB-T172 | $395 (NXP); $470 DigiKey, 52-week lead | |
| MR-CANHUBK344 | not checked | 6 CAN FD, 100BASE-T1; Zephyr `mr_canhubk3` |
| S32K388EVB-Q289 | $640 (NXP) | 2× Gigabit Ethernet |
| S32K396-BGA-DC1 | $1,439 (DigiKey), 39-week lead | |
| MCSPTR2AK396 motor kit | $1,850 (NXP); $2,202 (DigiKey), restock Jan 2027 | Inverter, 95 W resolver PMSM, 24 V |
| S32X-MB | not checked | Adds a second 3-phase connector |
| XIN1-MB-S32X, EV-POWEREVBHD2 (800 V SiC inverter) | – | Pre-production |
| FRDM-IMXRT1186 | $85 (NXP) | 2 EtherCAT/TSN ports |

## Software
- **Real-Time Drivers (RTD):** an AUTOSAR R21-11 MCAL that also works without AUTOSAR. Version 6.0.0 QLP01 released June 2025.
- **Motor control and tooling:** AMMCLib/RTCESL motor-control libraries, FreeMASTER/MCAT tuning, and the MATLAB Model-Based Design Toolbox for S32K3 v1.8.0 (December 2025, covers the S32K39x, about 130 examples).
- **Zephyr:** upstream support only for the s32k344.

## Emulation summary
See [03](03-emulation.md).
- **S32K388:** Renode models it, but the flash controller, HSE, ADC, LCU and BCTU are placeholders.
- **S32K344 and S32K39x:** no Renode platform yet. Start from the S32K388 platform.
- **QEMU:** only student forks, which aren't usable.
- **Synopsys VDK:** S32K3 coverage unconfirmed.

## Round-3 assessment (sized against the superseded combined spec)
- **S32K396:** the most automotive-native pick, but only 8 high-res pairs and 2 comparators, and expensive boards with long leads.
- **General-purpose S32K3:** enough for motors at normal switching frequencies (round 4). Needs checking: quadrature encoder and resolver support [U].
