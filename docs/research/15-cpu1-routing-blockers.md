# What was stopping the last thirty-six connections on cpu1

Written after taking cpu1 from 373 unrouted connections to 36 and then failing
twice, on two different blocks, for the same underlying reason. Both failures
are recorded here rather than worked around, because both are placement
problems wearing routing clothes, and the fix for each is a decision rather
than a technique.

> **This is a snapshot, not the state.** It records the board as it stood
> mid-route, and the resolution of all three blockers is appended at the end.
> cpu1 is fully routed now — `ROUTING` complete, 203 checks, DRC clean, zero
> unconnected — and what it became is in
> [`hw/cpu1/DESIGN-REVIEW.md`](../../hw/cpu1/DESIGN-REVIEW.md).

## The state, at the time

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

Counting it properly, rather than by trying things: in the strip between
x 11 and x 16, where every one of these has to pass, the vias already there
forbid four bands of y, and what is left is

| free band | height | lines |
|---|---|---|
| -6.73 to -4.73 | 2.00 mm | 5 |
| -8.28 to -8.23 | 0.05 mm | 0 |
| -9.23 to -9.92 | 0.69 mm | 1 |

Six lines. Seven static signals and reset need eight. Moving the east-side
decoupling row out by 0.7 mm was tried and gives back nothing: the vias whose
y matters belong to supply pins, and a pin's y does not move.

**The decision this needs:** move the four PWM lines that drop behind the
package. They drop at x 11.9 to 15.2 and run east, and their four vias are what
closes off 2.45 mm of that strip - the whole band from -4.73 to -2.28. Dropping
them at x 17 to 20 instead costs them nothing (they are already running east,
on their own pin lines, on the front) and turns six lines into eleven.

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

## How both were resolved

Both, in the end, went the way this note predicted: by moving a block rather
than by threading around one. Neither took the specific decision proposed
above, and the reason is worth recording.

**Ethernet.** The proposal was to move the CAN and RS-485 transceivers east.
That was surveyed and would have worked, but it costs a working block its
routing and buys one corridor. What the survey also turned up is that the
emptiest copper on this board is *under the package*: the back of an LQFP-144
carries nothing but the supply ring's vias and whatever the static band put
there, and the static band is all in the north half. So three of the four
north-edge RMII lines turn inward instead of outward, drop through inside the
ring, and cross the die. The field buses never had to move.

The six on the west and south edges went the other way - out past the analog
bank on the far side of the analog header, which is the one strip on this board
where nothing else wanted to be. Seven small parts moved out of that strip, and
each of them was there because it landed first, not because it belonged.

**The static band.** The four PWM drops did move east, as proposed, and the
strip behind the package opened up exactly as the arithmetic said it would.

**The DC-link sense line.** Not in this note at all, and the single biggest
obstacle of the three: it rose thirty millimetres east of the comparator it
feeds, putting a back-layer line across the full width of the board at
y -15.65. The rule that placed it - "rise as far east as the last tap" - is
right for the three current sense lines and wrong for the one whose tap is last
on the row. Making the riser a field of the lane rather than something inferred
from the taps freed the channel the reset line now takes.

The lesson the note drew stands, and is the reason all three fixes look alike:
the difficulty is never the route, it is the escape, and the strip was
allocated first-come-first-served. Every fix was to move whichever block got
there first.
