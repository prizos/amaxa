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
        # Table 84: what the converter presents at an analog pin.
        "adc_sample_capacitance": exact(4e-12),
        "adc_sample_resistance": exact(50.0),
        # What a 5 V-tolerant pin may see, as the datasheet states it: a
        # headroom above the *lowest* of the part's supplies, not a fixed
        # number. Recorded as the overhead so a check reads the board's own
        # rail rather than assuming 3.3 V. Table 12, note 3.
        "ft_input_overhead": exact(4.0),
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


# --- the input stage ---------------------------------------------------------
#
# 9 to 36 V in: a terminal, a fuse, a P-FET across the supply and a TVS on the
# rail behind it. The order matters and is argued in cpu1.py.

# The same Kangnex part as led12's, in KiCad's Phoenix MKDS footprint.
SCREW_TERM_2 = PartSpec(
    symbol="Connector:Screw_Terminal_01x02",
    footprint="TERM_2P5008:TerminalBlock_Phoenix_MKDS-1,5-2-5.08_1x02_P5.08mm_Horizontal",
    prefix="J", manufacturer="Ningbo Kangnex", mpn="WJ500V-5.08-2P", lcsc="C8465",
    value="9-36V",
)

# Slow-blow, and rated 63 V against a rail the TVS holds below 64.5 V only while
# it conducts - so the fuse, not the TVS, is what a sustained overvoltage has to
# open. led12 uses the same part; see FUSE_1206.md there and here.
# 1.5 A and not 1 A. The board draws 0.68 A at its terminal once the 3V3
# rail's budget is reflected through the 5 V buck that feeds it - the sum
# nothing used to compute - and a fuse wants half again on top of the load it
# passes every day. The same Littelfuse 468 series, one step up; the FET
# behind it still carries 2.3 A, which is more than this fuse will pass.
FUSE_1A5 = PartSpec(
    symbol="Device:Fuse", footprint="FUSE_1206:Fuse_1206_3216Metric", prefix="F",
    manufacturer="Littelfuse", mpn="046801.5NRHF", lcsc="C151143", value="1.5A",
    params={
        "trip_current": exact(1.5),
        "max_voltage": exact(63.0),
        "interrupt_rating": exact(50.0),
    },
)

# 100 V, not led12's 30 V part: the TVS sits behind this FET, so a reversed
# supply appears across it in full, and nothing clamps a negative transient
# below ground. SOT-223 for the 250 mOhm: a SOT-23 100 V P-FET is 1 ohm.
#
# Pins 1 = G, 2 = D, 3 = S, and the tab is pin 2, which is why the symbol is
# Q_PMOS_GDS and the footprint is TabPin2. See SOT223.md.
PFET_RPP = PartSpec(
    symbol="Transistor_FET:Q_PMOS_GDS", footprint="SOT223:SOT-223-3_TabPin2", prefix="Q",
    manufacturer="Diodes Incorporated", mpn="DMP10H400SE-13", lcsc="C156277",
    value="DMP10H400SE",
    params={
        "max_drain_source_voltage": exact(100.0),
        "max_gate_source_voltage": exact(20.0),
        "max_continuous_drain_current": exact(2.3),
        "on_resistance": exact(0.25),                      # maximum at V_gs = -10 V
        "gate_source_threshold_voltage": between(1.0, 3.0),
    },
)

# Holds V_gs off the FET's +/-20 V rating. The gate sits at ground through
# R_gate, so V_gs is the whole input voltage: 36 V in normal operation and up to
# the TVS's 64.5 V clamp during a surge, both beyond the FET.
#
# Unlike led12's, this Zener conducts in normal operation - anything above 15 V
# on a rail specified to 36 V does - and that is the intent, not a defect. The
# current is (V_in - V_z) / R_gate, a fifth of a milliamp, and
# test_power.py bounds the power in both parts. Same part as led12's; see
# SOD123.md.
ZENER_GATE_CLAMP = PartSpec(
    symbol="Device:D_Zener", footprint="SOD123:D_SOD-123", prefix="D",
    manufacturer="Jiangsu Changjing Electronics Technology",
    mpn="BZT52C15", lcsc="C2104", value="15V",
    params={
        "zener_voltage": between(13.8, 15.6),
        "max_power": exact(0.5),
    },
)

# SMBJ40A and not the 36 A part: a TVS must stand off the top of the rail it
# protects, and this board's input is specified to 36.0 V exactly. See SMB.md.
TVS_40V = PartSpec(
    symbol="Device:D_TVS", footprint="SMB:D_SMB", prefix="D",
    manufacturer="BORN", mpn="SMBJ40A", lcsc="C152095", value="SMBJ40A",
    params={
        "reverse_working_voltage": exact(40.0),
        "v_breakdown_max": exact(51.1),
        "v_clamp_max": exact(64.5),
    },
)


# --- the regulators ----------------------------------------------------------

# 100 V-class, so the TVS's 64.5 V clamp is not the thing that decides whether
# the board survives a surge. Constant on-time: the switching frequency comes
# from R_on, and the feedback node needs its own ripple, which is what the
# Type 3 network in cpu1.py is for. Figures from TI's datasheet SNVSAU4A
# (January 2019), tables in section 6, as recorded in SO8EP.md.
BUCK_100V = PartSpec(
    symbol="Regulator_Switching:LM5164DDA",
    footprint="SO8EP:SOIC-8-1EP_3.9x4.9mm_P1.27mm_EP2.514x3.2mm",
    prefix="U", manufacturer="Texas Instruments", mpn="LM5164DDAR", lcsc="C477928",
    value="LM5164",
    params={
        "v_in": between(6.0, 100.0),
        "v_in_abs_max": exact(100.0),
        "load_current_max": exact(1.0),
        "v_feedback": between(1.181, 1.218),
        # The on-time is inversely proportional to V_in. One characterised point
        # fixes the constant; test_power.py derives the frequency from it and
        # checks it against the datasheet's own 300 kHz worked example.
        "on_time_at_reference": exact(2550e-9),
        "on_time_reference_resistance": exact(75e3),
        "on_time_reference_input_voltage": exact(12.0),
        "on_time_min": exact(50e-9),
        "switching_frequency_max": exact(1e6),
        "peak_current_limit_min": exact(1.25),
        "enable_threshold": between(1.45, 1.55),
        # Section 8.2.2.6: 20 mV of ripple at the feedback pin at typical
        # conditions, and never less than 12 mV at minimum input.
        "feedback_ripple_target": exact(20e-3),
        "feedback_ripple_min": exact(12e-3),
        "bst_capacitance": between(1.5e-9, 2.5e-9),
        "input_capacitance_min": exact(2.2e-6),
        "pgood_pullup": between(10e3, 100e3),
    },
)

# The 3V3 rail, from 5 V. D-CAP2, so no compensation and no ripple injection:
# the recommended inductor and output capacitance come from the datasheet's
# Table 2 row for a 3.3 V output. Figures from SLVSCB0B (August 2014), as
# recorded in TSOT23_6.md.
BUCK_3V3 = PartSpec(
    symbol="Regulator_Switching:TPS562200", footprint="TSOT23_6:TSOT-23-6",
    prefix="U", manufacturer="Texas Instruments", mpn="TPS562200DDCR", lcsc="C49757",
    value="TPS562200",
    params={
        "v_in": between(4.5, 17.0),
        "v_feedback": between(0.758, 0.772),
        "switching_frequency": exact(650e3),
        "current_limit_min": exact(2.5),
        "bst_capacitance": exact(100e-9),
        "input_capacitance_min": exact(10e-6),
        "output_capacitance": between(20e-6, 68e-6),   # Table 2, V_out = 3.3 V
        "inductance": between(2.2e-6, 4.7e-6),         # Table 2, V_out = 3.3 V
    },
)

# VREF+ for the ADCs. A series reference, not a divider or the MCU's own
# VREFBUF: 0.2 % initial and 75 ppm/degC is what the current and voltage
# measurements are ultimately scaled by. Figures from TI's SBVS032F
# (August 2008), as recorded in SOT23.md.
VREF_3V0 = PartSpec(
    symbol="Reference_Voltage:REF3030", footprint="SOT23:SOT-23", prefix="U",
    manufacturer="Texas Instruments", mpn="REF3030AIDBZR", lcsc="C38423",
    value="REF3030",
    params={
        "output_voltage": between(2.994, 3.006),
        "v_in_max": exact(5.5),
        "output_current_max": exact(25e-3),
        "supply_bypass": exact(0.47e-6),
        "temperature_drift": exact(75e-6),
    },
)


# --- magnetics ---------------------------------------------------------------

# Saturation current above the buck's own peak current limit, so the inductor
# is never the thing that gives way first. See L_MWSA0603S.md.
IND_33U = PartSpec(
    symbol="Device:L", footprint="L_MWSA0603S:L_Sunlord_MWSA0603S", prefix="L",
    manufacturer="Sunlord", mpn="MWSA0603S-330MT", lcsc="C408454", value="33uH",
    params={
        "inductance": pm(33e-6, 0.20),
        "saturation_current": exact(2.5),
        "rms_current": exact(2.0),
        "dc_resistance": exact(0.27),
    },
)

IND_3U3 = PartSpec(
    symbol="Device:L", footprint="L_SWPA4030S:L_Sunlord_SWPA4030S", prefix="L",
    manufacturer="Sunlord", mpn="SWPA4030S3R3MT", lcsc="C15269", value="3.3uH",
    params={
        "inductance": pm(3.3e-6, 0.20),
        "saturation_current": exact(3.6),
        "rms_current": exact(2.4),
        "dc_resistance": exact(0.052),
    },
)


# --- passives the power block needs ------------------------------------------

# 100 V parts on the input: the datasheet asks for twice the maximum input
# voltage on a ceramic, because capacitance falls with DC bias.
CAP_2U2_100V_1210 = PartSpec(
    symbol="Device:C", footprint="C1210:C_1210_3225Metric", prefix="C",
    manufacturer="Samsung", mpn="CL32B225KCJSNNE", lcsc="C55151", value="2.2uF",
    params={"capacitance": pm(2.2e-6, 0.10), "max_voltage": exact(100.0)},
)
CAP_100N_100V_0603 = PartSpec(
    symbol="Device:C", footprint="C0603:C_0603_1608Metric", prefix="C",
    manufacturer="YAGEO", mpn="CC0603KRX7R0BB104", lcsc="C113803", value="100nF",
    params={"capacitance": pm(100e-9, 0.10), "max_voltage": exact(100.0)},
)

_C0805 = dict(symbol="Device:C", footprint="C0805:C_0805_2012Metric", prefix="C")
CAP_10U_0805 = PartSpec(
    **_C0805, manufacturer="Samsung", mpn="CL21A106KAYNNNE", lcsc="C15850", value="10uF",
    params={"capacitance": pm(10e-6, 0.20), "max_voltage": exact(25.0)},
)
CAP_22U_0805 = PartSpec(
    **_C0805, manufacturer="HRE", mpn="CGA0805X7R226M100MT", lcsc="C23692981", value="22uF",
    params={"capacitance": pm(22e-6, 0.20), "max_voltage": exact(10.0)},
)

CAP_3N3_0402 = PartSpec(
    **_C0402, manufacturer="YAGEO", mpn="CC0402KRX7R9BB332", lcsc="C107028", value="3.3nF",
    params={"capacitance": pm(3.3e-9, 0.10), "max_voltage": exact(50.0)},
)
CAP_2N2_0402 = PartSpec(
    **_C0402, manufacturer="YAGEO", mpn="CC0402KRX7R9BB222", lcsc="C106861", value="2.2nF",
    params={"capacitance": pm(2.2e-9, 0.10), "max_voltage": exact(50.0)},
)
# C0G, because this one couples the ripple ramp into the feedback node and an
# X7R's capacitance falls with bias. The datasheet asks for C0G by name.
#
# 220 pF and not the 56 pF of TI's reference design. Equation 26 is
# CB >= t / (3 x RFB1), where t is the load-transient settling time the design
# wants: TI get 56 pF from 75 us because their feedback divider's top resistor
# is 446 k. This board's is 158 k, chosen to land 5.0 V on standard values, so
# the same 56 pF satisfies the equation only to 26.5 us. 220 pF gives 98 us at
# the tolerance corner - 150 pF misses 75 us there by eight - and it is the
# value of this series with the stock. See SO8EP.md.
CAP_220P_0402 = PartSpec(
    **_C0402, manufacturer="FH", mpn="0402CG221J500NT", lcsc="C39122", value="220pF",
    params={"capacitance": pm(220e-12, 0.05), "max_voltage": exact(50.0)},
)

RES_226K_0402 = PartSpec(
    **_R0402, mpn="0402WGF2263TCE", lcsc="C26999", value="226k",
    params={"resistance": pm(226_000, 0.01), "max_power": exact(0.0625)},
)
RES_158K_0402 = PartSpec(
    **_R0402, mpn="0402WGF1583TCE", lcsc="C99856", value="158k",
    params={"resistance": pm(158_000, 0.01), "max_power": exact(0.0625)},
)
RES_121K_0402 = PartSpec(
    **_R0402, mpn="0402WGF1213TCE", lcsc="C11693", value="121k",
    params={"resistance": pm(121_000, 0.01), "max_power": exact(0.0625)},
)
# The Ethernet line terminations. Microchip's Figure 3.23 hangs one of these
# from each of TXP, TXN, RXP and RXN: in series across a pair they are ~100
# ohm, which in parallel with the 100 ohm the 1:1 transformer reflects from
# the cable gives the current-mode driver the 50 ohm it is specified into.
# Without them the driver works into 100 ohm and the amplitude is about double
# what Table 5.8 allows, and the receive pair has no chip-side termination at
# all. See parts/QFN24/QFN24.md.
RES_49R9_0402 = PartSpec(
    **_R0402, mpn="0402WGF499JTCE", lcsc="C25120", value="49R9",
    params={"resistance": pm(49.9, 0.01), "max_power": exact(0.0625)},
)

RES_100K_0402 = PartSpec(
    **_R0402, mpn="0402WGF1003TCE", lcsc="C25741", value="100k",
    params={"resistance": pm(100_000, 0.01), "max_power": exact(0.0625)},
)
RES_49K9_0402 = PartSpec(
    **_R0402, mpn="0402WGF4992TCE", lcsc="C25897", value="49.9k",
    params={"resistance": pm(49_900, 0.01), "max_power": exact(0.0625)},
)
RES_33K2_0402 = PartSpec(
    **_R0402, mpn="0402WGF3322TCE", lcsc="C122548", value="33.2k",
    params={"resistance": pm(33_200, 0.01), "max_power": exact(0.0625)},
)
RES_31K6_0402 = PartSpec(
    **_R0402, mpn="0402WGF3162TCE", lcsc="C11463", value="31.6k",
    params={"resistance": pm(31_600, 0.01), "max_power": exact(0.0625)},
)


# --- the safety chain --------------------------------------------------------
#
# The path from an MCU pin to a gate driver, and the two things that can break
# it: an enable the MCU holds, and a latch nothing but the MCU can clear.

# The symbol is KiCad's 74AHC541, because no library carries an LVC541A. Every
# pin number matches - TI's Pin Functions table was read in full - and only the
# input and output names differ, KiCad counting A0..A7 where TI counts A1..A8.
# See TSSOP20.md.
#
# LVC and not AHC or HC: what this part is for is going high-impedance quickly
# when the latch trips, and 7 ns of disable time is most of the trip budget's
# margin. HC at 3.3 V is four times that.
BUF_OCTAL = PartSpec(
    symbol="74xx:74AHC541", footprint="TSSOP20:TSSOP-20_4.4x6.5mm_P0.65mm",
    prefix="U", manufacturer="Texas Instruments", mpn="SN74LVC541APWR", lcsc="C113281",
    value="74LVC541A",
    params={
        "supply_voltage": between(1.65, 3.6),
        "propagation_delay_max": exact(5.1e-9),
        "disable_time_max": exact(7e-9),
        "enable_time_max": exact(7e-9),
        "output_skew_max": exact(1e-9),
        "output_current_max": exact(25e-3),          # per output, recommended
        "total_output_current_max": exact(50e-3),
        "input_low_voltage_max": exact(0.8),
        "input_high_voltage_min": exact(2.0),
    },
)

# The trip latch. A D flip-flop used as a set-reset: preset by anything that
# trips, cleared only by the MCU, and holding its state with no clock at all.
# The symbol is KiCad's 74AUP1G74, the same eight pins in the same order; see
# VSSOP8.md.
LATCH_DFF = PartSpec(
    symbol="74xGxx:74AUP1G74", footprint="VSSOP8:VSSOP-8_2.3x2mm_P0.5mm",
    prefix="U", manufacturer="Texas Instruments", mpn="SN74LVC1G74DCUR", lcsc="C70285",
    value="74LVC1G74",
    params={
        "supply_voltage": between(1.65, 5.5),
        "preset_to_output_max": exact(5.9e-9),
        "output_current_max": exact(24e-3),
        "input_low_voltage_max": exact(0.8),
        "input_high_voltage_min": exact(2.0),
    },
)

# Two Schottky diodes with their anodes joined, which is what lets three things
# pull the trip bus low without any of them being wired to each other: each
# reaches the bus through a diode and keeps its own net. Schottky and not
# silicon because the whole budget is the 0.8 V the logic calls a low, and a
# 0.7 V drop spends all of it. See SOT23.md.
SCHOTTKY_DUAL = PartSpec(
    symbol="Diode:BAT54A", footprint="SOT23:SOT-23", prefix="D",
    manufacturer="LRC", mpn="LBAT54ALT1G", lcsc="C12743", value="BAT54A",
    params={
        "forward_voltage_max": exact(0.24),          # at 0.1 mA
        "reverse_voltage_max": exact(30.0),
        "forward_current_max": exact(200e-3),
    },
)

# Series into every buffered output: enough to damp a ribbon cable's ringing
# without dropping anything a CMOS gate driver would notice.
RES_33R_0402 = PartSpec(
    **_R0402, mpn="0402WGF330JTCE", lcsc="C25105", value="33R",
    params={"resistance": pm(33, 0.01), "max_power": exact(0.0625)},
)

# Pin headers for now, by the user's decision: the connector to the power board
# gets chosen when there is a power board to connect to.
#
# The part ordered is the 2x40 of the same series, cut to 26 positions. There
# is no 2x26 male header in stock anywhere: HCTL do not list one, and the two
# that exist at LCSC - kinghelm's KH-2.54PH180-2X26P-L11.5 and its SMT sibling
# - are both at zero. A 2x40 strip is the normal way to get an odd length and
# this one is the same family, pitch and 8.5 mm pin as the 2x20 this connector
# grew from. See HDR2X26.md.
HEADER_2X26 = PartSpec(
    symbol="Connector_Generic:Conn_02x26_Odd_Even",
    footprint="HDR2X26:PinHeader_2x26_P2.54mm_Vertical", prefix="J",
    manufacturer="HCTL", mpn="PZ254-2-40-Z-8.5", lcsc="C2906029", value="digital",
    params={"current_rating": exact(3.0)},
)


# --- the trip comparators and their thresholds -------------------------------
#
# Seven trip points: each phase current in both directions, and the DC link's
# over-voltage. Bipolar current sensing is why there are two per phase - the
# signal idles mid-scale and leaves it either way.

# Singles rather than the two quad comparators the plan called for, because a
# quad this fast does not exist in stock: the choice was 4.5 ns in sevens or
# 300 ns in fours, and 300 ns is six times the whole trip budget. Push-pull
# output, so the seven reach the trip bus through Schottky diodes rather than
# by being wired together. See SOT23_6.md.
COMPARATOR = PartSpec(
    symbol="Comparator:TLV3501AIDBV", footprint="SOT23_6:SOT-23-6", prefix="U",
    manufacturer="Texas Instruments", mpn="TLV3501AIDBVR", lcsc="C193413",
    value="TLV3501",
    params={
        "supply_voltage": between(2.7, 5.5),
        # 20 mV of overdrive, over the whole temperature range. The 5 mV figure
        # is half as fast again, which is what the tap network in M6 has to
        # deliver against.
        "propagation_delay_max": exact(7e-9),
        "input_offset_voltage": exact(6.5e-3),
        "input_hysteresis": exact(6e-3),
        "common_mode_headroom": exact(0.2),      # from either rail
        "output_swing_from_rail": exact(50e-3),  # at 1 mA
    },
)

# Quad 12-bit, I2C. Its output range is its supply **once firmware has said
# so**: the part ships with V_REF = 1 in EEPROM, which selects the internal
# 2.048 V reference, and Table 4-2 of the datasheet is committed beside the
# part note as the evidence. This file used to state the supply case as though
# it were unconditional, and it is not - see MSOP10.md, which records what
# firmware has to write and why the power-up state is still the safe one.
#
# With the supply as the reference the thresholds are ratiometric to the logic
# rail while everything the ADCs measure is ratiometric to VREF+, which is the
# mismatch test_trip.py turns into a tolerance on every trip point.
THRESHOLD_DAC = PartSpec(
    symbol="Analog_DAC:MCP4728", footprint="MSOP10:MSOP-10_3x3mm_P0.5mm", prefix="U",
    manufacturer="Microchip Tech", mpn="MCP4728T-E/UN", lcsc="C478093",
    value="MCP4728",
    params={
        "supply_voltage": between(2.7, 5.5),
        "resolution_bits": exact(12),
        "channels": exact(4),
        # The reference the part ships selecting, from datasheet Table 4-2.
        # Not the one this board uses - firmware selects the supply instead -
        # but it is what the thresholds are worth until it does.
        "internal_reference": exact(2.048),
    },
)

HEADER_2X15 = PartSpec(
    symbol="Connector_Generic:Conn_02x15_Odd_Even",
    footprint="HDR2X15:PinHeader_2x15_P2.54mm_Vertical", prefix="J",
    manufacturer="HCTL", mpn="PZ254-2-15-Z-8.5", lcsc="C3012255", value="analog",
    params={"current_rating": exact(3.0)},
)

# Series into every fast ADC channel. Ten ohms and not a hundred: with the
# capacitor doing the filtering, the resistor's only other job is putting back
# what the converter's sampling capacitor takes, and it has 236 ns to do it.
RES_10R_0402 = PartSpec(
    **_R0402, mpn="0402WGF100JTCE", lcsc="C25077", value="10R",
    params={"resistance": pm(10, 0.01), "max_power": exact(0.0625)},
)

CAP_10N_0402 = PartSpec(
    **_C0402, manufacturer="YAGEO", mpn="CC0402KRX7R9BB103", lcsc="C60133", value="10nF",
    params={"capacitance": pm(10e-9, 0.10), "max_voltage": exact(50.0)},
)

RES_4K7_0402 = PartSpec(
    **_R0402, mpn="0402WGF4701TCE", lcsc="C25900", value="4.7k",
    params={"resistance": pm(4_700, 0.01), "max_power": exact(0.0625)},
)


# --- the field buses ---------------------------------------------------------
#
# CAN FD and RS-485, both differential, both terminated on a solder jumper so a
# board in the middle of a bus is not a board with two terminations.

# The symbol is KiCad's SN65HVD230, because no library carries a TCAN1044V. The
# eight pin numbers are identical - TI's own Pin Functions table was read in
# full - and two of the names differ: pin 5 is this part's IO supply where the
# HVD230's is a reference output, and pin 8 its standby input where the
# HVD230's is a slope control. See SOIC8.md.
#
# 5 V on VCC and 3.3 V on VIO, which is what makes a 5 V bus driver take 3.3 V
# logic without a level shifter. Its standby pin has an integrated pull-up, so
# the transceiver comes up listening and firmware has to ask for the bus.
CAN_TRANSCEIVER = PartSpec(
    symbol="Interface_CAN_LIN:SN65HVD230", footprint="SOIC8:SOIC-8_3.9x4.9mm_P1.27mm",
    prefix="U", manufacturer="Texas Instruments", mpn="TCAN1044VDRQ1", lcsc="C1852061",
    value="TCAN1044V",
    params={
        "supply_voltage": between(4.5, 5.5),
        "io_supply_voltage": between(1.7, 5.5),
        "loop_delay_max": exact(210e-9),
        "bus_fault_voltage": exact(58.0),
        "data_rate_max": exact(8e6),
    },
)

# Integrated fail-safe: the receiver reads high on an idle or shorted bus with
# no external bias network, which is the reason this part rather than a cheaper
# one. Its driver enable has a 2 Mohm pull-down and its receiver enable a
# pull-up, so an undriven board neither talks nor listens.
RS485_TRANSCEIVER = PartSpec(
    symbol="Interface_UART:THVD1450DR", footprint="SOIC8:SOIC-8_3.9x4.9mm_P1.27mm",
    prefix="U", manufacturer="Texas Instruments", mpn="THVD1450DR", lcsc="C2671361",
    value="THVD1450",
    params={
        "supply_voltage": between(3.0, 5.5),
        "bus_fault_voltage": exact(18.0),
        "data_rate_max": exact(50e6),
    },
)

HEADER_1X3 = PartSpec(
    symbol="Connector_Generic:Conn_01x03",
    footprint="HDR1X3:PinHeader_1x03_P2.54mm_Vertical", prefix="J",
    manufacturer="HCTL", mpn="PZ254-1-03-Z-8.5", lcsc="C2894926", value="bus",
    params={"current_rating": exact(3.0)},
)

# A footprint, not a part: two pads and a gap, closed with solder when this
# board is at the end of a bus. lcsc=None keeps it off the BOM.
SOLDER_JUMPER = PartSpec(
    symbol="Jumper:SolderJumper_2_Open",
    footprint="SJ2:SolderJumper-2_P1.3mm_Open_Pad1.0x1.5mm", prefix="JP",
    manufacturer="-", mpn="SOLDER-JUMPER-2", lcsc=None, value="open",
)

RES_60R4_0402 = PartSpec(
    **_R0402, mpn="0402WGF604JTCE", lcsc="C60310", value="60R4",
    params={"resistance": pm(60.4, 0.01), "max_power": exact(0.0625)},
)
RES_120R_0402 = PartSpec(
    **_R0402, mpn="0402WGF1200TCE", lcsc="C25079", value="120R",
    params={"resistance": pm(120, 0.01), "max_power": exact(0.0625)},
)
CAP_4N7_0402 = PartSpec(
    **_C0402, manufacturer="FH", mpn="0402B472K500NT", lcsc="C1538", value="4.7nF",
    params={"capacitance": pm(4.7e-9, 0.10), "max_voltage": exact(50.0)},
)


# --- USB -----------------------------------------------------------------
# A device port, not a power input: VBUS is sensed and goes nowhere else, and
# both CC pins carry the pull-down that tells a source this board is a sink
# drawing default current. Nothing here can back-feed the board's rails.
USB_C_RECEPTACLE = PartSpec(
    symbol="Connector:USB_C_Receptacle_USB2.0_16P",
    footprint="USBC16:USB_C_Receptacle_HRO_TYPE-C-31-M-12", prefix="J",
    manufacturer="Korean Hroparts Elec", mpn="TYPE-C-31-M-12", lcsc="C165948",
    value="USB-C",
    params={"current_rating": exact(5.0), "voltage_rating": exact(20.0)},
)

# ST's own part, not one of the dozen clones: an ESD array is bought for the
# figures in its datasheet, and this is the one whose datasheet could be read.
ESD_USB = PartSpec(
    symbol="Power_Protection:USBLC6-2SC6", footprint="SOT23_6:SOT-23-6", prefix="D",
    manufacturer="STMicroelectronics", mpn="USBLC6-2SC6", lcsc="C7519",
    value="USBLC6-2",
    params={
        "standoff_voltage": exact(5.25),
        "breakdown_voltage_min": exact(6.0),
        "clamping_voltage_max": exact(17.0),      # 5 A, 8/20 us, any I/O to GND
        "line_capacitance_max": exact(3.5e-12),   # I/O to GND
        "pair_capacitance_max": exact(1.7e-12),   # I/O to I/O
        "esd_contact_discharge": exact(15e3),     # IEC 61000-4-2
    },
)

RES_5K1_0402 = PartSpec(
    **_R0402, mpn="0402WGF5101TCE", lcsc="C25905", value="5K1",
    params={"resistance": pm(5.1e3, 0.01), "max_power": exact(0.0625)},
)


# --- Ethernet ------------------------------------------------------------
# Industrial temperature grade: this board sits in a motor drive, and the
# commercial part stops at +70 degC. Every figure here was read from SMSC's
# LAN8742A/LAN8742Ai datasheet, revision 1.1; see QFN24.md for how, because
# Microchip ships it encrypted and no extractor could open it as it came.
ETH_PHY = PartSpec(
    symbol="Interface_Ethernet:LAN8742A",
    footprint="QFN24:QFN-24-1EP_4x4mm_P0.5mm_EP2.5x2.5mm", prefix="U",
    manufacturer="Microchip Tech", mpn="LAN8742AI-CZ-TR", lcsc="C621425",
    value="LAN8742Ai",
    params={
        "io_supply_voltage": between(1.62, 3.6),      # VDDIO
        "analog_supply_voltage": between(3.0, 3.6),   # VDD1A, VDD2A
        "core_supply_voltage": between(1.14, 1.26),   # VDDCR, from the internal regulator
        "magnetics_supply_voltage": between(2.25, 3.6),
        "bias_resistance": pm(12.1e3, 0.01),          # RBIAS to ground, 1%
        # Table 5.8: 950 to 1050 mV peak, measured at the line side of the
        # transformer with the line replaced by 100 ohm. It is what decides
        # what the line terminations dissipate, and it is the whole reason
        # they exist: that figure is specified into 50 ohm, which is the 100
        # the cable reflects in parallel with the 100 they make.
        "transmit_amplitude_max": exact(1.05),
        # Table 5.11, tpurstd: supplies at operating level to nRST released,
        # 25 ms minimum. Section 3.8.6.1 requires a hardware reset after
        # power-up, and the straps that set REF_CLK direction and the PHY
        # address are latched on that releasing edge.
        "reset_release_delay_min": exact(25e-3),
        # The nRST input's high threshold, Table 5.6.
        "reset_input_high": exact(2.0),
        "crystal_frequency": exact(25e6),
        "crystal_esr_max": exact(30.0),
        "crystal_load_capacitance": exact(20e-12),
        "crystal_ppm_budget": exact(45e-6),           # tolerance + stability, aging aside
        "xtal_pin_capacitance": exact(3e-12),
    },
)

# 5032 rather than the cheaper 3225: at 25 MHz the smaller package's ESR runs
# 50 to 80 ohm, and the PHY's oscillator is specified to 30. See XTAL5032_4P.md.
XTAL_25M = PartSpec(
    symbol="Device:Crystal_GND24",
    footprint="XTAL5032_4P:Crystal_SMD_5032-4Pin_5.0x3.2mm", prefix="Y",
    manufacturer="Yajingxin", mpn="TXM25M0004503LDCDO00T", lcsc="C362363",
    value="25MHz",
    params={
        "frequency": exact(25e6),
        "load_capacitance": exact(20e-12),
        "esr_max": exact(30.0),
        "frequency_tolerance": exact(20e-6),
        "frequency_stability": exact(20e-6),
    },
)

# The magnetics are inside the jack. A discrete transformer plus an unshielded
# jack is the same parts count and one more thing to get the isolation rating
# wrong on. See RJ45HR.md.
ETH_JACK = PartSpec(
    symbol="Connector:RJ45_Hanrun_HR911105A_Horizontal",
    footprint="RJ45HR:RJ45_Hanrun_HR911105A_Horizontal", prefix="J",
    manufacturer="HANRUN", mpn="HR911105A", lcsc="C12074", value="RJ45",
    params={"isolation_voltage": exact(1500.0)},
)

RES_12K1_0402 = PartSpec(
    **_R0402, mpn="0402WGF1212TCE", lcsc="C25852", value="12K1",
    params={"resistance": pm(12.1e3, 0.01), "max_power": exact(0.0625)},
)
CAP_33P_0402 = PartSpec(
    **_C0402, manufacturer="FH", mpn="0402CG330J500NT", lcsc="C1562", value="33pF",
    params={"capacitance": pm(33e-12, 0.05), "max_voltage": exact(50.0)},
)
CAP_470P_0402 = PartSpec(
    **_C0402, manufacturer="FH", mpn="0402CG471J500NT", lcsc="C75274", value="470pF",
    params={"capacitance": pm(470e-12, 0.05), "max_voltage": exact(50.0)},
)


ALL: dict[str, PartSpec] = collect(globals())
"""Every part, by the name it is known by here. Used by the parts checks."""
