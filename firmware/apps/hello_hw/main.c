/*
 * hello_hw: a non-trivial "hello world" for the NUCLEO-H743ZI2.
 *
 * It proves the toolchain, startup code, clock tree and a set of peripherals
 * that matter for a motor/inverter controller:
 *   - 400 MHz clock from the ST-LINK 8 MHz reference through PLL1
 *   - console on USART3 (ST-LINK virtual COM port), 115200 8N1
 *   - three-phase 50 Hz sine PWM on TIM1: 20 kHz centre-aligned, complementary
 *     outputs, 1 us hardware dead-time, active-low break input on PE15
 *   - 20 kHz interrupt timing (execution time, period jitter, overruns) via DWT
 *   - ADC3 die temperature and VDDA from the internal reference
 *   - LEDs, button interrupt, independent watchdog, reset-cause reporting
 *   - core lockup and RAM/flash ECC errors routed to the TIM1 break
 */

#include <inttypes.h>
#include <stdbool.h>
#include <stdio.h>

#include "faults.h"
#include "hw.h"
#include "pwm.h"

#define PWM_HZ 20000U
#define DEADTIME_NS 1000U
#define SINE_MHZ 50000U /* 50 Hz electrical */
#define WATCHDOG_MS 2000U
#define STATUS_PERIOD_MS 1000U

static bool feed_watchdog = true;

static const char *revision_name(uint32_t rev)
{
    switch (rev) {
    case 0x1003: return "Y";
    case 0x2001: return "X";
    case 0x2003: return "V";
    default: return "?";
    }
}

static void print_banner(const char *reset_cause, int clock_rc, int pwm_rc,
                         const struct pwm_report *pwm, int adc_rc, int wdg_rc)
{
    uint32_t hal = HAL_GetHalVersion();
    printf("\n\namaxa hello_hw on NUCLEO-H743ZI2\n");
    printf("  reset cause  %s\n", reset_cause);
    printf("  compiler     GCC %s\n", __VERSION__);
    printf("  ST HAL       v%" PRIu32 ".%" PRIu32 ".%" PRIu32 "\n", hal >> 24, (hal >> 16) & 0xFFU,
           (hal >> 8) & 0xFFU);
    printf("  MCU          dev 0x%03" PRIx32 " rev %s, %u KB flash, UID %08" PRIx32 "%08" PRIx32 "%08" PRIx32 "\n",
           HAL_GetDEVID(), revision_name(HAL_GetREVID()), (unsigned)*(uint16_t *)FLASHSIZE_BASE,
           HAL_GetUIDw2(), HAL_GetUIDw1(), HAL_GetUIDw0());
    printf("  clocks       SYSCLK %" PRIu32 " MHz, APB2 %" PRIu32 " MHz%s (%d)\n",
           SystemCoreClock / 1000000U, HAL_RCC_GetPCLK2Freq() / 1000000U,
           clock_rc == 0 ? "" : clock_rc == -1 ? ", supply config was locked" : ", PLL setup FAILED",
           clock_rc);
    if (pwm_rc == 0) {
        printf("  pwm          TIM1 3-phase %u Hz centre-aligned, timer %" PRIu32 " MHz, ARR %" PRIu32
               ", dead-time %" PRIu32 " ns (DTG 0x%02x), sine %u Hz\n",
               PWM_HZ, pwm->timer_clock_hz / 1000000U, pwm->auto_reload, pwm->deadtime_ns, pwm->dtg,
               SINE_MHZ / 1000U);
        printf("               outputs PE9/PE8 PE11/PE10 PE13/PE12, break input PE15 (active low)\n");
    } else {
        printf("  pwm          init FAILED (%d)\n", pwm_rc);
    }
    printf("  adc          %s (%d)\n", adc_rc == 0 ? "ADC3 VREFINT + temperature sensor" : "init FAILED", adc_rc);
    printf("  watchdog     %s (%d)\n", wdg_rc == 0 ? "IWDG1, 2 s timeout" : "FAILED", wdg_rc);
    printf("  fault route  core lockup, flash/RAM ECC errors -> TIM1 break\n");
}

static void print_help(void)
{
    printf("commands:\n"
           "  ?  help            s  status now\n"
           "  +  modulation +10%%  -  modulation -10%%\n"
           "  b  software break (PWM outputs to their safe state)\n"
           "  r  re-arm PWM after a break\n"
           "  w  stop feeding the watchdog (simulated hang -> IWDG reset)\n"
           "  l  core lockup (double fault -> TIM1 break -> IWDG reset)\n"
           "button B1 cycles the modulation 0 / 30 / 60 / 90 %%\n\n");
}

static void print_status(uint32_t now_ms)
{
    struct pwm_stats st;
    pwm_take_stats(&st);

    int32_t temp_mdegc = 0;
    uint32_t vdda_mv = 0;
    int adc_rc = hw_adc_read_die(&temp_mdegc, &vdda_mv);

    int32_t expected = (int32_t)pwm_expected_period_cycles();
    int32_t jitter_lo = st.period_min_cycles ? (int32_t)st.period_min_cycles - expected : 0;
    int32_t jitter_hi = st.period_max_cycles ? (int32_t)st.period_max_cycles - expected : 0;

    printf("[%5" PRIu32 ".%03" PRIu32 "] pwm %s mod %3" PRIu32 "%% | isr %5" PRIu32 "/s max %3" PRIu32
           " us jitter %+" PRId32 "/%+" PRId32 " cyc overruns %" PRIu32 " breaks %" PRIu32,
           now_ms / 1000U, now_ms % 1000U, pwm_outputs_enabled() ? "ON " : "OFF",
           pwm_get_modulation() / 10U, st.isr_count, hw_cycles_to_us(st.isr_max_cycles), jitter_lo,
           jitter_hi, st.overruns, st.breaks);
    if (adc_rc == 0) {
        int32_t tenths = (temp_mdegc % 1000) / 100;
        printf(" | die %" PRId32 ".%" PRId32 " C vdda %" PRIu32 " mV", temp_mdegc / 1000,
               tenths < 0 ? -tenths : tenths, vdda_mv);
    } else {
        printf(" | adc error %d", adc_rc);
    }
    printf(" | bkin %s wdg %s\n", pwm_break_input_active() ? "ACTIVE" : "idle",
           feed_watchdog ? "fed" : "STARVED");
}

static void handle_command(int c, uint32_t now_ms)
{
    switch (c) {
    case '?':
    case 'h':
        print_help();
        break;
    case 's':
        print_status(now_ms);
        break;
    case '+':
        pwm_set_modulation(pwm_get_modulation() + 100U);
        printf("modulation %" PRIu32 "%%\n", pwm_get_modulation() / 10U);
        break;
    case '-': {
        uint32_t m = pwm_get_modulation();
        pwm_set_modulation(m >= 100U ? m - 100U : 0U);
        printf("modulation %" PRIu32 "%%\n", pwm_get_modulation() / 10U);
        break;
    }
    case 'b':
        pwm_software_break();
        printf("software break: PWM outputs forced to their safe state\n");
        break;
    case 'r': {
        int rc = pwm_rearm();
        if (rc == 0) {
            printf("PWM re-armed\n");
        } else {
            printf("re-arm refused (%d): a break source is still active\n", rc);
        }
        break;
    }
    case 'w':
        feed_watchdog = false;
        printf("watchdog no longer fed: expect an IWDG reset within %u ms\n", WATCHDOG_MS);
        break;
    case 'l':
        printf("lockup test: faulting inside HardFault now\n");
        faults_trigger_lockup();
        break;
    case '\r':
    case '\n':
        break;
    default:
        printf("unknown command '%c' (? for help)\n", c);
        break;
    }
}

int main(void)
{
    HAL_Init();
    HAL_EnableDBGSleepMode(); /* keep SWD debugging usable across __WFI() */
    int clock_rc = hw_init_clocks();
    hw_init_cycle_counter();
    hw_init_gpio();
    hw_init_console();
    setvbuf(stdout, NULL, _IONBF, 0);

    const char *reset_cause = hw_reset_cause();
    hw_route_faults_to_timer_break();

    int adc_rc = hw_adc_init();
    struct pwm_report pwm = {0};
    const struct pwm_config pwm_config = {
        .pwm_hz = PWM_HZ,
        .deadtime_ns = DEADTIME_NS,
        .electrical_mhz = SINE_MHZ,
    };
    int pwm_rc = pwm_init(&pwm_config, &pwm);
    int wdg_rc = hw_watchdog_start(WATCHDOG_MS);

    print_banner(reset_cause, clock_rc, pwm_rc, &pwm, adc_rc, wdg_rc);
    print_help();

    uint32_t last_status = HAL_GetTick();
    uint32_t last_blink = last_status;
    for (;;) {
        uint32_t now = HAL_GetTick();
        if (feed_watchdog) {
            hw_watchdog_kick();
        }

        /* Green: fast blink while switching, slow blink when outputs are off. */
        if (now - last_blink >= (pwm_outputs_enabled() ? 250U : 1000U)) {
            last_blink = now;
            hw_led_toggle(HW_LED_GREEN);
        }
        hw_led_set(HW_LED_YELLOW, pwm_get_modulation() > 0U);
        hw_led_set(HW_LED_RED, !pwm_outputs_enabled());

        if (hw_button_take_press()) {
            uint32_t m = pwm_get_modulation();
            pwm_set_modulation(m >= 900U ? 0U : m + 300U);
            printf("button: modulation %" PRIu32 "%%\n", pwm_get_modulation() / 10U);
        }

        int c = hw_console_getc();
        if (c >= 0) {
            handle_command(c, now);
        }

        if (now - last_status >= STATUS_PERIOD_MS) {
            last_status = now;
            print_status(now);
        }

        __WFI(); /* sleep until the next interrupt (SysTick, TIM1, button) */
    }
}
