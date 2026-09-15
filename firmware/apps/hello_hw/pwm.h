/*
 * Three-phase sine PWM on TIM1: complementary outputs with hardware dead-time,
 * break input, and timing statistics for the 20 kHz update interrupt.
 */
#ifndef PWM_H
#define PWM_H

#include <stdbool.h>
#include <stdint.h>

struct pwm_config {
    uint32_t pwm_hz;         /* switching frequency */
    uint32_t deadtime_ns;    /* requested dead-time */
    uint32_t electrical_mhz; /* sine frequency, millihertz */
};

struct pwm_report {
    uint32_t timer_clock_hz;
    uint32_t auto_reload;    /* counter peak; the period is twice this (centre-aligned) */
    uint32_t deadtime_ns;    /* dead-time actually programmed */
    uint8_t dtg;             /* TIM1_BDTR.DTG register value */
};

struct pwm_stats {
    uint32_t isr_count;         /* update interrupts since the previous snapshot */
    uint32_t isr_max_cycles;    /* longest interrupt body, DWT cycles */
    uint32_t period_min_cycles; /* shortest/longest time between interrupt entries */
    uint32_t period_max_cycles;
    uint32_t overruns;          /* updates still pending when the interrupt returned */
    uint32_t breaks;            /* break events since boot */
};

/* Configures TIM1 and starts switching at 0 % modulation. Returns 0 on success. */
int pwm_init(const struct pwm_config *config, struct pwm_report *report);

void pwm_set_modulation(uint32_t permille);
uint32_t pwm_get_modulation(void);

bool pwm_outputs_enabled(void);     /* TIM1 main output enable (MOE) */
bool pwm_break_input_active(void);  /* PE15 is low */
void pwm_software_break(void);
int pwm_rearm(void);                /* 0 on success, negative if a break is still active */

/* Copies the interval statistics and starts a new interval. */
void pwm_take_stats(struct pwm_stats *stats);
uint32_t pwm_expected_period_cycles(void);

#endif /* PWM_H */
