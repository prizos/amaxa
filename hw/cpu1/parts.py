"""
Every part on cpu1, as data.

The same shape as every board's part list: `PartSpec` from
`hw/tools/partspec.py`, a KiCad symbol, a footprint in this board's own
`parts/` tree, and the datasheet figures the checks reason about. Each value
comes from the part's review note in `parts/<LIB>/<LIB>.md`.

cpu1 is being built one block at a time, so this list grows with it.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from partspec import PartSpec, between, collect, exact, pm  # noqa: E402,F401


# --- the MCU -----------------------------------------------------------------

# Figures from ST's datasheet, DocID030538 Rev 3, as recorded in LQFP144.md:
# Table 24 (CEXT), Table 43 (HSE), Table 44 (LSE), the absolute maximum ratings
# (Table 21, IIO) and Figure 21 (NRST).
MCU_H743 = PartSpec(
    symbol="MCU_ST_STM32H7:STM32H743ZITx", footprint="LQFP144:LQFP-144_20x20mm_P0.5mm",
    prefix="U", manufacturer="STMicroelectronics", mpn="STM32H743ZIT6", lcsc="C114408",
    value="STM32H743ZIT6",
    params={
        "supply_voltage": between(1.62, 3.6),
        "vcap_capacitance": exact(2.2e-6),
        "hse_gm_crit_max": exact(1.5e-3),
        "hse_load_capacitor": between(5e-12, 25e-12),
        "lse_gm_crit_max": exact(2.7e-6),       # LSEDRV = 11, high drive
        "io_current_max": exact(20e-3),
        "nrst_capacitor": exact(100e-9),
    },
)


# --- passives ------------------------------------------------------------------
# Samsung and FH, all JLCPCB Basic or long-stocked Extended parts. See each
# library's review note.

_C0402 = dict(symbol="Device:C", footprint="C0402:C_0402_1005Metric", prefix="C")

CAP_100N_0402 = PartSpec(
    **_C0402, manufacturer="Samsung", mpn="CL05B104KO5NNNC", lcsc="C1525", value="100nF",
    params={"capacitance": pm(100e-9, 0.10), "max_voltage": exact(16.0)},
)
CAP_1U_0402 = PartSpec(
    **_C0402, manufacturer="Samsung", mpn="CL05A105KA5NQNC", lcsc="C52923", value="1uF",
    params={"capacitance": pm(1e-6, 0.10), "max_voltage": exact(25.0)},
)
CAP_2U2_0402 = PartSpec(
    **_C0402, manufacturer="Samsung", mpn="CL05A225MQ5NSNC", lcsc="C12530", value="2.2uF",
    params={"capacitance": pm(2.2e-6, 0.20), "max_voltage": exact(6.3)},
)
CAP_8P2_0402 = PartSpec(
    **_C0402, manufacturer="FH", mpn="0402CG8R2C500NT", lcsc="C1579", value="8.2pF",
    params={"capacitance": between(7.95e-12, 8.45e-12), "max_voltage": exact(50.0)},
)
CAP_6P8_0402 = PartSpec(
    **_C0402, manufacturer="FH", mpn="0402CG6R8C500NT", lcsc="C1576", value="6.8pF",
    params={"capacitance": between(6.55e-12, 7.05e-12), "max_voltage": exact(50.0)},
)
CAP_4U7_0603 = PartSpec(
    symbol="Device:C", footprint="C0603:C_0603_1608Metric", prefix="C",
    manufacturer="Samsung", mpn="CL10A475KO8NNNC", lcsc="C19666", value="4.7uF",
    params={"capacitance": pm(4.7e-6, 0.10), "max_voltage": exact(16.0)},
)

_R0402 = dict(symbol="Device:R", footprint="R0402:R_0402_1005Metric", prefix="R",
              manufacturer="UNI-ROYAL")
RES_10K_0402 = PartSpec(
    **_R0402, mpn="0402WGF1002TCE", lcsc="C25744", value="10k",
    params={"resistance": pm(10_000, 0.01), "max_power": exact(0.0625)},
)
RES_1K_0402 = PartSpec(
    **_R0402, mpn="0402WGF1001TCE", lcsc="C11702", value="1k",
    params={"resistance": pm(1_000, 0.01), "max_power": exact(0.0625)},
)

# Between 3V3 and VDDA: 600 ohm at 100 MHz keeps digital noise off the analog
# supply, and 0.9 ohm DC barely moves VDDA at the ADCs' few milliamps.
FERRITE_600R_0402 = PartSpec(
    symbol="Device:FerriteBead_Small", footprint="FB0402:L_0402_1005Metric", prefix="FB",
    manufacturer="Sunlord", mpn="GZ1005D601TF", lcsc="C14182", value="600R",
    params={"dc_resistance": exact(0.9), "max_current": exact(0.1)},
)


# --- clocks ----------------------------------------------------------------------

# Chosen on oscillator gain margin, not on price or stock. AN2867 asks for the
# MCU's maximum critical gm to be at least five times the crystal's, and that
# rules out every in-stock 8 MHz part in 3225 or HC-49S. This one has an 8 pF
# load and C0 under 5 pF. See XTAL5032.md.
XTAL_8M = PartSpec(
    symbol="Device:Crystal", footprint="XTAL5032:Crystal_SMD_5032-2Pin_5.0x3.2mm", prefix="Y",
    manufacturer="HCI", mpn="L0153G28000F08DTNJ", lcsc="C5221298", value="8MHz",
    params={
        "frequency": exact(8e6),
        "load_capacitance": exact(8e-12),
        "esr_max": exact(80.0),
        "shunt_capacitance": between(0.0, 5e-12),
    },
)

# 6 pF load and 0.85 pF C0, for the same reason: the common 12.5 pF parts give a
# margin barely above one against the H743's strongest LSE drive. Pins 2 and 3
# must not be connected. See XTAL_MC306.md.
XTAL_32K = PartSpec(
    symbol="Device:Crystal_GND23", footprint="XTAL_MC306:Crystal_SMD_SeikoEpson_MC306-4Pin_8.0x3.2mm",
    prefix="Y", manufacturer="Seiko Epson", mpn="Q13MC30620006", lcsc="C83979", value="32.768kHz",
    params={
        "frequency": exact(32768.0),
        "load_capacitance": exact(6e-12),
        "esr_max": exact(50e3),
        "shunt_capacitance": exact(0.85e-12),
    },
)


# --- people and debug --------------------------------------------------------------

_LED0603 = dict(symbol="Device:LED", footprint="LED0603:LED_0603_1608Metric", prefix="D",
                manufacturer="Hubei KENTO Elec")
LED_RED_0603 = PartSpec(
    **_LED0603, mpn="KT-0603R", lcsc="C2286", value="red",
    params={"forward_voltage": between(1.8, 2.4), "max_current": exact(20e-3)},
)
LED_YELLOW_GREEN_0603 = PartSpec(
    **_LED0603, mpn="KT-0603YG", lcsc="C2289", value="yellow-green",
    params={"forward_voltage": between(2.0, 2.2), "max_current": exact(20e-3)},
)

# The same part as led12's, which is already verified.
BUTTON_6MM = PartSpec(
    symbol="Switch:SW_Push", footprint="SW6MM:SW_PUSH_6mm", prefix="SW",
    manufacturer="Korean Hroparts Elec", mpn="K2-1102DP-C4SW-04", lcsc="C110153",
    value="6mm",
)

# A footprint, not a part: the Tag-Connect cable's pogo pins land on bare pads.
TAG_CONNECT = PartSpec(
    symbol="Connector:Conn_ARM_SWD_TagConnect_TC2030",
    footprint="TC2030:Tag-Connect_TC2030-IDC-NL_2x03_P1.27mm_Vertical", prefix="J",
    manufacturer="Tag-Connect", mpn="TC2030-IDC-NL", lcsc=None, value="SWD",
)

TEST_PAD = PartSpec(
    symbol="Connector:TestPoint", footprint="TP15:TestPoint_Pad_1.5x1.5mm", prefix="TP",
    manufacturer="-", mpn="TP-1.5MM", lcsc=None, value="TP",
)


ALL: dict[str, PartSpec] = collect(globals())
"""Every part, by the name it is known by here. Used by the parts checks."""
