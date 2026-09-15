# Industrial comms and EtherCAT

**Status:** comms is **not** a selection criterion; any protocol is fine. These notes come from round 1, when EtherCAT was wrongly given priority, and are kept for when a protocol is chosen.

[U] marks unverified claims.

## MCUs/MPUs with an integrated EtherCAT slave controller (ESC)

| Part | How | Notes |
|---|---|---|
| TI AM243x, AM263Px, AM261x, AM64x | PRU-ICSS firmware ESC | TI EtherCAT SubDevice SDK wraps Beckhoff SSC under BSD-3 (CoE/FoE/EoE, DC, CiA402). Conformance certificates for the AM263Px and AM261x LaunchPads ([release notes](https://software-dl.ti.com/processor-industrial-sw/esd/ind_comms_sdk/am263px/latest/docs/am263px/ethercat_subdevice/releasenotes.html)) |
| TI F28388D, F28P65x (DK variants), F29H85x | integrated ESC | F29H85x SDK has SSC examples ([docs](https://software-dl.ti.com/C2000/docs/f29h85x-sdk/latest/docs/html/ETHERCAT_DEV_OVERVIEW.html)); which F29H85x part numbers include the ESC is [U]. acontis supports C2000 |
| Infineon XMC4800 / XMC4300 | integrated Beckhoff ESC | SSC example on [GitHub](https://github.com/Infineon/mtb-example-xmc48-ethcat-ssc/) |
| Renesas RZ/T2M, RZ/T2L, RZ/N2L, RZ/T2H | integrated Beckhoff ESC | SSC tool needs ETG membership |
| Renesas RA8T2 | optional ESC | "2× ESC" claim [U] |
| NXP i.MX RT1180 | integrated ESC + Gigabit TSN switch | FRDM-IMXRT1186 $85; servo reference design ([App Code Hub](https://github.com/nxp-appcodehub/rd-motion-control-slave-servo-mimxrt1180)) |
| Microchip LAN9255 | SAM E53 + LAN9253 in one package | Harmony 3 EtherCAT |

**Not integrated:** NXP S32K3/S32K39x, STM32, AURIX, GD32 and AT32 need an external ESC. A software-only slave on a standard Ethernet MAC isn't practical, because EtherCAT needs hardware frame processing and distributed clocks (engineering judgement).

## External ESCs (host over SPI or parallel)

| Part | Summary |
|---|---|
| [Microchip LAN9252](https://ww1.microchip.com/downloads/aemDocuments/documents/OTH/ProductDocuments/DataSheets/00001909A.pdf) | 2/3 ports, 2 PHYs, 4 SyncManagers, 3 FMMUs, 4 KB DPRAM |
| [Microchip LAN9253](https://ww1.microchip.com/downloads/en/DeviceDoc/00003421A.pdf) | 8 SyncManagers, 8 FMMUs, 8 KB DPRAM, SQI host interface |
| Microchip LAN9254 | variant of the family [U details] |
| Beckhoff ET1100 | needs external PHYs |
| [Beckhoff ET1150](https://www.beckhoff.com/en-en/products/i-o/ethercat-development-products/elxxxx-etxxxx-fbxxxx-hardware/et1150.html) | 4 ports, 16 FMMUs/SyncManagers, Quad/Octal-SPI, BGA128; market release estimated **Q4 2026** |
| GigaDevice GDSCN832 (+ GD32H75E) | low-cost ESC launched late 2024 ([BusinessWire](https://www.businesswire.com/news/home/20241111685498/en/GigaDevice-Launches-New-EtherCAT-SubDevice-Controller-Chip-An-Excellent-Choice-for-Industrial-Automation)) |
| ADI fido5200 / ADIN2299 | multi-protocol industrial Ethernet including EtherCAT (the fido5100 lacks EtherCAT) ([ADI](https://www.analog.com/en/resources/technical-articles/fido5000-one-chip-many-ethernet-protocols.html)) |
| Hilscher netX 90 | firmware-selected protocol, host over SPI ([Hilscher](https://www.hilscher.com/products/multiprotocol-socs-stacks/multiprotocol-socs/netx-90)) |

## Stacks and licensing
- **Beckhoff Slave Stack Code (SSC):** royalty-free, but the download is ETG-members only ([ETG](https://www.ethercat.org/en/downloads/downloads_01DCC32A10294F2EA866F7E46FB0285F.htm)).
- **Open source:** SOES (slave) and SOEM (master) ([SOES](https://github.com/OpenEtherCATsociety/SOES)).
- **Commercial:** acontis, IBV (EtherCAT master for STM32), RT-Labs (XMC7000 master).

## Simulating EtherCAT without hardware
No emulator models an ESC (integrated or external). Options:
- **KickCAT:** open-source software ESC (`EmulatedESC`: registers, SyncManagers, FMMUs, DC clock, EEPROM), emulated network over TAP/shared memory, loads ESI XML, slave ports for LAN9252 and XMC4800 ([KickCAT](https://github.com/leducp/KickCAT)).
  - An SPI-attached ESC (LAN9252) is easier to simulate at binary level than an integrated one. A Renode SPI peripheral backed by KickCAT's `EmulatedESC` is plausible but untested.
- **SOES on Linux** against a SOEM or IgH master over veth/TAP. IgH's generic driver on veth is [U].
- **acontis EC-Simulator** (SiL or HiL) ([acontis](https://www.acontis.com/en/ethercat-simulation.html)).
- **Beckhoff TE1111:** slave simulation with DC, CoE/SoE and FMU/Simulink models ([Beckhoff](https://www.beckhoff.com/en-us/products/automation/twincat/texxxx-twincat-3-engineering/te1111.html)).

## EtherCAT timing facts
- **Cycles and sync:** distributed clocks run SYNC0 at 62.5 µs–1 ms. SYNC0 aligns to the PWM carrier, with jitter under 100 ns in good designs ([Elmo](https://www.elmomc.com/elmo_academy/ethercat-multi-axis-synchronization/)).
- **Profile:** CiA 402 (CoE) is the servo/CNC profile.
- **Functional safety:** FSoE (Safety over EtherCAT).

## Other protocols
- **CAN FD:** on nearly every candidate MCU (see [02](02-cheap-fast-arm-mcus.md)).
- **TSN / PROFINET IRT:** on the AM243x/AM263x, RZ/T2 class and RT1180.
- **10BASE-T1S (PLCA):** bounded latency, but too slow for µs-level PWM sync ([ADI](https://www.analog.com/en/resources/analog-dialogue/articles/how-10base-t1s-ethernet-simplifies-zonal-architectures.html)). Fine for slow supervisory nodes.
- **TI FSI:** ~3 µs latency for 32 bytes, used for board-to-board sync on C2000 ([SPRACM3E](https://www.ti.com/lit/an/spracm3e/spracm3e.pdf)).
