"""
The guard on the guards.

Checks get deleted, renamed, or quietly skipped, and a suite that runs nothing
passes. This fails when the number of checks changes, so removing one has to be
a deliberate, reviewable act rather than a silent one.

When you add or remove a check, update EXPECTED_CHECKS below in the same commit
as the change, and the diff will say so.
"""

EXPECTED_CHECKS = 25


def test_expected_number_of_checks_ran(collected_check_count):
    assert collected_check_count == EXPECTED_CHECKS, (
        f"{collected_check_count} checks collected, expected {EXPECTED_CHECKS}. "
        "If this is intended, update EXPECTED_CHECKS in checks/test_check_count.py "
        "in the same commit as the check you added or removed."
    )
