# Other motor-control and automotive MCUs (TI, Infineon, Renesas, ST, Microchip)

**Status:** evaluated in rounds 1–3. Most are outside the cheap, fast Arm direction on cost, core type or missing emulation, but they record the high end of the market.

- **[U]** means the claim wasn't checked on a primary source.
- Resolution "bits" = log2(PWM period ÷ high-resolution step), using the typical step.

## High-resolution motor/power MCUs (round 3)

| | TI F29H85x | TI AM263Px (enhanced analog) | TI F28P65x | Microchip dsPIC33AK512MPS512 | Renesas RH850/U2B |
|---|---|---|---|---|---|
| High-res PWM | 36 outputs, 75 ps typ / 152 ps max | up to 64 outputs, 100 ps typ / 180 ps max (pin muxing limits count) | 36 outputs, 150 ps typ / 310 ps max | 16 at 78 ps + 8 at 1.25 ns | 16 channels at 156 ps, plus GTM and 3× TSG3 motor timers |
| Bits at 20 / 100 / 500 kHz | 19.3 / 17.0 / 14.7 | 18.9 / 16.6 / 14.3 | 18.3 / 16.0 / 13.7 | 19.3 / 17.0 / 14.6 | 18.3 / 16.0 / 13.6 |
| Simultaneous sample-and-holds | 5 (2× 16-bit 1.19 MSPS, 3× 12-bit 3.92 MSPS); 80 inputs | 7 (12-bit, 3–4 MSPS); ~38 inputs | 3 (16/12-bit); 40 inputs | 5 (12-bit, 40 MSPS); 26 inputs | 3–5 SAR + 4–10 ΔΣ, 2 resolver converters |
| Hardware trip | 24 comparators (12-bit DACs), ~85 ns; fault pin ≤30 ns | 20 comparator modules; fault pin ≤30 ns | 11 comparator modules, ≤60 ns + routing | 8 comparators at 5 ns; fault pin 15 ns typ | 4–10 comparators at 200 ns; shut-off pin ≤50 ns |
| Programmable logic | CLB (6 tiles) | PRU-ICSS | CLB, CLA | 10 configurable logic cells | GTM MCS cores [U] |
| Compute | 3× C29x @200 MHz, lockstep | 4× Cortex-R5F @400 MHz | 2× C28x + CLA @200 MHz | 1 core @200 MHz, double-precision FPU | up to 6× G4MH @400 MHz |
| Grade / safety | AEC-Q100 G1; ASIL D / SIL 3 targeted, certification "planned" | AEC-Q100 (-Q1); ASIL D targeted | -Q1 parts; ASIL B / SIL 2 certified | AEC-Q100 G0/1; ASIL B / SIL 2 targeted | Tj 160 °C; ASIL D |
| Comms | 6 CAN FD, EtherCAT slave, FSI; no Ethernet MAC | Gigabit 3-port TSN switch, 8 CAN FD | USB, 2 CAN FD, EtherCAT slave | 2 CAN FD | 100M/1G TSN Ethernet, 8–10 CAN FD |
| Dev boards (DigiKey) | LaunchPad $36 (out of stock until Dec 2026); SOM-EVM $245 | LP-AM263P $136; controlCARD $249 | LaunchPad $66; controlCARD $209 | Curiosity EV74H48A $78 + DIM EV80L65A $14 | not stocked by distributors |
| Emulation (software side) | **1**: proprietary core, no emulator | **2**: only generic R5F cores exist | **1** | **1** | **2** (VDK coverage unconfirmed) |

Sources:
- [F29H85x data sheet](https://www.ti.com/lit/ds/symlink/f29h850tu.pdf) (Sep 2026 revision)
- [AM263P4 data sheet](https://www.ti.com/lit/ds/symlink/am263p4.pdf)
- [F28P65x data sheet](https://www.ti.com/lit/ds/symlink/tms320f28p650dk.pdf)
- [dsPIC33AK512MPS512 data sheet](https://ww1.microchip.com/downloads/aemDocuments/documents/MCU16/ProductDocuments/DataSheets/dsPIC33AK512MPS512-Family-Data-Sheet-DS70005591.pdf)
- [RH850/U2B data sheet](https://www.renesas.com/en/document/dst/rh850u2b-datasheet?r=1539266) (Rev. 1.10, Aug 2026)

### Notes per part
- **TI F29H85x:**
  - Firmware update: HSM with secure boot and A/B firmware swap.
  - SDFM (16 channels) needs external modulators, which conflicts with analog-only power boards.
  - The F29H85X-SOM-EVM is a 360-pin module with design files, and an adapter fits controlCARD baseboards.
  - The cheaper F29P32x has 18 high-res PWM and no 16-bit ADCs.
- **TI AM263Px:**
  - You must pick the enhanced-analog part; the standard part has 16 EPWM, 3 ADCs and 12 comparators.
  - ADC sample-and-holds 6 and 7 are the resolver ADCs, which exist only in the ZCZ-S/F packages.
  - ADCs are 12-bit only.
  - AM261x is a cheaper step-down: 2× R5F @500 MHz, 20 PWM, 3 ADCs.
- **TI F28P65x:** a mature predecessor of the F29H85x. TMDSCNCD28P65X controlCARD in stock.
- **Microchip dsPIC33AK:**
  - From $1.50 in volume ([press release](https://www.globenewswire.com/news-release/2025/06/18/3101327/0/en/Microchip-Enhances-Digital-Signal-Controller-Lineup-with-Industry-Leading-PWM-Resolution-and-ADC-Speed.html)).
  - Dual-panel flash with live update, immutable root of trust, 3 op-amps at 100 MHz.
  - Too few PWM outputs and sample-and-holds for large boards, and a single core.
- **Renesas RH850/U2B:**
  - Variants U2B24 / U2B10 / U2B6 have 6 / 4 / 3 cores. 156 ps comes from a 200 MHz high-res PWM clock.
  - Strong traction-inverter silicon, but boards are only available through Renesas.

## Other TI parts (round 1)
- **F28388D:**
  - 2× C28x + 2× CLA + Cortex-M4.
  - 32 PWM (16 high-res), 4 ADCs (16-bit 1.1 MSPS or 12-bit 3.5 MSPS), 8 SDFM channels.
  - Integrated EtherCAT slave controller on the M4. ASIL B / SIL 2. ~$12.60.
- **F28P55x:** 24 PWM, NPU, no EtherCAT.
- **AM243x (AM2434):**
  - 4× R5F @800 MHz + M4F, 18 SDFM, 2× PRU-ICSS.
  - SIL 3 systematic / SIL 2 hardware (TÜV SÜD).
  - Upstream Zephyr boards `am243x_evm` and `lp_am243x`.
- **PIL tooling:** PLECS C2000 support package v2.3.3 (F2838x, F29H85x). MathWorks C2000 Blockset.

## Infineon
- **AURIX TC4x** ([overview](https://www.infineon.com/assets/row/public/documents/10/156/infineon-tc4x-overview-productpresentation-en.pdf)):
  - Up to 6 cores @500 MHz, eGTM, ASIL D, full A/B swap.
  - The TMADC sends results and boundary flags straight to the timers.
  - High-res PWM step and channel counts are only in the NDA data sheet [U]. The eGTM feature list says "no HRPWM on TC4Dx, TC4Zx".
  - Ethernet up to 5 Gb, CAN-XL, 10BASE-T1S.
- **AURIX TC3xx (TC387/TC397):**
  - GTM timers with programmable MCS cores, but no high-res PWM (~10 ns steps [U]).
  - Kits: KIT_A2G_TC387 TFT $300, TriBoard $974.
- **XMC4800:**
  - Cortex-M4 @144 MHz, integrated Beckhoff EtherCAT slave controller.
  - CCU8/CCU4 timers (no high-res), 4× 12-bit ADCs, 4 delta-sigma demodulator modules.
  - No ASIL; ~$10 [U]. Relax EtherCAT Kit.
- **PSOC Control C3:** Cortex-M33 @180 MHz, high-res PWM <80 ps, 12-bit 12 MSPS ADC with 16-channel parallel sampling, SIL 2 libraries, <$5 [U]. No emulator.
- **XMC7000:** RT-Labs protocol package includes an EtherCAT master only.
- **Emulation:** Synopsys VDK for TC4xx (commercial). Open QEMU is a memory map only. A Zephyr TriCore PR (#107516) is open.

## Renesas
- **RZ/T2M:**
  - 2× Cortex-R52 @800 MHz, integrated Beckhoff EtherCAT slave controller, 3-port Gigabit TSN switch, 2× CAN FD.
  - 2× 12-bit ADC, 6 ΔΣ channels, "supports up to SIL 3".
  - $11.25–16.77 ([Renesas](https://www.renesas.com/en/products/rz-t2m)). RSK kit ~$440 [U].
  - Renode platform with CPU/GIC/UART/GPIO only. Zephyr `rzt2m_rsk`.
- **RZ/T2L, RZ/N2L:** single R52, integrated EtherCAT slave controller (N2L adds a TSN switch). Zephyr `rzt2l_rsk`, `rzn2l_rsk`.
- **RZ/T2H:** 4× A55 + 2× R52 @1 GHz, 63 PWM pins, 30 ΔΣ channels, EtherCAT master and slave, $40–44.
- **RA8T2:**
  - Cortex-M85 @1 GHz (+ M33), 52 ps high-res GPT [U from CNX], 2× 16-bit ADC, 2× Gigabit TSN, optional EtherCAT slave controller.
  - $16.80–24.59. MCK-RA8T2 $625.
- **RA6T2:** 16-bit 6.25 MSPS ADC, no EtherCAT. MathWorks support package (May 2026).
- **Emulation:** the Renode RA6M5/RA8M1 models have GPT, AGT, SCI and IIC only (no ADC, Ethernet or CAN).

## ST
- **Stellar SR5E1:** 2× Cortex-M7 @300 MHz, 24-channel HRTIM at ~104 ps [U], ASIL D, HSM. SR5E1-EVBE7000P $719, 99-week lead. Synopsys VDK exists for Stellar.
- **STM32G474:** 12 HRTIM outputs at 184 ps ([data sheet](https://www.st.com/resource/en/datasheet/stm32g474cb.pdf)). B-G474E-DPOW1 board $78.
- **STM32H7:**
  - HRTIM lacks the fine delay line [U], so it was dropped for GaN-class switching.
  - Fine for motors, and the best-emulated MCU (see [02](02-cheap-fast-arm-mcus.md), [03](03-emulation.md)).
  - No ST EtherCAT reference design.

## Microchip
- **LAN9255:** SAM E53 (Cortex-M4F) + LAN9253 EtherCAT slave controller in one package. Harmony 3 EtherCAT (SSC).
- **SAM E70:** Cortex-M7 @300 MHz. Renode model has UART and GEM Ethernet only.
- **PLECS PIL:** dsPIC33F. MPLAB Device Blocks for Simulink.

## Round-1 ranking (under the superseded EtherCAT-weighted brief)
1. TI AM263Px
2. TI F29H85x
3. Renesas RZ/T2M
4. Honourable mention: AURIX TC4x + ET1150
