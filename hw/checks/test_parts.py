"""
Gates on the parts library itself.

Nothing checks by machine that a part number matches its footprint, or that
pad 1 is the pin the datasheet calls pin 1. The review note is the record that
someone looked, so these make sure the record exists and stays honest.

Two lists divide the parts whose pinout came from a drawing. `NEEDS_A_HUMAN_EYE`
is what nobody has looked at yet. `CONFIRMED_FROM_A_RENDER` is what somebody
has, and it is only worth more than a memory because the looking left something
behind: the figure itself, cropped out of the manufacturer's document and
committed beside the note, with the document's URL and SHA-256 next to it. A
reviewer re-checks the claim by opening a PNG, and re-checks the *source* by
fetching the same bytes.

`assumes` is the important field. A drawing often settles less than the claim
needs - Diodes' SOT-223 drawings name the leads and never number them - and a
review that cannot say which half it read and which half it inferred is worth
no more than the guess it replaced.

Pin numbering is checked separately, in test_symbols.py.
"""

import json
import re

import pytest


@pytest.fixture(scope="session")
def part_dirs(board_dir):
    libraries = board_dir / "parts"
    return sorted(d for d in libraries.iterdir() if d.is_dir())


def test_every_part_library_has_a_review_note(part_dirs):
    """A part nobody wrote up is a part nobody checked."""
    missing = [d.name for d in part_dirs if not (d / f"{d.name}.md").is_file()]
    assert not missing, (
        "Part libraries without a review note:\n"
        + "\n".join(f"  parts/{name}/{name}.md" for name in missing)
        + "\nSee parts/README.md for what one contains."
    )


def test_every_part_library_has_exactly_one_footprint(part_dirs):
    """
    One footprint per library directory.

    Several parts sharing one is intended — both MOSFETs use the one SOT-23 —
    but they share the *file*.
    """
    wrong = {
        d.name: sorted(f.name for f in d.glob("*.kicad_mod"))
        for d in part_dirs
        if len(list(d.glob("*.kicad_mod"))) != 1
    }
    assert not wrong, f"Libraries without exactly one footprint: {wrong}"


def test_every_footprint_is_used(parts, part_dirs):
    """
    No footprint in the tree that nothing references.

    An orphan is either a part that was removed and left its footprint behind,
    or a footprint nobody wired up — and the second is the expensive one.
    """
    used = {part.footprint for part in parts.values()}
    orphans = []
    for d in part_dirs:
        for mod in d.glob("*.kicad_mod"):
            if f"{d.name}:{mod.stem}" not in used:
                orphans.append(f"  parts/{d.name}/{mod.name}")
    assert not orphans, "Footprints in the tree that no part uses:\n" + "\n".join(orphans)


def test_review_notes_name_their_part(parts, board_dir):
    """
    The note has to name the part number the design actually uses.

    Parts get swapped; notes get left behind. This catches a note still
    describing the part that was replaced.
    """
    stale = []
    for name, part in sorted(parts.items()):
        library = part.footprint.partition(":")[0]
        note = board_dir / "parts" / library / f"{library}.md"
        if not note.is_file():
            continue  # its own check covers this
        if part.mpn not in note.read_text():
            stale.append(f"  parts/{library}/{library}.md does not mention {part.mpn}")
    assert not stale, "Review notes out of date with the design:\n" + "\n".join(stale)


def test_unresolved_human_review_is_tracked(part_dirs, board_config, board_dir):
    """
    The set of things still waiting on a person is exactly what is declared.

    A marker that appears without being added here is one nobody is tracking;
    one that disappears without being removed is a review that quietly stopped
    being required. Both are how a board gets ordered with an unverified pinout.

    The declared list is the board's own `NEEDS_A_HUMAN_EYE`, in
    `<board>/checks/config.py`; clearing it is a precondition for ordering.
    """
    found = {
        d.name
        for d in part_dirs
        if (d / f"{d.name}.md").is_file()
        and "Needs a human eye" in (d / f"{d.name}.md").read_text()
    }
    declared = set(board_config.NEEDS_A_HUMAN_EYE)

    new = sorted(found - declared)
    resolved = sorted(declared - found)
    assert not new and not resolved, (
        "The unresolved-review list does not match the notes.\n"
        f"  marked but not tracked: {new}\n"
        f"  tracked but no longer marked: {resolved}\n"
        f"Update NEEDS_A_HUMAN_EYE in {board_dir.name}/checks/config.py in the same commit."
    )


def test_questions_waiting_on_a_decision_are_tracked_separately(part_dirs, board_config, board_dir):
    """
    A question no document can answer is not an unread datasheet.

    Both are things a person has to do, and filing them together is how the one
    that needs five minutes with a PDF hides behind the one that needs an
    enclosure to exist. `WAITING_ON_A_DECISION` is the second kind, and the
    marker in the note is "Waiting on a decision".
    """
    found = {
        d.name
        for d in part_dirs
        if (d / f"{d.name}.md").is_file()
        and "Waiting on a decision" in (d / f"{d.name}.md").read_text()
    }
    declared = set(getattr(board_config, "WAITING_ON_A_DECISION", {}))
    appeared = sorted(found - declared)
    gone = sorted(declared - found)
    assert not appeared and not gone, (
        "The waiting-on-a-decision list does not match the notes.\n"
        f"  marked but not tracked: {appeared}\n"
        f"  tracked but no longer marked: {gone}\n"
        f"Update WAITING_ON_A_DECISION in {board_dir.name}/checks/config.py."
    )


def test_a_confirmed_review_left_its_evidence_behind(part_dirs, board_config, board_dir):
    """
    Every part moved off the waiting list has the figure it was cleared by.

    `CONFIRMED_FROM_A_RENDER` names, per part library, the claims someone read
    out of the manufacturer's own drawing. This requires that each one still
    has its crop, and that the crop still says where it came from: the
    document, its URL, and the SHA-256 of the bytes that were rendered.

    Without this the two lists are the same thing - a statement that somebody
    once looked - and the only difference between them is which one is shorter.

    **It walks the figures on disk as well as the declared list**, because
    iterating the list alone only checks the claims someone remembered to
    declare. Six crops had accumulated that nothing reached: the two field-bus
    transceivers' common-mode and ESD ratings, the comparator's delay against
    capacitive load, the Schottky's forward and reverse curves, and the
    thermal table the board's declared ambient is derived from. Every one is
    cited by name in `parts.py` and every one could have been deleted, or had
    its digest blanked, with the suite still green.
    """
    declared = getattr(board_config, "CONFIRMED_FROM_A_RENDER", {})
    by_name = {d.name: d for d in part_dirs}

    problems = []
    for directory in sorted(part_dirs, key=lambda d: d.name):
        for figure in sorted((directory / "evidence").glob("*.png")):
            if figure.stem not in declared.get(directory.name, ()):
                problems.append(
                    f"  {directory.name}/{figure.stem}: a figure kept as evidence "
                    f"and not named in CONFIRMED_FROM_A_RENDER, so nothing holds "
                    f"it to its source")

    for library, claims in sorted(declared.items()):
        directory = by_name.get(library)
        if directory is None:
            problems.append(f"  {library}: no such part library")
            continue
        index = directory / "evidence" / "sources.json"
        if not index.is_file():
            problems.append(f"  {library}: no evidence/sources.json")
            continue
        records = json.loads(index.read_text())
        for slug in claims:
            record = records.get(slug)
            if record is None:
                problems.append(f"  {library}/{slug}: not in sources.json")
                continue
            figure = directory / "evidence" / f"{slug}.png"
            if not figure.is_file():
                problems.append(f"  {library}/{slug}: no {figure.name}")
            for field in ("document", "url", "sha256", "page", "shows"):
                if not record.get(field):
                    problems.append(f"  {library}/{slug}: no {field}")
            if len(str(record.get("sha256", ""))) != 64:
                problems.append(f"  {library}/{slug}: sha256 is not a digest")

    assert not problems, (
        "Confirmed reviews without their evidence:\n" + "\n".join(problems)
        + f"\nRegenerate with tools/datasheet.py evidence {board_dir.name} <LIB> <slug> ..."
    )


def test_a_part_is_not_on_both_review_lists(board_config):
    """
    Nothing is both waiting for a person and already confirmed.

    The two lists are a claim about the same part's pinout, so an entry in both
    means one of them was not updated - and the one left behind is always the
    one that says the work is done.
    """
    both = sorted(set(board_config.NEEDS_A_HUMAN_EYE)
                  & set(getattr(board_config, "CONFIRMED_FROM_A_RENDER", {})))
    assert not both, f"On both review lists: {both}"


def test_review_notes_name_a_real_part_constant(parts, part_dirs):
    """
    Each note's Component row names the constants in parts.py, exactly.

    These rows named the previous design source's component types — `Res680`,
    `PFetRpp`, `TvsSmbj12A` — for months after that source was deleted. Twelve
    identifiers that appeared in no source file, in the one row of the note a
    reader uses to find the part they are reading about.
    """
    import re

    by_library: dict[str, set[str]] = {}
    for name, part in parts.items():
        by_library.setdefault(part.footprint.partition(":")[0], set()).add(name)

    wrong = []
    for d in part_dirs:
        note = d / f"{d.name}.md"
        if not note.is_file():
            continue
        row = re.search(r"^\| Component \| (.*?) \|$", note.read_text(), re.M)
        if not row:
            wrong.append(f"  parts/{d.name}/{d.name}.md has no Component row")
            continue
        named = set(re.findall(r"`([^`]+)`", row.group(1)))
        expected = by_library.get(d.name, set())
        if named != expected:
            wrong.append(
                f"  parts/{d.name}/{d.name}.md names {sorted(named)}, "
                f"parts.py has {sorted(expected)}"
            )

    assert not wrong, "Review notes naming parts that do not exist:\n" + "\n".join(wrong)
