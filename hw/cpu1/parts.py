"""
Every part on cpu1, as data.

The same shape as every board's part list: `PartSpec` from
`hw/tools/partspec.py`, a KiCad symbol, a footprint in this board's own
`parts/` tree, and the datasheet figures the checks reason about. Each value
comes from the part's review note in `parts/<LIB>/<LIB>.md`.

cpu1 is being built one block at a time, so this list grows with it.
"""

import math

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
        # What the VCAP pins actually sit at, which is what biases the
        # capacitor on them. §5.1: "VCORE supplies, which values depend on
        # voltage scaling (0.7 V, 0.9 V, 1.0 V, 1.1 V or 1.2 V)". The top of
        # that is the worst case for a ceramic and the one the derating uses.
        "core_voltage": between(0.7, 1.2),
        "hse_gm_crit_max": exact(1.5e-3),
        "hse_load_capacitor": between(5e-12, 25e-12),
        "lse_gm_crit_max": exact(2.7e-6),       # LSEDRV = 11, high drive
        "io_current_max": exact(20e-3),
        "nrst_capacitor": exact(100e-9),
        # Table 84: what the converter presents at an analog pin, and the
        # ceiling it puts on what may be presented back to it.
        "adc_sample_capacitance": exact(4e-12),
        "adc_sample_resistance": exact(50.0),
        "adc_external_impedance_max": exact(50e3),
        # Table 20: the absolute maximum on a TT_xx pin, which is what every
        # pure analog input on this part is. Four volts, not VDDA plus a
        # diode: these pins have no positive injection path at all, which
        # Table 21 says by rating I_INJ at minus five to **plus nought**
        # milliamps. There is no current this pin may be driven above its
        # supply with; the limit is the voltage.
        "analog_input_voltage_max": exact(4.0),
        # What a 5 V-tolerant pin may see, as the datasheet states it: a
        # headroom above the *lowest* of the part's supplies, not a fixed
        # number. Recorded as the overhead so a check reads the board's own
        # rail rather than assuming 3.3 V. Table 12, note 3.
        "ft_input_overhead": exact(4.0),
        # The T6 suffix's grade, from the ordering-information table.
        "ambient_min": exact(-40.0),
        "ambient_max": exact(85.0),
        # Table 30: 400 MHz, VOS1, all peripherals enabled, at T_J 105 degC,
        # production tested. It is the figure the 3V3 rail is budgeted at, and
        # it is also what the package has to get rid of.
        "supply_current_max": exact(500e-3),
        # Table 126 and Table 22. ST give the equation beside them:
        # T_J max = T_A max + (P_D max x theta_JA). At the rail's own budget
        # and its high corner this package loses 1.73 W at 43.7 degC/W, which
        # is 76 degC of rise, so 125 - 76 = 49 degC is the most this board can
        # be declared for and `environment.ambient` sits at 45.
        "thermal_resistance_junction_ambient": exact(43.7),
        "junction_temperature_max": exact(125.0),
        # Table 23's own answer for this package, and the reason the 125 degC
        # above is the right row rather than a number from the absolute
        # maximums: 85 + 0.915 x 43.7 = 125.0 exactly, so ST's three figures
        # close on each other. A check asserts that, which is what would catch
        # reading the junction limit off the wrong table.
        "power_dissipation_at_reference_ambient": exact(0.915),
        "power_dissipation_reference_ambient": exact(85.0),
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
# The core regulator's capacitor. ST's Table 24 asks for 2.2 uF at each VCAP
# pin, and a 2.2 uF part cannot deliver 2.2 uF: its own tolerance takes it to
# 1.76 before bias takes anything. At 6.3 V rated and 1.25 V of bias - a fifth
# of the rating - what reached the pin was 1.41 uF, 36 % short of what ST
# specified, and the check that was meant to catch that compared the label.
# 4.7 uF at 10 V is worth 3.29 at the same bias.
CAP_4U7_0402 = PartSpec(
    **_C0402, manufacturer="Samsung", mpn="CL05A475MP5NRNC", lcsc="C23733", value="4.7uF",
    params={"capacitance": pm(4.7e-6, 0.20), "max_voltage": exact(10.0)},
)

CAP_8P2_0402 = PartSpec(
    **_C0402, manufacturer="FH", mpn="0402CG8R2C500NT", lcsc="C1579", value="8.2pF",
    params={"capacitance": between(7.95e-12, 8.45e-12), "max_voltage": exact(50.0)},
)
# The 32 kHz oscillator's load. 5.1 pF, not the 6.8 this board carried: with
# the stray the design declares, 6.8 presents the crystal 6.9 pF against a
# 6 pF cut, and 5.1 presents 6.05. No value in the E24 series gets closer, and
# `test_crystal_sees_its_load_capacitance` picks it rather than being told.
CAP_5P1_0402 = PartSpec(
    **_C0402, manufacturer="FH", mpn="0402CG5R1C500NT", lcsc="C60220", value="5.1pF",
    params={"capacitance": between(4.85e-12, 5.35e-12), "max_voltage": exact(50.0)},
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
# Between the gate-kill FET's drain and the line it pulls down. It bounds what
# the FET draws from a '541 output that has not let go yet: 3.465 V across
# 33 + 150 ohm is 19 mA against the buffer's 24 mA per output.
RES_150R_0402 = PartSpec(
    **_R0402, mpn="0402WGF1500TCE", lcsc="C25082", value="150R",
    params={"resistance": pm(150, 0.01), "max_power": exact(0.0625)},
)

# The analog rail this board hands the power board's sensors. It is an LDO and
# not a bead, and the reason is a voltage rather than noise: the sense lines
# come back into TT_xx analog pins that ST's Table 20 caps at 4.0 V absolute,
# with no positive-injection allowance at all, and a sensor's op-amp rails to
# its own supply during exactly the over-current the trip chain exists for. A
# bead off 5 V hands it 5.25 V to rail to. This hands it 3.366 V at the worst
# corner of its own 2 % accuracy, which is inside the pin's rating with 0.6 V
# to spare, so the fault this board cannot clamp stops being a fault.
#
# The noise is the second reason and it is real: 68 dB of PSRR at 1 kHz and
# 48 uVrms of its own, in front of sensors feeding a 12-bit converter, where
# what was there before was buck ripple through a ferrite. See SOT23_5.md.
LDO_3V3_ANALOG = PartSpec(
    symbol="Regulator_Linear:TLV70233_SOT23-5", footprint="SOT23_5:SOT-23-5",
    prefix="U", manufacturer="Texas Instruments", mpn="TLV70233DBVR",
    lcsc="C26833", value="TLV70233",
    params={
        "input_voltage_min": exact(2.0),
        "input_voltage_max": exact(5.5),
        "output_voltage": exact(3.3),
        "output_accuracy": exact(0.02),
        "output_current_max": exact(0.3),
        "dropout_at_max_current": exact(0.375),
        "output_capacitance_min": exact(100e-9),
        # TI asks for 0.1 to 1.0 uF across IN and GND when the source is not
        # close, which the 5 V island is not. The ESR ceiling that goes with
        # the output figure - 200 mOhm - is not declared here: no capacitor on
        # this board states an ESR, so it would be a float nothing could be
        # compared against. It is in SOT23_5.md instead, where the 0402 X5R
        # fitted is milliohms and the question does not arise.
        "input_capacitance_min": exact(100e-9),
        "quiescent_current": exact(55e-6),
    },
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
        # SBVS032F states the supply as V_OUT + 1 mV to 5.5 V. It is what
        # makes running this from 3V3 rather than 5 V possible, and running it
        # from 3V3 is what stops VREF+ existing before VDDA does.
        "supply_headroom": exact(1e-3),
        # ...which is the *unloaded* figure, and the datasheet says so in the
        # description: "Unloaded, the REF30xx can be operated with supplies
        # within 1mV of output voltage". Loaded, the dropout is the curve on
        # page 1 - about 10 mV per milliamp to 20 mA, 300 mV at the full 25.
        # With 129 mV of headroom on 3V3 that bounds what VREF+ may supply at
        # around 12 mA, which is half the part's output capability and was the
        # figure nothing on this board had ever written down. See the figure
        # in SOT23/evidence.
        "dropout_at_5ma": exact(50e-3),
        "dropout_at_10ma": exact(100e-3),
        "dropout_at_20ma": exact(200e-3),
        "dropout_at_25ma": exact(300e-3),
        "output_current_max": exact(25e-3),
        # 50 uA maximum, from the features list. It was hard-coded in the
        # check that uses it, which is a datasheet figure living somewhere
        # nothing else can see.
        "quiescent_current_max": exact(50e-6),
        "supply_bypass": exact(0.47e-6),
        "temperature_drift": exact(75e-6),
    },
)


# The gate kill. When the latch trips it pulls GATE_ENABLE_OUT low directly,
# because the '541 letting go does not pull anything low - it stops driving,
# and the line then discharges through its pull-down alone. At the 10 k those
# pull-downs are, that is 205 ns; through this it is 3 ns.
#
# Chosen for its gate, not its channel. There is 150 ohm in series with the
# drain, so on-resistance barely matters - but the gate hangs on TRIPPED,
# which also disables both buffers, so every picofarad there delays the whole
# chain. 60.67 pF is what a latch output charges in 2.5 ns; an AO3400A's
# 630 pF would have taken 38, which is most of the budget.
#
# And it is specified where it is used. Diodes' DS30599 gives R_DS(on) at
# V_GS = 4.5, 2.5 **and 1.8 V**, so the 2.5 V row is a maximum at a drive
# below the 3.135 V this board's rail falls to - not a figure read at 10 V
# and hoped for, which is what the alternatives offered.
FET_GATE_KILL = PartSpec(
    symbol="Transistor_FET:Q_NMOS_GSD", footprint="SOT523:SOT-523", prefix="Q",
    manufacturer="Diodes Incorporated", mpn="DMG1012T-7", lcsc="C20512",
    value="DMG1012T",
    params={
        "gate_threshold_max": exact(1.0),        # V_GS(TH) max, V_DS=V_GS, 250 uA
        "on_resistance_at_2v5": exact(0.5),      # R_DS(on) max at V_GS = 2.5 V
        "input_capacitance": exact(60.67e-12),   # C_iss typical
        "drain_source_voltage_max": exact(20.0),
        "drain_current_max": exact(0.8),
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
# 25 V, not 10, and the reason is `capacitors.bias_derating` rather than any
# question about standing off the rail. At 10 V rated and 5.25 V of bias this
# part is at half its rating and worth half its label; at 25 V it is at a
# fifth. The rating is what buys the capacitance back.
CAP_22U_0805 = PartSpec(
    **_C0805, manufacturer="Samsung", mpn="CL21A226MAQNNNE", lcsc="C45783", value="22uF",
    params={"capacitance": pm(22e-6, 0.20), "max_voltage": exact(25.0)},
)
_C1206 = dict(symbol="Device:C", footprint="C1206:C_1206_3216Metric", prefix="C")
# The 3V3 converter's input capacitor, where the bias is the 5 V rail rather
# than the 3.3 one - a fifth of 25 V - and where the minimum is the whole
# requirement. A 1206 for the tighter tolerance: this one is the only bulk
# capacitor on the board with nothing beside it to share the shortfall.
CAP_22U_25V_1206 = PartSpec(
    **_C1206, manufacturer="Samsung", mpn="CL31A226KAHNNNE", lcsc="C12891", value="22uF",
    params={"capacitance": pm(22e-6, 0.10), "max_voltage": exact(25.0)},
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
        # 24 mA per output at V_CC = 3 V, from the recommended operating
        # conditions - not 25, which was a rounding of it.
        "output_current_max": exact(24e-3),
        # **100 mA, not 50.** The absolute maximums give continuous output
        # current as +-50 mA *per output* and continuous current through V_CC
        # or GND as +-100 mA, which is the package figure. The note recorded
        # "50 mA per part", which is the per-output number read as a package
        # one - and it was the floor the gate-line pull-downs were sized
        # against, so the constraint that choice was made under was the wrong
        # one by a factor of two. See TSSOP20/evidence.
        "total_output_current_max": exact(100e-3),
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
        # **An LVC input has no clamp diode to V_CC**, and the two rows below
        # are how the datasheet says so: the absolute maximum on an input is a
        # flat 6.5 V rather than V_CC + 0.5, and I_IK is specified only for
        # V_I < 0. That absence is the point of the family - it is what makes
        # these inputs tolerant of 5.5 V on a 3.3 V rail - and it means nothing
        # inside the part limits a positive overshoot. SCES794E 7.1 and 7.3.
        "input_voltage_max": exact(5.5),            # recommended operating
        "input_voltage_absolute_max": exact(6.5),
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
        "reverse_voltage_max": exact(30.0),
        "forward_current_max": exact(200e-3),
        # Total capacitance, 10 pF maximum at V_R = 1.0 V and 1 MHz. Both
        # junctions of a BAT54A face the trip bus through their common anode,
        # so each package puts twice this on it, and six packages are most of
        # what the comparators have to pull down.
        "total_capacitance": exact(10e-12),
        # Forward voltage at three currents, all maxima at 25 degC, from the
        # electrical table. One figure was not enough: the trip bus runs these
        # at about 0.28 mA rather than the 0.1 mA the single recorded value
        # came from, and the clamp on the latch's clear runs one at about
        # 3 mA.
        "forward_voltage_at_100ua": exact(0.24),
        "forward_voltage_at_1ma": exact(0.32),
        "forward_voltage_at_10ma": exact(0.4),
        # How the drop moves with temperature, read off FIG.1 at 0.1 mA: the
        # 25 degC curve sits near 0.195 V and the -25 degC curve near 0.285,
        # which is 1.8 mV per degree of cooling. The board is declared down to
        # 0 degC, so it is 45 mV the trip bus's low level has to find. See the
        # figure in SOT23/evidence.
        "forward_voltage_tempco": exact(-1.8e-3),
        # Reverse current. **Not** the electrical table's 2 uA, which is
        # stated at V_R = 25 V and 25 degC and so describes neither the
        # voltage nor the temperature these see: on the trip bus they sit at
        # about 1.6 V reverse, and a board in a cabinet beside a motor drive
        # is not at 25 degC. FIG.2 of the same datasheet plots the current
        # against voltage at seven temperatures, and these two are read off
        # its 2 V end - the anchor at 75 degC, and the doubling interval taken
        # across the 75 to 125 degC span, which is the part of the curve the
        # declared ambient sits under. See the figure in SOT23/evidence.
        # Three points off that curve at 2 V, so the value used is
        # interpolated between the two that bracket the board's ambient rather
        # than extrapolated from one anchor. The first attempt anchored at
        # 75 degC and doubled every 17.4 - a slope taken across 75 to 125 -
        # and then used it at 45, which is the wrong side of the anchor. It
        # happened to be conservative there and would not have been on a
        # hotter board.
        "reverse_current_typical_at_25c": exact(0.11e-6),
        "reverse_current_typical_at_75c": exact(3.7e-6),
        "reverse_current_typical_at_125c": exact(27e-6),
        # And the curves are typical while the budget needs a maximum. The
        # electrical table gives both at its own condition - 0.5 uA typical
        # against 2 uA maximum at 25 V - so four is the spread between them.
        "reverse_current_typical_to_max": exact(2.0 / 0.5),
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
        # The 7 ns above is the switching table's figure, and the table states
        # no capacitive load. Figure 5 of the same datasheet plots the delay
        # against load at the same 20 mV overdrive: about 4.7 ns at 13 pF,
        # about 8.2 ns at 100 pF. So the table's own load is the left end of
        # that curve, and everything hung on the output past it costs 40 ps
        # per picofarad. On the trip bus, where twelve Schottky junctions and
        # 161 mm of track come to 135 pF, that is five nanoseconds the budget
        # was not counting. See the figure in SOT23_6/evidence.
        "delay_load_reference": exact(13e-12),
        "delay_per_farad": exact((8.2e-9 - 4.7e-9) / (100e-12 - 13e-12)),
        "input_offset_voltage": exact(6.5e-3),
        "input_hysteresis": exact(6e-3),
        "common_mode_headroom": exact(0.2),      # from either rail
        "output_swing_from_rail": exact(50e-3),  # at 1 mA
        # The shutdown pin is measured *down from the positive supply*, which
        # is the trap in it: "within 0.9 V of the most positive supply, the
        # part is disabled. When it is more than 1.7 V below the most positive
        # supply, the part is enabled." So SHDN is disable-active-high, ground
        # enables, and a part left floating near its own rail is a comparator
        # that is off. All seven here are tied to ground.
        "shutdown_enable_below_supply": exact(1.7),
        "shutdown_disable_within_supply": exact(0.9),
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
        # Its own DC accuracy, from the electrical table - every one of these
        # a maximum. They were not in this file at all, so the trip point's
        # error budget was the rail's tolerance and the comparator's offset
        # and nothing from the part that actually sets the threshold.
        "offset_error": exact(20e-3),            # at code 000h
        "gain_error": exact(0.0125),             # fraction of full scale
        "integral_nonlinearity": exact(13),      # LSB
    },
)

HEADER_2X15 = PartSpec(
    symbol="Connector_Generic:Conn_02x15_Odd_Even",
    footprint="HDR2X15:PinHeader_2x15_P2.54mm_Vertical", prefix="J",
    manufacturer="HCTL", mpn="PZ254-2-15-Z-8.5", lcsc="C3012255", value="analog",
    params={"current_rating": exact(3.0)},
)

# Series into every fast ADC channel, and the one number on this board that
# three constraints meet at. The capacitor has to roll off what the converter
# would alias, stay big enough to give back what the 4 pF sampling capacitor
# takes inside 236 ns - and stay *small* enough that the lead-lag it forms
# with the power board's 2 ohm source impedance does not move the comparator
# tap that shares the node. Ten ohms and 10 nF met the first two and failed
# the third by 17 %. Twenty-two and 4.7 nF meet all three with room.
RES_22R_0402 = PartSpec(
    **_R0402, mpn="0402WGF220JTCE", lcsc="C25092", value="22R",
    params={"resistance": pm(22, 0.01), "max_power": exact(0.0625)},
)

# The comparator-only path to the DC link. Nothing samples this node - PB2 is
# a comparator input, not an ADC one - so the reservoir requirement that fixes
# the channels above does not apply, and the network can be the one a tap
# actually wants: a kilohm against the 2 ohm upstream is a 0.2 % step error.
CAP_100P_0402 = PartSpec(
    **_C0402, manufacturer="FH", mpn="0402CG101J500NT", lcsc="C1546", value="100pF",
    params={"capacitance": pm(100e-12, 0.05), "max_voltage": exact(50.0)},
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
        # Dominant differential output, 1.4 to 3.3 V into 45 to 70 ohm. The
        # maximum is what a termination has to survive while the driver is
        # dominant, and nothing was computing that - only the bus-fault case,
        # which the open jumper excuses.
        # (The part also times out between 1.2 and 4 ms if held dominant,
        # which bounds a stuck-dominant fault but not normal traffic, so it is
        # not a figure anything here computes with.)
        "differential_output_max": exact(3.3),
        # Section 6.3, and read off the table in SOIC8/evidence. This one is
        # qualified to SAE J2962-2 per ISO 10650 and not to IEC 61000-4-2,
        # which the document never quotes: the discharge is applied while the
        # part is powered and working, which is the harder of the two, so the
        # number is recorded and the standard is recorded beside it.
        "esd_contact_discharge": exact(8e3),
        # V_CM, normal and standby modes, from the table in SOIC8/evidence.
        # ISO 11898-2 asks for -2 to 7 V, so this is a wide part.
        "common_mode_low": exact(-12.0),
        "common_mode_high": exact(12.0),
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
        # Driver differential output magnitude, 1.5 to 3.5 V into 54 ohm.
        # Unlike CAN there is no timeout: a half-duplex driver holds the line
        # for as long as DE is asserted.
        "differential_output_max": exact(3.5),
        # Section 7.3, "ESD Ratings [IEC]", on the bus pins. TI's own summary
        # says this is what removes the need for external protection on the
        # bus, and at 18 kV contact it is more than twice what the connector
        # requirement asks for.
        "esd_contact_discharge": exact(18e3),
        # The range the receiver's thresholds are specified over. TIA-485 asks
        # for -7 to 12 V; this part is one of TI's extended-range ones, which
        # is what lets the connector's ground go straight to the board's.
        "common_mode_low": exact(-15.0),
        "common_mode_high": exact(15.0),
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

# The two bus terminations, and the only two resistors on this board that are
# not 0402. They are bigger because they are the only two that carry their own
# transceiver's output: an 0402 is 62.5 mW and 50 V, and closing either jumper
# puts 46 mW into each CAN half and 103 mW into the RS-485 one, with 58 V
# across the CAN pair under the fault its own datasheet declares. Two of those
# three numbers are past an 0402 before any derating at all.
#
# `max_voltage` is declared only here. Every other resistor on the board is
# rated 50 V too, and nothing can drive 50 V across any of them; these are the
# ones a bus fault reaches, so these are the ones where the figure is a limit
# rather than a fact about the reel.
RES_60R4_0805 = PartSpec(
    symbol="Device:R", footprint="R0805:R_0805_2012Metric", prefix="R",
    manufacturer="UNI-ROYAL", mpn="0805W8F604JT5E", lcsc="C72998", value="60R4",
    params={"resistance": pm(60.4, 0.01), "max_power": exact(0.125),
            "max_voltage": exact(150.0)},
)
RES_120R_1206 = PartSpec(
    symbol="Device:R", footprint="R1206:R_1206_3216Metric", prefix="R",
    manufacturer="UNI-ROYAL", mpn="1206W4F1200T5E", lcsc="C17909", value="120R",
    params={"resistance": pm(120, 0.01), "max_power": exact(0.25),
            "max_voltage": exact(200.0)},
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
    params={
        "isolation_voltage": exact(1500.0),
        # HanRun's own grade, and the narrowest on this board. It is what
        # `environment.ambient` was set against.
        "ambient_min": exact(0.0),
        "ambient_max": exact(70.0),
    },
)

RES_12K1_0402 = PartSpec(
    **_R0402, mpn="0402WGF1212TCE", lcsc="C25852", value="12K1",
    params={"resistance": pm(12.1e3, 0.01), "max_power": exact(0.0625)},
)
# One per cent, where every other capacitor on the board is five or ten. These
# two set the link's clock frequency: the load band is what the crystal is
# pulled by, and at five per cent the pull is a few parts per million out of
# the ten the standard leaves once tolerance and drift are paid for.
CAP_36P_0402 = PartSpec(
    **_C0402, manufacturer="YAGEO", mpn="CQ0402FRNPO9BN360", lcsc="C3899281", value="36pF",
    params={"capacitance": pm(36e-12, 0.01), "max_voltage": exact(50.0)},
)
CAP_470P_0402 = PartSpec(
    **_C0402, manufacturer="FH", mpn="0402CG471J500NT", lcsc="C75274", value="470pF",
    params={"capacitance": pm(470e-12, 0.05), "max_voltage": exact(50.0)},
)


ALL: dict[str, PartSpec] = collect(globals())
"""Every part, by the name it is known by here. Used by the parts checks."""
