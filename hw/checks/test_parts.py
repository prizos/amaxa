"""
Gates on the parts library itself.

Nothing checks by machine that a part number matches its footprint, or that
pad 1 is the pin the datasheet calls pin 1. The review note is the record that
someone looked, so these make sure the record exists and stays honest.

Pin numbering is checked separately, in test_symbols.py.
"""

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
