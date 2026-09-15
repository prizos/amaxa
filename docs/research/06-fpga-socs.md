# FPGA and SoC-FPGA control boards

**Status:** researched in round 3 against the superseded combined spec (GaN, multilevel, dual active bridge). **Withdrawn** for this product: motors and inverters at 4–20 kHz don't need an FPGA. The notes are kept for reference.

[U] marks unverified claims. "est." marks a pin-budget estimate.

## When an FPGA-class board is justified
Only if the most demanding power board needs one of these:
- **Many independent gates:** 3-level ANPC 3-phase (18 gates), 5-level flying capacitor (24), modular multilevel or cascaded H-bridge cells, or 6+ interleaved phases with per-phase current balancing.
- **Fast cycle-by-cycle control:** GaN or SiC above ~300–500 kHz with digital control every cycle (peak/valley current mode, predictive control, dual-active-bridge phase shift needing sub-ns steps) [U threshold].
- **Many fast channels:** more than ~12 channels sampled simultaneously at ≥1 MSPS.
- **µs-scale decisions:** finite-set model-predictive control, optimised pulse patterns, or ordered multi-switch shutdown.

MCUs win everywhere else: DC/DC, PFC, H-bridges, two-level 3-phase inverters (including paralleled 300 A stages). They cost less, boot in milliseconds, need one firmware image, come in AEC-Q100/ASIL-D grades, and are simpler to emulate.

## Largest single power board per candidate

| Candidate | Silicon / real-time cores | Largest single board | PWM edge resolution | Fault → PWM off |
|---|---|---|---|---|
| **AMD Kria K24 SoM** on own carrier (dev kit KD240) | XCK24 (Zynq UltraScale+ MPSoC, 154K logic cells, 360 DSP); 2× Cortex-R5F + 4× A53 | 132 user I/O → ~24 legs + 24 fault + 32 simultaneous analog (est.) | fabric ~2–4 ns [U]; sub-ns with I/O delay or SerDes [U] | <10 ns unfiltered; 10–100 ns filtered (est.) |
| XA Zynq UltraScale+ chip-down; SoMs Trenz TE0820 / TE0808, Enclustra Mercury+ XU5 | same architecture | TE0820 up to 132 PL I/O; XU5 144; TE0808 156 HP + 96 HD | as K24 | as K24 |
| **Microchip PolarFire SoC** (Icicle MPFS250T, Discovery, BeagleV-Fire MPFS025T) | 23K–461K logic elements; 4× U54 + E51 RISC-V @667 MHz | 108–468 fabric I/O → ~20+ legs (est.) | 1.6 Gbps I/O serialisers → ~625 ps possible (derived) | as above; fabric live at power-up |
| Altera Agilex 5 E-series SoC (DE25-Nano, AXE5-Eagle) | 2× A76 + 2× A55; Nios V soft cores | DE25-Nano ~12–16 legs (est.) | ~2–3 ns [U] | as above; no hard real-time core |
| **imperix B-Board PRO** (embeddable) | Zynq-7030; 2× A9 | 16 legs (32 PWM), 8× 16-bit 2 MSPS simultaneous analog, 16 fault inputs | 4 ns, ±0.4 ns jitter | 50–60 ns |
| imperix B-Box 4 (lab) | ZU7EV | 24 legs (48 PWM), 24× 16-bit 20 MSPS analog | 250 ps; loops to 500 kHz | down to 800 ns |
| UltraZohm (open hardware, lab) | TE0808 with ZU9EG | 12 legs; 8× 16-bit 5 MSPS per card | PWM IP tested to 100 kHz | [U] |
| Lattice Certus-NX / Efinix Titanium (MCU companion) | 9K–65K LUT, 2× 12-bit 1 MSPS ADC / Ti35–Ti375 | small stages | [U] | fast |

## Grade, price, tools, emulation

| Candidate | Grade / safety | Buy | Toolchain | Software emulation | Comms |
|---|---|---|---|---|---|
| K24 / KD240 | commercial 0–85 °C, industrial −40–100 °C; SRAM fabric | SM-K24-XCL2GC $312.50 (qty 1, 12-week lead); KD240 $399; motor pack $199 | Vivado 2026.1 tiers; free Basic covers Kria; bitstream encryption may need paid tier [U] | AMD QEMU: **5/5**; Renode ZynqMP partial | 2 PS + 2 PL GbE (TSN), CAN, RS-485, USB |
| XA Zynq US+ | AEC-Q100; ISO 26262 ASIL-C claim from an old Xilinx press release (exida) [verify] | quote | same | same | carrier-defined |
| PolarFire SoC | AEC-Q100 Grade 1 (since March 2025); SEU-immune configuration; Libero TÜV-certified ASIL D tool flow | Icicle ~$400 [U]; Discovery $132 [U] | free Libero Silver licence (covers MPFS250) | Renode **4/5**; upstream QEMU HSS boot broken | 2 GbE (TSN/1588), 2 CAN, USB |
| Agilex 5 E | IEC 61508 SIL2 single-chip / SIL3 dual-chip concepts (TÜV-reviewed) | DE25-Nano $248 | free Quartus Pro licence | Altera Simics **3/5**; no QEMU | Ethernet, USB 3.1 |
| B-Board PRO | 0–80 °C | quote | imperix SDK (C++, Simulink, PLECS) + Vivado | proprietary OS [U] | GbE, CAN, USB, 3× SFP+ |
| Certus-NX / Titanium | AEC-Q100 parts | [U] | Radiant/Propel, Efinity [U] | Renode LiteX/VexRiscv | soft IP |

## Notes
- **PWM in fabric:** costs pins, not logic; 2 pins per leg. Resolution is one clock period.
  - The B-Board PRO's 250 MHz counter gives 4 ns edges ([data sheet](https://imperix.com/wp-content/uploads/document/B-Board_Datasheet.pdf)).
  - Sub-ns needs SerDes, I/O delay primitives or phase-shifted clocks. B-Box 4's 250 ps is the only published product figure ([imperix](https://imperix.com/products/control/rcp-controller/)).
- **Sensing:** on-chip ADCs are too slow (XADC dual 12-bit 1 MSPS, muxed). Use external simultaneous-sampling ADCs:
  - imperix: 2× LTC2324-16
  - UltraZohm: an 8-channel 16-bit 5 MSPS card
  - KD240: 8-channel 12-bit AD7352 through an ADC-hub IP ([KD240 hardware](https://xilinx.github.io/kria-apps-docs/kd240/foc-motor-ctrl/0_5/build/html/docs/hw_description.html))
- **Safe outputs:** SRAM FPGA pins are undefined during configuration. Add a buffer whose output enable is driven by the fault latch, plus pull-downs.
- **Boot time:** SRAM FPGA + Linux takes seconds to be PWM-ready; imperix documents ~20 s.
- **Updates:** must version the bitstream, the boot stages (FSBL, PMU firmware, ATF, U-Boot, or PolarFire HSS) and the real-time-core image together.
- **KD240 reference app:** encoder interface, FOC, SVPWM and PWM in fabric (Vitis HLS motor-control library). Faults are software-limit checks on averaged ADC data.
- **Beckhoff AX8000:** FPGA current control, 62.5 µs cycle, 1 µs reaction ([Beckhoff](https://www.beckhoff.com/en-en/products/motion/servo-drives/ax8000-multi-axis-servo-system/)). Automotive traction inverters appear to be mostly MCU-only [U].
- **Versal AI Edge Gen 2:** up to 8× A78AE + 10× R52; QEMU `amd-versal2-virt`. Overkill unless the same chip also does perception.
- **NI:** sbRIO-9607 (host for the GPIC inverter board) is not recommended for new designs; replacement sbRIO-9603. GPIC status [U].
- **Plexim RT Box, Speedgoat, Myway PE-Expert4, OPAL-RT:** lab-only, mostly five-figure prices [U].

## Round-3 FPGA ranking (withdrawn)
1. Kria K24, then chip-down XA Zynq UltraScale+
2. PolarFire SoC (automotive grade)
3. imperix B-Board PRO

- **Middle path considered:** an MCU plus a small AEC-Q100 FPGA (Certus-NX or Titanium), fitted only on the variants that need it.
