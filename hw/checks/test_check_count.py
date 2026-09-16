"""
The guards on the guards.

Two ways a suite quietly stops checking things.

A check gets deleted, renamed, or skipped, and a suite that runs nothing still
passes — so the number of checks is asserted, and removing one has to be a
deliberate, reviewable act rather than a silent one.

And a claim gets written into the design that nothing ever reads. That is the
worse of the two, because it does not look like an absence: `design.json` says
the 3.3 V rail is 3.234 to 3.366 V, a reviewer sees a number with a tolerance
on it, and there is no gate behind it at all. It is the same failure the design
source before this one had — an `assert` that parsed, resolved, and did
nothing — and it does not stop being that failure because we own the schema now.

When you add or remove a check, update EXPECTED_CHECKS below in the same commit
as the change, and the diff will say so.
"""

from pathlib import Path

EXPECTED_CHECKS = 33

HERE = Path(__file__).resolve().parent


def test_expected_number_of_checks_ran(collected_check_count):
    assert collected_check_count == EXPECTED_CHECKS, (
        f"{collected_check_count} checks collected, expected {EXPECTED_CHECKS}. "
        "If this is intended, update EXPECTED_CHECKS in checks/test_check_count.py "
        "in the same commit as the check you added or removed."
    )


def test_every_design_intent_is_read_by_something(design, board_dir):
    """
    Every value in the design that is not a part parameter is consumed.

    Part parameters come from a datasheet and are worth recording whether or not
    a check happens to use one today. Design *intent* is different: it is a
    promise the board makes, it was written down in order to be enforced, and
    one nobody reads is indistinguishable from one that passes.

    Intent is identified structurally rather than from a list, so a new one
    cannot be added without this noticing: a value whose owner is not a part.
    """
    parts = set(design["parts"])
    intent = sorted(
        key for key in design["values"] if key.rsplit(".", 1)[0] not in parts
    )
    assert intent, (
        "No design intent found at all. Either the design stopped declaring any, "
        "or design.json changed shape and this check is now looking at nothing."
    )

    readers = [p for p in HERE.glob("*.py") if p.name != Path(__file__).name]
    readers += sorted((board_dir / "sim").glob("*.cir.in"))
    corpus = "\n".join(p.read_text() for p in readers)

    def is_read(key: str) -> bool:
        owner, _, name = key.rpartition(".")
        # Decks name the whole path (`@rail.power_out.voltage:min@`); checks
        # split it across the two arguments of the `spec` fixture.
        return key in corpus or f'"{owner}", "{name}"' in corpus

    orphaned = [key for key in intent if not is_read(key)]
    assert not orphaned, (
        "Design intent that nothing reads:\n"
        + "\n".join(f"  {key}" for key in orphaned)
        + "\nA promise with no gate behind it is not a promise. Either check it "
        "in checks/, measure it in a sim deck, or delete it from the design."
    )
