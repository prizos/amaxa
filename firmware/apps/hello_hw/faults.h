/*
 * Fault handling and a deliberate core-lockup test.
 */
#ifndef FAULTS_H
#define FAULTS_H

/* Faults inside HardFault to put the Cortex-M7 into LOCKUP. With
 * hw_route_faults_to_timer_break() applied, LOCKUP breaks TIM1 in hardware
 * and the independent watchdog then resets the chip. Does not return. */
void faults_trigger_lockup(void);

#endif /* FAULTS_H */
