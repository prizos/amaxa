"""
What `tools/review.py` needs to know about cpu1 that it cannot read off the board.

Everything numeric in the review document is read from the board file and from
`build/design.json`. What is here is the prose: which block each part address
belongs to, what each block is for, and what someone looking at a plot of this
particular board should be told before they draw a conclusion from it.

Kept beside the board rather than in the tool because it is about this board.
The tool is about any board.
"""

TITLE = "cpu1 — the STM32H743 control board"

LEDE = """
One STM32H743ZIT6 generating every hard real-time signal - PWM,
PWM-synchronised sampling, the hardware trip - for a purely analog power board
soldered underneath it. This is the board as it stands, plotted from the same
`.kicad_pcb` the fab package is built from.
""".strip()

# Which block each part belongs to, by the address it is built under in
# cpu1.py. The order is the order the blocks are built in, which is also the
# order they were designed in, so the document reads the way the board grew.
BLOCKS: list[tuple[str, tuple[str, ...], str]] = [
    ("MCU core", ("mcu", "core", "leds", "button", "debug"),
     "The package, both crystals, reset and boot, the Tag-Connect pad, and a "
     "decoupling capacitor for every supply pin."),
    ("Input protection", ("power",),
     "Terminal, fuse, reverse-polarity FET with its gate Zener, and the TVS "
     "whose clamp voltage the buck has to outlive."),
    ("100 V buck", ("buck5",),
     "LM5164 constant-on-time buck to 5 V, rated far above that clamp - a "
     "60 V part here would be the regulator defect from led12 again."),
    ("3V3 buck", ("buck3v3",),
     "TPS562200 down to the logic rail."),
    ("Analog supply", ("analog",),
     "5VA and its ferrite, for the sensors on the power board."),
    ("Reference", ("vref",),
     "3.0 V series reference into VREF+, buffered out to the analog header."),
    ("Safety chain", ("safety",),
     "Two octal buffers and the hardware latch. Nothing reaches a gate driver "
     "unless firmware has deliberately allowed it, and a reset takes the "
     "permission away."),
    ("Trip comparators", ("trip",),
     "Seven TLV3501s and the threshold DAC, which powers up at zero - so an "
     "unprogrammed board trips as it powers up rather than switching."),
    ("ADC networks", ("adc",),
     "One RC per channel, sized from both ends: low enough to stop the "
     "switching node aliasing into the measurement, high enough to recharge "
     "inside the sampling window."),
    ("CAN FD", ("can",),
     "TCAN1044V with split termination on a solder jumper."),
    ("RS-485", ("rs485",),
     "THVD1450, fail-safe biased on-chip, 120 ohm on a jumper."),
    ("USB-C", ("usb",),
     "A device port that senses VBUS and takes no power from it. The board's "
     "one differential pair, drawn to 90 ohm from the stackup rather than to "
     "a width somebody remembered."),
    ("Ethernet", ("eth",),
     "The LAN8742A, a 25 MHz crystal it multiplies up to make the RMII "
     "reference clock, the straps that decide it should, and a jack with the "
     "magnetics inside it. The board grew to 130 by 110 mm to hold the jack."),
    ("Headers", ("header",),
     "Digital 2x20 and analog 2x15 to the power board."),
    ("Plane stitching", ("stitch",),
     "Capacitors that exist for the return current rather than for any part's "
     "supply: the front of this board is referenced to ground and the back to "
     "the supply islands, and these are where a signal changing layer can hand "
     "its return across."),
    ("Test points", ("tp_",),
     "A pad on every rail and on the signals bring-up needs."),
]

# What to say about each plotted layer. Keyed by the file's stem.
LAYERS: dict[str, str] = {
    "F_Cu": (
        "The component side, and most of the board's copper. Dense around the "
        "LQFP-144's escapes, the two regulators and the buffered PWM "
        "outputs; the long "
        "parallel runs across the middle are the analog inputs on their way "
        "from the header to the comparators. The two pairs in the top-left "
        "corner are the Ethernet link, and the only tracks on this board "
        "drawn to an impedance rather than a width."
    ),
    "In1_Cu": (
        "Ground, solid, notched at the top-left corner where the Ethernet "
        "jack's cable end sits. **No AGND/DGND split anywhere on this board** - "
        "analog is kept together by placement instead, which is a decision "
        "recorded in the plan rather than a habit. This is the plane the "
        "impedance-controlled pairs on F.Cu are referenced to."
    ),
    "In2_Cu": (
        "A solid 3V3 plane, and solid is the point. It used to carry a 5 V "
        "island inside it, which cut the plane In3.Cu is referenced to: In3 "
        "sits 0.175 mm below this layer and 0.43 mm above the ground under "
        "it, so most of its return flows here, and every motion-feedback line "
        "crossed the island's edge. The island is on B.Cu now, where it is "
        "local copper and nobody's reference."
    ),
    "In3_Cu": (
        "The inner signal layer, and the reason this board is six layers "
        "rather than four. It carries the eight motion-feedback signals from "
        "the package to the connector: on four layers every one of those "
        "crossings was a via, and there was nowhere left to put one. Both "
        "planes around it are solid, which is what keeps its return "
        "continuous - the nearer of the two is In2, and it is the layer that "
        "had to give up its island for that to be true."
    ),
    "In4_Cu": (
        "The second ground plane, and what both outer layers return to. With "
        "ground under B.Cu as well as under F.Cu, every through-hole via is a "
        "ground-to-ground layer change and any of the board's <<GROUND_VIAS>> "
        "ground vias "
        "will carry the return across."
    ),
    "B_Cu": (
        "The solder side, and the 5 V island. Placement is single-sided for "
        "this spin, so the back otherwise carries only what had to change "
        "layer: the analog sense lines "
        "crossing the input bank, the static signals running under the "
        "package, and the six RMII lines taking the long way round it."
    ),
    "assembly": (
        "Silkscreen over the fabrication layer: every designator, every "
        "courtyard, and the board outline. This is the drawing to check a "
        "part against before ordering."
    ),
}

RENDERS = {
    "top": "Top - single-sided placement.",
    "bottom": "Bottom - vias and through-hole pads only.",
}

# Said before anyone draws a conclusion from a picture of this board.
CAVEATS = [
    ("The copper is finished, the board is not", """
`board.mk` says `ROUTING := complete`, and DRC now runs in the mode that
demands every connection: it reports no unconnected items and no violations.
Every net on this board is drawn.

That is a statement about copper and nothing else. <<WAITING>>; the silkscreen
still overlaps in the dense passive fields, and nothing here has been built.
"""),
    ("The renders confirm nothing electrical", """
No 3D model library is installed in the environment these were generated in, so
parts appear as their bare land patterns. More importantly, a footprint renders
identically whether or not its pinout is right: the P-FET whose pin order came
from an LCSC symbol looks correct in a render either way. The renders are good
for spacing, connector access and silkscreen legibility, and for nothing else.
<<WAITING>> — and nothing of that kind could be settled from a picture
anyway.
"""),
    ("The silkscreen is placed, not drawn", """
Every reference designator's position is searched for rather than written
down: above the part, then below, either side, the corners, taking the first
place that clears every pad and every designator already placed. No two are
printed over each other, which a check enforces.

Designators do cross outlines. Over a part's own outline is where a designator
belongs; over a neighbour's it is untidy and still legible. Over another
designator it is neither, and there are none - that is the part a check
enforces, and it is the only part stated here as a number.

This paragraph used to count them: "six, four of those a part's own, one a
neighbour's", which is five. It was written before the board went from four
layers to six and nothing re-measured it. A count that cannot be derived from
the board on every build does not belong in a document that claims it cannot
go stale.
"""),
]
