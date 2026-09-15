# Emulation and VM support

## What needs emulating
- **In the emulator or VM:** firmware code, the boot and update flow, networking, and system integration across several boards.
- **Not in the emulator:** PWM, ADC timing and fault paths. Those are simulated with physics models. The emulator only needs peripheral models good enough for the drivers to run, plus a way to exchange values with the physics sim.

## Renode (open source, MIT licence)
Renode 1.17.0 was released 2026-09-06. Platform files were checked through the GitHub API on 2026-09-15 ([list](https://github.com/renode/renode/tree/master/platforms/cpus)).

| Vendor | Platforms present |
|---|---|
| ST | stm32f0, f042, f072, f103, **f4**, f412, f429, **f746**, f777, g0, **h7**, **h743**, h747, **h753**, l071, l072, l151, l552, w108, wba52 |
| NXP | **imxrt1064**, imxrt500, mimxrt798s, nxp-k6xf, **nxp-s32k388**, s32k118, vybrid, nxp-mimx8ml |
| Renesas | r7fa2e1a9, r7fa2l1a, r7fa4m1a, r7fa6m5b (RA6M5), r7fa8m1a (RA8M1), rz_g2l, rz_t2m, da14592 |
| Microchip | sam_e70, sam4s, atsamd21, atsamd51, polarfire-soc |
| AMD | zynq-7000, zynqmp |
| Generic cores | cortex-a9, cortex-a53, cortex-a78, cortex-r8, cortex-r52 |

**Not present:** GigaDevice GD32 (Arm), Artery AT32, Geehy APM32, STM32G4, STM32H5, i.MX RT1060/1170/1180, NXP MCX, TI (all), Infineon XMC/AURIX.

### How complete the models are
- **NXP S32K388:**
  - Modelled: 4× Cortex-M7, 8× FlexCAN, 2× GMAC Ethernet, LPUART/LPSPI/LPI2C, timers, DMA.
  - Placeholders: the C40 flash controller and HSE security-module mailboxes, so MCUboot or UDS reflashing fails without new models. Also the ADC, LCU and BCTU.
  - Partial: eMIOS. The FlexCAN FD-enable bit is a placeholder.
  - A two-machine FlexCAN test exists on the MR-CANHUBK3 board ([test](https://github.com/renode/renode/blob/master/tests/peripherals/NXP_FlexCAN.robot)).
- **STM32H7:**
  - Flash erase/program is modelled and tested since 1.16.1; bank swap is a placeholder.
  - FDCAN and Ethernet are modelled, and Zephyr PTP and CAN tests run.
  - The 1.17 RAMN 4-ECU UDS test fails on WriteDataByIdentifier because that board's flash persistence isn't modelled. Flash models decide whether update flows can run at all.
- **STM32 timers:** drive GPIO in PWM modes 1/2. Dead-time, break and complementary outputs are unimplemented.
- **i.MX RT1064:** Ethernet, ADC, eFlexPWM (compare interrupts only). No CAN.
- **Renesas RZ/T2M:** only the R52 cores, GIC, SCI UART and GPIO.
- **PolarFire SoC:** boots HSS, U-Boot and Linux in CI. The system-services model only handles serial number and SPI copy.
- **ZynqMP:** boots ATF, U-Boot and Linux with a Kria K26 device tree, but skips FSBL and PMU firmware. Neither Zynq platform has a CAN model.

### Integration features
- **External Control API:** ADC, CAN, GPIO, SPI, system bus, `RunFor`, `GetTime`. This is the link for a lock-stepped physics sim ([client](https://github.com/renode/renode/tree/master/tools/external_control_client)).
- **Networking:** SocketCAN bridge (Linux only, handles FD/XL frames), host TAP networking, multi-machine switches and CAN hubs.
- **Co-simulation:** SystemC TLM and Verilator (extended in 1.17).
- **CI:** Robot Framework tests, [Docker images](https://hub.docker.com/r/antmicro/renode), and [renode-test-action](https://github.com/antmicro/renode-test-action).

## QEMU
- **Upstream Cortex-M machines:** stm32vldiscovery, netduino2, netduinoplus2, olimex-stm32-h405, b-l475e-iot01a, mps2/mps3, lm3s*, microbit, max78000fthr ([docs](https://www.qemu.org/docs/master/system/target-arm.html)).
  - The STM32 machines have no GPIO, DMA, PWM, Ethernet or CAN. The B-L475E has no ADC, SPI or timers.
  - There is no S32K or i.MX RT machine.
- **TriCore (AURIX):** only `tricore_testboard` and a `KIT_AURIX_TC277_TRB` memory map.
  - A TC39x patch series was posted 2026-05-31. It models only the interrupt router, UART, system timer and SCU, and wasn't in the 2026-08-16 misc-HW pull.
- **PolarFire SoC:** the `microchip-icicle-kit` machine exists, but its HSS boot loader no longer runs.
- **AMD's QEMU fork** ([repo](https://github.com/Xilinx/qemu)):
  - Machines: Zynq-7000, ZynqMP and Versal, with the MicroBlaze PMU as a second QEMU instance.
  - Runs the real FSBL, PMU firmware, ATF and U-Boot. The CSU boot ROM is replaced by a QEMU model, and eFuse and BBRAM models exist.
  - CAN bridges to SocketCAN. Remote-Port + libsystemctlm-soc provide SystemC co-simulation.
  - [qemu-devicetrees](https://github.com/Xilinx/qemu-devicetrees) includes Kria K24/K26/KD240. Zephyr's `qemu_cortex_r5` board runs on this fork.

## Commercial virtual platforms
- **Synopsys Virtualizer Development Kits (VDKs):**
  - Confirmed for Infineon AURIX TC4xx ("memories, communication, timer, ADC, security and safety").
  - The May 2025 fact sheet lists "all S32 families", RH850 and Stellar, and claims reflashing/OTA, security testing and CI/CD support.
  - An NXP S32K5 VDK is confirmed. S32K3 and S32K39x coverage is not publicly confirmed.
  - TI support is limited to the TDA family. No public price.
- **MathWorks:** documents Simulink lock-step virtual HIL with the AURIX TC4x VDK.
- **Altera Simics:** Agilex 5 only. Boots U-Boot SPL → ATF → U-Boot → Linux/Zephyr with Ethernet, but no CAN. Free download; runs on Linux hosts.
- **Vector vVIRTUALtarget, dSPACE VEOS, Synopsys Silver:** host-compiled virtual ECUs. They can't exercise boot, flash or low-level driver code.
- **Lauterbach TRACE32 simulators:** core instruction-set only; peripherals need user-written models.
- **Arm Virtual Hardware (via Corellium):** i.MX 8M/93 and STM32U5 only.

## Real-silicon PIL tools (not emulators)
- **PLECS target support:** C2000 (F2838x, F29H85x), STM32 (G4/F3 only), Infineon XMC (XMC1400/XMC4400 only).
- **MathWorks:** C2000 Blockset, AM26x support package, Renesas RA6T2 support package (May 2026).
- **NXP:** Model-Based Design Toolbox for S32K3 v1.8.0 (December 2025), with SIL/PIL.

## Zephyr
Upstream Zephyr was checked on 2026-09-15.
- **GigaDevice boards:** gd32a503v_eval, gd32e103v_eval, gd32e507v_start, gd32e507z_eval, gd32f350r_eval, gd32f403z_eval, gd32f407v_start, gd32f450i_eval, gd32f450v_start, gd32f450z_eval, gd32f470i_eval, gd32l233r_eval, and 2 GD32VF103 (RISC-V) boards. **No GD32H7.**
- **No vendor directories** for Artery, Geehy, MindMotion, Nations or HPMicro. WCH boards are RISC-V.
- **NXP S32K3:** only the `s32k344` SoC (board `mr_canhubk3`). No S32K388 or S32K39x.
- **Host builds:** `native_sim` builds a Zephyr app as a Linux executable with TAP Ethernet. It tests application, networking and update logic from the same source, but not the real firmware binary.

## Software-side scorecard
Scores run 1–5, from the round-2 simulation research.

| Family (best tool) | CPU/IRQ | Boot/HSM | Flash & update | Networks | OS | Physics link | CI & cost | Overall |
|---|---|---|---|---|---|---|---|---|
| AMD Zynq UltraScale+ / Kria (AMD QEMU) | 5 | 4 | 5 | 5 | 5 | 4 | 5 | **5** |
| ST STM32H7 (Renode) | 5 | 3 | 4 | 5 | 4 | 5 | 5 | **4** |
| PolarFire SoC (Renode) | 4 | 4 | 3 | 4 | 4 | 5 | 5 | **4** |
| AURIX TC3xx/TC4x (Synopsys VDK) | 5 | 4 | 4 | 4 | 4 | 5 | 2 | **4** (2 with open tools only) |
| NXP S32K3/S32K39x (Renode) | 4 | 2 | 2 | 4 | 3 | 5 | 5 | **3** (4 with flash + HSE models) |
| ST Stellar SR5E1 (VDK) [U] | 4 | 3 | 3 | 3 | 3 | 4 | 2 | **3** |
| Altera Agilex 5 (Simics) | 4 | 4 | 4 | 3 | 4 | 3 | 3 | **3** |
| Renesas RH850/U2B (VDK) [U] | 3 | 2 | 3 | 3 | 3 | 4 | 2 | **2** |
| TI AM263Px | 2 | 1 | 1 | 2 | 2 | 3 | 3 | **2** |
| TI C2000 F29H85x/F28P65x | 1 | 1 | 1 | 1 | 1 | 1 | 1 | **1** |
| Microchip dsPIC33A (MPLAB simulator) | 3 | 1 | 2 | 1 | 1 | 1 | 3 | **1** |

Scores for the round-4 cheap Arm parts, from the checks above:
- **i.MX RT1062:** about 3, using the RT1064 model with a CAN model to add.
- **GD32 and AT32 parts:** 1 until an emulator platform is written. GD32F4 parts can use Zephyr `native_sim` host builds.

## Recommended stacks
- **MCU class (Renode):**
  1. Renode in Docker with Robot Framework tests in CI.
  2. Firmware: Zephyr or FreeRTOS with MCUboot (swap-move rather than bank swap).
  3. Networks: CAN through the SocketCAN bridge, so host UDS/XCP flashers can reach the firmware; Ethernet through TAP; other ECUs as extra Renode machines.
  4. Physics link: the plant sim acts as an External Control client. It advances time with `RunFor`, writes ADC values and fault inputs, and reads PWM registers.
- **SoC class (AMD QEMU):**
  1. Boot the real BOOT.BIN from emulated QSPI.
  2. Run Linux with RAUC or SWUpdate A/B on eMMC, and load the real-time-core firmware through remoteproc.
  3. CAN via `can-host-socketcan`, Ethernet via TAP.
  4. FPGA blocks become SystemC register stubs behind Remote-Port.

## Caveats
- No open emulator runs closed security-module firmware (NXP HSE, AURIX HSM, TI HSM). Secure-boot testing needs API stubs.
- **EtherCAT:** no emulator models an EtherCAT slave controller. See [08](08-industrial-comms.md) for software options.
