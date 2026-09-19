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

The numbers and exemption lists are each board's own, in
`<board>/checks/config.py`. Update them in the same commit as the change that
makes it necessary, and the diff will say so.
"""

from pathlib import Path

HERE = Path(__file__).resolve().parent


def test_expected_number_of_checks_ran(collected_check_count, board_config, board_dir):
    expected = board_config.EXPECTED_CHECKS
    assert collected_check_count == expected, (
        f"{collected_check_count} checks will run, expected {expected}. "
        f"If this is intended, update EXPECTED_CHECKS in {board_dir.name}/checks/config.py "
        "in the same commit as the check you added, removed or skipped."
    )


def test_every_design_intent_is_read_by_something(design, board_dir, parameters_read):
    """
    Every value in the design that is not a part parameter is consumed.

    Part parameters come from a datasheet and are worth recording whether or not
    a check happens to use one today. Design *intent* is different: it is a
    promise the board makes, it was written down in order to be enforced, and
    one nobody reads is indistinguishable from one that passes.

    Intent is identified structurally rather than from a list, so a new one
    cannot be added without this noticing: a value whose owner is not a part.

    Like the parameter guard below, it runs last and counts what the other
    checks actually looked up, as well as what the decks name: a check that
    reads `spec(oscillator, "stray_capacitance")` for two oscillators names
    neither in its text.
    """
    parts = set(design["parts"])
    intent = sorted(
        key for key in design["values"] if key.rsplit(".", 1)[0] not in parts
    )
    assert intent, (
        "No design intent found at all. Either the design stopped declaring any, "
        "or design.json changed shape and this check is now looking at nothing."
    )

    # Only the simulation decks are matched as text, because a deck names the
    # whole path in one token (`@rail.power_out.voltage:min@`) and there is no
    # lookup to record. Checks are matched by `parameters_read`, which is the
    # record of what `spec` actually handed out while the suite ran.
    #
    # This used to search the check files as text too. That made any mention
    # of a key count as a reader - including one inside a comment saying the
    # key was *not* checked yet, which is the exact opposite of what this
    # asserts, and which a mutation test walked straight through.
    decks = "\n".join(p.read_text() for p in sorted((board_dir / "sim").glob("*.cir.in")))

    def is_read(key: str) -> bool:
        owner, _, name = key.rpartition(".")
        return key in decks or (owner, name) in parameters_read

    orphaned = [key for key in intent if not is_read(key)]
    assert not orphaned, (
        "Design intent that nothing reads:\n"
        + "\n".join(f"  {key}" for key in orphaned)
        + "\nA promise with no gate behind it is not a promise. Either check it "
        "in checks/, measure it in a sim deck, or delete it from the design."
    )


def test_every_declared_parameter_is_read(design, board_dir, board_config, parameters_read):
    """
    Every datasheet figure in the design is consumed by a check or a deck.

    This runs last, because it asserts on what all the other checks looked up.

    The sibling check above covers design *intent*. This covers the other forty
    numbers: the ratings and tolerances copied out of datasheets into parts.py.
    They are the ones that look most like verification and are easiest to leave
    inert — a capacitor's voltage rating sitting in the design, next to a check
    that never asks for it, reads exactly like a capacitor whose voltage rating
    has been checked.

    It was worth writing: when it was first run, the bulk capacitance could be
    changed from 47 uF to 100 pF, both FETs' current ratings to 1 mA and the
    LED's to 1 mA, and every gate stayed green.
    """
    parts = set(design["parts"])
    declared = {
        (owner, name)
        for owner, _, name in (key.rpartition(".") for key in design["values"])
        if owner in parts
    }

    # Decks name parameters literally, as `@path:end@`, with no indirection to
    # resolve, so reading them textually is exact here in a way it is not for
    # the checks.
    decks = "\n".join(p.read_text() for p in sorted((board_dir / "sim").glob("*.cir.in")))
    read_by_a_deck = {
        (owner, name)
        for owner, name in declared
        if f"@{owner}.{name}:" in decks
    }

    exempt = board_config.UNREAD_PARAMETERS
    unread = sorted(declared - parameters_read - read_by_a_deck - set(exempt))
    assert not unread, (
        "Parameters declared in parts.py that nothing reads:\n"
        + "\n".join(f"  {owner}.{name}" for owner, name in unread)
        + "\nCheck one against something, measure it in a deck, or add it to "
        "UNREAD_PARAMETERS in <board>/checks/config.py with the reason it does not need to be. "
        "A rating nothing compares against is a comment with a float in it."
    )

    stale = sorted(set(exempt) - declared)
    assert not stale, (
        "UNREAD_PARAMETERS excuses parameters the design no longer declares:\n"
        + "\n".join(f"  {owner}.{name}" for owner, name in stale)
        + "\nRemove them, so the exemption list cannot outlive its reasons."
    )

    now_read = sorted((parameters_read | read_by_a_deck) & set(exempt))
    assert not now_read, (
        "UNREAD_PARAMETERS excuses parameters that something now reads:\n"
        + "\n".join(f"  {owner}.{name}" for owner, name in now_read)
        + "\nRemove them. An exemption nobody revisits is how the list grows "
        "until it excuses everything."
    )
