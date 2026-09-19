/*
 * amaxa cpu1 clock tree: an 8 MHz crystal on PH0/PH1, so the oscillator is
 * started rather than driven - RCC_HSE_ON. Everything downstream of it is
 * the NUCLEO's, deliberately: the firmware's timing was measured against
 * those numbers and this board was chosen to keep them.
 */
#include "clock.h"

#include "stm32h7xx_hal.h"

int board_init_clocks(void)
{
    int rc = 0;

    /* The H743 has no SMPS. The supply mode is written once after reset,
     * before the voltage scaling can be changed. An error here means it was
     * already locked (e.g. by a bootloader); like ST's generated code, carry on. */
    if (HAL_PWREx_ConfigSupply(PWR_LDO_SUPPLY) != HAL_OK) {
        rc = -1;
    }
    __HAL_PWR_VOLTAGESCALING_CONFIG(PWR_REGULATOR_VOLTAGE_SCALE1);
    while (!__HAL_PWR_GET_FLAG(PWR_FLAG_VOSRDY)) {
    }

    /* HSE 8 MHz crystal / M4 = 2 MHz; x N400 = 800 MHz VCO; / P2 = 400 MHz. */
    RCC_OscInitTypeDef osc = {
        .OscillatorType = RCC_OSCILLATORTYPE_HSE,
        .HSEState = RCC_HSE_ON,
        .PLL = {
            .PLLState = RCC_PLL_ON,
            .PLLSource = RCC_PLLSOURCE_HSE,
            .PLLM = 4,
            .PLLN = 400,
            .PLLP = 2,
            .PLLQ = 8,
            .PLLR = 2,
            .PLLRGE = RCC_PLL1VCIRANGE_1,
            .PLLVCOSEL = RCC_PLL1VCOWIDE,
            .PLLFRACN = 0,
        },
    };
    if (HAL_RCC_OscConfig(&osc) != HAL_OK) {
        return -2; /* the crystal or PLL1 did not start: still on HSI */
    }

    RCC_ClkInitTypeDef clk = {
        .ClockType = RCC_CLOCKTYPE_SYSCLK | RCC_CLOCKTYPE_HCLK | RCC_CLOCKTYPE_D1PCLK1 |
                     RCC_CLOCKTYPE_PCLK1 | RCC_CLOCKTYPE_PCLK2 | RCC_CLOCKTYPE_D3PCLK1,
        .SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK,
        .SYSCLKDivider = RCC_SYSCLK_DIV1, /* 400 MHz core */
        .AHBCLKDivider = RCC_HCLK_DIV2,   /* 200 MHz AHB/AXI */
        .APB3CLKDivider = RCC_APB3_DIV2,
        .APB1CLKDivider = RCC_APB1_DIV2,
        .APB2CLKDivider = RCC_APB2_DIV2, /* 100 MHz; TIM1 then runs at 200 MHz */
        .APB4CLKDivider = RCC_APB4_DIV2,
    };
    if (HAL_RCC_ClockConfig(&clk, FLASH_LATENCY_3) != HAL_OK) {
        return -3;
    }
    return rc;
}
