"""
cpu1's MCU pin map: every pin the STM32H743ZIT6 uses, and what it is for.

One table, read three ways. The design source wires the MCU from it; the
firmware's `board_pins.h` is generated from it; and `checks/test_pinmap.py`
checks it against ST's own description of the part, vendored in
`hw/silicon/STM32H743ZITx/`. Change a pin here and all three follow, or a check
says which one did not.

How it was laid out, and the three conflicts the package forced:

- **TIM1 stays on port E** (PE8–PE13, break on PE15), exactly as on the
  NUCLEO-H743ZI2, so the firmware's `BOARD_PWM_PORT` mask still works. The cost
  is COMP2, whose only external inputs are PE9 and PE11.
- **Ethernet's CRS_DV can only be on PA7**, and TIM8_CH1N can only be on PA5 or
  PA7, so TIM8_CH1N takes PA5 — the pin DAC1's second output would have used.
  The NUCLEO's TXD1 on PB13 collides with TIM1_CH1N, so TXD1 moves to PG12.
- **No 32-bit timer is free for the encoder.** TIM2 and TIM5 need PB3 (SWO) or
  PA1 (Ethernet's reference clock), so the encoder is on 16-bit TIM4 and its
  count is extended in firmware.

Ia and Ib are converted at the same instant, as are Vdc and Va: ADC1 and ADC2
locked together in dual simultaneous mode. Ic sits on ADC3, which shares the PWM
trigger but is not locked to it; three phase currents sum to zero, so Ic is the
one that can be reconstructed from the other two if its skew turns out to matter.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from mcu_pins import Pin  # noqa: E402

PART = "STM32H743ZITx"
SYMBOL = "MCU_ST_STM32H7:STM32H743ZITx"
FIRMWARE = "firmware/bsp/amaxa_cpu1/board_pins.h"

PINS = [
    # --- debug and clocks -----------------------------------------------------
    Pin("PA13", "DEBUG_JTMS-SWDIO", "SWDIO"),
    Pin("PA14", "DEBUG_JTCK-SWCLK", "SWCLK"),
    Pin("PB3", "DEBUG_JTDO-SWO", "SWO"),
    Pin("PH0", "RCC_OSC_IN", "HSE_IN", note="8 MHz crystal"),
    Pin("PH1", "RCC_OSC_OUT", "HSE_OUT"),
    Pin("PC14", "RCC_OSC32_IN", "LSE_IN", note="32.768 kHz crystal"),
    Pin("PC15", "RCC_OSC32_OUT", "LSE_OUT"),

    # --- USB, CAN, Ethernet, RS-485, console ----------------------------------
    Pin("PA11", "USB_OTG_FS_DM", "USB_DM"),
    Pin("PA12", "USB_OTG_FS_DP", "USB_DP"),
    Pin("PA9", "USB_OTG_FS_VBUS", "USB_VBUS", note="through a divider; USB is not a power input"),
    Pin("PD0", "FDCAN1_RX", "CAN_RX"),
    Pin("PD1", "FDCAN1_TX", "CAN_TX"),
    Pin("PD3", "GPIO", "CAN_STANDBY", "out"),
    Pin("PA1", "ETH_REF_CLK", "ETH_REF_CLK", note="50 MHz from the PHY"),
    Pin("PA2", "ETH_MDIO", "ETH_MDIO"),
    Pin("PC1", "ETH_MDC", "ETH_MDC"),
    Pin("PA7", "ETH_CRS_DV", "ETH_CRS_DV"),
    Pin("PC4", "ETH_RXD0", "ETH_RXD0"),
    Pin("PC5", "ETH_RXD1", "ETH_RXD1"),
    Pin("PG11", "ETH_TX_EN", "ETH_TX_EN"),
    Pin("PG13", "ETH_TXD0", "ETH_TXD0"),
    Pin("PG12", "ETH_TXD1", "ETH_TXD1", note="not PB13 as on the NUCLEO: that is TIM1_CH1N"),
    # PG14 was the PHY interrupt. In REF_CLK Out mode the LAN8742A has no
    # interrupt pin to drive it - its datasheet says so in as many words - so
    # the pin is free and firmware reads link state over MDIO instead.
    Pin("PG15", "GPIO", "ETH_PHY_RESET", "out"),
    Pin("PD5", "USART2_TX", "RS485_TX"),
    Pin("PD6", "USART2_RX", "RS485_RX"),
    Pin("PD4", "USART2_DE", "RS485_DE", note="driver enable, timed by the UART itself"),
    Pin("PD8", "USART3_TX", "CONSOLE_TX", note="also the ROM bootloader's"),
    Pin("PD9", "USART3_RX", "CONSOLE_RX"),

    # --- PWM: TIM1, six complementary outputs and a single-ended one -----------
    Pin("PE9", "TIM1_CH1", "PWM1_A_HIGH"),
    Pin("PE8", "TIM1_CH1N", "PWM1_A_LOW"),
    Pin("PE11", "TIM1_CH2", "PWM1_B_HIGH"),
    Pin("PE10", "TIM1_CH2N", "PWM1_B_LOW"),
    Pin("PE13", "TIM1_CH3", "PWM1_C_HIGH"),
    Pin("PE12", "TIM1_CH3N", "PWM1_C_LOW"),
    # The fourth channel of each timer is a single-ended output: no
    # complementary partner, so no hardware dead time. That is a property of
    # the silicon and is worth a power board knowing. What it drives is not:
    # a brake chopper, a PFC switch, a fan, a second-stage gate - the power
    # board decides, the ID straps say which board it is, and firmware
    # configures it. Naming these for one application put that decision on
    # this board, where it does not belong.
    Pin("PE14", "TIM1_CH4", "PWM1_CH4", note="single-ended: no complementary pair, no dead time"),
    Pin("PE15", "TIM1_BKIN", "TRIP1_N", net="TRIP_N", note="from the hardware trip latch, active low"),
    Pin("PE6", "TIM1_BKIN2", "FAULT1_N", note="gate-driver fault, active low"),

    # --- PWM: TIM8, the same again --------------------------------------------
    Pin("PC6", "TIM8_CH1", "PWM2_A_HIGH"),
    Pin("PA5", "TIM8_CH1N", "PWM2_A_LOW", note="PA7 is Ethernet's CRS_DV"),
    Pin("PC7", "TIM8_CH2", "PWM2_B_HIGH"),
    Pin("PB14", "TIM8_CH2N", "PWM2_B_LOW"),
    Pin("PC8", "TIM8_CH3", "PWM2_C_HIGH"),
    Pin("PB15", "TIM8_CH3N", "PWM2_C_LOW"),
    Pin("PC9", "TIM8_CH4", "PWM2_CH4", note="single-ended: no complementary pair, no dead time"),
    Pin("PG2", "TIM8_BKIN", "TRIP2_N", net="TRIP_N", note="one latch output, one node, both timers"),
    Pin("PG3", "TIM8_BKIN2", "FAULT2_N", note="gate-driver fault, active low"),

    # --- analog ------------------------------------------------------------------
    Pin("PF11", "ADC1_INP2", "FAST1", note="simultaneous with FAST2"),
    Pin("PF13", "ADC2_INP2", "FAST2"),
    Pin("PC2_C", "ADC3_INP0", "FAST3", note="needs the PC2 analog switch closed"),
    Pin("PA6", "ADC1_INP3", "FAST4", note="simultaneous with FAST5"),
    Pin("PB1", "ADC2_INP5", "FAST5"),
    Pin("PC3_C", "ADC3_INP1", "FAST6", note="needs the PC3 analog switch closed"),
    Pin("PF9", "ADC3_INP2", "FAST7"),
    Pin("PF7", "ADC3_INP3", "FAST8"),
    Pin("PF5", "ADC3_INP4", "SLOW1"),
    Pin("PF3", "ADC3_INP5", "SLOW2"),
    Pin("PC0", "ADC3_INP10", "SLOW3"),
    Pin("PA3", "ADC1_INP15", "SLOW4"),
    Pin("PF10", "ADC3_INP6", "BOARD_ID1", note="resistor divider on the power board"),
    Pin("PF4", "ADC3_INP9", "BOARD_ID2"),
    Pin("PB2", "COMP1_INP", "COMP_FAST4", note="optional second over-voltage path"),
    Pin("PA4", "DAC1_OUT1", "DAC_TEST", note="resolver excitation or analog test"),

    # --- position feedback ---------------------------------------------------------
    Pin("PD12", "TIM4_CH1", "ENC_A"),
    Pin("PD13", "TIM4_CH2", "ENC_B"),
    Pin("PD14", "TIM4_CH3", "ENC_Z"),
    Pin("PB4", "TIM3_CH1", "HALL_1"),
    Pin("PB5", "TIM3_CH2", "HALL_2"),
    Pin("PB0", "TIM3_CH3", "HALL_3"),
    Pin("PB6", "USART1_TX", "ENC_SERIAL_TX", note="reserved: the encoder type is undecided"),
    Pin("PB7", "USART1_RX", "ENC_SERIAL_RX"),

    # --- safety chain and power-board control ----------------------------------------
    Pin("PG4", "GPIO", "PWM_ENABLE_N", "out", note="pulled up on the board, so off until driven"),
    Pin("PG5", "GPIO", "TRIP_CLEAR_N", "out", note="the only way to clear the trip latch; pulled up, so a reset pin does not clear it"),
    Pin("PF0", "I2C2_SDA", "DAC_SDA", note="trip-threshold DAC"),
    Pin("PF1", "I2C2_SCL", "DAC_SCL"),
    Pin("PD7", "GPIO", "GATE_ENABLE", "out"),
    # Two relay drives, not a pre-charge and a main contactor. Which one is
    # which - if the power board has relays at all - is that board's
    # business, read from the ID straps and configured in firmware.
    Pin("PG0", "GPIO", "RELAY1", "out"),
    Pin("PG1", "GPIO", "RELAY2", "out"),
    Pin("PG9", "GPIO", "STO1_FEEDBACK", "in"),
    Pin("PG10", "GPIO", "STO2_FEEDBACK", "in"),
    Pin("PE2", "GPIO", "ID_STRAP0", "in"),
    Pin("PE3", "GPIO", "ID_STRAP1", "in"),
    Pin("PE4", "GPIO", "ID_STRAP2", "in"),
    Pin("PE5", "GPIO", "ID_STRAP3", "in"),

    # --- people -------------------------------------------------------------------------
    Pin("PE1", "GPIO", "LED_STATUS", "out"),
    Pin("PG6", "GPIO", "LED_FAULT", "out"),
    Pin("PG7", "GPIO", "LED_COMMS", "out"),
    Pin("PC13", "GPIO", "BUTTON", "in"),
]

# The digital header to the power board, as a sequence rather than a pinout: two
# signals then a ground, all the way along, and the pin numbers fall out of the
# order. J3 is a 2x20 with KiCad's odd/even numbering, so this list is read
# straight through - pin 1, pin 2, pin 3 - across both rows.
#
# Every PWM name here is the *buffered* net, the one on the far side of the
# octal buffer and its series resistor. The MCU's own net of the same name
# without the suffix never reaches this connector, and a check says so.
HEADER_GROUND = "GND"
HEADER_DIGITAL = [
    # The static signals first, at the end of the connector furthest from the
    # buffers: straps and feedback, which change once a minute at most.
    # In the order they leave the package, furthest first, for the same reason
    # the buffered outputs are: ten tracks crossing the board without crossing
    # each other.
    "RELAY1", "RELAY2",
    "ID_STRAP0", "ID_STRAP1", "ID_STRAP2", "ID_STRAP3",
    "FAULT1_N",
    "STO1_FEEDBACK", "STO2_FEEDBACK",
    "FAULT2_N",
    "3V3",
    # Then the buffered outputs, in the order their buffer presents them, which
    # is the order the MCU's own pins come out of the package. Nothing here is
    # grouped by phase, and that is deliberate: this order is what lets fifteen
    # tracks cross the board without crossing each other, and the table is what
    # makes it checkable rather than a drawing nobody dares touch.
    "PWM2_CH4_OUT", "PWM2_C_HIGH_OUT", "PWM2_B_HIGH_OUT", "PWM2_A_HIGH_OUT",
    "PWM2_A_LOW_OUT", "PWM2_C_LOW_OUT", "PWM2_B_LOW_OUT",
    "PWM1_CH4_OUT", "PWM1_C_HIGH_OUT", "PWM1_C_LOW_OUT", "PWM1_B_HIGH_OUT",
    "PWM1_B_LOW_OUT", "PWM1_A_HIGH_OUT", "PWM1_A_LOW_OUT", "GATE_ENABLE_OUT",
]


# The analog header, the same way. Every name here is the *raw* signal as it
# arrives from the power board: the comparators tap it directly, and the
# anti-alias filter between it and the MCU's own ADC pin is a later block. That
# order is the point - a filter fast enough for the ADC is far too slow to trip
# on.
HEADER_ANALOG = [
    "FAST1_SENSE", "FAST2_SENSE", "FAST3_SENSE",
    "FAST4_SENSE", "FAST5_SENSE", "FAST6_SENSE", "FAST7_SENSE",
    "FAST8_SENSE",
    "SLOW1_SENSE", "SLOW2_SENSE", "SLOW3_SENSE", "SLOW4_SENSE",
    "BOARD_ID1_SENSE", "BOARD_ID2_SENSE",
    "VREF+", "5VA", "5VA",
]


def header_pins(signals: list[str], ground: str, count: int) -> dict[int, str]:
    """
    Pin number -> net, for a header carrying `signals` with a ground every two.

    The pattern is the point: nothing on this connector is more than one pin
    from a return path, which is what makes a ribbon cable to a gate driver
    survivable. Any pins left over at the end are ground as well.
    """
    out: dict[int, str] = {}
    remaining = list(signals)
    pin = 1
    while pin <= count:
        for _ in range(2):
            if remaining and pin <= count:
                out[pin] = remaining.pop(0)
                pin += 1
        if pin <= count:
            out[pin] = ground
            pin += 1
    if remaining:
        raise ValueError(f"{len(remaining)} signals do not fit on {count} pins: {remaining}")
    return out


# Pairs converted at the same instant, in dual regular simultaneous mode:
# (on ADC1, on ADC2).
SIMULTANEOUS = [
    ("FAST1", "FAST2"),
    ("FAST4", "FAST5"),
]
