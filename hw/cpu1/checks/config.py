"""
What the common checks in hw/checks/ need to know that is specific to cpu1.
"""

# Still being built: some nets wait for blocks not drawn yet (design.json's
# `pending`), and board.mk says ROUTING := incomplete.
COMPLETE = False

# Checks that must actually run for this board, common and board-specific.
EXPECTED_CHECKS = 32

# Parameters recorded in parts.py that nothing reads, each with the reason.
UNREAD_PARAMETERS: dict[tuple[str, str], str] = {}

# Part libraries whose review note still says "Needs a human eye".
NEEDS_A_HUMAN_EYE: dict[str, str] = {}
