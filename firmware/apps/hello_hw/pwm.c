#include "pwm.h"

#include <math.h>

#include "board.h"
#include "hw.h"
#include "stm32h7xx_hal.h"

#define SINE_BITS 10U
#define SINE_SIZE (1U << SINE_BITS)
#define PHASE_120 0x55555555U
#define PHASE_240 0xAAAAAAAAU
#define BREAK_FLAGS (TIM_SR_BIF | TIM_SR_B2IF | TIM_SR_SBIF)

static TIM_HandleTypeDef tim1;
static int16_t sine_q15[SINE_SIZE];

static uint32_t half_scale;                 /* compare value for 50 % duty */
static volatile int32_t amplitude;          /* compare swing at full sine */
static volatile uint32_t modulation_permille;
static uint32_t phase;
static uint32_t phase_step;
static uint32_t expected_period_cycles;

/* Interval statistics, updated in interrupt context. */
static volatile uint32_t isr_count;
static volatile uint32_t isr_max_cycles;
static volatile uint32_t period_min_cycles = UINT32_MAX;
static volatile uint32_t period_max_cycles;
static volatile uint32_t overruns;
static volatile uint32_t breaks;
static uint32_t last_entry;
static bool have_last_entry;

/*
 * Encodes a dead-time for TIM1_BDTR.DTG (tDTS = one timer tick):
 *   0xxxxxxx  DT = DTG[7:0]         x tDTS
 *   10xxxxxx  DT = (64 + DTG[5:0])  x 2 tDTS
 *   110xxxxx  DT = (32 + DTG[4:0])  x 8 tDTS
 *   111xxxxx  DT = (32 + DTG[4:0])  x 16 tDTS
 */
static uint8_t deadtime_to_dtg(uint32_t deadtime_ns, uint32_t tick_ps, uint32_t *actual_ns)
{
    static const struct {
        uint8_t prefix, base, max_field, multiplier;
    } encodings[] = {
        {0x00, 0, 127, 1},
        {0x80, 64, 63, 2},
        {0xC0, 32, 31, 8},
        {0xE0, 32, 31, 16},
    };
    uint64_t want_ps = (uint64_t)deadtime_ns * 1000ULL;
    for (unsigned i = 0; i < sizeof(encodings) / sizeof(encodings[0]); i++) {
        uint64_t units = want_ps / ((uint64_t)tick_ps * encodings[i].multiplier);
        if (units >= encodings[i].base && units <= (uint64_t)encodings[i].base + encodings[i].max_field) {
            *actual_ns = (uint32_t)(units * encodings[i].multiplier * tick_ps / 1000ULL);
            return (uint8_t)(encodings[i].prefix | (units - encodings[i].base));
        }
    }
    *actual_ns = (uint32_t)((63ULL * 16ULL * tick_ps) / 1000ULL);
    return 0xFF; /* longest representable dead-time: 1008 ticks */
}

void HAL_TIM_PWM_MspInit(TIM_HandleTypeDef *htim)
{
    if (htim->Instance != TIM1) {
        return;
    }
    __HAL_RCC_TIM1_CLK_ENABLE();
    __HAL_RCC_GPIOE_CLK_ENABLE();

    /* Weak pull-downs hold the gate signals low whenever the pins are not
     * driven (reset, reprogramming). A real power board adds stronger ones. */
    GPIO_InitTypeDef outputs = {
        .Pin = BOARD_PWM_PINS,
        .Mode = GPIO_MODE_AF_PP,
        .Pull = GPIO_PULLDOWN,
        .Speed = GPIO_SPEED_FREQ_HIGH,
        .Alternate = BOARD_PWM_AF,
    };
    HAL_GPIO_Init(BOARD_PWM_PORT, &outputs);

    /* Break input is active low: idle high through the pull-up. */
    GPIO_InitTypeDef break_input = {
        .Pin = BOARD_PWM_BKIN_PIN,
        .Mode = GPIO_MODE_AF_PP,
        .Pull = GPIO_PULLUP,
        .Speed = GPIO_SPEED_FREQ_LOW,
        .Alternate = BOARD_PWM_AF,
    };
    HAL_GPIO_Init(BOARD_PWM_PORT, &break_input);
}

int pwm_init(const struct pwm_config *config, struct pwm_report *report)
{
    for (uint32_t i = 0; i < SINE_SIZE; i++) {
        float angle = 2.0f * (float)M_PI * (float)i / (float)SINE_SIZE;
        sine_q15[i] = (int16_t)lrintf(32767.0f * sinf(angle));
    }

    /* TIM1 is on APB2; with an APB2 prescaler above 1 the timer clock is 2 x PCLK2. */
    uint32_t timer_clock = HAL_RCC_GetPCLK2Freq();
    if ((RCC->D2CFGR & RCC_D2CFGR_D2PPRE2) >= RCC_D2CFGR_D2PPRE2_DIV2) {
        timer_clock *= 2U;
    }

    /* Centre-aligned: the counter runs 0 -> ARR -> 0, so one period is 2 x ARR ticks. */
    uint32_t auto_reload = timer_clock / (2U * config->pwm_hz);
    if (auto_reload < 100U || auto_reload > 0xFFFFU) {
        return -1;
    }
    half_scale = auto_reload / 2U;
    expected_period_cycles = SystemCoreClock / config->pwm_hz;

    uint32_t tick_ps = (uint32_t)(1000000000000ULL / timer_clock);
    uint32_t actual_deadtime_ns = 0;
    uint8_t dtg = deadtime_to_dtg(config->deadtime_ns, tick_ps, &actual_deadtime_ns);

    tim1.Instance = TIM1;
    tim1.Init.Prescaler = 0;
    tim1.Init.CounterMode = TIM_COUNTERMODE_CENTERALIGNED1;
    tim1.Init.Period = auto_reload;
    tim1.Init.ClockDivision = TIM_CLOCKDIVISION_DIV1;
    tim1.Init.RepetitionCounter = 1; /* one update event per full PWM period */
    tim1.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_ENABLE;
    if (HAL_TIM_PWM_Init(&tim1) != HAL_OK) {
        return -2;
    }

    TIM_OC_InitTypeDef channel = {
        .OCMode = TIM_OCMODE_PWM1,
        .Pulse = half_scale,
        .OCPolarity = TIM_OCPOLARITY_HIGH,
        .OCNPolarity = TIM_OCNPOLARITY_HIGH,
        .OCFastMode = TIM_OCFAST_DISABLE,
        .OCIdleState = TIM_OCIDLESTATE_RESET, /* safe state: both switches off */
        .OCNIdleState = TIM_OCNIDLESTATE_RESET,
    };
    static const uint32_t channels[] = {TIM_CHANNEL_1, TIM_CHANNEL_2, TIM_CHANNEL_3};
    for (unsigned i = 0; i < 3U; i++) {
        if (HAL_TIM_PWM_ConfigChannel(&tim1, &channel, channels[i]) != HAL_OK) {
            return -3;
        }
    }

    TIM_BreakDeadTimeConfigTypeDef protection = {
        .OffStateRunMode = TIM_OSSR_ENABLE,
        .OffStateIDLEMode = TIM_OSSI_ENABLE,
        .LockLevel = TIM_LOCKLEVEL_OFF,
        .DeadTime = dtg,
        .BreakState = TIM_BREAK_ENABLE,
        .BreakPolarity = TIM_BREAKPOLARITY_LOW,
        .BreakFilter = 3,
        .Break2State = TIM_BREAK2_DISABLE,
        .Break2Polarity = TIM_BREAK2POLARITY_HIGH,
        .Break2Filter = 0,
        .AutomaticOutput = TIM_AUTOMATICOUTPUT_DISABLE, /* a break latches until re-armed */
    };
    if (HAL_TIMEx_ConfigBreakDeadTime(&tim1, &protection) != HAL_OK) {
        return -4;
    }

    phase_step = (uint32_t)(((uint64_t)config->electrical_mhz << 32) /
                            ((uint64_t)config->pwm_hz * 1000ULL));
    pwm_set_modulation(0);

    __HAL_TIM_CLEAR_FLAG(&tim1, TIM_FLAG_UPDATE | BREAK_FLAGS);
    __HAL_TIM_ENABLE_IT(&tim1, TIM_IT_UPDATE | TIM_IT_BREAK);
    HAL_NVIC_SetPriority(TIM1_BRK_IRQn, 0, 0); /* highest */
    HAL_NVIC_SetPriority(TIM1_UP_IRQn, 1, 0);
    HAL_NVIC_EnableIRQ(TIM1_BRK_IRQn);
    HAL_NVIC_EnableIRQ(TIM1_UP_IRQn);

    for (unsigned i = 0; i < 3U; i++) {
        if (HAL_TIM_PWM_Start(&tim1, channels[i]) != HAL_OK ||
            HAL_TIMEx_PWMN_Start(&tim1, channels[i]) != HAL_OK) {
            return -5;
        }
    }

    report->timer_clock_hz = timer_clock;
    report->auto_reload = auto_reload;
    report->deadtime_ns = actual_deadtime_ns;
    report->dtg = dtg;
    return 0;
}

void pwm_set_modulation(uint32_t permille)
{
    if (permille > 1000U) {
        permille = 1000U;
    }
    modulation_permille = permille;
    amplitude = (int32_t)(half_scale * permille / 1000U);
}

uint32_t pwm_get_modulation(void)
{
    return modulation_permille;
}

bool pwm_outputs_enabled(void)
{
    return (TIM1->BDTR & TIM_BDTR_MOE) != 0U;
}

bool pwm_break_input_active(void)
{
    return HAL_GPIO_ReadPin(BOARD_PWM_PORT, BOARD_PWM_BKIN_PIN) == GPIO_PIN_RESET;
}

void pwm_software_break(void)
{
    TIM1->EGR = TIM_EGR_BG;
}

int pwm_rearm(void)
{
    if (pwm_break_input_active()) {
        return -1;
    }
    TIM1->SR = ~BREAK_FLAGS;
    TIM1->DIER |= TIM_DIER_BIE;
    TIM1->BDTR |= TIM_BDTR_MOE;
    if (!pwm_outputs_enabled()) {
        return -2; /* another break source is still asserted */
    }
    hw_led_set(HW_LED_RED, false);
    return 0;
}

void pwm_take_stats(struct pwm_stats *stats)
{
    uint32_t primask = __get_PRIMASK();
    __disable_irq();
    stats->isr_count = isr_count;
    stats->isr_max_cycles = isr_max_cycles;
    stats->period_min_cycles = (period_min_cycles == UINT32_MAX) ? 0U : period_min_cycles;
    stats->period_max_cycles = period_max_cycles;
    stats->overruns = overruns;
    stats->breaks = breaks;
    isr_count = 0;
    isr_max_cycles = 0;
    period_min_cycles = UINT32_MAX;
    period_max_cycles = 0;
    overruns = 0;
    __set_PRIMASK(primask);
}

uint32_t pwm_expected_period_cycles(void)
{
    return expected_period_cycles;
}

/* The 20 kHz "control loop": advance the sine phase and load three duty cycles. */
void TIM1_UP_IRQHandler(void)
{
    uint32_t entry = DWT->CYCCNT;
    TIM_TypeDef *timer = TIM1;
    if ((timer->SR & TIM_SR_UIF) == 0U) {
        return;
    }
    timer->SR = ~TIM_SR_UIF;

    if (have_last_entry) {
        uint32_t period = entry - last_entry;
        if (period < period_min_cycles) {
            period_min_cycles = period;
        }
        if (period > period_max_cycles) {
            period_max_cycles = period;
        }
    }
    last_entry = entry;
    have_last_entry = true;

    phase += phase_step;
    int32_t swing = amplitude;
    int32_t mid = (int32_t)half_scale;
    timer->CCR1 = (uint32_t)(mid + ((swing * sine_q15[phase >> (32U - SINE_BITS)]) >> 15));
    timer->CCR2 = (uint32_t)(mid + ((swing * sine_q15[(phase + PHASE_120) >> (32U - SINE_BITS)]) >> 15));
    timer->CCR3 = (uint32_t)(mid + ((swing * sine_q15[(phase + PHASE_240) >> (32U - SINE_BITS)]) >> 15));

    isr_count++;
    uint32_t spent = DWT->CYCCNT - entry;
    if (spent > isr_max_cycles) {
        isr_max_cycles = spent;
    }
    if (timer->SR & TIM_SR_UIF) {
        overruns++; /* the next period started before this one was handled */
    }
}

void TIM1_BRK_IRQHandler(void)
{
    TIM_TypeDef *timer = TIM1;
    uint32_t flags = timer->SR & BREAK_FLAGS;
    if (flags == 0U) {
        return;
    }
    timer->SR = ~flags;
    /* A held break input keeps setting BIF: mute the interrupt until re-armed. */
    timer->DIER &= ~TIM_DIER_BIE;
    breaks++;
    hw_led_set(HW_LED_RED, true);
}
