#!/usr/bin/env python3
"""
Assert what the firmware does when it runs, not just that it links.

CI built both board support packages and stopped there. Everything this
project's hardware rests on - "an unprogrammed board is inert", the trip
latch, the buffers - is firmware behaviour, and nothing checked any of it
while the board next door carried 188 derived checks.

This reads the console of a Renode run and holds it to what the safety
story claims. It is a smoke test, not a proof: the emulator models the
STM32 and not the board around it, so what it can see is the firmware's own
state - the timer it configured, whether it is driving, and what it thinks
the break input is doing.

**An emulator's silence is not agreement.** The first version of this file
asserted that the outputs were off by reading `pwm OFF` off the status line,
which the firmware derives from `TIM1->BDTR & TIM_BDTR_MOE`. Renode does not
implement BDTR: it reads back zero whatever is written to it, so that
assertion printed OFF for firmware that had armed the bridge, and could not
have failed for any firmware at all. Everything below that rests on a
register now says which register, and checks the register is there first -
the banner prints BDTR as it reads back, and the dead-time the firmware
programmed into it is the witness. Nothing is asserted from a register that
reads back as though it were not implemented.

    python3 tools/sim_check.py <console.log> <board>
"""

import re
import sys
from pathlib import Path

# Return codes the banner reports that this emulator produces on firmware
# that is correct, with the reason. Same discipline as the hardware side's
# BLOCKING: a failure the run cannot avoid is declared and explained, never
# left to pass by not being looked at. Anything not named here must be zero.
EMULATED: dict[str, str] = {
    "clocks": (
        "-1: the supply configuration (PWR_CR3) reads back as already locked. "
        "Renode's H7 PWR model does not implement the LDO/SMPS selection, so "
        "HAL_PWREx_ConfigSupply refuses it. The PLL setup after it succeeds, "
        "which is what the 400 MHz on the same line reports."
    ),
    "adc": (
        "-2: HAL_ADC_Init fails. Renode's H7 ADC model does not implement "
        "ADC3's boost/calibration registers, so nothing downstream of it runs "
        "- which is where the status line's 'adc error -10' comes from too."
    ),
}

# TIM1_BDTR field positions, from RM0433 section 43.4.18.
BDTR_DTG = 0xFF
BDTR_MOE = 1 << 15


def main() -> int:
    if len(sys.argv) != 3:
        sys.exit(f"usage: {Path(sys.argv[0]).name} <console.log> <board>")
    text = Path(sys.argv[1]).read_text()
    board = sys.argv[2]
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]

    problems = []
    # Properties this run could not see, with the reason. They are printed
    # on a passing run too: a check that quietly drops what it cannot test
    # is how the MOE assertion came to look like coverage for two commits.
    unverified = []

    def want(what: str, pattern: str) -> re.Match | None:
        found = next((re.search(pattern, line) for line in lines
                      if re.search(pattern, line)), None)
        if not found:
            problems.append(f"  {what}: nothing matched /{pattern}/")
        return found

    # It booted far enough to configure the thing the whole board is for.
    timer = want("the PWM banner",
                 r"pwm\s+TIM1 3-phase (\d+) Hz .*timer (\d+) MHz, ARR (\d+), "
                 r"dead-time (\d+) ns \(DTG 0x([0-9a-f]+)\)")
    if timer:
        frequency, clock, reload = (int(timer.group(n)) for n in (1, 2, 3))
        dead_time, dtg = int(timer.group(4)), int(timer.group(5), 16)
        # The Hz on that line is a compile-time #define printed back. What the
        # timer will actually do is the other three numbers, so derive it and
        # hold the claim to the arithmetic: centre-aligned counts up and down,
        # so a period is two ARR.
        derived = clock * 1_000_000 / (2 * reload)
        if abs(derived - frequency) > 1:
            problems.append(
                f"  the banner says {frequency} Hz but a {clock} MHz timer with "
                f"ARR {reload} centre-aligned switches at {derived:.0f} Hz")
        if dead_time <= 0:
            problems.append(f"  dead-time {dead_time} ns: a bridge needs one")

        # Is BDTR actually there? The dead-time is the witness: the firmware
        # wrote DTG and printed both what it wrote and what came back. If they
        # agree the register is implemented and the MOE bit beside them means
        # something; if BDTR reads back without the dead-time in it, every
        # claim drawn from that register is worthless and this says so rather
        # than reporting the zeros as good news.
        register = want("the BDTR readback", r"BDTR 0x([0-9a-f]{8})")
        if register:
            bdtr = int(register.group(1), 16)
            if bdtr == 0 and dtg != 0:
                # Renode 1.17.0 has no BDTR anywhere in it: every write is
                # dropped and every read returns zero. Say so and drop the
                # claims that rest on it, rather than reporting the zeros as
                # "the outputs are off". This branch is itself falsifiable -
                # the day the register gains a model the readback stops being
                # zero, this stops matching, and the real assertion below
                # takes over.
                unverified.append(
                    "MOE: BDTR reads back as all zeros with DTG 0x%02x written to "
                    "it, which is this emulator having no model for the register. "
                    "Whether the bridge is armed cannot be seen from here, so the "
                    "status line's pwm ON/OFF was not used." % dtg)
            elif bdtr & BDTR_DTG != dtg:
                problems.append(
                    f"  BDTR reads back 0x{bdtr:08x}, with DTG 0x{bdtr & BDTR_DTG:02x} "
                    f"where the firmware wrote 0x{dtg:02x}: the register is modelled "
                    f"but did not take the dead-time.")
            elif bdtr & BDTR_MOE:
                problems.append(
                    f"  BDTR 0x{bdtr:08x} has MOE set when pwm_init returned: the "
                    f"bridge is armed before anything commanded it.")

    # Every return code the banner reports. A firmware that fails to start
    # half of itself and says so in a line nobody reads is not a passing run.
    for line in lines:
        found = re.match(r"\s{2}(\w+)\s+(.*?)\((-?\d+)\)\s*$", line)
        if not found:
            continue
        block, code = found.group(1), int(found.group(3))
        if code == 0:
            continue
        if block not in EMULATED:
            problems.append(f"  {block} reported {code} and nothing says why:\n      {line}")
        elif not EMULATED[block].startswith(f"{code}:"):
            problems.append(
                f"  {block} reported {code}; the declared emulator limitation is "
                f"{EMULATED[block].split(':')[0]}:\n      {line}")

    # And it reported its state at least twice, so the loop is running.
    reports = [line for line in lines if re.search(r"\bpwm (ON|OFF)\b", line)]
    if len(reports) < 2:
        problems.append(f"  only {len(reports)} status reports: the main loop is not running")

    # Where the register is modelled, the status line's own claim has to agree
    # with it. Where it is not, this says nothing - the line is reporting a
    # register read that returns zero regardless.
    if not unverified:
        driving = [line for line in reports if re.search(r"\bpwm ON\b", line)]
        if driving:
            problems.append(
                f"  the outputs are driving without being commanded to:\n"
                f"      {driving[0]}")

    # The break input is where its pull-up puts it, so a real break would be
    # a change rather than the state it booted in. This one is a GPIO, which
    # the platform description does model and the reset macro does drive.
    if reports and "bkin idle" not in reports[-1]:
        problems.append(f"  the break input is not idle at rest:\n      {reports[-1]}")

    for line in lines:
        if re.search(r"error executing|Exception|\[ERROR\]", line):
            problems.append(f"  the emulator reported: {line}")

    if problems:
        print(f"{board}: the firmware ran and did not behave:\n" + "\n".join(problems))
        return 1
    print(f"{board}: booted, configured TIM1 at the frequency its own ARR implies, "
          f"reported {len(reports)} times, break input idle")
    for note in unverified:
        print(f"  not verified here - {note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
