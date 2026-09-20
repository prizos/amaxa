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

    python3 tools/sim_check.py <console.log> <board>
"""

import re
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 3:
        sys.exit(f"usage: {Path(sys.argv[0]).name} <console.log> <board>")
    text = Path(sys.argv[1]).read_text()
    board = sys.argv[2]
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]

    problems = []

    def want(what: str, pattern: str) -> re.Match | None:
        found = next((re.search(pattern, line) for line in lines
                      if re.search(pattern, line)), None)
        if not found:
            problems.append(f"  {what}: nothing matched /{pattern}/")
        return found

    # It booted far enough to configure the thing the whole board is for.
    timer = want("the PWM banner", r"pwm\s+TIM1 3-phase (\d+) Hz .*dead-time (\d+) ns")
    if timer:
        frequency, dead_time = int(timer.group(1)), int(timer.group(2))
        if not 1_000 <= frequency <= 100_000:
            problems.append(f"  PWM at {frequency} Hz, which is not a motor drive")
        if dead_time <= 0:
            problems.append(f"  dead-time {dead_time} ns: a bridge needs one")

    # And it reported its state at least twice, so the loop is running.
    reports = [line for line in lines if re.search(r"\bpwm (ON|OFF)\b", line)]
    if len(reports) < 2:
        problems.append(f"  only {len(reports)} status reports: the main loop is not running")

    # The property the hardware is designed around: nothing drives until
    # something deliberately asks it to. Re-arming is not asking.
    driving = [line for line in reports if re.search(r"\bpwm ON\b", line)]
    if driving:
        problems.append(
            f"  the outputs are driving without being commanded to:\n"
            f"      {driving[0]}"
        )

    # The break input is where its pull-up puts it, so a real break would be
    # a change rather than the state it booted in.
    if reports and "bkin idle" not in reports[-1]:
        problems.append(f"  the break input is not idle at rest:\n      {reports[-1]}")

    for line in lines:
        if re.search(r"error executing|Exception|\[ERROR\]", line):
            problems.append(f"  the emulator reported: {line}")

    if problems:
        print(f"{board}: the firmware ran and did not behave:\n" + "\n".join(problems))
        return 1
    print(f"{board}: booted, configured TIM1, reported {len(reports)} times, "
          f"never drove an output unasked, break input idle")
    return 0


if __name__ == "__main__":
    sys.exit(main())
