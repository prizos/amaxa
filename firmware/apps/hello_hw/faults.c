#include "faults.h"

#include <stdbool.h>

#include "hw.h"

static volatile bool lockup_requested;

/* Executes an undefined instruction (UDF). UsageFault is not enabled, so
 * this escalates to HardFault. */
static void undefined_instruction(void)
{
    __builtin_trap();
}

void faults_trigger_lockup(void)
{
    lockup_requested = true;
    undefined_instruction();
}

void HardFault_Handler(void)
{
    if (lockup_requested) {
        /* A second fault while in HardFault locks up the core. */
        undefined_instruction();
    }
    hw_panic("HardFault");
}
