# cpu1 — the control board

The STM32H743ZIT6 board that generates every hard real-time signal, and is later
soldered onto one analog power board. Built one block at a time, and now
**fully routed**: every net is drawn, `board.mk` says `ROUTING := complete`, and
DRC runs in the mode that demands every connection.

The encoder and Hall inputs now reach the digital connector too, which is why
this board is six layers rather than four: see
[`docs/research/16-cpu1-motion-feedback.md`](../../docs/research/16-cpu1-motion-feedback.md)
for the arithmetic. What the encoder *is* — single-ended, RS-422, open
collector — is still the power board's decision; cpu1 carries pins.

**What is on it, and how much of it is drawn, is in
[`review/README.md`](review/README.md)** — the board plotted layer by layer,
every footprint and every net, with the counts read from the board file rather
than written down. `make review BOARD=cpu1` regenerates it. This file is about
*how* the board is built; that one is about what it currently is, and it cannot
go stale.

Nets still waiting for later blocks are *pending*, each naming the block that
will connect it (`_MILESTONES` in [`cpu1.py`](cpu1.py)); the review lists them.

| | |
|---|---|
| Stackup | 6 layers, 1 oz throughout, **PCBWay's own published 1.6 mm build**: 7628 outer prepreg at 0.1855, 0.43 cores, 7628 middle prepreg at 0.175. Picked out of their table because that outer prepreg is identical to the 4-layer spin's, so the controlled-impedance pairs are unchanged — their default 6-layer build uses 2116 at 0.1195 and would have moved every pair |
| Layers | F.Cu signal, In1.Cu ground, **In2.Cu a solid 3V3 plane**, In3.Cu signal, In4.Cu ground, B.Cu signal and the 5 V island — **no split plane anywhere**: the island was on In2 and cut the plane In3 is referenced to, so it moved outward, where it is local copper rather than a reference. A ground via ring on a 14 mm pitch stitches the plane edges |
| Size | 130 × 110 mm — grown from 100 × 80 to hold the Ethernet jack. Four M3 holes, milled as circles on the edge layer so they carry no net and no BOM line |
| MCU | STM32H743ZIT6, LCSC C114408 — **zero stock at both JLCPCB and LCSC** on 2026-09-19; see [its review note](parts/LQFP144/LQFP144.md) |

## The pin map

[`pinmap.py`](pinmap.py) is the single table of what every MCU pin does. It is
checked against ST's own description of the part, vendored in
[`../silicon/STM32H743ZITx/`](../silicon/STM32H743ZITx/SOURCE.md), and it
generates the firmware's
[`board_pins.h`](../../firmware/bsp/amaxa_cpu1/board_pins.h). Edit the table,
never the header.

```sh
make pins BOARD=cpu1           # check the pin map against the silicon
make pins-write BOARD=cpu1     # regenerate the firmware header
```

`make pins` fails if a pin cannot carry the signal it is used for, a digital
function has no alternate-function number, a pin or name is used twice, a
peripheral is used in part (a UART with one line, RMII with eight of nine
signals, a bridge leg with a high side and no low side), a pair meant to be
sampled simultaneously is not on ADC1 and ADC2, ST's data and KiCad's symbol
disagree about the part, or the committed header is not what the table
generates.

87 of the package's 114 I/O pins are used. Both figures are written here and nothing regenerates them — `make pins-write` prints the first and not the second, and no check compares either. This sentence used to claim it was immune to going stale; it is not, unlike [`review/README.md`](review/README.md), which is. Three conflicts shaped the layout,
and the table's docstring records them: Ethernet's CRS_DV and TIM8_CH1N want the
same pin, no 32-bit timer is free for the encoder, and keeping TIM1 where the
NUCLEO has it costs COMP2's external inputs.

## How the MCU core is laid out

Most of it is computed from the netlist and the footprint, not written as
coordinates ([`layout.py`](layout.py), with helpers in
[`../tools/layout_lib.py`](../tools/layout_lib.py)):

- **Supply pins take their plane vias inward.** An LQFP-144 has an 18 mm square
  of empty board inside its pad ring, where no signal will ever escape. Outside
  the ring, vias on neighbouring 0.5 mm-pitch pins collide; inside, they stagger
  in rings — ground at 9.3 mm from the centre, 3V3 at 8.5 mm, and 7.7 mm for a 3V3
  pin beside another.
- **Each supply pin's capacitor goes outward**, turned so its first pad faces the
  pin, with its ground via beyond. Capacitors on neighbouring pins spread apart.

VDDA's filter, both crystals, debug, the indicators and the button are placed by
hand, near the pins they serve.

## Where it stands

Everything on this board is drawn, routed and checked: 197 checks, DRC with
no violations and no unconnected items, gerbers for all six copper layers plus
drill and IPC-D-356, `make reproducible` regenerating the same board, `make
offline` building with every network call refused, both firmware BSPs
compiling, and `NEEDS_A_HUMAN_EYE` and `WAITING_ON_A_DECISION` empty.

**It is not ready to order, and `checks/config.py` says why.** One entry in
`BLOCKING`: nothing adds up what a rail actually carries. Each rail's current
is a declared band that the converter, the fuse and the inductors are sized
against, and what is *on* the rail is a prose comment summed by hand. It has
already failed once - fifteen pull-downs taken from 10 k to 1.2 k added 43 mA
and pushed 3V3 to 806 mA against its own 800, and no check moved.

The converters' capacitance against DC bias was the entry before it. That one
is closed: `capacitors.bias_derating` states what a Class II ceramic loses as
a coefficient on the fraction of its rating it is operated at, every datasheet
minimum on the board is held against the derated value, and the parts that
could not meet theirs went up in voltage rating - which is what lowers the
field - rather than up in count.

The analog inputs' over-voltage was a third and is not any more. The board
used to hand the power board's sensors 5 V through a bead and take their
outputs into pins ST caps at **4.0 V absolute** with no positive-injection
allowance at all, which an op-amp rails past during exactly the over-current
the trip chain exists for. `docs/research/07` called for clamps; they do not
fit, and three positions were tried. The rail is regulated to 3.3 V instead,
so the worst a sensor can rail to is 3.366 V and the fault stops existing.
What it costs is at the connector, and `parts/HDR2X15` says so.

`COMPLETE` was True for a while and that was wrong - not because the board is
bad, but because the gate behind it tested two things and the flag was read as
a claim about six. It runs both ways now: a board that says it is unfinished
has to name what is unfinished, and a board that says it is finished has to
have nothing left in `BLOCKING`.

## What the checks establish

[`checks/test_core.py`](checks/test_core.py) derives everything from ST's
datasheet figures and the parts' own:

| Check | From |
|---|---|
| Every supply pin has its **own** 100 nF within 3 mm, matched one to one | ST pin data, netlist, placed board |
| Bulk: 4.7 µF on 3V3, 1 µF on 3V3 and on VDDA | Datasheet Figure 13 |
| One 2.2 µF on each VCAP pin | Datasheet Table 24 |
| Each crystal sees its specified load, at every corner | Crystal load, capacitor tolerance, and stray — declared for the MCU's two, **measured off the board file** for the PHY's |
| No declared stray is smaller than the copper on its own leg | Track widths and pad areas, against the stackup |
| **Oscillator gain margin at least 5**, both crystals | Datasheet Tables 43–44, crystal ESR and C0 |
| Indicators visibly lit and inside the LED's and the pin's ratings | LED and resistor tolerances, pin limit |
| NRST's 100 nF, BOOT0 and button pull-downs, VDDA fed only through a ferrite | Datasheet Figure 21, netlist |

The gain-margin check chose the crystals. Every in-stock 8 MHz part in 3225 or
HC-49S, and the common 12.5 pF 32 kHz parts, fail it — the latter at a margin of
1.8. Each would start on the bench and might not start cold.

**Nothing is now waiting on an unread datasheet.** Thirteen part libraries
carried a "needs a human eye" marker — a pin-out, a cathode, an exposed pad,
all drawn rather than written. Each document has been fetched, the figure that
settles it rendered, and the crop committed beside the note with the source's
URL and SHA-256: `CONFIRMED_FROM_A_RENDER` in
[`checks/config.py`](checks/config.py), and `tools/datasheet.py` is how.
`NEEDS_A_HUMAN_EYE` is empty and still checked, because the next part added
will land on it.

**Two libraries left that list another way.** `HDR2X26` and `USBC16` carried
the marker and have no `evidence/` directory: their questions were answered by
deciding rather than by reading - the 2×26 header's pin numbering by generating
it from the pin map, and the USB-C shell's overhang by the port not being
exposed. "Each document has been fetched" is true of the thirteen in
`CONFIRMED_FROM_A_RENDER` and was never true of these two, and this paragraph
said fourteen for a while, which was neither number.

`WAITING_ON_A_DECISION` is empty too. It held one entry — whether the USB-C
shell overhangs the board edge, which depends on an enclosure that does not
exist — and that port is not exposed, so the question does not arise. The list
stays, and is still checked, so that a five-minute PDF cannot hide behind it.

ST's AN4938 hardware guide has still not been read, and cannot be from here:
`www.st.com` resolves but every connection to it returns nothing, so the
datasheet above came from LCSC's copy instead. **Nothing on this board depends
on AN4938** — the decoupling is Figure 13 of the datasheet and the VCAP values
are its Table 24, both read and committed as evidence. It is worth a person's
eye before a second spin, not before this one.

## Three things a check cannot be written from a table for

**Where the field buses' ESD protection is.** There is none on the board, and
that is the decision rather than an omission: both transceivers are qualified
on their bus pins, at ±8 kV powered contact and ±18 kV contact, and a TVS in
front of a part rated above the TVS is capacitance on a pair whose impedance
matters. The check walks out from each connector and requires everything a
cable can reach to be a two-terminal passive or to carry a rating — so a
cheaper transceiver fails it, and so would an unrated buffer on the pair.

**Why both cable grounds tie straight to the board's.** Industrial practice
puts 100 Ω there. Each standard states the ground offset a receiver must
tolerate — −2 to +7 V for CAN, −7 to +12 for RS-485 — and these parts are
specified to ±12 V and ±15 V, so the offset that breaks either link is one no
standard requires anybody to survive. A resistor covering more than that has to
dissipate it: at the ±15 V edge, 100 Ω at each end is **2.25 W**.
`parts/SOIC8/SOIC8.md` has the arithmetic and what would change it.

**That pcbnew was correcting the board on the way past.** `LoadBoard`
re-resolves connectivity as it reads, so a via placed on the wrong net inside a
pad came out on the pad's net with no DRC violation — the file the layout wrote
and the file every check reads were not the same file. `tools/fill_zones.py`
now compares the board's own text either side of the step and refuses it if any
via or track moved net.

## Two deviations from Microchip's reference, both by choice

The Ethernet line terminations are now fitted — four 49.9 Ω, which is what
gives the current-mode driver its specified 50 Ω load and the receive pair a
chip-side termination it had none of. Two smaller deviations from Microchip's
Figure 3.23 remain by choice, both written up in
[`parts/QFN24/QFN24.md`](parts/QFN24/QFN24.md): there is no ferrite on the
analog supply, and the magnetics' centre taps sit on the rail rather than on a
bypass to ground.

ST's AN4938 is unread and unreachable from here, and nothing depends on it; the
USB-C shell question is closed because that port is not exposed.

