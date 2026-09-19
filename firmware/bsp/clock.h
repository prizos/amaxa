/*
 * Bringing the core up to 400 MHz, which is a board's job and not an app's.
 *
 * The PLL numbers depend on what the crystal is and how it is connected, and
 * those are properties of the board. The app asks once and gets a return code;
 * everything it needs to know about the failure is in that code, because there
 * is nothing it could do differently.
 */
#ifndef BSP_CLOCK_H
#define BSP_CLOCK_H

/*
 * 0 on success.
 * -1: the supply mode was already locked (a bootloader got there first). The
 *     clocks are still configured; this is a warning, not a failure.
 * -2: the external oscillator or PLL1 did not start. Still running on HSI.
 * -3: the core could not be switched to the PLL.
 */
int board_init_clocks(void);

#endif /* BSP_CLOCK_H */
