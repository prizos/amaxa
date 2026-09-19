# SOIC8 — the two field-bus transceivers

| | |
|---|---|
| Component | `CAN_TRANSCEIVER`, `RS485_TRANSCEIVER` |
| Manufacturer | Texas Instruments |
| Part number | `TCAN1044VDRQ1`, `THVD1450DR` |
| LCSC | [C1852061](https://www.lcsc.com/product-detail/C1852061.html), [C2671361](https://www.lcsc.com/product-detail/C2671361.html) |
| Footprint | `SOIC-8_3.9x4.9mm_P1.27mm` |

Two parts in one package outline, so one library. Stock 13,804 and 5,499, read
from JLCPCB's component API on 2026-09-17.

## Why these two

Both were chosen for what they do when nothing is driving them, which on a
board whose whole safety story is "unprogrammed means inert" is the property
that matters more than price.

**TCAN1044V** comes out of reset listening: its `STB` pin has an integrated
pull-up, so a floating MCU pin leaves it in standby rather than transmitting.
Its ±58 V bus rating is the reason it is not a cheaper part — a CAN wire in a
machine shares a loom with things at 48 V, and a transceiver that survives
contact with them is a board that comes back rather than a board that is
replaced.

**THVD1450** has the fail-safe biasing built in: the datasheet's §9.3 says the
receiver output "remains logic high under a bus-idle or bus-short condition
without the need for external failsafe biasing resistors". The plan called for
a bias network on this bus; there is none, and this is why. Its driver enable
has a 2 MΩ pull-down and its receiver enable a pull-up, so an undriven board
neither talks nor stops listening.

## Figures used from the datasheets

TI's *TCAN1044V*, SLLSFG2 (December 2019), and *THVD1410, THVD1450, THVD1451,
THVD1452*, SLLSEY3E (May 2018, revised May 2019).

| Figure | Value | Where |
|---|---|---|
| TCAN1044V V_CC | 4.5 to 5.5 V | §6.4 |
| TCAN1044V V_IO | 1.7 to 5.5 V | §6.4 |
| TCAN1044V bus fault voltage | ±58 V on CANH and CANL | §6.1 |
| TCAN1044V total loop delay | 210 ns max, V_IO 2.8 to 5.5 V | §6.9 |
| TCAN1044V data rate | 8 Mbps, CAN FD | §1, §8.1 |
| THVD1450 V_CC | 3 to 5.5 V | §7.4 |
| THVD1450 bus voltage, absolute max | −18 to 18 V at any bus pin | §7.1 |
| THVD1450 signalling rate | 50 Mbps | §7.4 |
| TCAN1044V bus ESD | ±8 kV powered contact, SAE J2962-2 per ISO 10650 | §6.3, `evidence/can_esd_ratings.png` |
| THVD1450 bus ESD | ±18 kV contact, IEC 61000-4-2 | §7.3, `evidence/rs485_esd_ratings.png` |
| TCAN1044V common mode | −12 to 12 V, normal and standby | §6.6, `evidence/can_common_mode.png` |
| THVD1450 common mode | ±15 V, the range the thresholds hold over | §7.5, `evidence/rs485_common_mode.png` |

**The signalling rate was wrong here once.** It was recorded as 500 kbps, which
is the THVD1410's figure — the same datasheet covers four parts and the rate is
the row that differs between them. 500 kbps would have passed every check by
being pessimistic, which is the kind of wrong that never surfaces.

**±18 kV is not ±18 V.** The IEC 61000-4-2 contact-discharge rating and the
bus-pin absolute maximum are both 18 in this datasheet and mean nothing like
each other. `bus_fault_voltage` is the DC one, from §7.1, and it is what the
connector's fault-current check works from.

## Neither bus has a protection device, and that is the decision

The plan asked for ESD on both. Neither got one, because both transceivers are
already qualified on their bus pins at or above what the connectors need, and a
TVS array in front of a part rated higher than the array is capacitance on a
pair whose impedance matters in exchange for nothing.

`bus.esd_level` asks for **8 kV by contact**, IEC 61000-4-2 level 4, which is
what anything with a connector on the outside of a machine is expected to
survive. `test_nothing_unrated_for_a_strike_sits_on_a_bus_terminal` walks out
from each connector and requires that every part it reaches is either a
two-terminal passive or carries a rating that meets it — so the decision
survives a transceiver being swapped, and so would an unrated buffer hung on
the pair, which a check naming the transceiver would miss.

**The two are not qualified to the same standard, and the check compares them
as though they were.** The THVD1450's ±18 kV is IEC 61000-4-2 contact. The
TCAN1044V's ±8 kV is SAE J2962-2 per ISO 10650, a *powered* contact discharge:
the part is running while it is struck, which is the harder of the two tests at
the same voltage, and TI's document never quotes IEC 61000-4-2 at all. Treating
8 kV powered as meeting an 8 kV IEC requirement is the one assumption here, and
it is written into `evidence/sources.json` beside the crop rather than left in
the arithmetic.

## Both cable grounds go straight to the board's, and that is the decision too

Each connector's third pin is the cable's reference, and on both it is tied
directly to board ground. Industrial practice on RS-485 — TI's own design
guide included — puts 100 Ω in that path, so that two machines whose grounds
sit a few volts apart drive a bounded current down the cable rather than
whatever the wire will carry.

**What makes the hard tie affordable is the margin in these two parts.** Each
standard states the ground offset a receiver must tolerate: ISO 11898-2 asks
CAN for −2 to +7 V, TIA-485 asks RS-485 for −7 to +12. These are specified to
±12 V and ±15 V. The offset that would break either link is one no standard
requires anybody to survive.

**And a resistor sized to cover more than that cannot be an 0402.** Two 100 Ω,
one at each end of the cable, carry ΔV/200 between them; at the ±15 V edge of
the THVD1450's range that is a ground difference of 30 V and 560 mW in each
resistor — nine times what an 0402 is rated for, and more than a 1206 with any
derating. Sizing the part honestly means choosing the offset it is allowed to
fail at, which is a property of the installation and not of this board.

`test_a_cable_ground_tied_straight_to_the_boards_is_one_the_parts_can_afford`
holds the margin rather than the decision: swap either transceiver for one that
merely meets its standard and the justification is gone and the check fails.

**What none of this covers** is a long cable between two machines on separate
supplies, where the offset is bounded by nothing. The answer there is an
isolated transceiver, not a resistor — a different part, and not in this plan.

## The orderable is the automotive part

`TCAN1044VDRQ1` is the AEC-Q100 orderable. Its English datasheet is a scan that
nothing here could read — 44 pages yielding ten kilobytes of text — which is
why the electrical figures above were first taken from the industrial
TCAN1044V datasheet, SLLSFG2, the same silicon.

**That is no longer the only readable source.** TI's Chinese-language edition of
the −Q1 document, **ZHCSIP6B** (August 2019, revised October 2021), is text and
is what LCSC serves for C1852061. Its tables are in English. The ESD figure
comes from it, and V_CC, V_IO, the ±58 V bus rating, the 210 ns loop delay and
the 8 Mbps rate were all re-read there and agree with SLLSFG2.

## Pin mapping

KiCad has no TCAN1044V symbol. `Interface_CAN_LIN:SN65HVD230` is used, whose
eight pins are in the same places, and whose names are the ones this board's
checks read:

| Pin | SN65HVD230 name | TCAN1044V | Here |
|---|---|---|---|
| 1 | D | TXD | `CAN_TX` |
| 2 | GND | GND | ground |
| 3 | VCC | VCC | 5 V |
| 4 | R | RXD | `CAN_RX` |
| 5 | Vref | V_IO | **3V3** |
| 6 | CANL | CANL | `CAN_L` |
| 7 | CANH | CANH | `CAN_H` |
| 8 | Rs | STB | `CAN_STANDBY` |

**Pin 5 is the trap.** On the SN65HVD230 it is `Vref`, an output at V_CC/2; on
the TCAN1044V it is `V_IO`, the supply that sets what a logic high is on TXD
and RXD. Wired as the symbol names it — left open, or worse driven — the
transceiver's logic side would have no supply. It is on 3V3 here, which is what
makes the 3.3 V MCU and the 5 V bus side work together, and the rail matching
in `checks/test_buses.py` is what holds it there.

`Interface_UART:THVD1450DR` is the real part's symbol: 1 RO, 2 ~RE, 3 DE,
4 DI, 5 GND, 6 A, 7 B, 8 VCC. `~RE` is tied to ground, which is the *enabled*
state, so the receiver hears the bus while this node transmits — the only way a
half-duplex node notices a collision.

**Footprint.** KiCad stock `Package_SO:SOIC-8_3.9x4.9mm_P1.27mm`, unmodified,
which is the D package both orderables are in.
