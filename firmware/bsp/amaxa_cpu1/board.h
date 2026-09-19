/*
 * amaxa cpu1 pin map, in the names the apps already use.
 *
 * Nothing here is a pin number. Every one of these is an alias for an entry in
 * the generated `board_pins.h`, which comes from `hw/cpu1/pinmap.py` - the same
 * table the schematic is wired from. Write a pin number here and it is a second
 * source of truth for the pinout, which is exactly what the generator exists to
 * prevent; a check compares the generated header against the committed one, and
 * it cannot compare anything it has not been told about.
 *
 * The names are the NUCLEO's because the apps are: `hello_hw` was written
 * against that board and its macro names are the interface. What each one means
 * on this board is in the comment beside it.
 */
#ifndef BOARD_H
#define BOARD_H

#include "board_pins.h"

/* Three indicators, active high, driven through 1k. The NUCLEO's colours are
 * what the app calls them; on this board they mean status, fault and comms. */
#define BOARD_LED_GREEN_PORT   PIN_LED_STATUS_PORT
#define BOARD_LED_GREEN_PIN    PIN_LED_STATUS_PIN
#define BOARD_LED_YELLOW_PORT  PIN_LED_COMMS_PORT
#define BOARD_LED_YELLOW_PIN   PIN_LED_COMMS_PIN
#define BOARD_LED_RED_PORT     PIN_LED_FAULT_PORT
#define BOARD_LED_RED_PIN      PIN_LED_FAULT_PIN

/* User button, active high, with a pull-down on the board. PC13 is in the
 * 15..10 EXTI group, the same as the NUCLEO's. */
#define BOARD_BUTTON_PORT      PIN_BUTTON_PORT
#define BOARD_BUTTON_PIN       PIN_BUTTON_PIN
#define BOARD_BUTTON_IRQn      EXTI15_10_IRQn

/* Console: USART3 on PD8/PD9, brought out to test pads rather than to a
 * virtual COM port - there is no debugger bridge on this board. */
#define BOARD_VCP_UART         USART3
#define BOARD_VCP_PORT         PIN_CONSOLE_TX_PORT
#define BOARD_VCP_TX_PIN       PIN_CONSOLE_TX_PIN
#define BOARD_VCP_RX_PIN       PIN_CONSOLE_RX_PIN
#define BOARD_VCP_AF           PIN_CONSOLE_TX_AF

/*
 * TIM1 three-phase complementary PWM, AF1, all six on port E as on the NUCLEO -
 * which is why `BOARD_PWM_PORT` is still one port and the firmware's existing
 * setup carries over unchanged. The break input is the hardware trip latch, not
 * a spare pin: nothing reaches a gate driver unless the latch allows it.
 */
#define BOARD_PWM_PORT         PIN_PWM1_A_LOW_PORT
#define BOARD_PWM_PINS         (PIN_PWM1_A_LOW_PIN | PIN_PWM1_A_HIGH_PIN |  \
                                PIN_PWM1_B_LOW_PIN | PIN_PWM1_B_HIGH_PIN |  \
                                PIN_PWM1_C_LOW_PIN | PIN_PWM1_C_HIGH_PIN)
#define BOARD_PWM_BKIN_PIN     PIN_TRIP1_N_PIN
#define BOARD_PWM_AF           PIN_PWM1_A_LOW_AF

#endif /* BOARD_H */
