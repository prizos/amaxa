"""
Every part on the led12 board, as data.

Deliberately free of any SKiDL import: this is a description of what we buy and
what its datasheet says, and it should stay readable, diffable and checkable
without a design tool in the loop. `led12.py` turns these into SKiDL parts;
`checks/test_parts.py` reads them to confirm each symbol exists and its pin
numbers match its footprint's pads.

Each part names a **KiCad symbol** and a **footprint in our own parts/ tree**.
The symbol is what makes the design readable — pins gain names like `VI`, `VO`,
`G`, `S`, `D` instead of bare numbers — and it is also what catches a part wired
to the wrong pin, because the symbol's pin numbers must line up with the
footprint's pads.

Parameters are SI, as `(low, high)` pairs, and their names are the ones the
checks and simulation decks already use. Do not rename them: nineteen
`(path, name)` pairs are hard-coded in `checks/test_electrical.py` and eleven
more in the `.cir.in` decks.

Every value here comes from the part's review note in `parts/<LIB>/<LIB>.md`,
which records the datasheet it was read from and what a human confirmed.
"""

from dataclasses import dataclass, field


# --- how a tolerance is written ---------------------------------------------


def pm(nominal: float, fraction: float) -> tuple[float, float]:
    """A nominal value with a symmetric tolerance: `pm(2200, 0.01)` is 2.2k ±1%."""
    return nominal * (1 - fraction), nominal * (1 + fraction)


def exact(value: float) -> tuple[float, float]:
    """A single figure from a datasheet, with no stated spread."""
    return value, value


def between(low: float, high: float) -> tuple[float, float]:
    """A range the datasheet states outright, such as a threshold voltage."""
    return low, high


@dataclass(frozen=True)
class PartSpec:
    """One purchasable part, or one deliberately unpurchased piece of copper."""

    symbol: str
    """KiCad symbol, `Library:Name`. Its pin numbers must match the footprint."""

    footprint: str
    """`<LIB>:<NAME>`, resolved against `parts/<LIB>/<NAME>.kicad_mod`."""

    prefix: str
    """Designator prefix we expect KiCad's symbol to assign."""

    manufacturer: str
    mpn: str

    lcsc: str | None
    """Supplier code, or None for something we deliberately do not buy."""

    value: str
    """What goes in the BOM's Value column and on the silkscreen."""

    params: dict[str, tuple[float, float]] = field(default_factory=dict)
    """Datasheet figures the checks and simulations reason about, in SI units."""


# --- resistors, 0805, 1 %, 125 mW -------------------------------------------
# One Yageo series so the BOM carries a single supplier line. See R0805.md for
# why the LED series resistor is 2.2k and not the 680R first drawn.

_R0805 = dict(
    symbol="Device:R",
    footprint="R0805:R_0805_2012Metric",
    prefix="R",
    manufacturer="Yageo",
)
_R0805_RATINGS = {"max_power": exact(0.125), "max_voltage": exact(150.0)}

RES_2K2 = PartSpec(
    **_R0805, mpn="RC0805FR-072K2L", lcsc="C114561", value="2.2k",
    params={"resistance": pm(2200, 0.01), **_R0805_RATINGS},
)
RES_10K = PartSpec(
    **_R0805, mpn="RC0805FR-0710KL", lcsc="C84376", value="10k",
    params={"resistance": pm(10_000, 0.01), **_R0805_RATINGS},
)
RES_100K = PartSpec(
    **_R0805, mpn="RC0805FR-07100KL", lcsc="C96346", value="100k",
    params={"resistance": pm(100_000, 0.01), **_R0805_RATINGS},
)
RES_3K3 = PartSpec(
    **_R0805, mpn="RC0805FR-073K3L", lcsc="C114531", value="3.3k",
    params={"resistance": pm(3300, 0.01), **_R0805_RATINGS},
)

# --- ceramic capacitors ------------------------------------------------------

_C0805 = dict(symbol="Device:C", footprint="C0805:C_0805_2012Metric", prefix="C")

CAP_100N = PartSpec(
    **_C0805, manufacturer="YAGEO", mpn="CC0805KRX7R9BB104", lcsc="C49678",
    value="100nF",
    params={"capacitance": pm(100e-9, 0.10), "max_voltage": exact(50.0)},
)
CAP_1U = PartSpec(
    **_C0805, manufacturer="Samsung", mpn="CL21B105KBFNNNE", lcsc="C28323",
    value="1uF",
    params={"capacitance": pm(1e-6, 0.10), "max_voltage": exact(50.0)},
)
CAP_10U = PartSpec(
    **_C0805, manufacturer="Samsung", mpn="CL21A106KAYNNNE", lcsc="C15850",
    value="10uF",
    params={"capacitance": pm(10e-6, 0.20), "max_voltage": exact(25.0)},
)

# 47 uF and not the 100 uF first drawn: 100 uF at 25 V does not exist in a 1210
# MLCC, and the part originally chosen for it was a 6.3 V device. See C1210.md.
CAP_BULK = PartSpec(
    symbol="Device:C", footprint="C1210:C_1210_3225Metric", prefix="C",
    manufacturer="Chinocera", mpn="HGC1210R5476M250NSVK", lcsc="C7432791",
    value="47uF",
    params={"capacitance": pm(47e-6, 0.20), "max_voltage": exact(25.0)},
)

# --- protection --------------------------------------------------------------

# The 468 series, not the 466 first drawn: the 466 is fast-acting despite having
# been picked to be slow-blow. See FUSE_1206.md.
FUSE_1A = PartSpec(
    symbol="Device:Fuse", footprint="FUSE_1206:Fuse_1206_3216Metric", prefix="F",
    manufacturer="Littelfuse", mpn="0468001.NRHF", lcsc="C45157", value="1A",
    params={"trip_current": exact(1.0)},
)

# Breakdown and clamping voltage are not attributes of a generic diode, but the
# whole 12 V rail is designed around them, so they are recorded here.
TVS_12V = PartSpec(
    symbol="Device:D_TVS", footprint="SMB:D_SMB", prefix="D",
    manufacturer="Brightking", mpn="SMBJ12A/TR13", lcsc="C111091", value="SMBJ12A",
    params={
        "reverse_working_voltage": exact(12.0),
        "v_breakdown_min": exact(14.7),
        "v_clamp_max": exact(19.9),
    },
)

# --- semiconductors ----------------------------------------------------------

# Transistor_FET, not Device: `Device:Q_PMOS_GSD` does not exist in any KiCad
# library, which the design source named for months without anything noticing,
# because nothing resolved symbols. test_symbols.py is what notices now.
# Both of these carry pins numbered 1=G, 2=S, 3=D, matching the SOT-23 pads.
_SOT23 = dict(footprint="SOT23:SOT-23", prefix="Q")

# AO3407A and not the Si2301 first drawn: this circuit holds the gate at ground
# while the source sits at the rail, so V_gs is the whole 13.2 V in normal
# operation, and the Si2301 is rated +/-8 V. See SOT23.md.
PFET_RPP = PartSpec(
    symbol="Transistor_FET:Q_PMOS_GSD", **_SOT23,
    manufacturer="Alpha & Omega Semiconductor", mpn="AO3407A", lcsc="C15155",
    value="AO3407A",
    params={
        "max_drain_source_voltage": exact(30.0),
        "max_continuous_drain_current": exact(4.3),
        "on_resistance": exact(0.048),
    },
)

NFET_SWITCH = PartSpec(
    symbol="Transistor_FET:2N7002", **_SOT23,
    manufacturer="onsemi", mpn="2N7002LT1G", lcsc="C16338", value="2N7002",
    params={
        "max_drain_source_voltage": exact(60.0),
        "max_continuous_drain_current": exact(0.115),
        "gate_source_threshold_voltage": between(1.0, 2.5),
        "on_resistance": exact(7.5),
    },
)

# Chosen for a bounded forward voltage: 2.0 to 2.4 V at 20 mA, written down in
# the datasheet rather than inferred. See LED0805.md.
LED_RED = PartSpec(
    symbol="Device:LED", footprint="LED0805:LED_0805_2012Metric", prefix="D",
    manufacturer="Everlight", mpn="17-21SURC/S530-A3/4T", lcsc="C2943978",
    value="red",
    params={"forward_voltage": between(2.0, 2.4), "max_current": exact(0.020)},
)

# The symbol is KiCad's LM1084-3.3, which carries the same pin numbering
# (GND=1, VOUT=2, VIN=3). No symbol exists for the Gainsil part itself.
# It replaced the AMS1117, whose 15 V maximum sat below the TVS clamp of
# 19.9 V - the protection would have destroyed what it protects. See SOT223.md.
LDO_3V3 = PartSpec(
    symbol="Regulator_Linear:LM1084-3.3", footprint="SOT223:SOT-223-3_TabPin2",
    prefix="U", manufacturer="Gainsil", mpn="GS2401C-33CTR3", lcsc="C6283798",
    value="3.3V",
    params={"v_in_max": exact(44.0), "v_out": pm(3.3, 0.01)},
)

# --- mechanical --------------------------------------------------------------

# The leads 6.5 mm apart are internally connected; the two independent poles are
# the leads 4.5 mm apart. KiCad numbers the four holes 1, 1, 2, 2. See SW6MM.md.
BUTTON_6MM = PartSpec(
    symbol="Switch:SW_Push", footprint="SW6MM:SW_PUSH_6mm", prefix="SW",
    manufacturer="Korean Hroparts Elec", mpn="K2-1102DP-C4SW-04", lcsc="C110153",
    value="6mm",
)

# The Kangnex part drops into KiCad's Phoenix MKDS footprint exactly - same
# 5.08 mm pitch, same 1.30 mm drill - at a quarter of the price. Do not
# substitute the KF128: its leads need a 1.60 mm drill. See TERM_2P5008.md.
SCREW_TERM_2 = PartSpec(
    symbol="Connector:Screw_Terminal_01x02",
    footprint="TERM_2P5008:TerminalBlock_Phoenix_MKDS-1,5-2-5.08_1x02_P5.08mm_Horizontal",
    prefix="J", manufacturer="Ningbo Kangnex", mpn="WJ500V-5.08-2P", lcsc="C8465",
    value="12V in",
)

# Bare copper, not a purchasable part: `lcsc=None` keeps it off the BOM.
# Square rather than round because a footprint whose silkscreen is only a circle
# has no computable bounding box. See TP15.md.
TEST_PAD = PartSpec(
    symbol="Connector:TestPoint", footprint="TP15:TestPoint_Pad_1.5x1.5mm",
    prefix="TP", manufacturer="amaxa", mpn="TP-1.5MM", lcsc=None, value="",
)


ALL: dict[str, PartSpec] = {
    name: value
    for name, value in list(globals().items())
    if isinstance(value, PartSpec)
}
"""Every part, by the name it is known by here. Used by the parts checks."""
