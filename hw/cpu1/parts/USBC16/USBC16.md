# USBC16 — the USB-C receptacle

| | |
|---|---|
| Component | `USB_C_RECEPTACLE` |
| Manufacturer | Korean Hroparts Elec |
| Part number | `TYPE-C-31-M-12` |
| LCSC | [C165948](https://www.lcsc.com/product-detail/C165948.html) |
| Footprint | `USB_C_Receptacle_HRO_TYPE-C-31-M-12` |

The 16-pin USB 2.0 subset of a Type-C receptacle: power, ground, both CC pins,
D+ and D− on both rows, and the two sideband pins. No SuperSpeed pairs, because
this MCU has no SuperSpeed to put on them. Stock 213,595, read from JLCPCB's
component API on 2026-09-17.

## A device port that takes no power

VBUS goes to exactly two places: the ESD array's clamp, and PA9. It reaches no
rail, no diode and no regulator. The board is powered from its terminal or from
the daughter-board header, next to a supply that may be at 36 V, and a host
that found itself sourcing any of that would stop being a host.

That decision is what makes this connector's ratings interesting in one
direction only. 20 V is what a Type-C source can be persuaded to deliver, and
the only thing stopping it here is a pair of 5.1 kΩ resistors saying *ordinary
sink, default current*. The connector is built for 20 V anyway, and
`test_usb.py` checks it against the bus voltage rather than trusting the
resistors twice.

## Both CC pins, and why not one resistor

Each CC pin gets its own 5.1 kΩ to ground. Which pin a source sees depends on
which way up the plug went in, so one resistor shared between them makes a port
that works in one orientation and not the other — the exact failure a
reversible connector exists to prevent, reintroduced to save a component.

The CC pins are also the one pair of connector signals that do not pass through
the ESD array, which only has two channels. That is deliberate and it is
checked rather than assumed: a strike arriving on CC finds 5.1 kΩ and a ground
plane, and no silicon at all. `test_usb.py` derives that from the netlist, so a
CC pin later wired to a GPIO — which is how a board gets orientation detection
— stops being exempt and the check says so.

## Figures used

| Figure | Value | Where |
|---|---|---|
| Current rating | 5 A | LCSC's parametric data for C165948 |
| Voltage rating | 20 V | same |
| Contacts | 16, USB 2.0 | same |

The current rating is recorded and deliberately unread — this port draws
nothing — with the reason in `checks/config.py`.

## Pin mapping

KiCad's `Connector:USB_C_Receptacle_USB2.0_16P`, whose pad names are the
specification's own: A1/A12/B1/B12 ground, A4/A9/B4/B9 VBUS, A5 CC1, B5 CC2,
A6/B6 D+, A7/B7 D−, A8/B8 SBU1 and SBU2.

**Both rows carry the same signal**, which is what makes the connector
reversible, and SKiDL joins each pair into one net. Joining them in *copper*
is a fan-out problem the layout has not solved yet: D+ appears twice with a D−
pad between the two, so the link cannot be a straight track. It waits for M8
with the rest of the escapes.

**SBU1 and SBU2 are left unconnected on purpose** — they carry alternate modes
this board has none of — and said so in the design source, rather than left for
a check to ask about two pads with no net.

**Footprint.** KiCad stock
`Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12`, unmodified, which is drawn
for this manufacturer's part by name.

## Needs a human eye

The receptacle's **mounting-shell pads against the board edge**. The footprint
places the connector's mouth at the edge of the outline, and whether the shell
overhangs, sits flush, or needs a notch in the edge cut is a mechanical
question about the enclosure this board goes in, which does not exist yet.
