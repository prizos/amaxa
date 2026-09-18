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
     "reference clock, and the straps that decide it should. The jack and its "
     "magnetics wait for M7d, with the board size."),
    ("Headers", ("header",),
     "Digital 2x20 and analog 2x15 to the power board."),
    ("Test points", ("tp_",),
     "A pad on every rail and on the signals bring-up needs."),
]

# What to say about each plotted layer. Keyed by the file's stem.
LAYERS: dict[str, str] = {
    "F_Cu": (
        "The component side. Dense around the LQFP-144's escapes and the two "
        "regulators; sparse above them, where the safety chain, the "
        "comparators and the buses are placed but not yet joined up."
    ),
    "In1_Cu": (
        "One solid ground plane. **No AGND/DGND split anywhere on this "
        "board** - analog is kept together by placement instead, which is a "
        "decision recorded in the plan rather than a habit."
    ),
    "In2_Cu": (
        "Power islands. 3V3 fills most of the layer; the 5 V island inside it "
        "is a higher-priority zone, so it wins the overlap. That is what lets "
        "the two share a layer without a hand-drawn boundary between them."
    ),
    "B_Cu": (
        "The solder side, nearly empty. Placement is single-sided for this "
        "spin, so the back carries only what had to change layer to escape "
        "the package."
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
    ("The copper is unfinished on purpose", """
`board.mk` says `ROUTING := incomplete`. The MCU core and the power block are
routed; everything from the safety chain onward is placed only, and its
connections are left for M8, when the whole board is in view. DRC runs in the
mode that still refuses anything drawn wrongly but does not demand what has not
been drawn at all - so a clean DRC here does not mean a finished board, and the
unrouted count above is the honest number.
"""),
    ("The renders confirm nothing electrical", """
No 3D model library is installed in the environment these were generated in, so
parts appear as their bare land patterns. More importantly, a footprint renders
identically whether or not its pinout is right: the P-FET whose pin order came
from an LCSC symbol looks correct in a render either way. The renders are good
for spacing, connector access and silkscreen legibility, and for nothing else.
The parts still waiting on a person are listed in `checks/config.py`, and not
one of them can be settled from a picture.
"""),
    ("The silkscreen still overlaps", """
Visible in the assembly plot, in the dense passive fields - the ADC network
column and the comparator outputs. Known, and deferred with the rest of the
finishing work.
"""),
]
