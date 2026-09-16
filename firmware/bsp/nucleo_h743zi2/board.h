/*
 * NUCLEO-H743ZI2 pin map (ST user manual UM2407).
 */
#ifndef BOARD_H
#define BOARD_H

/* User LEDs, active high. */
#define BOARD_LED_GREEN_PORT   GPIOB   /* LD1 */
#define BOARD_LED_GREEN_PIN    GPIO_PIN_0
#define BOARD_LED_YELLOW_PORT  GPIOE   /* LD2 */
#define BOARD_LED_YELLOW_PIN   GPIO_PIN_1
#define BOARD_LED_RED_PORT     GPIOB   /* LD3 */
#define BOARD_LED_RED_PIN      GPIO_PIN_14

/* User button B1, active high (external pull-down on the board). */
#define BOARD_BUTTON_PORT      GPIOC
#define BOARD_BUTTON_PIN       GPIO_PIN_13
#define BOARD_BUTTON_IRQn      EXTI15_10_IRQn

/* ST-LINK virtual COM port: USART3 on PD8 (TX) / PD9 (RX), AF7. */
#define BOARD_VCP_UART         USART3
#define BOARD_VCP_PORT         GPIOD
#define BOARD_VCP_TX_PIN       GPIO_PIN_8
#define BOARD_VCP_RX_PIN       GPIO_PIN_9
#define BOARD_VCP_AF           GPIO_AF7_USART3

/*
 * TIM1 three-phase complementary PWM on the Zio connector, AF1:
 *   PE9  CH1   PE8  CH1N
 *   PE11 CH2   PE10 CH2N
 *   PE13 CH3   PE12 CH3N
 *   PE15 BKIN  (break input, active low)
 */
#define BOARD_PWM_PORT         GPIOE
#define BOARD_PWM_PINS         (GPIO_PIN_8 | GPIO_PIN_9 | GPIO_PIN_10 | \
                                GPIO_PIN_11 | GPIO_PIN_12 | GPIO_PIN_13)
#define BOARD_PWM_BKIN_PIN     GPIO_PIN_15
#define BOARD_PWM_AF           GPIO_AF1_TIM1

#endif /* BOARD_H */
