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

from conftest import PARAMETERS_READ

EXPECTED_CHECKS = 44

HERE = Path(__file__).resolve().parent

# Parameters recorded in parts.py that no check and no deck consumes, each with
# the reason it is not a hole. A datasheet figure worth writing down is usually
# worth checking; where it genuinely is not, the reason belongs here rather than
# in nobody's head.
#
# Everything not named here must be read by something. That rule is what makes
# the entries below cost something to add, which is the point — the alternative
# is forty numbers that look like constraints and constrain nothing.
UNREAD_PARAMETERS = {
    ("power.q_rpp", "on_resistance"): (
        "the pass element's drop is under a millivolt at this board's 55 mA, so "
        "no margin depends on it. Recorded because a higher-current board would "
        "care, and the part would be chosen on it"
    ),
    ("power.q_rpp", "max_continuous_drain_current"): (
        "checked by hand at 4.3 A against a 1 A fuse: the fuse is the binding "
        "constraint and test_fuse_headroom covers that end"
    ),
    ("switch.q_switch", "max_continuous_drain_current"): (
        "115 mA against a measured 20 mA of LED current. The LED current is "
        "checked directly, twice, so this would restate it"
    ),
    ("power.tvs", "v_breakdown_max"): (
        "the two figures that bound the design are the stand-off voltage and "
        "the clamping voltage, and both are checked. Breakdown sits between "
        "them and constrains nothing on its own"
    ),
    ("power.c_hf", "capacitance"): (
        "decoupling, sized by convention rather than by a calculation this "
        "board makes. Its placement is checked instead, which is the property "
        "that actually matters for a 100 nF part"
    ),
    ("power.c_bulk", "capacitance"): (
        "the declared band is manufacturing tolerance only, and the number that "
        "would matter is the effective capacitance under DC bias — an X5R 1210 "
        "delivers roughly half its marked value at 12 V. Checking 47 uF +/-20% "
        "against anything would be checking a figure the part does not have on "
        "this rail. Recorded in parts/C1210/C1210.md, not modelled anywhere"
    ),
}


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


def test_every_declared_parameter_is_read(design, board_dir):
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

    unread = sorted(declared - PARAMETERS_READ - read_by_a_deck - set(UNREAD_PARAMETERS))
    assert not unread, (
        "Parameters declared in parts.py that nothing reads:\n"
        + "\n".join(f"  {owner}.{name}" for owner, name in unread)
        + "\nCheck one against something, measure it in a deck, or add it to "
        "UNREAD_PARAMETERS in this file with the reason it does not need to be. "
        "A rating nothing compares against is a comment with a float in it."
    )

    stale = sorted(set(UNREAD_PARAMETERS) - declared)
    assert not stale, (
        "UNREAD_PARAMETERS excuses parameters the design no longer declares:\n"
        + "\n".join(f"  {owner}.{name}" for owner, name in stale)
        + "\nRemove them, so the exemption list cannot outlive its reasons."
    )

    now_read = sorted((PARAMETERS_READ | read_by_a_deck) & set(UNREAD_PARAMETERS))
    assert not now_read, (
        "UNREAD_PARAMETERS excuses parameters that something now reads:\n"
        + "\n".join(f"  {owner}.{name}" for owner, name in now_read)
        + "\nRemove them. An exemption nobody revisits is how the list grows "
        "until it excuses everything."
    )
