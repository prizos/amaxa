/*
 * Board bring-up helpers for hello_hw: clocks, LEDs, button, console UART,
 * ADC (die temperature / VDDA), independent watchdog, reset cause.
 */
#ifndef HW_H
#define HW_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "board.h"
#include "stm32h7xx_hal.h"

enum hw_led { HW_LED_GREEN, HW_LED_YELLOW, HW_LED_RED };

/* 8 MHz HSE (ST-LINK) -> PLL1 -> 400 MHz SYSCLK, 200 MHz AHB, 100 MHz APBs.
 * Returns 0, or a negative step number; on failure the chip keeps running on
 * whatever clock is active (HSI after reset), so the console still works. */
int hw_init_clocks(void);
void hw_init_gpio(void);
void hw_init_console(void);
void hw_init_cycle_counter(void);

void hw_led_set(enum hw_led led, bool on);
void hw_led_toggle(enum hw_led led);

/* Returns true once per debounced press of the user button. */
bool hw_button_take_press(void);
/* Called from the EXTI interrupt. */
void hw_button_irq(void);

/* Console on the ST-LINK virtual COM port. */
int hw_console_getc(void); /* -1 when no byte is waiting */
void hw_console_write(const char *buf, size_t len);

/* ADC3 internal channels. Returns 0 on success, negative on failure. */
int hw_adc_init(void);
int hw_adc_read_die(int32_t *temp_mdegc, uint32_t *vdda_mv);

int hw_watchdog_start(uint32_t timeout_ms);
void hw_watchdog_kick(void);

/* Human-readable reason for the last reset; clears the RCC reset flags. */
const char *hw_reset_cause(void);

/* Route core lockup, flash/RAM double-ECC errors and PVD to the timer break
 * inputs, so these faults force the PWM outputs off in hardware. */
void hw_route_faults_to_timer_break(void);

/* Converts DWT cycle counts to microseconds at the current core clock. */
uint32_t hw_cycles_to_us(uint32_t cycles);

void hw_panic(const char *reason) __attribute__((noreturn));

#endif /* HW_H */
