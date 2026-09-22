#!/usr/bin/env python3
"""
cpu1 — the STM32H743 control board, as a circuit.

Built one block at a time. What exists so far:

- the MCU, with every pin in `pinmap.py` on its own named net and every unused
  I/O pin marked `NC`;
- its core: supply decoupling, the core regulator's capacitors, the filtered
  analog supply, both crystals, reset and boot, the Tag-Connect debug footprint,
  three LEDs, a button and test pads on the console;
- the power block: 9 to 36 V in through a fuse, a reverse-polarity FET and a
  TVS, a 100 V buck to 5 V, a second buck to 3V3, and the series reference that
  drives VREF+;
- the safety chain: the trip latch, the two octal buffers every PWM output
  passes through, and the digital header to the power board;
- the trip comparators: seven of them, their threshold DAC, and the analog
  header the signals they watch arrive on.

Everything a pin will eventually connect to lands in a later block, and until it
does that net is *pending*: `_MILESTONES` below names the block that will
connect each one.

`pinmap.py` is the single table of what each MCU pin does. This file wires the
MCU from it, so a pin cannot be used here that the pin map, and therefore the
firmware header and the silicon checks, do not know about.

Component values come from ST's datasheet for the part (DocID030538 Rev 3) and
from each part's own listing; `parts/<LIB>/<LIB>.md` records which, and
`checks/test_core.py` re-derives what depends on them.

Run it with `make -C hw build BOARD=cpu1`.
"""

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tools"))
sys.path.insert(1, str(HERE))

# skidl_design first: it tells SKiDL where KiCad's symbol libraries are.
from skidl_design import part, run  # noqa: E402
from skidl import POWER, Net  # noqa: E402

import mcu_pins  # noqa: E402
import parts  # noqa: E402
from stm32 import Silicon  # noqa: E402

PINMAP = mcu_pins.load("cpu1")

# What the board is designed to, rather than what any one part is.
INTENT: dict[str, tuple[float, float]] = {
    # What the board accepts at its terminal. 24 V nominal industrial, +50 %,
    # down to a 12 V battery at the end of its discharge.
    "input.voltage": (9.0, 36.0),
    # Where the input undervoltage lockout must sit: above the voltage at which
    # nothing useful runs, and below the lowest input the board claims to take,
    # so it starts at 9 V rather than on the way to it.
    "input.lockout": (7.0, 8.9),
    # The logic rail, 3.3 V ±5 %. The MCU's own limits are checked against it.
    "rail.3v3.voltage": (3.135, 3.465),
    # What each rail is designed to deliver, to its *own* loads. The 3V3 buck
    # runs from the 5 V rail, so everything the 3V3 rail carries appears again
    # on the 5 V one; `_reflected_current` in test_power.py adds it, and the
    # regulator, the fuse and the FET are sized against the sum. Budgeting
    # them separately is how a 1 A converter came to be asked for 1.36 A.
    #
    # **What is on each rail used to be an itemised list here, summed by
    # hand.** It is not any more:
    # `test_each_rail_carries_no_more_than_it_is_budgeted` walks the netlist -
    # every part's declared supply current attributed to the pin it draws it
    # from, every resistor chain with a DC path to ground at the rail that
    # feeds it, and every promise a block makes to the far side - and prints
    # the itemisation on every run. The comment could not be wrong in a way
    # anything noticed, and it was: it carried 45 mA for the RS-485
    # transceiver, which is below that part's bus current alone.
    #
    # Two numbers in that sum deserve to be read before the band is trusted:
    # the PHY's 102 mA is a *typical* - its datasheet has no maximum supply
    # current anywhere - and the comparators' 5 mA is a 25 degC figure rather
    # than one over temperature. Both are recorded at their parts.
    "rail.3v3.current": (0.0, 0.8),
    "rail.5v.voltage": (4.75, 5.25),
    # The 5 V rail's own loads, on the same terms: the check adds them up and
    # prints them. The reference's 25 mA used to be itemised here and is not
    # any more - it moved to 3V3 so that VREF+ cannot exist before VDDA does,
    # and the hand-written entry stayed behind for a while, which is the other
    # way a summed comment goes wrong.
    "rail.5v.current": (0.0, 0.20),
    # What the analog header is allowed to draw from 3V3A, which is what the
    # 5 V rail's budget above carries for it, through the LDO.
    "analog.supply_current": (0.0, 0.05),
    # And the same promise for VREF+, which had none. It leaves on one pin of
    # the analog connector with no series element, and the power board's
    # sensors are ratiometric to it - so something out there draws from it and
    # nothing said how much. Five milliamps is fifty millivolts of dropout off
    # the reference's own curve, against the 129 mV of headroom 3V3 leaves at
    # its low corner; the part could give 25 mA and the rail could not.
    "vref.supply_current": (0.0, 5e-3),
    # The highest voltage a sensor on the far side of the analog connector may
    # ever present to one of the fast inputs, **including while it is
    # failing**. These pins are TT_xx analog inputs and ST's Table 20 caps
    # them at 4.0 V absolute - not VDDA plus a diode drop, which is the number
    # everybody reaches for: Table 21 rates injection current on them at minus
    # five to **plus nought** milliamps, so there is no positive-injection
    # path at all and the limit is a voltage with nothing below it.
    #
    # **This used to be a requirement on a board that does not exist yet**,
    # because the rail this board handed those sensors was 5 V through a bead
    # and an op-amp rails to its own supply. `docs/research/07` answered it
    # with "RC corner ~1-2 MHz **plus clamps**"; the RC is built and the
    # clamps do not fit - a clamp has to sit on the sense net ahead of the
    # series resistor, and searching the whole analog region for somewhere a
    # SOT-363 and its two vias would go found nothing. Three positions were
    # tried and built: the strip between the header and the first column is
    # two millimetres wide, the band at y -25.8 is the channel the RMII
    # crosses the board in, and the band below the comparators collides with
    # the trip diodes and the jack's mounting pad.
    #
    # It is not a requirement on the far side any more. The analog rail is
    # regulated to 3.3 V, so what a sensor can rail to is a number this board
    # sets, and `test_no_analog_input_may_be_presented_more_than_its_pin_allows`
    # derives this band's ceiling from that rail rather than taking it on
    # trust. What remains on the power board is narrower and ordinary: do not
    # drive these pins from the 12-15 V aux.
    "analog.input_voltage_max": (0.0, 4.0),
    # How far the analog rail may sit from its nominal 3.3 V by the time it
    # reaches the connector. The sensors on the far side are ratiometric to
    # VREF+ so their *reading* does not depend on this, but their own headroom
    # is specified from their supply, and it is also what bounds how high they
    # can rail into an analog pin. A tenth of a volt: the LDO's own 2 % is
    # 66 mV of it and the copper between it and the connector is the rest.
    "analog.supply_drop": (0.0, 0.1),
    # How far from the pin it serves a local capacitor may sit. It was a bare
    # 3.0 in `checks/test_core.py`, used by the MCU's decoupling check alone;
    # it is here because a second check wants the same idea for the analog
    # regulator's input capacitor, and two copies of a number is how the trip
    # budget ended up in two files. Three millimetres is what "beside it"
    # means for a 0402 next to a fine-pitch package: the capacitor's own body
    # is 1 mm, so this is about one part's width of track at each end.
    "layout.decoupling_reach": (0.0, 3.0),
    # What each conversion is assumed to manage, end to end. Nothing on the
    # board measures it either; it is what the fuse, the FET and the inductors
    # are sized against, and it is the first thing to measure at bring-up.
    "power.efficiency": (0.80, 0.95),
    # The 3V3 buck's own efficiency, which decides how much of the 3V3 budget
    # lands back on the 5 V rail. A synchronous buck at 5 V in, 3.3 V out and
    # a few hundred milliamps sits near 90 %; the low end is the one that
    # matters here and it is deliberately pessimistic.
    "buck3v3.efficiency": (0.85, 0.93),
    # The 100 V buck's switching frequency, set by one resistor. High enough for
    # a small inductor, low enough that switching losses at 36 V stay modest.
    "buck5.switching_frequency": (350e3, 450e3),
    # Pin and board capacitance each crystal's load capacitors sit alongside.
    # ST's datasheet offers 10 pF as a rough estimate and says nothing about the
    # OSC pins themselves, so these are assumed, and they are the thing to
    # measure at bring-up - the oscillator's frequency error is what they move.
    # The floors are not free to be anything: the board file says what the
    # tracks and pads on each leg are worth, and a check holds each floor above
    # its own copper. The LSE's was 2 pF against 2.23 pF of copper on the
    # longer leg, which is a corner the board could not reach.
    #
    # **And the LSE's floor is now thin enough to be worth measuring.** Once
    # the pad model stopped assuming fringing away, LSE_IN's copper came out
    # at 2.34 pF, which leaves 0.16 pF of the 2.5 for the MCU's own OSC pin -
    # and a pin is picofarads, not tenths. Either this floor is too low or the
    # 6.8 pF load capacitors are too large; raising the floor to a physical
    # 3.0 pF makes the load check fail at 6.275 pF against a 6 pF cut, which
    # says the capacitors. What it cannot say is by how much, because the one
    # number that would settle it - ST's capacitance for the OSC pins - is not
    # in the datasheet. It is the first thing to measure on the 32 kHz
    # oscillator at bring-up, and the frequency error is what shows it.
    "hse.stray_capacitance": (3e-12, 5e-12),
    "lse.stray_capacitance": (2.5e-12, 4.5e-12),
    # An indicator LED that can be seen in a lit room, at the least current the
    # tolerances allow.
    "leds.visible_current": (0.5e-3, 20e-3),
    # What the power board's fault outputs may sit at while asserting. This is
    # an interface promise, not a measurement: the fault lines are open-drain,
    # and the trip bus reaches them through a Schottky, so what they pull down
    # to plus a diode drop has to still read as a low here.
    "header.fault_output_low": (0.0, 0.4),
    # The dead time firmware will insert between a bridge's two sides. Not a
    # board parameter either, but everything the board adds between an MCU pin
    # and a gate has to be small against it, and this is what "small" is
    # measured against.
    "pwm.dead_time": (0.5e-6, 5e-6),
    # How well a trip point has to be known. It is a protective limit, not a
    # measurement - you set it above the working maximum and what matters is
    # that it is above it and below what breaks. Saying so is what makes the
    # DAC's reference choice a decision rather than an oversight.
    #
    # **Twelve per cent, and it read ten while three terms were missing.** At
    # a quarter of full scale, which is the lowest threshold this board is
    # designed to set, the budget is 5.0 % from the 3V3 rail the DAC uses as
    # its reference, 2.4 % from the DAC's own offset, 1.5 % from the
    # comparator's offset and hysteresis, 1.3 % from the DAC's nonlinearity
    # and 1.25 % from its gain error - 11.5 % in all. Only the first and third
    # were being added; the MCP4728's own accuracy was not in parts.py.
    #
    # What the power board has to do with that: set each trip at least an
    # eighth below what breaks and an eighth above the working maximum.
    #
    # The rail term is the one worth attacking and neither obvious answer
    # works. The rail's *achieved* static band is ±2.45 %, but the declared
    # ±5 % is deliberate headroom for load steps and ripple, so tightening the
    # declaration would be spending margin that is doing a job. The DAC's
    # internal 2.048 V reference removes the rail term and makes every
    # millivolt term a larger share of a smaller full scale, which is worse.
    # Referencing the thresholds to VREF+, so a trip is ratiometric with the
    # measurement the way the ADC channels are, would do it - and the MCP4728
    # cannot take an external reference. That is a part change, not a tweak.
    "trip.threshold_tolerance": (0.0, 0.12),
    # The lowest threshold this board is designed to be able to set, as a
    # fraction of the DAC's full scale. It matters because the fixed errors -
    # the comparator's offset, the DAC's offset, its nonlinearity - are
    # millivolts, and a millivolt is a larger share of a small threshold. A
    # trip point sits above the working maximum of whatever it watches, so a
    # board wanting one below a quarter of full scale has a sense gain that is
    # wrong by four, not a threshold problem.
    "trip.threshold_floor": (0.25, 1.0),
    # How long a trip may take, from the current leaving its sensor to the
    # buffer letting go. It is set by how long a half bridge survives a
    # shoot-through and by nothing on this board, which is why it is stated
    # here rather than worked out from the parts: the parts are chosen to fit
    # inside it. Two check files used to carry their own copy of the number.
    "trip.budget": (0.0, 50e-9),
    # How much of that budget the tap network in front of the comparators may
    # cost. This used to say "kept back for a filter this board has not
    # drawn", which was wrong twice over: the filter was drawn - the ADC's own
    # capacitor sits on the node the comparators watch - and it was costing
    # 20 ns of the 20 without anybody having measured it. It is measured now,
    # in `test_a_trip_stops_the_outputs_inside_the_budget`, and spent out of
    # the budget like every other term. Four tenths is the ceiling on it.
    "trip.reserved_share": (0.0, 0.4),
    # What DC bias takes off a Class II ceramic, as a coefficient on the
    # fraction of its rating the part is operated at: a capacitor sitting at
    # a fifth of its rated voltage is assumed to have lost a fifth of its
    # capacitance. It is applied to every minimum a datasheet asks for and to
    # no maximum, because a capacitor does not gain.
    #
    # **It is an assumption, and it is written here so that it is one thing
    # somebody owns rather than a silence.** The effect is real and large -
    # the Ethernet reset capacitor's delay is already argued with its
    # capacitance "derated to a third by its own DC bias" - and the data that
    # would settle it is not obtainable: Samsung's CL21/CL31 datasheets, TDK's
    # C-series catalogue and Murata's GRM catalogue were all fetched and read,
    # and not one of them plots capacitance against bias for the part it
    # describes. That data lives in each maker's online tool, which
    # `make offline` cannot reach and which is not a document to cite.
    #
    # A flat derating was the first attempt and it was worse than the gap: at
    # a flat half, the 3V3 converter's 20-68 uF window becomes unsatisfiable,
    # because the three capacitors needed at the bottom exceed the ceiling at
    # the other tolerance corner. Proportional to the field is the right
    # shape - it is the field that depolarises the dielectric - and it is what
    # makes the fix a voltage rating rather than a bigger pile of parts.
    #
    # **It is the first thing to measure on an assembled board**, and until
    # then every rail's capacitance is known to be at least what the checks
    # say and no better.
    "capacitors.bias_derating": (0.0, 1.0),
    # How much of a part's own rating this board will use. Half is what a
    # 0402 in still air is worth, and it applies to every rating that is a
    # thermal one - a resistor's power, a ferrite's current. It was written
    # out in three check files, which is how `trip.budget` got here too.
    "parts.derating": (0.0, 0.5),
    # The air this board sits in. Nothing declared one, and three separate
    # things only mean anything against a number: a Schottky's reverse leakage
    # runs over two decades across the range its own datasheet plots and sets
    # the trip bus's noise margin; the Ethernet jack is graded zero to seventy
    # and nothing compared that with anything; and the MCU has to get rid of
    # what it dissipates.
    #
    # **Forty-five is what the package leaves, and it is a real constraint on
    # where this board can live.** ST's Section 7.9 gives the equation and
    # Tables 126 and 22 give both figures: 43.7 degC/W for the LQFP-144 20x20
    # and 125 degC at the junction. The 3V3 rail budgets the MCU at Table 30's
    # 500 mA - 400 MHz, VOS1, every peripheral on - which at the rail's high
    # corner is 1.73 W and seventy-six degrees of rise. That leaves 49 degC of
    # ambient, and forty-five is that with a few degrees in hand.
    #
    # Forty-nine is what the arithmetic leaves exactly; forty-five is that
    # with four degrees in hand, which is the number to quote. (Three comments
    # around this board gave three different figures for it - 53, 50 and 49 -
    # because each had done the division with a different one of the rail's
    # corners.)
    #
    # It is lower than the seventy the jack would have allowed, and lower than
    # a cabinet beside a motor drive is likely to be. Raising it means
    # justifying a current below ST's worst case, or getting the heat out of
    # the package some other way; either is a decision, and the point of
    # declaring this is that the decision now has to be made rather than
    # discovered.
    "environment.ambient": (0.0, 45.0),
    # What the power board may hang on one gate line, at the connector. It
    # matters because of what happens at a trip: the buffers go to high
    # impedance and the line is then discharged by its pull-down alone, so
    # whatever the far side presents is in the trip budget. This board's own
    # copper is about 4 pF per line. Ten is the far side's share: this board is
    # soldered onto the power board, so there is no cable - a gate driver's
    # input pin and a short track on the other side of the header fit inside
    # it, and anything that needs a flying lead does not.
    "header.gate_line_capacitance": (0.0, 10e-12),
    # What the digital connector may draw from the 3V3 pin it carries. It was
    # a line in the budget comment above and nothing else, which is the shape
    # of problem this whole block has: a number somebody typed into prose and
    # summed by hand. Declared here, it is read by
    # `test_each_rail_carries_no_more_than_it_is_budgeted` off the netlist.
    "header.supply_current": (0.0, 0.1),
    # And what counts as low there. This used to be read off the *latch's*
    # V_IL, 0.8 V, for a net that never reaches the latch - it crosses the
    # header into a gate driver. What a gate driver calls a low is the far
    # side's number, so it is an interface promise like the fault line's
    # 0.4 V beside it. 0.8 V is the strictest thing a 3.3 V CMOS input is
    # likely to ask for, so the figure does not move; what changes is that it
    # is now this board asking rather than the wrong datasheet answering.
    "header.gate_line_low": (0.0, 0.8),
    # Where each kind of channel rolls off. The fast ones carry what the control
    # loop reads every PWM cycle: low enough to stop the switching node aliasing
    # into the measurement, high enough that the measurement is of now.
    "adc.fast_corner": (1.0e6, 2.0e6),
    "adc.slow_corner": (1.0e3, 20.0e3),
    # The sampling window firmware will use, and what the measurement is worth.
    # 8.5 ADC cycles at 36 MHz is the shortest that makes sense for a current
    # read inside a PWM period; the band's low end is what every settling check
    # works to.
    "adc.sampling_time": (236e-9, 458e-9),
    "adc.resolution_bits": (12.0, 12.0),
    "adc.settling_error": (0.0, 0.5),
    # How long a board-ID strap may take to settle. It is not a corner, which
    # is why these two channels sit outside the slow band: a strap is a DC
    # level read once at start-up, and the only thing it has to do is be right
    # by the time firmware looks. Fifty milliseconds is invisible against a
    # power-up. The network as built takes 10.9 ms, so the band is a factor of
    # 4.6 above it - not the two hundred an earlier version of this comment
    # claimed, which made the margin read as uncritical when it is within a
    # factor of five.
    "adc.strap_settling": (0.0, 50e-3),
    # What the power board must drive these pins from: an op-amp output, which
    # is what a current sensor's output stage is. The filter's corner depends on
    # this as much as on its own resistor - a sensor with a hundred ohms of
    # output impedance moves the corner by a decade with nothing on this board
    # changing - so it is an interface promise rather than an assumption, and
    # every corner and settling figure here is worked with it included.
    "header.source_impedance": (0.0, 2.0),
    # The board-ID pins are the exception, and the pin map says so in as many
    # words: "resistor divider on the power board". A divider cannot present
    # two ohms without drawing hundreds of milliamps, so holding those two
    # channels to the figure above was asking the power board for something
    # the same repository had already told it not to build. A strap divider
    # that loads 3V3 at a fraction of a milliamp is several kilohms, and this
    # is the band that admits one - comfortably inside the MCU's own 50 k
    # ceiling on what an ADC input may look back into.
    "header.strap_impedance": (0.0, 10e3),
    # What a terminated bus must present between its two wires, at each end.
    # ISO 11898 and TIA-485 both ask for the cable's characteristic impedance,
    # which for the twisted pair either of them runs on is 120 ohm nominal; the
    # band is what a real cable and a real resistor tolerance come to.
    "bus.termination": (108.0, 132.0),
    # The CAN bit rate arbitration happens at. It is a firmware choice, and the
    # reason it is written down here is that arbitration is the one part of a
    # CAN frame where a bit must reach the far end of the cable and come back
    # inside one bit time, so it is what the transceivers' loop delay is spent
    # against. The data phase is faster and does not arbitrate.
    "can.arbitration_rate": (125e3, 500e3),
    # How much of that round trip the two transceivers themselves may take,
    # leaving the rest for the cable and for the far node to make up its mind.
    # A quarter is the share TI's own bit-timing examples work to.
    "can.transceiver_delay_share": (0.0, 0.25),
    # The split termination's midpoint capacitor, as the impedance it presents
    # to common mode at the fastest bit rate the transceiver can signal at,
    # relative to the half termination it sits behind. Small means the common
    # mode sees a path to ground where the differential signal sees none, which
    # is the whole reason the termination is split.
    "can.common_mode_shunt": (0.0, 0.3),
    # What USART2 will clock the RS-485 pair at. As with the CAN rate this is a
    # firmware choice written down so the part can be held to it.
    "rs485.baud": (9600.0, 500e3),
    # What a USB 2.0 cable's pair is, and what the spec allows a board to
    # present to it: 90 ohm differential, plus or minus 15 %.
    "usb.differential_impedance": (76.5, 103.5),
    # The pull-down a sink puts on both CC pins so a source knows something is
    # there and that it wants default current. USB Type-C calls it Rd, 5.1 kohm
    # nominal; the band is the tolerance the specification allows.
    "usb.cc_pulldown": (4.08e3, 6.12e3),
    # The bus voltage a source may put on VBUS. This board senses it and does
    # nothing else with it, so this is the figure everything on that net has to
    # survive rather than a rail the board runs from.
    "usb.vbus_voltage": (4.4, 5.25),
    # What the transceiver drives the pair through, and how fast a full-speed
    # edge may be. Both are the USB 2.0 specification's, and together they say
    # how much capacitance the pair can afford to carry.
    "usb.driver_impedance": (28.0, 44.0),
    "usb.rise_time": (4e-9, 20e-9),
    # How much of that edge the protection on the pair may spend. A tenth is
    # the point at which the array stops being free and starts being a filter.
    "usb.protection_edge_share": (0.0, 0.10),
    # How far apart the pair's two halves may end up, as a share of the fastest
    # edge they carry. This is not a timing budget - a full-speed bit is eighty
    # nanoseconds and nothing here threatens it - it is a radiation one: a pair
    # whose halves arrive at different times is a pair that has turned some of
    # its signal into common mode, and common mode on a cable is an antenna.
    "usb.skew_share": (0.0, 0.01),
    # What a strike on the cable has to find survivable. IEC 61000-4-2 level 4
    # is 8 kV by contact, which is the level anything with a connector on the
    # outside of a machine is expected to meet.
    "usb.esd_level": (8e3, 15e3),
    # The same level, asked of the field buses, and for the same reason: CAN
    # and RS-485 leave this board on a cable that a person can touch. Neither
    # carries an external protection device, because neither needs one - both
    # transceivers are qualified on their bus pins, and the check below is
    # what holds that. The CAN part's qualification is SAE J2962-2 per ISO
    # 10650 rather than IEC 61000-4-2, a powered discharge rather than an
    # unpowered one; the two are not the same test, and that is recorded in
    # parts/SOIC8/evidence rather than smoothed over here.
    "bus.esd_level": (8e3, 18e3),
    # What each bus standard requires a receiver to tolerate between the two
    # ends' grounds: ISO 11898-2 for CAN, TIA-485 for RS-485. Both connectors
    # carry the cable's reference straight onto this board's ground with no
    # resistor in the way, which is only safe because both transceivers are
    # specified well past these - and a check is what holds that true.
    "can.common_mode_required": (-2.0, 7.0),
    "rs485.common_mode_required": (-7.0, 12.0),
    # And how much wider than that a transceiver has to be for the hard tie
    # to be the right call. The argument is *margin* - "both parts here are
    # specified well past it" - and a strict inequality states none: a part
    # at -7.01 V would have passed with ten millivolts and the tie would have
    # been justified by nothing. Half again is what these two clear
    # comfortably (2.7x for the CAN part, 1.6x for the RS-485 one) and is
    # about where "well past" stops being a fair description.
    "bus.common_mode_margin": (1.5, 4.0),
    # What IEEE 802.3 allows the link's clock to drift by, end to end. The
    # PHY's datasheet then splits it into tolerance, stability and ageing.
    "ethernet.clock_budget": (0.0, 50e-6),
    # What 100BASE-TX runs on, between the PHY and the magnetics: 100 ohm
    # differential, with the tolerance IEEE 802.3 allows the cable itself.
    "ethernet.differential_impedance": (85.0, 115.0),
    # How slow 100BASE-TX's own edges are, and how much of one the two halves
    # of a pair may be apart. As with USB this is not a timing budget - the
    # receiver equalises far worse - it is how much of the signal is allowed to
    # become common mode, which is what leaves on the cable.
    "ethernet.rise_time": (3e-9, 5e-9),
    # And how much of each half has to be beside its partner at all.
    #
    # The share above is the physics - a discontinuity much shorter than the
    # distance an edge travels while it rises is electrically short - and on
    # these routes it is **slack by a factor of two**: a tenth of a 3 ns edge
    # is 48.7 mm and the longest half of either pair is 24.7 mm, so nothing
    # a pair could do would breach it. A pair with the two halves on opposite
    # corners of the board would pass. It is worth keeping and it cannot fail.
    #
    # This one can. It is a ratchet rather than a derivation: 35 % is just
    # under what this placement achieves - 50.9 % and 39.7 % on the longer
    # half of each pair, limited by the jack's pad pitch and the crossing -
    # so any change that makes a pair less of a pair fails here and has to be
    # argued for.
    "ethernet.coupled_fraction": (0.35, 1.0),
    "ethernet.skew_share": (0.0, 0.03),
    # What has to stand between the cable and the rest of the machine. IEEE
    # 802.3 asks 1500 V rms, and the jack's magnetics are the only barrier.
    "ethernet.isolation": (1500.0, 4000.0),
    # How far a signal changing layer may be from the nearest capacitor tying
    # the ground plane to a supply plane. The front of this board is referenced
    # to ground and the back to the supply islands, so every via between them
    # leaves a return current to cross, and those capacitors are the only
    # crossings. The number is the detour, which is the loop, which is what
    # radiates.
    # Ten millimetres, not the five a fast edge would like: the fifteen
    # buffered outputs dip under the digital connector, and the nearest board
    # anybody can reach from there is beyond it. At the buffers' three
    # nanosecond edges the knee is near 120 MHz, where a wavelength in this
    # laminate is over a metre, so the detour is a hundredth of one - short
    # enough that the loop it makes is the smallest thing in that corner.
    "routing.reference_change_distance": (0.0, 10.0),
    # How far above the fabricator's floor the board's own copper has to sit.
    # `fab/pcbway.kicad_dru` says it plainly - "these are the fabricator's
    # floor, not a design target. A board that only just clears them is one
    # the fab can make, not one that will come back reliably" - and DRC
    # compares with `min`, so equality passes and says nothing. A fifth is the
    # smallest margin that means anything against etch and registration
    # spread; the routing grid already gives most of this board a quarter to
    # three quarters more than the floor, so what this catches is the copper
    # that was placed by hand and never checked against anything but DRC.
    "routing.clearance_over_floor": (1.2, 2.0),
    # The fastest edge any track on this board carries, for working out what
    # one track couples into another. The buffers' outputs are the quickest
    # thing here at about three nanoseconds and the RMII is slower again, so
    # one nanosecond is below anything a part on this board specifies -
    # deliberately, because coupling rises as the edge shortens and the
    # comparator inputs have six millivolts to spend.
    "trip.aggressor_edge": (1e-9, 3e-9),
    # The tracks from a surface pad down to its plane via. Inductance in series
    # with whatever that pad was decoupling; a pad that needs more than this
    # wants moving rather than reaching for.
    "routing.stub_length": (0.0, 3.5),
}

# Which later block connects the other end of each net. Matched in order; a net
# matching none of these is an error, so a new pin cannot slip in unexplained.
_MILESTONES = [
    (r"^(FAST1|FAST2|FAST3|FAST4|FAST5|FAST6|FAST7|FAST8|SLOW\d|BOARD_ID\d|COMP_FAST4|DAC_TEST)$",
     "M6: the ADC input networks and comparator taps"),
    (r"^\w+_SENSE$",
     "M6: the anti-alias filter between this and the ADC pin it belongs to"),

]


# Nets this file already connects at both ends. Everything else has to name the
# block that will, so a pin cannot be added without saying where it goes.
_CONNECTED = re.compile(
    r"^(SW\w+|HSE_\w+|LSE_\w+|CONSOLE_\w+|LED_\w+|BUTTON|BOOT0|NRST|VDDA|VCAP\d"
    r"|PWM\w+|TRIP\w+|FAULT\d_N|GATE_ENABLE|RELAY\d|STO\d_FEEDBACK|ID_STRAP\d"
    r"|\w+_SENSE|DAC_S\w+|CAN_\w+|RS485_\w+|USB_\w+|ENC_\w+|HALL_\d"
    r"|ETH_\w+"
    r"|FAST1|FAST2|FAST3|FAST4|FAST5|FAST6|FAST7|FAST8|SLOW\d|BOARD_ID\d|COMP_FAST4|DAC_TEST)$"
)


def waiting_for(net: str) -> str:
    for pattern, milestone in _MILESTONES:
        if re.match(pattern, net):
            return milestone
    raise ValueError(f"net {net} has no milestone that connects it")


def build() -> Net:
    silicon = Silicon(PINMAP.PART)
    mcu = part(parts.MCU_H743, "mcu", "U1")
    by_number = {pin.num: pin for pin in mcu.pins}

    def pins_named(name: str) -> list:
        return [by_number[n] for n in silicon.pins[name].positions]

    # The rails. Every regulator reaches its rail through an inductor, and an
    # inductor is passive, so ERC cannot see that anything drives these nets.
    # It does - power_block() below - and the drive is declared here.
    v3v3 = Net("3V3")
    gnd = Net("GND")
    v3v3.drive = POWER
    gnd.drive = POWER

    # VBAT and USB's supply straight from 3V3, and PDR_ON high to keep the
    # internal reset supervisor on: decisions, not placeholders.
    for name in ("VDD", "VBAT", "VDD33_USB", "PDR_ON"):
        for pin in pins_named(name):
            v3v3 += pin
    # One ground. Analog is kept apart by placement, not by splitting the plane.
    for name in ("VSS", "VSSA"):
        for pin in pins_named(name):
            gnd += pin

    nets = {}
    for name, net in (("VDDA", "VDDA"), ("VREF+", "VREF+"), ("BOOT0", "BOOT0"), ("NRST", "NRST")):
        nets[net] = Net(net)
        nets[net].connect(*pins_named(name))
    for index, pin in enumerate(pins_named("VCAP"), start=1):
        nets[f"VCAP{index}"] = Net(f"VCAP{index}")
        nets[f"VCAP{index}"].connect(pin)

    used = set()
    for p in PINMAP.PINS:
        # Two pins may share one node, so the net may already exist. Built by
        # hand rather than with setdefault, which would construct a second Net
        # every time and leave it dangling.
        if p.net_name not in nets:
            nets[p.net_name] = Net(p.net_name)
        nets[p.net_name].connect(by_number[silicon.position(p.pin)])
        used.add(p.pin)

    mcu_core(silicon, mcu, by_number, v3v3, gnd, nets)
    power_block(v3v3, gnd, nets)
    safety_chain(v3v3, gnd, nets)
    analog_input(nets["5V"], gnd, nets)
    trip_comparators(v3v3, gnd, nets)
    adc_inputs(v3v3, gnd, nets)
    field_buses(v3v3, gnd, nets)
    usb(v3v3, gnd, nets)
    ethernet(v3v3, gnd, nets)
    plane_stitching(v3v3, gnd)

    # Unused I/O is left unconnected on purpose, and said so. Firmware sets these
    # to analog mode, the lowest-leakage state.
    for name in sorted(set(silicon.io_pins) - used):
        for pin in pins_named(name):
            pin += NC  # noqa: F821 - SKiDL puts NC in builtins

    return v3v3


def mcu_core(silicon, mcu, by_number, v3v3, gnd, nets) -> None:
    """Everything the MCU needs before it will run, and nothing it only uses."""

    def pin_number(name: str) -> list[str]:
        return silicon.pins[name].positions

    # One 100 nF at every supply pin, named for the pin it serves, so placement
    # can find it and the decoupling check can pair it back. Datasheet
    # Figure 13: N x 100 nF plus one 4.7 uF on VDD.
    for name in ("VDD", "VDD33_USB", "VBAT"):
        for number in pin_number(name):
            cap = part(parts.CAP_100N_0402, f"core.dec.p{number}", f"C{100 + int(number)}")
            v3v3 += cap[1]
            gnd += cap[2]
    bulk = part(parts.CAP_4U7_0603, "core.bulk", "C1")
    v3v3 += bulk[1]
    gnd += bulk[2]
    usb_bulk = part(parts.CAP_1U_0402, "core.usb_bulk", "C2")
    v3v3 += usb_bulk[1]
    gnd += usb_bulk[2]

    # The core regulator's capacitors: 2.2 uF, ESR under 100 mOhm, on each VCAP
    # pin. Datasheet Table 24.
    for index, number in enumerate(pin_number("VCAP"), start=1):
        cap = part(parts.CAP_4U7_0402, f"core.vcap.p{number}", f"C{2 + index}")
        nets[f"VCAP{index}"] += cap[1]
        gnd += cap[2]

    # The analog supply, through a ferrite from the logic rail, with 1 uF and
    # 100 nF at the pin. One ground: the ADCs' return is the plane, and analog
    # parts are kept apart by where they sit, not by a split.
    bead = part(parts.FERRITE_600R_0402, "core.vdda.bead", "FB1")
    v3v3 += bead[1]
    nets["VDDA"] += bead[2]
    # A bead is passive, so ERC cannot see that the rail behind it drives VDDA.
    # It does: the drive is declared here, on the one net that needs it.
    nets["VDDA"].drive = POWER
    for address, spec, ref in (
        ("core.vdda.c1u", parts.CAP_1U_0402, "C5"),
        (f"core.dec.p{pin_number('VDDA')[0]}", parts.CAP_100N_0402, f"C{100 + int(pin_number('VDDA')[0])}"),
    ):
        cap = part(spec, address, ref)
        nets["VDDA"] += cap[1]
        gnd += cap[2]

    # VREF+ is a supply pin like any other as far as decoupling goes: 100 nF at
    # the pin, named for it so placement and the decoupling check find it, and a
    # 1 uF beside it. What drives it is the reference in power_block().
    for address, spec, ref in (
        (f"core.dec.p{pin_number('VREF+')[0]}", parts.CAP_100N_0402, f"C{100 + int(pin_number('VREF+')[0])}"),
        ("core.vref.c1u", parts.CAP_1U_0402, "C11"),
    ):
        cap = part(spec, address, ref)
        nets["VREF+"] += cap[1]
        gnd += cap[2]

    # 8 MHz crystal and its load capacitors. No series resistor: the drive
    # level is well inside the crystal's 200 uW, and the check says whether the
    # gain margin needs one.
    hse = part(parts.XTAL_8M, "core.hse.crystal", "Y1")
    nets["HSE_IN"] += hse[1]
    nets["HSE_OUT"] += hse[2]
    for address, net, ref in (("core.hse.c_in", "HSE_IN", "C6"), ("core.hse.c_out", "HSE_OUT", "C7")):
        cap = part(parts.CAP_8P2_0402, address, ref)
        nets[net] += cap[1]
        gnd += cap[2]

    # 32.768 kHz crystal. Its pins 2 and 3 are internal and must not be
    # connected - Epson's datasheet says so in as many words.
    lse = part(parts.XTAL_32K, "core.lse.crystal", "Y2")
    nets["LSE_IN"] += lse[1]
    nets["LSE_OUT"] += lse[4]
    lse[2] += NC  # noqa: F821
    lse[3] += NC  # noqa: F821
    for address, net, ref in (("core.lse.c_in", "LSE_IN", "C8"), ("core.lse.c_out", "LSE_OUT", "C9")):
        cap = part(parts.CAP_5P1_0402, address, ref)
        nets[net] += cap[1]
        gnd += cap[2]

    # Reset: the internal 30-50 k pull-up plus 100 nF, datasheet Figure 21.
    nrst_cap = part(parts.CAP_100N_0402, "core.nrst.cap", "C10")
    nets["NRST"] += nrst_cap[1]
    gnd += nrst_cap[2]

    # Boot from flash unless a probe or a bridge on the pad says otherwise.
    boot_pull = part(parts.RES_10K_0402, "core.boot0.pulldown", "R1")
    nets["BOOT0"] += boot_pull[1]
    gnd += boot_pull[2]
    nets["BOOT0"] += part(parts.TEST_PAD, "tp_boot0", "TP1")[1]

    # SWD on a Tag-Connect footprint: no connector fitted, the cable's pogo pins
    # land on the pads.
    swd = part(parts.TAG_CONNECT, "core.swd", "J1")
    v3v3 += swd["VCC"]
    gnd += swd["GND"]
    nets["SWDIO"] += swd["SWDIO"]
    nets["SWCLK"] += swd["SWCLK"]
    nets["SWO"] += swd["SWO"]
    nets["NRST"] += swd[3]

    # The console, and the ROM bootloader, on bare pads.
    nets["CONSOLE_TX"] += part(parts.TEST_PAD, "tp_console_tx", "TP2")[1]
    nets["CONSOLE_RX"] += part(parts.TEST_PAD, "tp_console_rx", "TP3")[1]
    gnd += part(parts.TEST_PAD, "tp_gnd", "TP4")[1]
    v3v3 += part(parts.TEST_PAD, "tp_3v3", "TP5")[1]

    # Indicators, driven high from the MCU through 1 k.
    for index, (name, spec) in enumerate(
        (("LED_STATUS", parts.LED_YELLOW_GREEN_0603), ("LED_FAULT", parts.LED_RED_0603),
         ("LED_COMMS", parts.LED_YELLOW_GREEN_0603)),
        start=1,
    ):
        key = name.lower().removeprefix("led_")
        resistor = part(parts.RES_1K_0402, f"core.led.{key}.resistor", f"R{1 + index}")
        led = part(spec, f"core.led.{key}.led", f"D{index}")
        nets[name] += resistor[1]
        Net(f"{name}_A").connect(resistor[2], led["A"])
        gnd += led["K"]

    # The button, active high with an external pull-down, as on the NUCLEO the
    # firmware was written for.
    button = part(parts.BUTTON_6MM, "core.button.switch", "SW1")
    v3v3 += button[1]
    nets["BUTTON"] += button[2]
    pull = part(parts.RES_10K_0402, "core.button.pulldown", "R5")
    nets["BUTTON"] += pull[1]
    gnd += pull[2]


def power_block(v3v3, gnd, nets) -> None:
    """
    9 to 36 V in, and the three rails the board runs on.

    Input protection, a 100 V buck to 5 V, a small buck to 3V3, and a series
    reference for VREF+. Every value here is checked back in
    `checks/test_power.py` against the figures in `parts.py`, which come from
    the parts' own datasheets.
    """
    vin = Net("VIN")
    vin.drive = POWER
    v5 = nets["5V"] = Net("5V")
    v5.drive = POWER

    # --- the input stage -----------------------------------------------------
    #
    # Terminal, fuse, P-FET, then the TVS. The order is the design:
    #
    # The DRAIN faces the supply and the SOURCE faces the load, so the body
    # diode points the way current should flow and the FET blocks when the
    # supply is reversed. Wired the other way round the board still works on the
    # bench and the body diode conducts under reverse polarity - led12's defect,
    # and test_power.py derives the orientation rather than tabulating it.
    #
    # The TVS sits BEHIND the FET, on the protected rail. In front of it a
    # reversed supply would forward-bias the TVS into a short and take the fuse
    # with it, which makes the FET pointless: reverse the terminal here and
    # nothing at all happens. The cost is that the FET sees the full reverse
    # voltage, which is why it is a 100 V part.
    terminal = part(parts.SCREW_TERM_2, "power.terminal", "J2")
    fuse = part(parts.FUSE_1A5, "power.fuse", "F1")
    q_rpp = part(parts.PFET_RPP, "power.q_rpp", "Q1")
    r_gate = part(parts.RES_100K_0402, "power.r_gate", "R6")
    d_clamp = part(parts.ZENER_GATE_CLAMP, "power.d_gate_clamp", "D4")
    tvs = part(parts.TVS_40V, "power.tvs", "D5")

    Net("VIN_RAW").connect(terminal[1], fuse[1])
    gnd += terminal[2]
    Net("VIN_FUSED").connect(fuse[2], q_rpp["D"])
    vin += q_rpp["S"]

    # The gate is at ground through R6, so V_gs is the whole input voltage until
    # D4 clamps it. Cathode to the source, anode to the gate: the Zener conducts
    # when the source is more than its voltage above the gate.
    Net("RPP_GATE").connect(q_rpp["G"], r_gate[1], d_clamp[2])
    vin += d_clamp[1]
    gnd += r_gate[2]

    vin += tvs[1]
    gnd += tvs[2]
    vin += part(parts.TEST_PAD, "tp_vin", "TP6")[1]

    # --- 5 V ------------------------------------------------------------------
    #
    # A constant-on-time buck: the switching frequency comes from R9, and the
    # feedback comparator needs ripple of its own at FB. R12/C16 make a ramp
    # from the switch node in phase with the inductor current and C17 couples it
    # in - the datasheet's Type 3 network, the one its own reference design
    # uses, and the one that keeps the output ripple to millivolts.
    buck5 = part(parts.BUCK_100V, "buck5.ic", "U2")
    gnd += buck5["GND"], buck5["EP"]
    vin += buck5["VIN"]

    for address, spec, ref in (
        ("buck5.c_in1", parts.CAP_2U2_100V_1210, "C12"),
        ("buck5.c_in2", parts.CAP_2U2_100V_1210, "C13"),
        ("buck5.c_in_hf", parts.CAP_100N_100V_0603, "C14"),
    ):
        cap = part(spec, address, ref)
        vin += cap[1]
        gnd += cap[2]

    # Input undervoltage lockout: the converter starts when EN/UVLO passes
    # 1.5 V, so this divider is what sets the input voltage that happens at.
    r_uvlo_top = part(parts.RES_226K_0402, "buck5.r_uvlo_top", "R7")
    r_uvlo_bottom = part(parts.RES_49K9_0402, "buck5.r_uvlo_bottom", "R8")
    vin += r_uvlo_top[1]
    Net("UVLO").connect(r_uvlo_top[2], r_uvlo_bottom[1], buck5["EN/UVLO"])
    gnd += r_uvlo_bottom[2]

    r_on = part(parts.RES_31K6_0402, "buck5.r_on", "R9")
    Net("RON").connect(buck5["RON"], r_on[1])
    gnd += r_on[2]

    # Pad 1 faces the switch pin and pad 2 the bootstrap pin, which is how the
    # capacitor sits on the board.
    c_bst = part(parts.CAP_2N2_0402, "buck5.c_bst", "C15")
    Net("BST_5V").connect(buck5["BST"], c_bst[2])

    sw5 = Net("SW_5V")
    sw5.connect(buck5["SW"], c_bst[1])
    inductor = part(parts.IND_33U, "buck5.inductor", "L1")
    sw5 += inductor[1]
    v5 += inductor[2]

    for address, spec, ref in (
        ("buck5.c_out1", parts.CAP_10U_0805, "C18"),
        ("buck5.c_out2", parts.CAP_10U_0805, "C19"),
    ):
        cap = part(spec, address, ref)
        v5 += cap[1]
        gnd += cap[2]

    r_fb_top = part(parts.RES_158K_0402, "buck5.r_fb_top", "R10")
    r_fb_bottom = part(parts.RES_49K9_0402, "buck5.r_fb_bottom", "R11")
    v5 += r_fb_top[1]
    fb5 = Net("FB_5V")
    fb5.connect(r_fb_top[2], r_fb_bottom[1], buck5["FB"])
    gnd += r_fb_bottom[2]

    # 100 k, not the 121 k this had. The injected ripple is inversely
    # proportional to R and C, so the *smallest* ripple is at the top of both
    # tolerance bands - and the check read the bottom of both, which is the
    # corner that makes it look largest. At 121 k the board could only promise
    # 12.80 mV against the LM5164's 12 mV minimum, a seven per cent margin
    # reported as thirty-three. At 100 k it promises 15.48 mV, which is 29 %,
    # and puts the nominal nearer the datasheet's 20 mV than it was.
    r_ramp = part(parts.RES_100K_0402, "buck5.r_ramp", "R12")
    c_ramp = part(parts.CAP_3N3_0402, "buck5.c_ramp", "C16")
    c_couple = part(parts.CAP_220P_0402, "buck5.c_couple", "C17")
    sw5 += r_ramp[1]
    Net("RAMP").connect(r_ramp[2], c_ramp[1], c_couple[2])
    v5 += c_ramp[2]
    fb5 += c_couple[1]

    # Power good, pulled up to the rail it reports on the far side of, brought
    # to a pad, and - this is the part that matters - into the trip latch.
    #
    # Without it the only power-related thing that presets the latch is NRST,
    # which is the MCU deciding it has browned out, and on the way down that
    # is the *last* event, not the first. When the input dips below the
    # LM5164's UVLO the 5 V rail decays; below about 4 V the 3V3 buck stops
    # switching too, and 3V3 then falls on 44 uF into a 770 mA load at about
    # 17.5 V/ms - 3.3 V to 1.7 V in ninety microseconds. Through that window
    # the MCU is still executing (V_DD min 1.62 V), the '541 buffers are still
    # driving (1.65 V) and the latch is still latching (1.65 V), but the
    # threshold DAC and all seven comparators are below their specified
    # minimum supply of 2.7 V. Every trip threshold and every comparator
    # output is undefined while PWM is still leaving the board, for about one
    # and a half PWM periods.
    #
    # PGOOD is open drain, already the right polarity, and asserts at the
    # *regulation* threshold - milliseconds before the rail collapses rather
    # than ninety microseconds after. The second diode of D7 was sitting
    # unused with its anode already on TRIP_SET_N. One track, no BOM change,
    # and it presets on the way up as well, which is what you want.
    #
    # No MCU pin: the pin map is fixed and this is a bring-up signal as well,
    # not one firmware acts on.
    # 49.9k and not 10k: the datasheet's range starts at 10 k, and a 10 k part
    # at 1 % starts below it. Higher is better here anyway - the pin's own
    # pull-down is 30 ohm, so the low level is microvolts either way.
    r_pgood = part(parts.RES_49K9_0402, "buck5.r_pgood", "R13")
    v3v3 += r_pgood[2]
    nets["PGOOD"] = Net("PGOOD")
    nets["PGOOD"].connect(r_pgood[1], buck5["PGOOD"],
                          part(parts.TEST_PAD, "tp_pgood", "TP7")[1])
    v5 += part(parts.TEST_PAD, "tp_5v", "TP8")[1]

    # --- 3V3 -------------------------------------------------------------------
    #
    # D-CAP2, so there is nothing to compensate and no ripple to inject: the
    # inductor and output capacitance come straight from the datasheet's table
    # for a 3.3 V output, and the checks hold them to it.
    buck3 = part(parts.BUCK_3V3, "buck3v3.ic", "U3")
    gnd += buck3["GND"]
    v5 += buck3["VIN"], buck3["EN"]

    # 22 uF, not the 10 uF this had. The TPS562200 asks for 10 uF at its VIN
    # pin, and a 10 uF part's own tolerance is 8 uF at the corner - it never
    # met the figure. It passed because the check summed every capacitor on
    # the 5 V net, the 5 V buck's output bulk included, so the part actually
    # fitted here could have been deleted without anything noticing.
    for address, spec, ref in (
        ("buck3v3.c_in", parts.CAP_22U_25V_1206, "C20"),
        ("buck3v3.c_in_hf", parts.CAP_100N_0402, "C21"),
    ):
        cap = part(spec, address, ref)
        v5 += cap[1]
        gnd += cap[2]

    c_bst3 = part(parts.CAP_100N_0402, "buck3v3.c_bst", "C22")
    Net("BST_3V3").connect(buck3["VBST"], c_bst3[2])
    sw3 = Net("SW_3V3")
    sw3.connect(buck3["SW"], c_bst3[1])
    inductor3 = part(parts.IND_3U3, "buck3v3.inductor", "L2")
    sw3 += inductor3[1]
    v3v3 += inductor3[2]

    for address, spec, ref in (
        ("buck3v3.c_out1", parts.CAP_22U_0805, "C23"),
        ("buck3v3.c_out2", parts.CAP_22U_0805, "C24"),
    ):
        cap = part(spec, address, ref)
        v3v3 += cap[1]
        gnd += cap[2]

    r_fb3_top = part(parts.RES_33K2_0402, "buck3v3.r_fb_top", "R14")
    r_fb3_bottom = part(parts.RES_10K_0402, "buck3v3.r_fb_bottom", "R15")
    v3v3 += r_fb3_top[1]
    Net("FB_3V3").connect(r_fb3_top[2], r_fb3_bottom[1], buck3["VFB"])
    gnd += r_fb3_bottom[2]

    # --- VREF+ -------------------------------------------------------------------
    #
    # A series reference, not a divider off 3V3 and not the MCU's own VREFBUF:
    # everything the ADCs measure is scaled by this voltage, so its 0.2 % and
    # 75 ppm/degC are the board's measurement accuracy. It needs no output
    # capacitor; the 1 uF and 100 nF at the pin are the MCU's.
    #
    # **From 3V3, not from the 5 V rail, and that is a sequencing decision.**
    # VDDA is 3V3 through a ferrite, and 3V3 comes from a buck whose VIN and
    # EN are both on the 5 V rail. With the reference on 5 V the order was
    # forced and came out the same way every power-up: 5 V rises, the
    # reference follows it and is regulating at 3.006 V as soon as 5 V passes
    # 3 V, and only then does the 3V3 buck clear its own UVLO at about 4.1 V
    # and soft-start VDDA from zero over a millisecond. For that millisecond
    # VREF+ sat up to 3 V above VDDA, against an absolute maximum of VDDA plus
    # 0.4 - tens of milliamps out of VREF+ into the 3V3 rail through an
    # unrated structure on the die, every power cycle, showing up as reference
    # leakage and ADC offset drift months later rather than as a dead board.
    #
    # The part makes this free. SBVS032F specifies its supply as V_OUT + 1 mV
    # to 5.5 V, so 3V3 at its 3.135 V corner leaves 129 mV of headroom on a
    # 1 mV requirement, and VREF+ now rises with the rail VDDA is derived
    # from instead of a millisecond ahead of it. The steady-state margin the
    # 3.0 V choice was made for is unchanged.
    vref = part(parts.VREF_3V0, "vref.ic", "U4")
    v3v3 += vref["IN"]
    gnd += vref["GND"]
    nets["VREF+"] += vref["OUT"]
    nets["VREF+"].drive = POWER
    c_vref_in = part(parts.CAP_1U_0402, "vref.c_in", "C25")
    v3v3 += c_vref_in[1]
    gnd += c_vref_in[2]
    nets["VREF+"] += part(parts.TEST_PAD, "tp_vref", "TP9")[1]


def safety_chain(v3v3, gnd, nets) -> None:
    """
    What stands between an MCU pin and a gate driver.

    Two things have to be true for a PWM edge to leave this board: the MCU must
    be holding PWM_ENABLE_N low, and the trip latch must be clear. Either one
    failing takes every output high-impedance, where a pull-down at the
    connector holds it low.

    The latch is the part that makes this more than an enable line. It is set by
    anything that trips - a gate-driver fault, and in a later block the current
    comparators - and by NRST, so the board comes out of power-on and out of
    every reset already tripped. Nothing clears it but PG5, deliberately.
    """
    # The trip bus. Everything that trips pulls it low through a diode of its
    # own, so three sources share one node without sharing a net: a fault line
    # stays its own net all the way to the MCU pin that reports it.
    trip_set = nets["TRIP_SET_N"] = Net("TRIP_SET_N")
    pull_up = part(parts.RES_10K_0402, "safety.r_trip_pullup", "R16")
    v3v3 += pull_up[1]
    trip_set += pull_up[2]

    # Pins 1 and 2 are the cathodes and pin 3 the common anode, so the anode is
    # the bus and each cathode reaches the thing that pulls it down.
    faults = part(parts.SCHOTTKY_DUAL, "safety.d_faults", "D6")
    trip_set += faults[3]
    nets["FAULT1_N"] += faults[1]
    nets["FAULT2_N"] += faults[2]
    # D7's two cathodes are the two ways a supply says the board is not fit to
    # drive: NRST is the MCU's own brown-out, PGOOD is the 5 V rail's. Either
    # one low pulls the bus down through the common anode and presets.
    reset = part(parts.SCHOTTKY_DUAL, "safety.d_reset", "D7")
    trip_set += reset[3]
    nets["NRST"] += reset[1]
    nets["PGOOD"] += reset[2]

    # The gate enable's own input, held off.
    #
    # This is the one buffer input on the board that nothing defines. The
    # others are TIM1 and TIM8 channels, driven by their timers in alternate
    # function; PD7 is a plain GPIO, and a plain GPIO is a floating input
    # until firmware configures it - which for this pin no firmware path yet
    # does. A floating CMOS input is not just undefined at the output, it
    # sits the '541's input stage near mid-rail and draws cross-conduction
    # current through it. The board already states the rule this follows, a
    # few hundred lines up: every pin nobody is driving gets a 10 k. The
    # enable, both relays and every buffered output had one; this did not.
    #
    # Down, not up: the far side of the buffer has a pull-down at the
    # connector, so low is the state that means the gates are off.
    gate_enable_pull = part(parts.RES_10K_0402, "safety.r_gate_enable_pulldown", "R99")
    nets["GATE_ENABLE"] += gate_enable_pull[1]
    gnd += gate_enable_pull[2]

    # Both fault lines idle high, so an unfitted power board is not a fault.
    for address, net, ref in (
        ("safety.r_fault1_pullup", "FAULT1_N", "R17"),
        ("safety.r_fault2_pullup", "FAULT2_N", "R18"),
    ):
        resistor = part(parts.RES_10K_0402, address, ref)
        v3v3 += resistor[1]
        nets[net] += resistor[2]

    # The latch: a D flip-flop with its clock and data tied low, used for its
    # asynchronous preset and clear alone. Preset wins the board's power-on,
    # because NRST is low then and PRE is what NRST reaches.
    latch = part(parts.LATCH_DFF, "safety.latch", "U7")
    v3v3 += latch["VCC"]
    gnd += latch["GND"], latch["D"], latch["C"]
    trip_set += latch["~{PRE}"]

    # **The clear is a pulse, not a level, and the copper is what makes it
    # one.** PG5 used to reach the latch's CLR directly, with R20 covering
    # only the case where the pin is high-impedance. To clear a trip firmware
    # drives PG5 low; if it then stops - an ISR spinning, a fault handler that
    # still feeds the watchdog, a debugger halt with the IWDG frozen - the pin
    # is frozen low and CLR is asserted for ever.
    #
    # That does not leave the board tripped. It leaves it oscillating. A trip
    # asserts PRE, the buffers go high-impedance and the pull-downs hold the
    # gates off, the current decays, the comparator releases PRE, and with CLR
    # still low the latch goes straight to the cleared state: the buffers
    # re-enable, PWM resumes, and it over-currents again. The board sits in
    # sustained over-current at the trip threshold, at whatever rate the
    # motor's L/R and the comparator's 6 mV of hysteresis set, which is the
    # opposite of what this function's name promises. While both inputs are
    # low Q-bar is high, so TRIP_N reads "no break" and the MCU is not even
    # told.
    #
    # A capacitor in the path breaks the DC. Driving PG5 low couples the edge
    # onto CLR, which sits at 3.3 x 1k/11k = 0.30 V - a valid low - and
    # recovers through R20 with a time constant of 52 us, so the clear is
    # asserted for about 10 us and released whatever the pin does afterwards.
    # Ten microseconds against the latch's few nanoseconds, and against the
    # millisecond the firmware currently holds the pin down for, so the window
    # in which a trip arriving mid-clear could be missed gets a hundred times
    # smaller rather than larger.
    #
    # **The release needs a clamp, and the latch does not have one.** When PG5
    # goes high again the capacitor is charged, so the step lands on top of
    # the rail: 3.3 x (1 + 10/11) = 6.3 V nominal, 6.6 V at the corner. An
    # earlier version of this comment said the series resistor held the
    # current into the latch's input clamp to 0.2 mA, and that was wrong in
    # the way that matters - an LVC input has no clamp to V_CC. Its absolute
    # maximum is a flat 6.5 V rather than V_CC + 0.5, and I_IK is specified
    # only for negative inputs; that is exactly what makes the family tolerant
    # of 5.5 V on a 3.3 V rail. So there was no clamp current to limit, and
    # the node simply went to 6.3 V and stayed there for the 25 us the RC
    # takes to come back - past the 5.5 V recommended maximum every time a
    # trip is cleared, and past the 6.5 V absolute maximum at the rail's high
    # corner. On the one part standing between the MCU and the gate drivers.
    #
    # D13 is the clamp: a Schottky from the clear node to 3V3, both junctions
    # in parallel. It holds the node at the rail plus a forward drop, about
    # 3.9 V, and the series 1 k limits what flows into it to 3 mA. It does
    # nothing on the falling edge, where the node goes *below* the rail. No
    # arrangement of the two resistors avoids this: the low level needs
    # R98/R20 < 0.3, which forces the overshoot above 1.77 times the rail.
    clear_series = part(parts.RES_1K_0402, "safety.r_clear_series", "R98")
    clear_couple = part(parts.CAP_4N7_0402, "safety.c_clear", "C245")
    nets["TRIP_CLEAR_N"] += clear_series[1]
    Net("TRIP_CLEAR_COUPLE").connect(clear_series[2], clear_couple[1])
    clear_latch = Net("TRIP_CLEAR_LATCH_N")
    clear_latch.connect(clear_couple[2], latch["~{CLR}"])
    clear_pull_up = part(parts.RES_10K_0402, "safety.r_clear_pullup", "R20")
    v3v3 += clear_pull_up[1]
    clear_latch += clear_pull_up[2]
    clear_clamp = part(parts.SCHOTTKY_DUAL, "safety.d_clear_clamp", "D13")
    clear_latch += clear_clamp[3]          # the common anode, on the clear node
    v3v3 += clear_clamp[1]
    # One junction, not both. Three milliamps is a hundredth of what one of
    # these carries, and a second cathode on the same net asks the stitching
    # generator for a second plane via in a corner that has room for one.
    clear_clamp[2] += NC  # noqa: F821

    # Q is high when tripped, which is what the buffers' second enable wants.
    # Q-bar is low when tripped, which is what a break input wants: one output,
    # one node, both timers. No series resistor between them - an open circuit
    # in a safety path is worse than the ringing one would damp.
    tripped = Net("TRIPPED")
    tripped += latch["Q"]
    nets["TRIP_N"] += latch["~{Q}"]

    # Both latch outputs get a pull, and they pull opposite ways because the
    # outputs are complementary and both have to fail to "tripped".
    #
    # Without them these two nets are silicon to silicon: Q reaches nothing
    # but the two buffers' second enable, Q-bar nothing but the two timers'
    # break inputs. One unwetted pin on a VSSOP-8 - or U7 not placed at all -
    # and the buffers see a floating enable, which a CMOS input will read as
    # whatever it likes and most often reads as low. That is both buffers
    # enabled by PWM_ENABLE_N alone, with the hardware trip silently absent,
    # on a board that passes bring-up and looks right until the over-current
    # it was supposed to stop. The same open takes both BKIN pins with it.
    #
    # 100 k rather than 10 k: it only has to beat a CMOS input's microamp of
    # leakage, and the latch is a low-power AUP part that should not spend a
    # third of a milliamp holding its own output against a resistor.
    tripped_pull_up = part(parts.RES_100K_0402, "safety.r_tripped_pullup", "R85")
    v3v3 += tripped_pull_up[1]
    tripped += tripped_pull_up[2]

    trip_n_pull_down = part(parts.RES_100K_0402, "safety.r_trip_n_pulldown", "R86")
    nets["TRIP_N"] += trip_n_pull_down[1]
    gnd += trip_n_pull_down[2]

    # The enable the MCU holds. Pulled up, so a pin that is not being driven -
    # during reset, or with no firmware at all - is a pin that says "off".
    enable_pull_up = part(parts.RES_10K_0402, "safety.r_enable_pullup", "R19")
    v3v3 += enable_pull_up[1]
    nets["PWM_ENABLE_N"] += enable_pull_up[2]

    header = part(parts.HEADER_2X26, "header.digital", "J3")
    pins = PINMAP.header_pins(PINMAP.HEADER_DIGITAL, PINMAP.HEADER_GROUND,
                              len(header.pins))

    buffered = {}
    reference = 21
    for index, (address, ref, channels) in enumerate((
        # Channel order is the order the MCU's pins leave the package, so the
        # eight tracks into each buffer run side by side and never cross. The
        # header table downstream follows the same order for the same reason.
        ("safety.buffer1", "U5", [
            "PWM1_CH4", "PWM1_C_HIGH", "PWM1_C_LOW", "PWM1_B_HIGH",
            "PWM1_B_LOW", "PWM1_A_HIGH", "PWM1_A_LOW", "GATE_ENABLE",
        ]),
        ("safety.buffer2", "U6", [
            "PWM2_CH4", "PWM2_C_HIGH", "PWM2_B_HIGH", "PWM2_A_HIGH",
            "PWM2_A_LOW", "PWM2_C_LOW", "PWM2_B_LOW", None,
        ]),
    )):
        buffer = part(parts.BUF_OCTAL, address, ref)
        v3v3 += buffer["VCC"]
        gnd += buffer["GND"]
        nets["PWM_ENABLE_N"] += buffer["G1"]
        tripped += buffer["G2"]
        for channel, name in enumerate(channels):
            if name is None:
                # An unused input is tied low rather than left to float, and
                # its output goes nowhere on purpose.
                gnd += buffer[f"A{channel}"]
                buffer[f"Y{channel}"] += NC  # noqa: F821
                continue
            nets[name] += buffer[f"A{channel}"]
            series = part(parts.RES_33R_0402, f"safety.series.{name.lower()}", f"R{reference}")
            reference += 1
            Net(f"{name}_B").connect(buffer[f"Y{channel}"], series[1])
            buffered[f"{name}_OUT"] = Net(f"{name}_OUT")
            buffered[f"{name}_OUT"] += series[2]

    # Every buffered output holds itself low when the buffer is not driving it.
    # This is the whole point of the series resistor being before it: the
    # pull-down is at the connector, where a gate driver reads it.
    #
    # 10 k, and the second job these have is not theirs to do. A trip puts the
    # buffers into high impedance, and the line then discharges through this
    # resistor alone - 205 ns at 10 k, against a 50 ns budget. They were
    # briefly 1.2 k for that reason, which bought 34 ns of fall by spending
    # 35 mA of 3V3 that the rail's own budget had not been told about and did
    # not have. There is no value that satisfies both: the budget wants 600
    # ohm or less and the rail wants 1.4 k or more, and the window is empty.
    #
    # So the fall is done by a transistor instead, on the one line that means
    # "stop" - see the gate kill below - and these go back to the value the
    # static job actually wants.
    for name, net in buffered.items():
        pull_down = part(parts.RES_10K_0402, f"safety.pulldown.{name.lower()}", f"R{reference}")
        reference += 1
        net += pull_down[1]
        gnd += pull_down[2]

    # **The gate kill.** The '541 going high-impedance is not the same event as
    # the gate line going low, and the budget's own sentence - "how long a half
    # bridge survives a shoot-through" - is about the second. Nothing was
    # counting the difference, and through a pull-down the difference is most
    # of the budget.
    #
    # Q2 pulls GATE_ENABLE_OUT down as soon as the latch trips, through 150 ohm
    # that bounds what it takes from a buffer output which has not let go yet:
    # 3.465 V across the 33 ohm series and this 150 is 19 mA, against the 24 mA
    # the '541 wants to stay inside per output. The line then falls in 3.3 ns
    # rather than 205, and turning Q2 on costs 2.5 ns in front of that.
    #
    # **This makes GATE_ENABLE the signal the trip's timing rests on**, and
    # that is a statement about the interface, not just about this board: the
    # power board has to disable every gate driver from this one pin, and the
    # fourteen PWM lines are a second layer that arrives 200 ns later. The pin
    # map says so now. It is the Infineon MADK convention - `docs/research/07`
    # records "active-low gate kill" - but this board had never said it.
    gate_kill = part(parts.FET_GATE_KILL, "safety.q_gate_kill", "Q2")
    kill_drain = part(parts.RES_150R_0402, "safety.r_gate_kill_drain", "R100")
    Net("GATE_KILL_DRAIN").connect(kill_drain[1], gate_kill["D"])
    buffered["GATE_ENABLE_OUT"] += kill_drain[2]
    tripped += gate_kill["G"]
    gnd += gate_kill["S"]

    # The relays are not buffered - they are not in the PWM path - but they are
    # pulled down for the same reason: a pin nobody is driving must not close a
    # contactor.
    for name in ("RELAY1", "RELAY2"):
        pull_down = part(parts.RES_10K_0402, f"safety.pulldown.{name.lower()}", f"R{reference}")
        reference += 1
        nets[name] += pull_down[1]
        gnd += pull_down[2]

    # Board identification: the power board grounds whichever straps it wants,
    # so an unfitted board reads all ones.
    for name in ("ID_STRAP0", "ID_STRAP1", "ID_STRAP2", "ID_STRAP3"):
        pull_up = part(parts.RES_10K_0402, f"safety.pullup.{name.lower()}", f"R{reference}")
        reference += 1
        v3v3 += pull_up[1]
        nets[name] += pull_up[2]

    # Safe-torque-off feedback reads low when nothing is driving it, and low
    # means "not permitted to run". A disconnected cable is not a permission.
    for name in ("STO1_FEEDBACK", "STO2_FEEDBACK"):
        pull_down = part(parts.RES_10K_0402, f"safety.pulldown.{name.lower()}", f"R{reference}")
        reference += 1
        nets[name] += pull_down[1]
        gnd += pull_down[2]

    for number, name in pins.items():
        if name == "GND":
            gnd += header[number]
        elif name == "3V3":
            v3v3 += header[number]
        elif name in buffered:
            buffered[name] += header[number]
        else:
            nets[name] += header[number]

    for address, ref in (("safety.buffer1", "C26"), ("safety.buffer2", "C27"),
                         ("safety.latch", "C28")):
        cap = part(parts.CAP_100N_0402, f"{address}.decoupling", ref)
        v3v3 += cap[1]
        gnd += cap[2]


def analog_input(v5, gnd, nets) -> None:
    """
    What arrives from the power board, before anything is done to it.

    Every signal on this connector is raw: the comparators watch these nets
    directly, and the anti-alias filter between each one and the MCU's own ADC
    pin is a later block. The order matters more than it looks. A filter with a
    corner low enough to be worth having on a 1 MSPS ADC costs hundreds of
    nanoseconds, and the trip budget is fifty - so the trip has to be taken
    from ahead of it or not at all.

    The board also sends two things the other way: the reference everything is
    measured against, so the power board's sensors can be ratiometric to it,
    and an analog supply for them.
    """
    header = part(parts.HEADER_2X15, "header.analog", "J4")
    pins = PINMAP.header_pins(PINMAP.HEADER_ANALOG, PINMAP.HEADER_GROUND,
                              len(header.pins))

    # **An LDO, not a bead, and the reason is a voltage.** This rail used to be
    # 5 V through a ferrite. The sensors it powers drive the sense lines, and
    # those come back into TT_xx analog pins ST's Table 20 caps at 4.0 V
    # absolute - no positive-injection allowance at all, so the limit is a
    # voltage with nothing below it. An op-amp rails to its own supply during
    # the over-current the trip chain exists for, and a 5 V supply means it
    # rails to 5.25. `docs/research/07` answered that with "RC plus clamps";
    # the clamps do not fit on this board, and three positions were tried.
    #
    # So the rail is regulated to 3.3 V instead. At the worst corner of the
    # part's own 2 % accuracy a sensor can rail to 3.366 V, which is inside
    # the pin's rating with 0.6 V to spare, and the fault this board could not
    # clamp stops being a fault. What it costs is stated at the connector: a
    # power board that wants 5 V sensors makes 5 V from the 12-15 V aux it
    # already has on the digital header, and scales their output to this rail.
    ldo = part(parts.LDO_3V3_ANALOG, "analog.ldo", "U19")
    v5 += ldo["IN"], ldo["EN"]   # no enable control: the rail lives with 5 V
    gnd += ldo["GND"]
    ldo["NC"] += NC  # noqa: F821
    v5a = Net("3V3A")
    v5a += ldo["OUT"]
    v5a.drive = POWER

    # TI asks for 0.1 to 1 uF across IN and GND when the source is far away,
    # and the 5 V island is as far from this connector as anything gets.
    ldo_in = part(parts.CAP_1U_0402, "analog.ldo_input", "C246")
    v5 += ldo_in[1]
    gnd += ldo_in[2]

    # And the output pair, which was the bead's pair. The part is stable on
    # 0.1 uF of *effective* capacitance - its own words, and the reason it is
    # worth saying is that effective is what the DC-bias question elsewhere on
    # this board is about. A 1 uF 0402 X5R at 3.3 V of a 25 V rating has an
    # order of magnitude in hand against that 0.1.
    for address, spec, ref in (("analog.bulk", parts.CAP_1U_0402, "C38"),
                               ("analog.decoupling", parts.CAP_100N_0402, "C39")):
        cap = part(spec, address, ref)
        v5a += cap[1]
        gnd += cap[2]

    for number, name in pins.items():
        if name == "GND":
            gnd += header[number]
        elif name == "3V3A":
            v5a += header[number]
        else:
            if name not in nets:
                nets[name] = Net(name)
            nets[name] += header[number]


def trip_comparators(v3v3, gnd, nets) -> None:
    """
    Seven comparators, their thresholds, and how they reach the latch.

    Each phase current is compared against two thresholds, because the signal
    idles mid-scale and an over-current leaves that point in either direction.
    The DC link gets one. Every one of them is wired so that **the output goes
    low when the trip condition is true**, and pulls the trip bus down through a
    Schottky of its own - the same arrangement the fault lines use, for the same
    reason: seven sources share one node without sharing a net.

    That polarity is also what makes an unprogrammed board safe. The DAC
    **powers up** at zero - its EEPROM ships that way, datasheet Table 4-2,
    and the crop is committed at parts/MSOP10/evidence/ - so every high-side
    threshold is zero, every phase current sitting at its mid-scale idle is
    already above it, and the board trips the moment it powers up. The
    low-side comparators do not trip at zero and do not need to: nothing can
    run while the other three are asserting.

    **Power-up, not reset.** The MCP4728 has no reset pin, it sits on 3V3
    which does not drop when NRST is asserted, and its only other reset path
    is an I2C general-call that needs the bus working. After a watchdog reset
    or a debugger halt the thresholds are whatever the firmware that just
    stopped last wrote them to - possibly a half-finished multi-channel
    write. The latch is still preset in every one of those cases, so the
    board still comes up with its outputs off; what does not survive the
    reset is the *second* layer of the argument. A hung I2C bus leaves the
    thresholds frozen with nothing on the board able to power-cycle U15.
    """
    dac = part(parts.THRESHOLD_DAC, "trip.dac", "U15")
    v3v3 += dac["VDD"]
    gnd += dac["VSS"]
    # Latch the outputs as they are written; nothing here needs four thresholds
    # to change at one instant.
    gnd += dac["~{LDAC}"]
    # The busy flag matters only while writing the EEPROM, which this board
    # never does - the power-up value has to stay the factory zero.
    dac["RDY/~{BSY}"] += NC  # noqa: F821
    nets["DAC_SCL"] += dac["SCL"]
    nets["DAC_SDA"] += dac["SDA"]
    for address, net, ref in (("trip.r_scl_pullup", "DAC_SCL", "R59"),
                              ("trip.r_sda_pullup", "DAC_SDA", "R60")):
        pull_up = part(parts.RES_4K7_0402, address, ref)
        v3v3 += pull_up[1]
        nets[net] += pull_up[2]

    thresholds = {}
    for channel, name in (("A", "TRIP_LEVEL_HIGH"), ("B", "TRIP_LEVEL_LOW"),
                          ("C", "TRIP_LEVEL_FAST4"), ("D", "DAC_SPARE")):
        thresholds[name] = Net(name)
        thresholds[name] += dac[f"VOUT{channel}"]
    thresholds["DAC_SPARE"] += part(parts.TEST_PAD, "tp_dac_spare", "TP10")[1]

    for address, spec, ref in (("trip.dac.decoupling", parts.CAP_100N_0402, "C29"),
                               ("trip.dac.bulk", parts.CAP_1U_0402, "C30")):
        cap = part(spec, address, ref)
        v3v3 += cap[1]
        gnd += cap[2]

    # Each threshold gets a pull, and which way depends on which input it is
    # on. An "above" comparator has the threshold on + and the signal on -, so
    # a threshold that drifts to zero trips; a "below" one is the other way
    # round and wants its threshold pulled up. Both directions are "tripped".
    #
    # Without them these nets run from one DAC pin to between one and three
    # comparator inputs and nothing else. A TLV3501's input bias is picoamps,
    # so an open DAC output - a part not placed, one pin unwetted - leaves the
    # threshold to leakage and to whatever couples into it, and it can sit
    # anywhere. If it sits high, the three phase over-current trips and the
    # DC-link over-voltage trip never assert: protection that is gone, on a
    # board that boots safe and looks right, until firmware clears the latch.
    #
    # 100 k is a microamp against a buffered DAC output, which moves the
    # threshold by less than the comparator's own offset.
    THRESHOLD_PULLS = (
        ("trip.r_level_high_pulldown", "TRIP_LEVEL_HIGH", "down", "R87"),
        ("trip.r_level_low_pullup", "TRIP_LEVEL_LOW", "up", "R88"),
        ("trip.r_level_fast4_pulldown", "TRIP_LEVEL_FAST4", "down", "R89"),
    )

    for address, net, direction, ref in THRESHOLD_PULLS:
        pull = part(parts.RES_100K_0402, address, ref)
        thresholds[net] += pull[1]
        if direction == "down":
            gnd += pull[2]
        else:
            v3v3 += pull[2]

    outputs = {}
    # Each comparator, and which way round its inputs go. "above" means the
    # trip is the signal rising past the threshold, so the signal is on the
    # inverting input and the output falls when it does.
    for index, (signal, threshold, sense) in enumerate((
        ("FAST1_SENSE", "TRIP_LEVEL_HIGH", "above"), ("FAST1_SENSE", "TRIP_LEVEL_LOW", "below"),
        ("FAST2_SENSE", "TRIP_LEVEL_HIGH", "above"), ("FAST2_SENSE", "TRIP_LEVEL_LOW", "below"),
        ("FAST3_SENSE", "TRIP_LEVEL_HIGH", "above"), ("FAST3_SENSE", "TRIP_LEVEL_LOW", "below"),
        ("FAST4_SENSE", "TRIP_LEVEL_FAST4", "above"),
    )):
        key = f"{signal.split('_')[0].lower()}_{'high' if sense == 'above' else 'low'}"
        comparator = part(parts.COMPARATOR, f"trip.{key}", f"U{8 + index}")
        # From 5 V, not the logic rail. These parts guarantee their inputs only
        # to 0.2 V below their supply, and the signals they watch reach VREF+ at
        # 3.0 V - which on a 3.3 V rail at the bottom of its band is outside the
        # range the datasheet covers. On 5 V there is nearly two volts of room.
        # The outputs swing to 5 V with it, which the trip bus does not mind:
        # each one reaches the bus through a diode that blocks when it is high.
        nets["5V"] += comparator["V+"]
        gnd += comparator["V-"]
        # Held enabled. The pin is an input with no pull of its own, and a
        # comparator idling in shutdown is a trip point that does not exist.
        gnd += comparator["SHDN"]
        if signal not in nets:
            nets[signal] = Net(signal)
        if sense == "above":
            nets[signal] += comparator["-"]
            thresholds[threshold] += comparator["+"]
        else:
            nets[signal] += comparator["+"]
            thresholds[threshold] += comparator["-"]
        outputs[f"TRIP_{key.upper()}"] = Net(f"TRIP_{key.upper()}")
        outputs[f"TRIP_{key.upper()}"] += comparator[5]

        cap = part(parts.CAP_100N_0402, f"trip.{key}.decoupling", f"C{31 + index}")
        nets["5V"] += cap[1]
        gnd += cap[2]

    # Four dual Schottkys carry the seven outputs onto the trip bus. The spare
    # diode is tied off rather than left to pick up whatever is near it.
    ordered = list(outputs)
    for index in range(4):
        diodes = part(parts.SCHOTTKY_DUAL, f"trip.d_outputs{index + 1}", f"D{8 + index}")
        nets["TRIP_SET_N"] += diodes[3]
        for pad in (1, 2):
            position = index * 2 + pad - 1
            if position < len(ordered):
                outputs[ordered[position]] += diodes[pad]
            else:
                diodes[pad] += NC  # noqa: F821


def adc_inputs(v3v3, gnd, nets) -> None:
    """
    One RC between each signal as it arrives and the ADC pin that measures it.

    Two jobs, and they pull in opposite directions. The filter has to roll off
    what the converter would otherwise alias, and it has to leave the pin
    settling fast enough to be sampled in a few hundred nanoseconds. A big
    capacitor does the first and ruins the second.

    What resolves it is that the capacitor is a *reservoir*, not a load: the
    converter's own 4 pF steals a little charge from it at each sample and the
    series resistor puts it back long before the window closes. ST's Equation 1
    assumes no such reservoir and would reject every value here;
    `checks/test_adc.py` works the settling out from the charge sharing
    instead, and says why in as many words.

    The fast channels are the ones the control loop reads every PWM cycle. The
    slow ones are temperatures and housekeeping, and get a corner three decades
    lower because nothing is waiting on them.
    """
    fast = ("FAST1", "FAST2", "FAST3", "FAST4", "FAST5", "FAST6", "FAST7", "FAST8")
    slow = ("SLOW1", "SLOW2", "SLOW3", "SLOW4", "BOARD_ID1", "BOARD_ID2")

    resistor_ref, capacitor_ref = 61, 40
    for name in fast + slow:
        quick = name in fast
        series = part(parts.RES_22R_0402 if quick else parts.RES_1K_0402,
                      f"adc.{name.lower()}.series", f"R{resistor_ref}")
        shunt = part(parts.CAP_4N7_0402 if quick else parts.CAP_100N_0402,
                     f"adc.{name.lower()}.shunt", f"C{capacitor_ref}")
        resistor_ref += 1
        capacitor_ref += 1
        nets[f"{name}_SENSE"] += series[1]
        nets[name] += series[2], shunt[1]
        gnd += shunt[2]

    # The DC link again, into the MCU's own comparator. A second path to the
    # same fact, taken from the same place the external comparators take it,
    # and independent of them so a fault in one is not a fault in both.
    #
    # **A kilohm and 100 pF, not the channel network.** PB2 is a comparator
    # input: nothing samples it, so it needs no reservoir against a sampling
    # capacitor, and the network can be what a tap actually wants. The old
    # copy of the channel network made FAST4 the *worst* tap on the board
    # rather than the best-protected one - two 10 ohm branches in parallel are
    # 4.95, which took a step 29 % low and delayed a ramp by 40 ns. The
    # redundancy was costing accuracy and time. In parallel with the channel's
    # 22 ohm this contributes 0.5 ohm of loading and 100 pF of delay.
    series = part(parts.RES_1K_0402, "adc.comp_fast4.series", f"R{resistor_ref}")
    shunt = part(parts.CAP_100P_0402, "adc.comp_fast4.shunt", f"C{capacitor_ref}")
    resistor_ref += 1
    capacitor_ref += 1
    nets["FAST4_SENSE"] += series[1]
    nets["COMP_FAST4"] += series[2], shunt[1]
    gnd += shunt[2]

    # The MCU's own DAC output, on a pad. Reserved for resolver excitation,
    # which is a decision this board has not taken; until it does, a series
    # resistor and somewhere to put a probe.
    series = part(parts.RES_1K_0402, "adc.dac_test.series", f"R{resistor_ref}")
    nets["DAC_TEST"] += series[1]
    Net("DAC_TEST_OUT").connect(series[2], part(parts.TEST_PAD, "tp_dac_test", "TP11")[1])


def field_buses(v3v3, gnd, nets) -> None:
    """
    CAN FD and RS-485: two differential buses, each on three pins.

    Both transceivers are chosen for what they do when nothing is driving them.
    The CAN part's standby pin has an integrated pull-up, so it comes out of
    reset listening rather than talking. The RS-485 part's driver enable has a
    2 Mohm pull-down and its receiver enable a pull-up, and it reads a logic
    high on an idle or shorted bus with no external bias network at all - which
    is the reason it is this part and not a cheaper one, and why the fail-safe
    resistors the plan called for are not here.

    Termination is on a solder jumper on both. A bus wants exactly two
    terminations, at its two ends, and a board that cannot be anything but an
    end is a board that cannot go in the middle.
    """
    v5 = nets["5V"]

    # --- CAN FD --------------------------------------------------------------
    can = part(parts.CAN_TRANSCEIVER, "can.transceiver", "U16")
    v5 += can["VCC"]
    v3v3 += can["Vref"]      # pin 5: this part's IO supply, not a reference out
    gnd += can["GND"]
    nets["CAN_TX"] += can["D"]
    nets["CAN_RX"] += can["R"]
    nets["CAN_STANDBY"] += can["Rs"]   # pin 8: standby, pulled up inside

    for address, rail, ref in (("can.decoupling_vcc", v5, "C55"),
                               ("can.decoupling_vio", v3v3, "C56")):
        cap = part(parts.CAP_100N_0402, address, ref)
        rail += cap[1]
        gnd += cap[2]

    can_header = part(parts.HEADER_1X3, "can.header", "J5")
    canh = Net("CAN_H")
    canl = Net("CAN_L")
    canh.connect(can["CANH"], can_header[1])
    canl.connect(can["CANL"], can_header[2])
    gnd += can_header[3]

    # Split termination: two halves with the midpoint bypassed to ground, which
    # is what gives a CAN bus a defined common mode as well as a defined
    # differential impedance. In series with a jumper, so it can be left open.
    #
    # **A jumper in each leg.** One jumper, in the CANH leg, is what this had,
    # and it does not disconnect the termination - it disconnects half of it.
    # With JP1 open and the board shipped that way, CANH sees nothing while
    # CANL still carries 60.4 ohm in series with 4.7 nF to ground: the pair is
    # asymmetrically loaded on every board that is not a cable end, which is
    # the normal case. A recessive-to-dominant edge on CANL then asks the
    # transceiver for 4.7 nF x 2 V / 40 ns = 235 mA, far past what it drives,
    # so it current-limits and that one line's edge stretches to about 130 ns
    # - 27 % of a 2 Mbit/s FD data bit, turned straight into common mode on a
    # cable leaving the machine. The RS-485 side next door is built correctly
    # and the contrast is visible between the two blocks: its jumper breaks
    # the only path there is.
    #
    # Two SJ2 footprints, no new BOM line.
    jumper = part(parts.SOLDER_JUMPER, "can.termination_jumper", "JP1")
    jumper_low = part(parts.SOLDER_JUMPER, "can.termination_jumper_low", "JP3")
    # R97, not R76: the ADC block hands out references from a running counter
    # and that counter reached 76. Two parts asking for one designator is a
    # designator SKiDL renames, silently, and a board that then carries a
    # reference no assembly house will accept.
    upper = part(parts.RES_60R4_0805, "can.termination_upper", "R97")
    lower = part(parts.RES_60R4_0805, "can.termination_lower", "R77")
    split = part(parts.CAP_4N7_0402, "can.termination_split", "C57")
    canh += jumper[1]
    Net("CAN_TERM").connect(jumper[2], upper[1])
    Net("CAN_TERM_MID").connect(upper[2], lower[1], split[1])
    Net("CAN_TERM_LOW").connect(lower[2], jumper_low[2])
    canl += jumper_low[1]
    gnd += split[2]

    # --- RS-485 --------------------------------------------------------------
    rs485 = part(parts.RS485_TRANSCEIVER, "rs485.transceiver", "U17")
    v3v3 += rs485["VCC"]
    gnd += rs485["GND"]
    nets["RS485_TX"] += rs485["DI"]
    nets["RS485_RX"] += rs485["RO"]
    nets["RS485_DE"] += rs485["DE"]
    # Held off by a resistor, not by the transceiver's internal 2 Mohm. Every
    # other "a pin nobody is driving" on this board gets 10 k - the buffer
    # enable, both relays, every buffered output - and a driver enable earns
    # it most: a spuriously enabled RS-485 driver holds a multi-drop bus and
    # blocks every other node on it. At 2 Mohm a microamp of leakage is two
    # volts, which is above the DE threshold.
    de_pull_down = part(parts.RES_10K_0402, "rs485.r_de_pulldown", "R94")
    nets["RS485_DE"] += de_pull_down[1]
    gnd += de_pull_down[2]
    # The receiver stays on, including while this board is transmitting, which
    # is how a half-duplex node hears its own collisions.
    gnd += rs485["~{RE}"]

    cap = part(parts.CAP_100N_0402, "rs485.decoupling", "C58")
    v3v3 += cap[1]
    gnd += cap[2]

    rs485_header = part(parts.HEADER_1X3, "rs485.header", "J6")
    bus_a = Net("RS485_A")
    bus_b = Net("RS485_B")
    bus_a.connect(rs485["A"], rs485_header[1])
    bus_b.connect(rs485["B"], rs485_header[2])
    gnd += rs485_header[3]

    rs485_jumper = part(parts.SOLDER_JUMPER, "rs485.termination_jumper", "JP2")
    termination = part(parts.RES_120R_1206, "rs485.termination", "R78")
    bus_a += rs485_jumper[1]
    Net("RS485_TERM").connect(rs485_jumper[2], termination[1])
    bus_b += termination[2]


def usb(v3v3, gnd, nets) -> None:
    """
    USB-C, as a device port and nothing else.

    **VBUS goes to one pin and stops.** It is not wired to a rail, through a
    diode, or to anything that could carry current into the board: this board is
    powered from its terminal or from the daughter-board header, and a USB host
    plugged in beside a 24 V supply must not find itself sourcing any of it.
    What VBUS does reach is PA9, which ST's pin table calls `FT_u` - five-volt
    tolerant, with the USB option - and which is the pin the OTG core's own
    session comparators sit behind. The plan said to divide it down first; a
    divider would keep the pin safe and stop those comparators working, so the
    board would need firmware to do something non-standard to notice a host.

    Both CC pins get their own pull-down. One resistor shared between them
    would work in exactly one cable orientation, which is the bug a Type-C
    connector exists to prevent.

    The ESD array sits between the connector and everything else, so a strike
    arriving on the cable meets it before it meets a pin.
    """
    receptacle = part(parts.USB_C_RECEPTACLE, "usb.receptacle", "J7")
    protection = part(parts.ESD_USB, "usb.protection", "D12")

    # Shell and signal ground are the same here: one connector, one board, and
    # nothing for a split to isolate from.
    gnd += receptacle["GND"], receptacle["SHIELD"], protection["GND"]

    # The cable side of the pair, between the connector and the array. Both
    # rows of the receptacle carry the same signal, which is what makes the
    # connector reversible.
    # D+ takes the array's second channel and D- its first. The two channels
    # are identical, and which way round they go decides whether the pair stays
    # on the same sides of itself from the package to the connector or crosses
    # inside the array - which it cannot do without a via in the middle of a
    # controlled-impedance run.
    cable_dp = Net("USB_DP_CABLE")
    cable_dm = Net("USB_DM_CABLE")
    cable_dp.connect(receptacle["D+"], protection[3])
    cable_dm.connect(receptacle["D-"], protection[1])

    # The board side, on to the MCU.
    nets["USB_DP"] += protection[4]
    nets["USB_DM"] += protection[6]

    # VBUS: the connector, the array's clamp, and the sense pin through 1 k.
    #
    # The resistor is there for the case this board is *designed* for - "a USB
    # host plugged in beside a 24 V supply must not find itself sourcing any
    # of it", a few lines up - which is a board whose rails may be at zero
    # while a host holds 5.25 V on this pin. ST's Table 20 allows an FT pin
    # Min(VDD, VDDA, VDD33USB, VBAT) + 4.0 V, and VBAT and VDD33USB are both
    # on 3V3 here, so with the board off that allowance is 4.0 V and the
    # permitted positive injection is 0 mA. A direct connection puts the
    # host's supply into a dead rail through the pin's own upper structure
    # with nothing limiting it; 1 k limits it to about 4.5 mA.
    #
    # It costs nothing on the sensing side: the OTG core compares this pin
    # against its own thresholds and draws microamps, so a kilohm is
    # millivolts of error. The plan's divider is still refused, for the reason
    # given above - a divider stops those comparators working.
    vbus_series = part(parts.RES_1K_0402, "usb.r_vbus", "R95")
    Net("USB_VBUS_IN").connect(receptacle["VBUS"], protection["VBUS"], vbus_series[1])
    nets["USB_VBUS"] += vbus_series[2]

    for address, pin, ref in (("usb.cc1_pulldown", "CC1", "R79"),
                              ("usb.cc2_pulldown", "CC2", "R80")):
        resistor = part(parts.RES_5K1_0402, address, ref)
        Net(f"USB_{pin}").connect(receptacle[pin], resistor[1])
        gnd += resistor[2]

    # SBU1 and SBU2 are for alternate modes this board has none of. Left
    # unconnected deliberately, and said so, rather than left to the check that
    # would otherwise ask why two pads have no net.
    receptacle["SBU1"] += NC  # noqa: F821 - SKiDL puts NC in builtins
    receptacle["SBU2"] += NC  # noqa: F821


def ethernet(v3v3, gnd, nets) -> None:
    """
    100BASE-TX over RMII: the PHY, a 25 MHz crystal, and a jack with the
    magnetics inside it.

    **The PHY makes the reference clock.** A 25 MHz crystal is cheaper and
    quieter than a 50 MHz oscillator, and the LAN8742A will multiply one up and
    drive the RMII REF_CLK out of its nINT pin. The price is in the datasheet's
    own words: "When configured for REF_CLK Out Mode, the device generates the
    50MHz RMII REF_CLK and the nINT interrupt is not available." So this board
    has no PHY interrupt line, PG14 is free again, and firmware learns about
    link changes by reading the PHY over MDIO - which is what it does anyway
    every time it wants to know the speed.

    Nearly every strap is left alone on purpose. MODE[2:0] come up at 111
    through their own pull-ups, which is "all capable, auto-negotiation
    enabled"; PHYAD0 comes up at 0, which is the address this board wants;
    REGOFF has an internal pull-down, and pulling it down is what turns the
    internal 1.2 V regulator *on*. The one strap that has to be fought is
    nINTSEL, which defaults to the interrupt mode this design cannot use.
    """
    phy = part(parts.ETH_PHY, "eth.phy", "U18")

    v3v3 += phy["VDDIO"], phy["VDD1A"], phy["VDD2A"]
    gnd += phy["VSS"]

    # The core rail is the PHY's own regulator output, not a rail of this
    # board's: it exists between one pin and two capacitors.
    core = Net("ETH_VDDCR")
    # The pin is a supply input that its own silicon supplies. ERC cannot see
    # that, the way it cannot see what feeds the MCU's VCAP pins, so the drive
    # is declared here rather than left as a warning nobody reads.
    core.drive = POWER
    core += phy["VDDCR"]
    for address, spec, ref in (("eth.core_bulk", parts.CAP_1U_0402, "C59"),
                               ("eth.core_hf", parts.CAP_470P_0402, "C60")):
        cap = part(spec, address, ref)
        core += cap[1]
        gnd += cap[2]

    for address, spec, ref, pin in (("eth.dec_vddio", parts.CAP_100N_0402, "C61", "VDDIO"),
                                    ("eth.dec_vdd1a", parts.CAP_100N_0402, "C62", "VDD1A"),
                                    ("eth.dec_vdd2a", parts.CAP_100N_0402, "C63", "VDD2A")):
        cap = part(spec, address, ref)
        v3v3 += cap[1]
        gnd += cap[2]

    # The bias current the whole analog front end is referenced to. 12.1 k, 1 %,
    # because it sets transmit amplitude and nothing else adjusts it.
    bias = part(parts.RES_12K1_0402, "eth.bias", "R81")
    Net("ETH_RBIAS").connect(phy["RBIAS"], bias[1])
    gnd += bias[2]

    # --- the clock ----------------------------------------------------------
    crystal = part(parts.XTAL_25M, "eth.xtal.crystal", "Y3")
    xin = Net("ETH_XTAL1")
    xout = Net("ETH_XTAL2")
    xin.connect(phy["XTAL1/CLKIN"], crystal[1])
    xout.connect(phy["XTAL2"], crystal[3])
    gnd += crystal[2], crystal[4]
    for address, ref, node in (("eth.xtal.c_in", "C64", xin), ("eth.xtal.c_out", "C65", xout)):
        cap = part(parts.CAP_36P_0402, address, ref)
        node += cap[1]
        gnd += cap[2]

    # --- RMII, and the two lines that manage it -----------------------------
    nets["ETH_TXD0"] += phy["TXD0"]
    nets["ETH_TXD1"] += phy["TXD1"]
    nets["ETH_TX_EN"] += phy["TXEN"]
    nets["ETH_RXD0"] += phy["RXD0/MODE0"]
    nets["ETH_RXD1"] += phy["RXD1/MODE1"]
    nets["ETH_CRS_DV"] += phy["CRS_DV/MODE2"]
    nets["ETH_MDIO"] += phy["MDIO"]
    nets["ETH_MDC"] += phy["MDC"]
    nets["ETH_PHY_RESET"] += phy["~{RST}"]
    nets["ETH_REF_CLK"] += phy["~{INT}/REFCLKO"]

    # And nRST gets a capacitor, because the pull-up alone releases the PHY's
    # reset in microseconds. Section 3.8.6.1 requires a hardware reset after
    # power-up and Table 5.11 gives tpurstd - supplies at level to nRST
    # released - a 25 ms *minimum*. With 10 k into 2 pF the pin tracks the
    # rail up and the reset is over before it has begun, and the straps that
    # decide REF_CLK direction and the PHY address are latched on that edge:
    # a PHY that latches the wrong mode comes up silent with every voltage on
    # the board correct. 4.7 uF gives about 44 ms, and 28 ms even with the
    # capacitance derated to a third by its own DC bias.
    # The 1 k is in series with the capacitor rather than with the pin, which
    # gets the delay without the problem the capacitor alone would create: the
    # MCU asserts this reset by pulling the node down, and 4.7 uF discharged
    # through an I/O's own ~50 ohm is about 66 mA for a couple of hundred
    # microseconds, against a pin rated 20. Through 1 k it is 3.3 mA, and the
    # release is still (10 k + 1 k) x 4.7 uF.
    reset_series = part(parts.RES_1K_0402, "eth.r_reset_delay", "R96")
    # C91, not C81: C68 to C90 are the plane-stitching capacitors, allocated as
    # a contiguous block, and C81 is one of them. The block has grown twice,
    # for the two crossings to the inner signal layer that needed a tie beside
    # them - power good's, and the gate kill's gate.
    reset_delay = part(parts.CAP_4U7_0603, "eth.c_reset", "C91")
    nets["ETH_PHY_RESET"] += reset_series[1]
    Net("ETH_RESET_RC").connect(reset_series[2], reset_delay[1])
    gnd += reset_delay[2]

    # MDIO is open-drain at the PHY and idles high; nRST is held out of reset
    # until firmware decides otherwise, so a board that never runs still has a
    # PHY it can talk to over a debugger.
    for address, net, ref, spec in (("eth.r_mdio_pullup", "ETH_MDIO", "R82", parts.RES_4K7_0402),
                                    ("eth.r_reset_pullup", "ETH_PHY_RESET", "R83", parts.RES_10K_0402)):
        resistor = part(spec, address, ref)
        nets[net] += resistor[1]
        v3v3 += resistor[2]

    # The one strap that is not already where this design wants it.
    strap = part(parts.RES_10K_0402, "eth.r_refclk_strap", "R84")
    Net("ETH_NINTSEL").connect(phy["LED2/~{INTSEL}"], strap[1])
    gnd += strap[2]

    # RXER carries PHYAD0 at reset and nothing after it: the STM32's RMII has
    # no receive-error input, and the internal pull-down gives address 0.
    phy["RXER/PHYAD0"] += NC  # noqa: F821 - SKiDL puts NC in builtins
    # LED1 doubles as REGOFF, whose internal pull-down keeps the 1.2 V
    # regulator on. Driving an LED from it would make the regulator's state
    # depend on which way the LED is wired, which is a trade this board does
    # not need: it has its own indicators and a debug port.
    phy["LED1/REGOFF"] += NC  # noqa: F821

    # --- the jack -----------------------------------------------------------
    jack = part(parts.ETH_JACK, "eth.jack", "J8")
    lines = {}
    for name, phy_pin, jack_pin in (("ETH_TD_P", "TXP", "TD+"), ("ETH_TD_N", "TXN", "TD-"),
                                    ("ETH_RD_P", "RXP", "RD+"), ("ETH_RD_N", "RXN", "RD-")):
        lines[name] = Net(name)
        lines[name].connect(phy[phy_pin], jack[jack_pin])

    # Each line gets its 49.9 ohm to the rail, which is what Microchip's
    # Figure 3.23 asks for and what this board was missing. Two of them in
    # series across a pair are ~100 ohm; in parallel with the 100 ohm the 1:1
    # transformer reflects from the cable that gives the current-mode driver
    # the 50 ohm its output amplitude is specified into, and it gives the
    # receive pair a chip-side termination it had none of.
    #
    # They go to 3V3 rather than to a ferrite-fed node of their own. The
    # figure feeds VDD1A, VDD2A and these four from one bead; this board's
    # analog supplies are on the plane, which is a separate and much smaller
    # deviation - it decides how much transmit common-mode current ends up in
    # the plane, not whether the line is terminated. parts/QFN24/QFN24.md
    # keeps the score.
    for address, net, ref in (("eth.term_td_p", "ETH_TD_P", "R90"),
                              ("eth.term_td_n", "ETH_TD_N", "R91"),
                              ("eth.term_rd_p", "ETH_RD_P", "R92"),
                              ("eth.term_rd_n", "ETH_RD_N", "R93")):
        resistor = part(parts.RES_49R9_0402, address, ref)
        lines[net] += resistor[1]
        v3v3 += resistor[2]

    # The transformer's centre taps are where the transmitter's current comes
    # from, so they sit on the supply rather than on ground, and each gets its
    # own bypass because the two windings switch at different moments and
    # would otherwise share the return path through the rail.
    v3v3 += jack["TCT"], jack["RCT"]
    for address, ref in (("eth.tap_bypass1", "C66"), ("eth.tap_bypass2", "C67")):
        cap = part(parts.CAP_100N_0402, address, ref)
        v3v3 += cap[1]
        gnd += cap[2]

    # Pin 8 is the common of the jack's own termination network and the shell
    # is the cable's screen. Both go to this board's one ground: there is no
    # second ground here to isolate them from, and a screen left floating is an
    # antenna that happens to be earthed at the other end of the cable.
    gnd += jack[8], jack["SH"]

    # Nothing drives the jack's four LEDs. Both of the PHY's LED pins double as
    # configuration straps, and buying two indicators with a strap polarity
    # each is a poor trade on a board that already has three LEDs and a debug
    # port. The pins are left unconnected deliberately, and said so.
    jack["NC"] += NC  # noqa: F821 - SKiDL puts NC in builtins
    for pad in ("9", "10", "11", "12"):
        jack[pad] += NC  # noqa: F821


def plane_stitching(v3v3, gnd) -> None:
    """
    Capacitors that exist for the return current, not for any part's supply.

    The front of this board is referenced to the ground plane under it and the
    back to the supply islands. Every via between the two layers moves the
    signal across and leaves its return to find its own way, and the only
    crossings between those planes are capacitors. Where the decoupling happens
    to be near, the return has a short way over; where it does not, the current
    goes round whatever loop it can find, and the loop is what radiates.

    Twenty-one of them. Six in a row beyond the digital connector, where fifteen
    buffered outputs dip under its first row and there is nowhere nearer to put
    them; one each at the USB connector's fan-out, the debug escapes, the
    power-good line and the CAN termination; two on the Ethernet block; and six
    across the strip the analog fan changes layers in, which is otherwise the
    emptiest part of this board and was therefore the furthest from a tie; and
    one beside the static pull resistors, which moved south out of the USB
    connector's shadow and took two layer changes with them.

    They are the one set of parts on this board whose position is their whole
    purpose, and not one of them was put where it is by judgement:
    `test_routing.py` failed, named the layer changes it had stranded, and
    these went where that list said.
    """
    for index in range(23):
        cap = part(parts.CAP_100N_0402, f"stitch.{index + 1}", f"C{68 + index}")
        v3v3 += cap[1]
        gnd += cap[2]


def pending(names: list[str]) -> dict[str, str]:
    """Every net with only the MCU on it, and the block that will change that."""
    return {net: waiting_for(net) for net in names if not _CONNECTED.match(net)}


if __name__ == "__main__":
    names = sorted(
        {p.net_name for p in PINMAP.PINS}
        | {name for name in PINMAP.HEADER_ANALOG if name.endswith("_SENSE")}
    )
    sys.exit(run(build, HERE, INTENT, pending(names)))
