#include "hw.h"

#include "clock.h"

#include <string.h>

#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))

static const struct {
    GPIO_TypeDef *port;
    uint16_t pin;
} leds[] = {
    [HW_LED_GREEN] = {BOARD_LED_GREEN_PORT, BOARD_LED_GREEN_PIN},
    [HW_LED_YELLOW] = {BOARD_LED_YELLOW_PORT, BOARD_LED_YELLOW_PIN},
    [HW_LED_RED] = {BOARD_LED_RED_PORT, BOARD_LED_RED_PIN},
};

static UART_HandleTypeDef console;
static ADC_HandleTypeDef adc;
static IWDG_HandleTypeDef iwdg;

static bool gpio_ready;
static bool console_ready;
static bool adc_ready;
static bool iwdg_running;

static volatile uint32_t button_pending;
static uint32_t button_last_ms;

/* ------------------------------------------------------------------------- */
/* Clocks                                                                    */
/* ------------------------------------------------------------------------- */

int hw_init_clocks(void)
{
    /* The numbers moved to the board support package, where the crystal is.
     * This board is not the only one this app runs on any more. */
    return board_init_clocks();
}

void hw_init_cycle_counter(void)
{
    CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
    *(uint32_t *)0xE0001FB0UL = 0xC5ACCE55UL; /* DWT lock access register (Cortex-M7) */
    DWT->CYCCNT = 0;
    DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;
}

uint32_t hw_cycles_to_us(uint32_t cycles)
{
    return (uint32_t)(((uint64_t)cycles * 1000000ULL) / SystemCoreClock);
}

/* ------------------------------------------------------------------------- */
/* LEDs and button                                                           */
/* ------------------------------------------------------------------------- */

void hw_enable_port_clock(GPIO_TypeDef *port)
{
    if (port == GPIOA) {
        __HAL_RCC_GPIOA_CLK_ENABLE();
    } else if (port == GPIOB) {
        __HAL_RCC_GPIOB_CLK_ENABLE();
    } else if (port == GPIOC) {
        __HAL_RCC_GPIOC_CLK_ENABLE();
    } else if (port == GPIOD) {
        __HAL_RCC_GPIOD_CLK_ENABLE();
    } else if (port == GPIOE) {
        __HAL_RCC_GPIOE_CLK_ENABLE();
    } else if (port == GPIOF) {
        __HAL_RCC_GPIOF_CLK_ENABLE();
    } else if (port == GPIOG) {
        __HAL_RCC_GPIOG_CLK_ENABLE();
    } else if (port == GPIOH) {
        __HAL_RCC_GPIOH_CLK_ENABLE();
    } else if (port == GPIOI) {
        __HAL_RCC_GPIOI_CLK_ENABLE();
    } else if (port == GPIOJ) {
        __HAL_RCC_GPIOJ_CLK_ENABLE();
    } else if (port == GPIOK) {
        __HAL_RCC_GPIOK_CLK_ENABLE();
    }
}

void hw_init_gpio(void)
{
    for (size_t i = 0; i < ARRAY_SIZE(leds); i++) {
        hw_enable_port_clock(leds[i].port);
    }
    hw_enable_port_clock(BOARD_BUTTON_PORT);

    for (size_t i = 0; i < ARRAY_SIZE(leds); i++) {
        HAL_GPIO_WritePin(leds[i].port, leds[i].pin, GPIO_PIN_RESET);
        GPIO_InitTypeDef out = {
            .Pin = leds[i].pin,
            .Mode = GPIO_MODE_OUTPUT_PP,
            .Pull = GPIO_NOPULL,
            .Speed = GPIO_SPEED_FREQ_LOW,
        };
        HAL_GPIO_Init(leds[i].port, &out);
    }

    GPIO_InitTypeDef button = {
        .Pin = BOARD_BUTTON_PIN,
        .Mode = GPIO_MODE_IT_RISING,
        .Pull = GPIO_NOPULL,
    };
    HAL_GPIO_Init(BOARD_BUTTON_PORT, &button);
    HAL_NVIC_SetPriority(BOARD_BUTTON_IRQn, 10, 0);
    HAL_NVIC_EnableIRQ(BOARD_BUTTON_IRQn);

    gpio_ready = true;
}

void hw_led_set(enum hw_led led, bool on)
{
    HAL_GPIO_WritePin(leds[led].port, leds[led].pin, on ? GPIO_PIN_SET : GPIO_PIN_RESET);
}

void hw_led_toggle(enum hw_led led)
{
    HAL_GPIO_TogglePin(leds[led].port, leds[led].pin);
}

void hw_button_irq(void)
{
    uint32_t now = HAL_GetTick();
    if (now - button_last_ms >= 200U) { /* debounce */
        button_last_ms = now;
        button_pending = 1U;
    }
}

bool hw_button_take_press(void)
{
    uint32_t primask = __get_PRIMASK();
    __disable_irq();
    bool pressed = button_pending != 0U;
    button_pending = 0U;
    __set_PRIMASK(primask);
    return pressed;
}

/* ------------------------------------------------------------------------- */
/* Console (USART3 on the ST-LINK virtual COM port), polled                  */
/* ------------------------------------------------------------------------- */

void HAL_UART_MspInit(UART_HandleTypeDef *huart)
{
    if (huart->Instance != BOARD_VCP_UART) {
        return;
    }
    __HAL_RCC_USART3_CLK_ENABLE();
    hw_enable_port_clock(BOARD_VCP_PORT);
    GPIO_InitTypeDef pins = {
        .Pin = BOARD_VCP_TX_PIN | BOARD_VCP_RX_PIN,
        .Mode = GPIO_MODE_AF_PP,
        .Pull = GPIO_PULLUP,
        .Speed = GPIO_SPEED_FREQ_LOW,
        .Alternate = BOARD_VCP_AF,
    };
    HAL_GPIO_Init(BOARD_VCP_PORT, &pins);
}

void hw_init_console(void)
{
    console.Instance = BOARD_VCP_UART;
    console.Init.BaudRate = 115200;
    console.Init.WordLength = UART_WORDLENGTH_8B;
    console.Init.StopBits = UART_STOPBITS_1;
    console.Init.Parity = UART_PARITY_NONE;
    console.Init.Mode = UART_MODE_TX_RX;
    console.Init.HwFlowCtl = UART_HWCONTROL_NONE;
    console.Init.OverSampling = UART_OVERSAMPLING_16;
    console.Init.OneBitSampling = UART_ONE_BIT_SAMPLE_DISABLE;
    console.Init.ClockPrescaler = UART_PRESCALER_DIV1;
    console.AdvancedInit.AdvFeatureInit = UART_ADVFEATURE_NO_INIT;
    if (HAL_UART_Init(&console) != HAL_OK) {
        hw_panic("console UART");
    }
    console_ready = true;
}

int hw_console_getc(void)
{
    if (!console_ready) {
        return -1;
    }
    USART_TypeDef *uart = console.Instance;
    if (uart->ISR & USART_ISR_ORE) {
        uart->ICR = USART_ICR_ORECF;
    }
    if ((uart->ISR & USART_ISR_RXNE_RXFNE) == 0U) {
        return -1;
    }
    return (int)(uart->RDR & 0xFFU);
}

void hw_console_write(const char *buf, size_t len)
{
    if (!console_ready) {
        return;
    }
    USART_TypeDef *uart = console.Instance;
    for (size_t i = 0; i < len; i++) {
        for (uint32_t spins = 0; (uart->ISR & USART_ISR_TXE_TXFNF) == 0U; spins++) {
            if (spins > 1000000U) {
                return; /* transmitter stuck: drop output rather than hang */
            }
        }
        uart->TDR = (uint8_t)buf[i];
    }
}

/* ------------------------------------------------------------------------- */
/* ADC3: VREFINT (for VDDA) and the die temperature sensor                   */
/* ------------------------------------------------------------------------- */

void HAL_ADC_MspInit(ADC_HandleTypeDef *hadc)
{
    if (hadc->Instance == ADC3) {
        __HAL_RCC_ADC3_CLK_ENABLE();
    }
}

int hw_adc_init(void)
{
    /* ADC kernel clock: CKPER, which defaults to HSI (64 MHz); /4 in the ADC. */
    RCC_PeriphCLKInitTypeDef kernel_clock = {
        .PeriphClockSelection = RCC_PERIPHCLK_ADC,
        .AdcClockSelection = RCC_ADCCLKSOURCE_CLKP,
    };
    if (HAL_RCCEx_PeriphCLKConfig(&kernel_clock) != HAL_OK) {
        return -1;
    }

    adc.Instance = ADC3;
    adc.Init.ClockPrescaler = ADC_CLOCK_ASYNC_DIV4;
    adc.Init.Resolution = ADC_RESOLUTION_16B;
    adc.Init.ScanConvMode = ADC_SCAN_DISABLE;
    adc.Init.EOCSelection = ADC_EOC_SINGLE_CONV;
    adc.Init.LowPowerAutoWait = DISABLE;
    adc.Init.ContinuousConvMode = DISABLE;
    adc.Init.NbrOfConversion = 1;
    adc.Init.DiscontinuousConvMode = DISABLE;
    adc.Init.ExternalTrigConv = ADC_SOFTWARE_START;
    adc.Init.ExternalTrigConvEdge = ADC_EXTERNALTRIGCONVEDGE_NONE;
    adc.Init.ConversionDataManagement = ADC_CONVERSIONDATA_DR;
    adc.Init.Overrun = ADC_OVR_DATA_OVERWRITTEN;
    adc.Init.LeftBitShift = ADC_LEFTBITSHIFT_NONE;
    adc.Init.OversamplingMode = DISABLE;
    if (HAL_ADC_Init(&adc) != HAL_OK) {
        return -2;
    }
    if (HAL_ADCEx_Calibration_Start(&adc, ADC_CALIB_OFFSET_LINEARITY, ADC_SINGLE_ENDED) != HAL_OK) {
        return -3;
    }
    adc_ready = true;
    return 0;
}

static int adc_sample(uint32_t channel, uint32_t *raw)
{
    ADC_ChannelConfTypeDef ch = {
        .Channel = channel,
        .Rank = ADC_REGULAR_RANK_1,
        .SamplingTime = ADC_SAMPLETIME_810CYCLES_5,
        .SingleDiff = ADC_SINGLE_ENDED,
        .OffsetNumber = ADC_OFFSET_NONE,
        .Offset = 0,
        .OffsetRightShift = DISABLE,
        .OffsetSignedSaturation = DISABLE,
    };
    if (HAL_ADC_ConfigChannel(&adc, &ch) != HAL_OK) {
        return -1;
    }
    if (HAL_ADC_Start(&adc) != HAL_OK) {
        return -2;
    }
    int rc = -3;
    if (HAL_ADC_PollForConversion(&adc, 50) == HAL_OK) {
        *raw = HAL_ADC_GetValue(&adc);
        rc = 0;
    }
    (void)HAL_ADC_Stop(&adc);
    return rc;
}

int hw_adc_read_die(int32_t *temp_mdegc, uint32_t *vdda_mv)
{
    if (!adc_ready) {
        return -10;
    }
    uint32_t vref_raw = 0;
    uint32_t ts_raw = 0;
    int rc = adc_sample(ADC_CHANNEL_VREFINT, &vref_raw);
    if (rc == 0) {
        rc = adc_sample(ADC_CHANNEL_TEMPSENSOR, &ts_raw);
    }
    if (rc != 0) {
        return rc;
    }

    /* Factory calibration values live in system memory (16-bit, 3.3 V). */
    int32_t ts_cal1 = *TEMPSENSOR_CAL1_ADDR;
    int32_t ts_cal2 = *TEMPSENSOR_CAL2_ADDR;
    if (vref_raw == 0U || ts_cal2 == ts_cal1) {
        return -4;
    }
    uint32_t vdda = __HAL_ADC_CALC_VREFANALOG_VOLTAGE(vref_raw, ADC_RESOLUTION_16B);

    /* Scale the reading to the 3.3 V calibration reference, then interpolate. */
    int32_t ts_at_cal_ref = (int32_t)((ts_raw * vdda) / TEMPSENSOR_CAL_VREFANALOG);
    int32_t span_mdegc = ((int32_t)TEMPSENSOR_CAL2_TEMP - (int32_t)TEMPSENSOR_CAL1_TEMP) * 1000;
    *temp_mdegc = (ts_at_cal_ref - ts_cal1) * span_mdegc / (ts_cal2 - ts_cal1) +
                  (int32_t)TEMPSENSOR_CAL1_TEMP * 1000;
    *vdda_mv = vdda;
    return 0;
}

/* ------------------------------------------------------------------------- */
/* Watchdog, reset cause, fault routing, panic                               */
/* ------------------------------------------------------------------------- */

int hw_watchdog_start(uint32_t timeout_ms)
{
    /* LSI (~32 kHz) / 64 = 500 counts per second; the reload value is 12 bits. */
    uint32_t reload = timeout_ms * (LSI_VALUE / 64U) / 1000U;
    if (reload == 0U || reload > 0x0FFFU) {
        return -1;
    }
    __HAL_DBGMCU_FREEZE_IWDG1(); /* don't reset while halted in a debugger */
    iwdg.Instance = IWDG1;
    iwdg.Init.Prescaler = IWDG_PRESCALER_64;
    iwdg.Init.Reload = reload;
    iwdg.Init.Window = IWDG_WINDOW_DISABLE;
    if (HAL_IWDG_Init(&iwdg) != HAL_OK) {
        return -2;
    }
    iwdg_running = true;
    return 0;
}

void hw_watchdog_kick(void)
{
    if (iwdg_running) {
        (void)HAL_IWDG_Refresh(&iwdg);
    }
}

const char *hw_reset_cause(void)
{
    /* Order matters: a watchdog reset also pulses NRST, power-on also sets BOR. */
    const char *cause = "unknown";
    if (__HAL_RCC_GET_FLAG(RCC_FLAG_IWDG1RST)) {
        cause = "independent watchdog (IWDG1)";
    } else if (__HAL_RCC_GET_FLAG(RCC_FLAG_WWDG1RST)) {
        cause = "window watchdog (WWDG1)";
    } else if (__HAL_RCC_GET_FLAG(RCC_FLAG_SFTRST)) {
        cause = "software reset";
    } else if (__HAL_RCC_GET_FLAG(RCC_FLAG_PORRST)) {
        cause = "power-on";
    } else if (__HAL_RCC_GET_FLAG(RCC_FLAG_BORRST)) {
        cause = "brown-out";
    } else if (__HAL_RCC_GET_FLAG(RCC_FLAG_PINRST)) {
        cause = "reset pin (NRST)";
    }
    __HAL_RCC_CLEAR_RESET_FLAGS();
    return cause;
}

void hw_route_faults_to_timer_break(void)
{
    __HAL_RCC_SYSCFG_CLK_ENABLE();
    /* Each bit connects a fault signal to the break inputs of TIM1/8/15/16/17.
     * They are write-once: only a reset clears them. */
    SYSCFG->CFGR |= SYSCFG_CFGR_CM7L       /* Cortex-M7 LOCKUP */
                    | SYSCFG_CFGR_FLASHL   /* flash double ECC error */
                    | SYSCFG_CFGR_ITCML | SYSCFG_CFGR_DTCML | SYSCFG_CFGR_AXISRAML
                    | SYSCFG_CFGR_SRAM1L | SYSCFG_CFGR_SRAM2L | SYSCFG_CFGR_SRAM3L
                    | SYSCFG_CFGR_SRAM4L | SYSCFG_CFGR_BKRAML; /* RAM double ECC errors */
}

void hw_panic(const char *reason)
{
    /* PWM off first, then report. TIM1 register writes are harmless if its
     * clock is not enabled yet. */
    TIM1->BDTR &= ~TIM_BDTR_MOE;
    if (gpio_ready) {
        hw_led_set(HW_LED_RED, true);
    }
    static const char prefix[] = "\r\n*** PANIC: ";
    hw_console_write(prefix, sizeof(prefix) - 1U);
    hw_console_write(reason, strlen(reason));
    hw_console_write("\r\n", 2U);
    for (;;) {
        /* Nothing feeds the watchdog any more: IWDG1 resets the chip. */
    }
}
