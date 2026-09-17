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

**The signalling rate was wrong here once.** It was recorded as 500 kbps, which
is the THVD1410's figure — the same datasheet covers four parts and the rate is
the row that differs between them. 500 kbps would have passed every check by
being pessimistic, which is the kind of wrong that never surfaces.

**±18 kV is not ±18 V.** The IEC 61000-4-2 contact-discharge rating and the
bus-pin absolute maximum are both 18 in this datasheet and mean nothing like
each other. `bus_fault_voltage` is the DC one, from §7.1, and it is what the
connector's fault-current check works from.

## The orderable is the automotive part

`TCAN1044VDRQ1` is the AEC-Q100 orderable, whose own datasheet is a scanned
document nothing here could read — 44 pages that yield ten kilobytes of text.
Every figure above comes from the industrial TCAN1044V datasheet, SLLSFG2,
which is the same silicon and is machine-readable. The −Q1 document was fetched
and confirmed to list `TCAN1044VDRQ1` as an orderable; nothing else was taken
from it.

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
