"""
led12 placement and routing.

Read by hw/tools/layout.py, which writes it into the KiCad board atopile
generates. Coordinates are millimetres in the board's own frame: x runs right,
y runs *down*, and the board is 50 x 40 mm, so the usable area is x -25 to 25
and y -20 to 20.

The floorplan follows the current:

    y -17   the 12 V bus, clear of the parts it feeds
    y -13   input chain, left to right: terminal, fuse, FET, TVS, bulk, decoupling
            and the regulator at the right-hand end
    y  -8   regulator's capacitors and load, then the test pads at y -2
    y  +6   the button and its debounce network, bottom left
    y +3..15 four LED branches, bottom right, return bus on their left

Ground is not routed. It is a pour on the back copper, and every surface-mount
ground pad reaches it through its own via — see VIAS.

Two rules shaped the routing. A track may not cross a pad of another net, which
is why the power rails run on their own line above or below the parts rather
than straight through them. And the back copper belongs to the ground pour, so
every signal is on the front.
"""

# --- placement: atopile address -> (x, y) or (x, y, rotation) ---------------
#
# Every part on the board must appear here. The engine refuses to run if one is
# missing, so a part added to the schematic cannot quietly land at the origin.

PLACEMENT = {
    # Input chain. The terminal is at the left edge where a person can get a
    # screwdriver to it, and nothing is placed to its left.
    "power.terminal": (-21.5, -13.0),
    "power.fuse": (-10.4, -13.0),
    "power.q_rpp": (-5.8, -13.0),
    "power.r_gate": (-9.5, -17.0),
    "power.tvs": (0.3, -13.0),
    "power.c_bulk": (7.0, -13.0),
    "power.c_hf": (11.5, -13.0),
    # Regulator, at the right-hand end of the input chain.
    "rail.ldo": (18.5, -13.0),
    "rail.c_in": (11.5, -6.0),
    "rail.c_out": (19.5, -8.0),
    "rail.r_load": (19.5, -5.0),
    # Test pads in a row across the middle, where a probe can reach them
    # without fouling a part.
    "tp_gnd": (11.0, -2.0),
    "tp_12v": (15.5, -2.0),
    "tp_3v3": (19.5, -2.0),
    "tp_gate": (-6.0, 10.0),
    # Button and debounce, bottom left. The button is at the edge so a finger
    # reaches it without touching anything else.
    "switch.button": (-22.0, 6.0),
    "switch.r_series": (-11.0, 10.5),
    "switch.r_pulldown": (-6.0, 14.0),
    "switch.c_debounce": (-6.0, 17.0),
    "switch.q_switch": (-1.0, 12.0),
    # Four LED branches, bottom right. Each LED sits to the left of its
    # resistor so the current runs right to left into the return bus, with no
    # track having to hop over a pad. The resistors are turned around because
    # their first pad is the 12 V end, which has to face the bus.
    "leds[0].led": (6.0, 3.0),
    "leds[0].resistor": (12.0, 3.0, 180),
    "leds[1].led": (6.0, 7.0),
    "leds[1].resistor": (12.0, 7.0, 180),
    "leds[2].led": (6.0, 11.0),
    "leds[2].resistor": (12.0, 11.0, 180),
    "leds[3].led": (6.0, 15.0),
    "leds[3].resistor": (12.0, 15.0, 180),
}

# --- designators -------------------------------------------------------------
#
# Offsets in board millimetres from each part's origin. The default puts the
# label 1.7 mm above the part, which suits an 0805; anything with a taller
# outline, or a neighbour directly above it, needs saying explicitly. Silkscreen
# printed over a pad is clipped away by the fab, so the board comes back with
# that part unlabelled.

LABELS = {
    "*": (0.0, -1.7),
    "power.terminal": (0.0, 7.0),      # below: above would run off the board
    "power.q_rpp": (0.0, -2.6),        # SOT-23 is taller than an 0805
    "switch.q_switch": (0.0, -2.6),
    "power.tvs": (0.0, -3.2),          # SMB, taller again
    "power.c_bulk": (0.0, -2.4),       # 1210
    "rail.ldo": (0.0, -4.5),           # SOT-223, tallest part on the board
    "rail.c_out": (-2.9, 0.0),         # the regulator sits directly above it
    "rail.r_load": (-2.9, 0.0),        # its own column is full above and below
    # The three test pads sit shoulder to shoulder and their labels are three
    # characters wide, so the middle one goes below rather than beside.
    "tp_gnd": (0.0, -1.9),
    "tp_12v": (-3.4, 1.5),          # diagonally clear of its own pad and the track
    "tp_3v3": (0.0, -1.9),
    "switch.c_debounce": (-2.7, 0.0),  # the pulldown sits directly above it
}

LABEL_FONT = {"size": 0.9, "thickness": 0.15}

# --- widths ------------------------------------------------------------------
# These have to be at least what led12/rules.kicad_dru demands, and DRC fails
# if they are not.

UNFUSED = 1.0  # ahead of the fuse, where nothing limits the current
POWER = 0.5  # downstream of a 1 A fuse
SIGNAL = 0.25  # microamps; the width is for handling, not current

F = "F.Cu"

# --- routes: (net, width, layer, [points]) -----------------------------------
#
# A point is either "address:pad", which follows the part if it moves, or a
# literal (x, y) corner. Segments are drawn between consecutive points.

ROUTES = [
    # Terminal to fuse. It detours below the terminal rather than running
    # straight across, because the terminal's own ground pad is in the way.
    ("VIN_RAW", UNFUSED, F, [
        "power.terminal:1", (-21.5, -9.5), (-11.8, -9.5), "power.fuse:1",
    ]),

    # Fuse to the reverse-polarity FET's source.
    ("VIN_FUSED", POWER, F, [
        "power.fuse:2", (-7.6, -13.0), (-7.6, -12.05), "power.q_rpp:2",
    ]),

    # That FET's gate is held at ground through its resistor, so it conducts
    # only when the supply is the right way round. Routed below everything.
    ("RPP_GATE", SIGNAL, F, [
        "power.q_rpp:1", (-6.74, -18.7), (-10.41, -18.7), "power.r_gate:1",
    ]),

    # The 12 V bus runs on its own line above the input chain, with a stub down
    # to each part. Running it through the row would cross four ground pads.
    ("12V", POWER, F, [(-4.86, -16.5), (13.6, -16.5)]),
    ("12V", POWER, F, ["power.q_rpp:3", (-4.86, -16.5)]),
    ("12V", POWER, F, ["power.tvs:1", (-1.85, -16.5)]),
    ("12V", POWER, F, ["power.c_bulk:1", (5.52, -16.5)]),
    ("12V", POWER, F, ["power.c_hf:1", (10.55, -16.5)]),
    # Down the right of the decoupling capacitor and into the regulator's input.
    ("12V", POWER, F, [(13.6, -16.5), (13.6, -10.7), "rail.ldo:3"]),
    # The regulator's input capacitor hangs off the same vertical.
    ("12V", POWER, F, ["rail.c_in:1", (10.55, -6.0), "power.c_hf:1"]),
    # Down the middle of the board to the LED branches, through the test point.
    ("12V", POWER, F, [(13.6, -10.7), (13.6, -4.0), (15.5, -4.0), (15.5, 15.0)]),
    # Across to the button, keeping below the terminal.
    ("12V", POWER, F, [
        "power.q_rpp:3", (-4.86, -5.0), (-22.0, -5.0), "switch.button:1",
    ]),

    # The button has two holes per pole, joined inside the switch but not on
    # the board. DRC counts that as unconnected until copper joins them.
    ("12V", POWER, F, [(-22.0, 6.0), (-15.5, 6.0)]),

    # The regulator's output pin and its tab are one pad in the netlist but two
    # pieces of copper, so they need joining, same as the button's poles.
    ("3V3", SIGNAL, F, [(15.35, -13.0), (21.65, -13.0)]),

    # Regulator output. It leaves from the tab and drops below the package to
    # reach the output capacitor.
    ("3V3", SIGNAL, F, [
        (21.65, -13.0), (21.65, -9.8), (18.55, -9.8), "rail.c_out:1",
    ]),
    ("3V3", SIGNAL, F, ["rail.c_out:1", "rail.r_load:1"]),
    ("3V3", SIGNAL, F, ["rail.r_load:1", (18.59, -2.0), "tp_3v3:1"]),

    # Button to the debounce network. The track passes through the button's
    # second pad of the same pole, which is the same net.
    ("BTN", SIGNAL, F, ["switch.button:2", "switch.r_series:1"]),

    # The gate node: series resistor, pulldown, capacitor, FET and test point
    # all meet on one line.
    ("GATE", SIGNAL, F, [
        "switch.r_series:2", (-3.5, 10.5), (-3.5, 11.05), "switch.q_switch:1",
    ]),
    ("GATE", SIGNAL, F, ["switch.r_pulldown:1", (-6.91, 10.5)]),
    ("GATE", SIGNAL, F, ["switch.c_debounce:1", "switch.r_pulldown:1"]),

    # LED returns: a bus down the left of the array, into the FET's drain.
    ("LED_RETURN", POWER, F, ["switch.q_switch:3", (3.0, 12.0)]),
    ("LED_RETURN", POWER, F, [(3.0, 3.0), (3.0, 15.0)]),
    ("LED_RETURN", POWER, F, [(3.0, 3.0), "leds[0].led:1"]),
    ("LED_RETURN", POWER, F, [(3.0, 7.0), "leds[1].led:1"]),
    ("LED_RETURN", POWER, F, [(3.0, 11.0), "leds[2].led:1"]),
    ("LED_RETURN", POWER, F, [(3.0, 15.0), "leds[3].led:1"]),

    # Each branch: LED anode to its own resistor, resistor to the 12 V bus.
    ("LED_A", SIGNAL, F, ["leds[0].led:2", "leds[0].resistor:2"]),
    ("leds[1]-LED_A", SIGNAL, F, ["leds[1].led:2", "leds[1].resistor:2"]),
    ("leds[2]-LED_A", SIGNAL, F, ["leds[2].led:2", "leds[2].resistor:2"]),
    ("leds[3]-LED_A", SIGNAL, F, ["leds[3].led:2", "leds[3].resistor:2"]),
    ("12V", POWER, F, ["leds[0].resistor:1", (15.5, 3.0)]),
    ("12V", POWER, F, ["leds[1].resistor:1", (15.5, 7.0)]),
    ("12V", POWER, F, ["leds[2].resistor:1", (15.5, 11.0)]),
    ("12V", POWER, F, ["leds[3].resistor:1", (15.5, 15.0)]),
]

# --- ground stitching --------------------------------------------------------
#
# (pad, via position, net, via diameter, drill). Each entry is one surface-mount
# ground pad and its own way down to the plane. 0.3 mm drilled in a 0.6 mm pad
# leaves a 0.15 mm annular ring, which is the fab's floor.
#
# The terminal is absent on purpose: its leads go through the board, so it
# reaches the plane without help.

VIA = (0.6, 0.3)

VIAS = [
    ("power.r_gate:2", (-8.59, -15.2), "GND", *VIA),
    ("power.tvs:2", (2.45, -9.5), "GND", *VIA),
    ("power.c_bulk:2", (8.48, -9.5), "GND", *VIA),
    ("power.c_hf:2", (12.45, -10.5), "GND", *VIA),
    ("rail.ldo:1", (17.5, -15.3), "GND", *VIA),
    ("rail.c_in:2", (12.45, -3.5), "GND", *VIA),
    ("rail.c_out:2", (22.5, -8.0), "GND", *VIA),
    ("rail.r_load:2", (22.5, -5.0), "GND", *VIA),
    ("tp_gnd:1", (11.0, 0.5), "GND", *VIA),
    ("switch.r_pulldown:2", (-3.6, 14.0), "GND", *VIA),
    ("switch.c_debounce:2", (-3.2, 17.0), "GND", *VIA),
    ("switch.q_switch:2", (-1.94, 14.5), "GND", *VIA),
]

# --- the ground plane --------------------------------------------------------
#
# The whole back layer. KiCad clips the pour to the board outline, so the
# rectangle only has to be large enough to cover it.

# The pour keeps 0.5 mm from everything, which is the strictest clearance any
# rule on this board asks for: rules.kicad_dru wants that much between the
# unfused input and ground, because a person wires that terminal by hand and a
# stray strand should not be able to bridge them. KiCad's filler does not apply
# custom rules, so the pour has to be told.
PLANE = {
    "net": "GND",
    "layer": "B.Cu",
    "outline": [(-24.5, -19.5), (24.5, -19.5), (24.5, 19.5), (-24.5, 19.5)],
    "pad_clearance": 0.5,
    "min_thickness": 0.25,
    "thermal_gap": 0.3,
    "thermal_bridge": 0.5,
}
