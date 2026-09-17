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

from pinmap import Pin  # noqa: E402

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
    Pin("PG14", "GPIO", "ETH_PHY_IRQ", "in"),
    Pin("PG15", "GPIO", "ETH_PHY_RESET", "out"),
    Pin("PD5", "USART2_TX", "RS485_TX"),
    Pin("PD6", "USART2_RX", "RS485_RX"),
    Pin("PD4", "USART2_DE", "RS485_DE", note="driver enable, timed by the UART itself"),
    Pin("PD8", "USART3_TX", "CONSOLE_TX", note="also the ROM bootloader's"),
    Pin("PD9", "USART3_RX", "CONSOLE_RX"),

    # --- PWM: TIM1, the main bridge -------------------------------------------
    Pin("PE9", "TIM1_CH1", "PWM1_A_HIGH"),
    Pin("PE8", "TIM1_CH1N", "PWM1_A_LOW"),
    Pin("PE11", "TIM1_CH2", "PWM1_B_HIGH"),
    Pin("PE10", "TIM1_CH2N", "PWM1_B_LOW"),
    Pin("PE13", "TIM1_CH3", "PWM1_C_HIGH"),
    Pin("PE12", "TIM1_CH3N", "PWM1_C_LOW"),
    Pin("PE14", "TIM1_CH4", "PWM1_BRAKE", note="brake chopper"),
    Pin("PE15", "TIM1_BKIN", "TRIP1_N", note="from the hardware trip latch, active low"),
    Pin("PE6", "TIM1_BKIN2", "FAULT1_N", note="gate-driver fault, active low"),

    # --- PWM: TIM8, a second bridge or a PFC stage -----------------------------
    Pin("PC6", "TIM8_CH1", "PWM2_A_HIGH"),
    Pin("PA5", "TIM8_CH1N", "PWM2_A_LOW", note="PA7 is Ethernet's CRS_DV"),
    Pin("PC7", "TIM8_CH2", "PWM2_B_HIGH"),
    Pin("PB14", "TIM8_CH2N", "PWM2_B_LOW"),
    Pin("PC8", "TIM8_CH3", "PWM2_C_HIGH"),
    Pin("PB15", "TIM8_CH3N", "PWM2_C_LOW"),
    Pin("PC9", "TIM8_CH4", "PWM2_PFC", note="PFC switch"),
    Pin("PG2", "TIM8_BKIN", "TRIP2_N", note="from the hardware trip latch, active low"),
    Pin("PG3", "TIM8_BKIN2", "FAULT2_N", note="gate-driver fault, active low"),

    # --- analog ------------------------------------------------------------------
    Pin("PF11", "ADC1_INP2", "IA", note="simultaneous with IB"),
    Pin("PF13", "ADC2_INP2", "IB"),
    Pin("PC2_C", "ADC3_INP0", "IC", note="needs the PC2 analog switch closed"),
    Pin("PA6", "ADC1_INP3", "VDC", note="simultaneous with VA"),
    Pin("PB1", "ADC2_INP5", "VA"),
    Pin("PC3_C", "ADC3_INP1", "VB", note="needs the PC3 analog switch closed"),
    Pin("PF9", "ADC3_INP2", "VC"),
    Pin("PF7", "ADC3_INP3", "AUX_FAST"),
    Pin("PF5", "ADC3_INP4", "SLOW1"),
    Pin("PF3", "ADC3_INP5", "SLOW2"),
    Pin("PC0", "ADC3_INP10", "SLOW3"),
    Pin("PA3", "ADC1_INP15", "SLOW4"),
    Pin("PF10", "ADC3_INP6", "BOARD_ID1", note="resistor divider on the power board"),
    Pin("PF4", "ADC3_INP9", "BOARD_ID2"),
    Pin("PB2", "COMP1_INP", "OV_COMP", note="optional second over-voltage path"),
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
    Pin("PG5", "GPIO", "TRIP_CLEAR", "out", note="the only way to clear the trip latch"),
    Pin("PF0", "I2C2_SDA", "DAC_SDA", note="trip-threshold DAC"),
    Pin("PF1", "I2C2_SCL", "DAC_SCL"),
    Pin("PD7", "GPIO", "GATE_ENABLE", "out"),
    Pin("PG0", "GPIO", "RELAY_PRECHARGE", "out"),
    Pin("PG1", "GPIO", "RELAY_MAIN", "out"),
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

# Pairs converted at the same instant, in dual regular simultaneous mode:
# (on ADC1, on ADC2).
SIMULTANEOUS = [
    ("IA", "IB"),
    ("VDC", "VA"),
]
