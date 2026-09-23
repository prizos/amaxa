# Interface to the analog power board

These are design notes for a digital board that drives one soldered-on, purely analog power board. Parts of this were sized against the superseded combined spec in [01](01-requirements.md); motor/inverter boards need less.

[U] marks unverified claims.

## Keeping the power board analog
- **Type-specific parts on the power board:** the gain and anti-alias filter for each type are analog parts, so they belong on the power board. The digital board keeps one fixed input network — 22 Ω and 4.7 nF, a 1.27–1.73 MHz corner — after the pattern of TI's controlCARDs, [SPRUIR3](https://www.ti.com/lit/pdf/spruir3).
- **The clamps were the requirement, and they are not any more.** This section used to say so: `hw/cpu1` builds the RC and has nowhere to put a clamp, because one has to sit on the sense net *ahead* of the series resistor and there is no room in the analog fan for a SOT-363 and its two vias. Three positions were tried and built. So the requirement went to the power board — *do not present more than 4.0 V, ever, including while your op-amp is railing* — which is a requirement on a board that did not exist, written because the digital board could not meet it.

  **It met it a different way.** The analog supply the connector carries was 5 V through a ferrite, which is what made a railing op-amp a 5.25 V fault against ST's 4.0 V absolute maximum for a TT_xx pin. It is now regulated to 3.3 V by a TLV70233, so **the worst a sensor powered from this board can present is 3.366 V** — the regulator's nominal at the top of its own 2 % accuracy — and that is inside the pin's rating with 0.6 V to spare. `analog.input_voltage_max` is that figure rather than ST's, derived from the regulator and checked against it, so the promise is now "do not present more than the rail I give you".

  ST's own numbers are still the reason the limit is a voltage: Table 20 caps a TT_xx input at 4.0 V absolute, and Table 21 rates injection on those pins at −5 to **+0 mA**, so there is no positive-injection path to be inside of. Both crops are committed at `hw/cpu1/parts/LQFP144/evidence/`.

  **What this costs a power board:** sensors run from 3.3 V. An ACS724, a LEM module or anything else wanting 5 V makes its own from the gate-drive supply it has by definition, and scales its output to this rail. **It does not get that supply through this connector** — see the note on supplies below.
- **Scaling:** each power board maps its rated peak to ~90% of ADC full scale.
- **Wide range within one type:** two fixed-gain amplifier outputs from one Kelvin shunt (e.g., ×1 and ×50) on two ADC channels, or shunts switched by MOSFETs driven from a digital-board GPIO. Neither puts logic on the power board.
- **Isolated sensing:** isolated **amplifiers** have analog outputs, so they keep the power board analog. Isolated **sigma-delta modulators** output a digital bitstream, so they break the rule.

| Isolated amplifier | Input | Bandwidth | Delay | CMTI |
|---|---|---|---|---|
| [AMC1300B](https://www.ti.com/lit/ds/symlink/amc1300.pdf) | ±250 mV | 250–310 kHz | ≤3 µs | 100 kV/µs |
| [AMC1302](https://www.ti.com/lit/ds/symlink/amc1302.pdf) | ±50 mV | 220–280 kHz | – | – |
| [AMC3330](https://www.ti.com/lit/ds/symlink/amc3330.pdf) | ±1 V, built-in DC/DC | 300–375 kHz | – | 85 kV/µs |
| ACPL-C87x | 0–2 V | 100 kHz [U] | – | – |

These suit control loops up to ~50 kHz. They are too slow for a trip under 1 µs.

## External simultaneous-sampling ADCs (if the MCU's ADCs aren't enough)

| Part | Channels / bits | Rate | Notes | Interface |
|---|---|---|---|---|
| AD7606C-16/-18 | 8 / 16, 18 | 1 MSPS [U] | per-channel ranges; family has ~22 kHz anti-alias filter | SPI / parallel |
| [ADS8588S](https://www.ti.com/lit/ds/symlink/ads8588s.pdf) | 8 / 16 | 200 kSPS/ch | on-chip 24 kHz anti-alias filter | parallel / serial |
| [ADS8598H](https://www.ti.com/lit/ds/symlink/ads8598h.pdf) | 8 / 18 | 500 kSPS/ch | 1.24 µs conversion | parallel / serial |
| AD7380 / AD7380-4 | 2 / 4, 16-bit | 4 MSPS | differential | SPI |
| AD4630-24 | 2 / 24 | 2 MSPS/ch | – | multi-lane SPI (FPGA) |
| [ADS9224R](https://www.ti.com/lit/ds/symlink/ads9224r.pdf) | 2 / 16 | 3 MSPS | 333 ns latency | enhanced SPI or parallel |
| LTC2358-18 | 8 / 18 | 200 kSPS [U] | – | CMOS or LVDS [U] |
| [ADS131M08](https://www.ti.com/lit/ds/symlink/ads131m08.pdf) | 8 / 24 ΔΣ | ≤32 kSPS | ~104 µs settling | SPI; slow channels only |

- **Built-in filter limit:** the 16–24 kHz anti-alias filters built into the AD7606 and ADS85x8 limit them to drives switching at 20 kHz or below.
- **SPI read time:** 8 channels × 18 bits at 20 Mbps takes ~7 µs.

## Protection (two layers)
1. **Gate driver on the power board (analog desaturation/over-current detection).**
   - The [UCC21710](https://www.ti.com/lit/ds/symlink/ucc21710.pdf) filters its over-current input for 120 ns, pulls the output low in 270 ns typical (400 ns max), and flags the fault within 750 ns. It rejects input pulses shorter than 40 ns.
   - SiC short-circuit withstand in one Wolfspeed example is 2.9 µs ([app note](https://assets.wolfspeed.com/uploads/2024/01/Wolfspeed_PRD-08296_SiC_MOSFET_Short_Circuit_Application_Note.pdf)).
2. **Digital-board comparators with DAC thresholds set per type.**
   - Comparator plus trip takes ≤~90 ns on C2000-class MCUs.
   - A hardware latch disables every output, and only firmware can clear it.
- **Safe state:** PWM outputs go to a hardware-enforced safe state before firmware runs (buffer with output enable, pull-downs). **There is no separate watchdog device**, and `hw/cpu1` does not have one: this line used to claim "a watchdog path that cuts PWM" and there is no such net. What exists instead is the MCU's own independent watchdog, whose timeout is a reset, and `NRST` is one of the four cathodes on the trip bus — so a watchdog expiry presets the latch through the same diode a brown-out does. It is a real path; it is not a separate part, and a power board should not expect one.

### `GATE_ENABLE` is a master kill, and the timing rests on it

**This is the requirement a power board most has to honour, and it was
implied rather than stated until `hw/cpu1` was routed and measured.**

The digital board's trip budget is 50 ns — set by how long a half bridge
survives a shoot-through, not by anything on the board — and the measured
chain is 40.5 ns of it. The last term in that chain is a gate line actually
going low, and **only `GATE_ENABLE` gets there in time**:

| line | falls in | how |
|---|---|---|
| `GATE_ENABLE` | **3.4 ns** | a MOSFET shorts it to ground the moment the latch trips |
| the fourteen PWM lines | **32–39 ns bare, up to 188 ns loaded** | their own 10 kΩ pull-downs, once the buffers let go |

Both rows are derived from the netlist and the routed copper by
`test_the_pwm_lines_really_are_the_second_layer_the_interface_promises`, and
the PWM row has two ends because it depends on the power board. With nothing
attached the lines fall in 32–39 ns — the board's own copper is only a couple
of picofarads. With the 10 pF a gate driver's input pin may present, the
slowest reaches 188 ns. **That loaded corner is where the "~200 ns" this
document used to state came from**, quoted for three revisions as though it
were the figure rather than one end of a band.

So: **the power board must disable every gate driver from `GATE_ENABLE`
alone.** A design that treats it as advisory and gates on the PWM lines has a
hole of tens to a couple of hundred nanoseconds — depending on its own input
capacitance, which the digital board cannot know — where this board believes
it has stopped and the bridge is still being commanded. The PWM lines are a
real second layer and they are not the first one.

There was no resistor that made the PWM lines fast enough: the budget wanted
pull-downs under 600 Ω and the 3V3 rail's own budget wanted over 1.4 kΩ, and
that window is empty. Hence the transistor, and hence this requirement.

It matches the convention the [Infineon MADK M3](https://www.infineon.com/assets/row/public/documents/60/44/infineon-ug-2020-12-eval-m3-302f-usermanual-en.pdf?fileId=5546d46272aa54c00172db1cf44937be) already uses — "active-low gate kill" in the table below — so it costs a power board nothing to follow.
- **Safe Torque Off:** IEC 61800-5-2 STO with two independent channels removing gate-driver supply and logic input, with test-pulse diagnostics ([TI TIDA-01599](https://www.ti.com/lit/ug/tiduds9b/tiduds9b.pdf)).

### Open decision: smart gate drivers
- **What they are:** SPI "smart" gate drivers such as the [UCC5870-Q1](https://www.ti.com/lit/ds/symlink/ucc5870-q1.pdf) (SPI interface, 10-bit ADC).
- **Conflict:** they put digital logic on the power board, which breaks the analog-only rule.
- **What excluding them costs:** the ASIL-D diagnostics automotive traction inverters usually rely on.

## Signals across the solder joint
- **Signalling:** single-ended 3.3 V CMOS for a soldered board. 22–33 Ω series resistor at the source, a ground pin every 2 signals, pull-downs. LVDS or optical links are only needed for cabled systems.
- **Supplies across the joint, as `hw/cpu1` actually builds them:** 3.3 V out on the digital header, and 3V3A plus a 3.0 V reference out on the analog one. **There is no 12–15 V auxiliary pin and no 5 V analog pin.** Both were in the plan and neither was fitted: the digital header carries 52 pins and not one of them is a supply into this board, so cpu1 is powered from its own terminal block and from nothing else.
  That matters twice. The ideal-diode OR the plan called for, which would have let a power board supply the digital board, does not exist — so a system built on this pair needs two supplies or a wire. And the 5 V-sensor mitigation above cannot route through this connector; a power board making 5 V does it on its own side. Six documents in this repository said otherwise until an adversarial pass counted the pins.
  Only signals and low-power supplies cross the joint; load current stays on the power board.
- **Scale every sense output to `VREF+`, not to the sensor's own supply.** `hw/cpu1` exports a 3.000 V series reference on its own connector pin, and three things on the digital side are now fractions of it and of nothing else: the ADCs' full scale, the comparators' trip thresholds, and the code a control loop compares against. The threshold DAC's supply *is* that reference pin, so a threshold written as "a quarter of full scale" is a quarter of the same volt the converter measures against and the same volt the power board scaled its sensor to. A sensor scaled to its 3V3A supply instead loses that: two references, and a trip point that moves when either one does. The reference can supply 12.9 mA and this board has taken 7.74 of it, so **budget about 5 mA at the connector** and put a buffer on the power board if its dividers want more.
- **Grounding:**
  - Interface ground is control ground. On high-voltage types that is the low-voltage side of the isolated drivers and amplifiers.
  - Non-isolated types tie control ground to DC− at one point, at the shunt's Kelvin connection.
- **Common footprint:** nested pin groups. Group A (e.g., 4 PWM, 6 analog, ID, supplies) is always used; groups B and C add channels for larger types.
  - Unused PWM stays disabled with pull-downs.
  - Unused analog inputs are biased to a "not fitted" level, which also flags open solder joints.
  - SGET OSM is a solder-down module standard with 4 sizes; whether its sizes nest is [U].

## Identifying the power board and loading its configuration
- **ID hardware:** 1–2 ID resistor dividers read by the ADC, plus strap pins. Because the pairing is permanent, a factory record in digital-board memory is enough.
- **ID memory is optional:** a passive EEPROM on analog boards is a common exception — imperix sensors use 1-wire EEPROM; Raspberry Pi HATs use an ID EEPROM; IEEE 1451.4 TEDS defines analog sensors with memory.
- **Boot sequence:**
  1. Boot with the output buffer disabled.
  2. Read the ID and check it lies in a valid band.
  3. Match it against the factory type record (CRC-protected).
  4. Load the type descriptor: PWM topology, dead-time limits, frequency range, safe state, channel map and scaling, comparator thresholds, limits, loop gains.
  5. Arm protection, run self-test, then enable outputs. Lock out on any mismatch.
- **One firmware image** holds all N descriptors. The ID read goes through a hardware-abstraction call, so CI can boot every type in the emulator.

## Existing products that split control from power

| Ecosystem | Interface | Signals / analog convention |
|---|---|---|
| TI controlCARD | 120/180-pin HSEC8 edge | 5 V in; ADC clamps and RC filters on the card, conditioning on the kit. [TIDM-02009](https://www.ti.com/tool/TIDM-02009): one F28388D runs a SiC inverter + DC/DC |
| [Infineon MADK M3](https://www.infineon.com/assets/row/public/documents/60/44/infineon-ug-2020-12-eval-m3-302f-usermanual-en.pdf?fileId=5546d46272aa54c00172db1cf44937be) | 30-pin (M1: 20-pin) | 6+2 PWM at 3.3 V, active-low gate kill, raw shunt pairs, 0–3.3 V DC-bus divider, NTC, 3.3 V/15 V |
| [Microchip DIM + MCLV-48V-300W](https://github.com/microchip-pic-avr-solutions/mclv-48v-300w-an1292-dspic33ck64mc105) | DIM connector | current amplified on the board or by dsPIC op-amps, selected by resistors |
| [NXP HVP-MC3PH](https://www.nxp.com/design/design-center/development-boards-and-designs/HVP-MC3PH) | edge connector [U] | analog phase/bus currents and voltages, back-EMF, PFC current, temperature; hardware OC/OV comparators |
| imperix PEB + B-Box | cables | optical fibre per gate and optical fault return; RJ45 carries a differential pair, ±15 V and 1-wire ID. PEB-800-40 handles desat, OV, OT and shoot-through locally; 120 ns minimum dead-time ([PEB-800-40](https://imperix.com/doc/help/peb-800-40)) |
| [UltraZohm](https://ultrazohm.org/hardware/adapter_cards/adapter_cards.html) | adapter-card slots | analog cards: 10 fully differential signals; digital cards: 30 single-ended via CPLD |
| [Elmo Gold Twitter](https://www.elmomc.com/product/gold-twitter/) | soldered pins | complete drive module, 80 A/80 V, 35×30×11.5 mm |
| [Novanta/Ingenia Everest CORE](https://drives.novantamotion.com/eve-core/product-description) | plugged or soldered | complete drive; 16-bit sensing with 4 current ranges; PWM 10–100 kHz; 2-channel STO SIL3 |

## Other reference architectures (round 1)

| Product | Split | Compute | Takeaway |
|---|---|---|---|
| Synapticon SOMANET Node | Com / Core / Drive stacked modules | xCORE + Arm [U] | STO/SBC SIL3 PLe, FSoE; module-to-module bus unverified |
| TI TIDM-02006 | central F2838x (EtherCAT, outer loops) + F28004x current-loop nodes over isolated FSI daisy chain | C2000 | FSI ~3 µs latency for 32 bytes, syncs PWM across 1+8 nodes ([SPRACM3E](https://www.ti.com/lit/an/spracm3e/spracm3e.pdf)) |
| TI TIDEP-01032 | single-chip EtherCAT + 2-axis FOC | AM243x | control loop on R5F triggered by SDFM interrupt |
| openinverter, VESC, ODrive | logic board + power stage | STM32F1/F405 | cheap parameterised MCUs go a long way; no auto-ID, no safety certification |

## Sigma-delta note (not applicable to analog-only boards)
- **Delay:** ADuM7701 at 20 MHz with sinc3 at decimation 256 gives 86 dB at 78 kSPS ([ADI](https://www.analog.com/media/en/technical-documentation/data-sheets/ADuM7701.pdf)), but ~19 µs group delay (calculated). That's too slow for 100 kHz loops.
- **Workaround:** a parallel low-decimation filter for fast protection.
