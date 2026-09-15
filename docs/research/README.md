# Control board MCU research

Research notes for selecting the MCU on the amaxa digital control board. The work was done on 2026-09-15.

## Files

| File | Contents |
|---|---|
| [01-requirements.md](01-requirements.md) | Project brief, how it changed, and the signal spec for a motor/inverter driver board |
| [02-cheap-fast-arm-mcus.md](02-cheap-fast-arm-mcus.md) | **Current shortlist**: cheap, fast Arm MCUs (Western and Chinese), with features, prices and the recommendation |
| [03-emulation.md](03-emulation.md) | Which emulators and VMs can run the firmware, updates and networking, and how well |
| [04-nxp-s32-and-imx-rt.md](04-nxp-s32-and-imx-rt.md) | NXP S32K3, S32K39x, i.MX RT1180, MCX E31 and S32K5, evaluated earlier |
| [05-other-motor-control-mcus.md](05-other-motor-control-mcus.md) | TI, Infineon, Renesas, ST and Microchip motor-control and automotive MCUs, evaluated earlier |
| [06-fpga-socs.md](06-fpga-socs.md) | FPGA SoC control boards (Zynq, PolarFire, Agilex) and when an FPGA is justified |
| [07-power-board-interface.md](07-power-board-interface.md) | Interface to the analog power board: sensing, protection, ID, and existing products that split control from power |
| [08-industrial-comms.md](08-industrial-comms.md) | EtherCAT and other comms options (comms is not a selection criterion) |

## Current direction
- A cheap Arm Cortex-M MCU with a fast core, running most of the control in real-time software on a single core.
- Leading candidates (details in [02](02-cheap-fast-arm-mcus.md)):
  - **NXP i.MX RT1062:** Cortex-M7 at 600 MHz, $7.97 each at 1,200 units, and an emulator model is nearly ready.
  - **GigaDevice GD32H759:** Cortex-M7 at 600 MHz with more motor and CAN hardware. Its price is not verified, and it has no emulator model yet.

## Open decisions
1. **Production volume.** It decides whether the GD32H759's per-unit saving pays back the one-time work of writing its emulator model.
2. **Position feedback for servo power boards:** quadrature encoder, Hall, resolver, or serial absolute encoders.
3. **Gate drivers:** whether "smart" SPI gate drivers are allowed on the analog-only power boards (see [07](07-power-board-interface.md)).
4. **Automotive qualification:** whether automotive-grade parts (AEC-Q100, ISO 26262 ASIL) are required.
5. **Chinese prices:** they still need checking on LCSC, which blocked automated lookups.

## Caveats
- The web-search quota for the session ran out partway through. Later facts came from fetching vendor, distributor and GitHub pages directly.
- **[U]** marks claims that were not verified against a primary source.
- Prices are DigiKey prices on 2026-09-15 unless stated otherwise. Single-unit prices are far above volume prices.
- The research brief changed several times. [01](01-requirements.md) records how, and files 04–08 include material gathered under earlier versions of it.
