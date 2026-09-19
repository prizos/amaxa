# What is stopping the last thirty-six connections on cpu1

Written after taking cpu1 from 373 unrouted connections to 36 and then failing
twice, on two different blocks, for the same underlying reason. Both failures
are recorded here rather than worked around, because both are placement
problems wearing routing clothes, and the fix for each is a decision rather
than a technique.

## The state

`ROUTING := incomplete`, DRC clean, 153 checks passing, 36 connections left:

| what | how many |
|---|---|
| Ethernet RMII | 10 |
| the static signals' MCU end | 14 |
| the threshold DAC's I2C | 4 |
| `VREF+`, `BOOT0`, `DAC_TEST`, the reset diode | 4 |
| supply stubs | 4 |

Everything else on the board is routed, and every one of those routes is
generated from pad geometry rather than written out.

## The two blocks that did not land

### Ethernet RMII: three edges, one corner, and a jack in the way

The ten RMII signals leave the package on three different edges - four north,
three west, three south - and all ten have to reach a PHY forty-five
millimetres away in the north-west corner. Between them and it are, in order:
the CAN and RS-485 transceivers with their six signals turning north, the debug
port's three back-layer runs, the boot and LED cluster, the threshold DAC, and
the analog connector, which is a 2x15 on through-hole pins and therefore a wall
on both layers except between two of its rows.

The analog connector turns out not to be the problem. Its fourteen row gaps are
each 0.39 mm of usable width - tight but exact, and the input networks' own
back-layer lanes run at the cells' heights, which the staggered columns put
half a row away from every gap. Ten of the fourteen are free.

The problem is the first six millimetres. Everything that leaves the package's
north edge turns in the same strip, and the four field-bus signals turn north
in a column wall at x -3.8 to -4.7 that runs from y -12 to y -42. Crossing it
needs a front-layer hop, and a hop needs two vias, and there is nowhere to put
them: the corridor between the debug port's front-layer escape and the first
bus column is 0.55 mm wide and a via needs 0.95.

**The decision this needs:** move the CAN and RS-485 blocks east. Both
transceivers sit at x 2 with their signals coming out of the package's east
side and doubling back west to reach them. Moved to x 12-16 they would be
shorter, and the strip north of the package - the only way west for the four
RMII signals on that edge - would be empty. That is a placement change to two
blocks that are already routed, so it is not small, but it is mechanical, and
it is the change the board wants regardless of Ethernet.

### The static signals: a band five deep where seven have to fit

The ten static signals - four ID straps, two relays, two STO feedbacks and two
gate-driver faults - have their MCU pins on four different edges and their pull
resistors in one column on the far side of the board. Sorting them once on the
way out, in the order the resistor column is in rather than the order the pins
are in, makes the whole fan planar: each turns north on its own column and runs
east on its own lane, and nothing crosses anything.

Seven of them have to leave through one band: the gap between the supply ring's
vias and the four PWM lines that drop behind the package. That band is 4.5 mm
tall, which is nine lines at the pitch a via needs, and it also has to carry
reset, which crosses the board in it. Two vias inside it decide the real
answer: the decoupling row's ground via at y -7.75, and SWDIO's, which cannot
move east past x 11.9 without bridging the solder mask between two capacitor
pads. Between them the band is five lines deep, and seven signals plus reset
need eight.

Both relays were moved out through the corner north of the band, which got it
to six. The seventh has nowhere, and every variant tried - moving reset south
past the PWM drops, moving the PWM drops, giving the last signal the corner,
running it on the front - collides with something already there. The work got
to sixteen DRC violations from a clean board and stopped.

**The decision this needs:** one of three. Move the east-side decoupling row
out by a millimetre and a half, which frees SWDIO's line and makes the band
seven deep. Or move the debug port's SWDIO pin, which the pin map allows and
the firmware does not care about. Or give the escape vias their own smaller
size - 0.45 mm on a 0.15 mm drill is inside what the fab quotes - which buys
the 0.025 mm that three of these conflicts are short by.

## The shape of both problems

Neither block is hard to route. Both are hard to *escape*: the difficulty is in
the first ten millimetres, where every net on that edge of the package wants
the same strip, and the strip was allocated first-come-first-served as blocks
landed. The blocks that landed early - the field buses, the debug port, the
decoupling rows - took what they needed and left the ones that landed late with
the remainder.

The generators made this visible rather than causing it: because every route is
computed from pad geometry, moving a block moves its routes, and the cost of
trying a placement is one edit and one DRC run. That is what made it possible
to establish, rather than guess, that the corridor is 0.55 mm and a via is
0.95.
