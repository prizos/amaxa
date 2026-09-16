"""
Gates on the parts library itself.

Nothing checks by machine that a part number matches its footprint, or that
pad 1 is the pin the datasheet calls pin 1. The review note is the record that
someone looked, so these make sure the record exists and stays honest.
"""

import re

import pytest


@pytest.fixture(scope="session")
def part_dirs(board_dir):
    parts = board_dir / "parts"
    return sorted(d for d in parts.iterdir() if d.is_dir())


def test_every_part_library_has_a_review_note(part_dirs):
    """A part nobody wrote up is a part nobody checked."""
    missing = [d.name for d in part_dirs if not (d / f"{d.name}.md").is_file()]
    assert not missing, (
        "Part libraries without a review note:\n"
        + "\n".join(f"  parts/{name}/{name}.md" for name in missing)
        + "\nSee parts/README.md for what one contains."
    )


def test_every_part_library_declares_components(part_dirs):
    """A directory atopile registers as a library but nothing declares from."""
    empty = [d.name for d in part_dirs if not (d / f"{d.name}.ato").is_file()]
    assert not empty, f"Part libraries with no .ato: {empty}"


def test_every_part_library_has_exactly_one_footprint(part_dirs):
    """
    One footprint per library directory.

    atopile takes the library name from the directory, so two footprints in one
    directory are two parts claiming the same library name. Sharing is fine and
    intended — both MOSFETs use the one SOT-23 — but they share the *file*.
    """
    wrong = {
        d.name: sorted(f.name for f in d.glob("*.kicad_mod"))
        for d in part_dirs
        if len(list(d.glob("*.kicad_mod"))) != 1
    }
    assert not wrong, f"Libraries without exactly one footprint: {wrong}"


def test_declared_footprints_exist(part_dirs):
    """
    Every `footprint=` names a file that is actually there.

    atopile resolves these late, in the middle of writing the PCB, and the
    failure names a library rather than the line that was wrong.
    """
    missing = []
    for d in part_dirs:
        source = (d / f"{d.name}.ato").read_text()
        for name in re.findall(r'footprint="([^"]+)"', source):
            if not (d / name).is_file():
                missing.append(f"  parts/{d.name}/{d.name}.ato -> {name}")
    assert not missing, "Footprints named in source but not present:\n" + "\n".join(
        missing
    )


def test_review_notes_name_their_part(part_dirs):
    """
    The note has to name the part number the source actually uses.

    Parts get swapped; notes get left behind. This catches a note that still
    describes the part that was replaced.
    """
    stale = []
    for d in part_dirs:
        source = (d / f"{d.name}.ato").read_text()
        note_path = d / f"{d.name}.md"
        if not note_path.is_file():
            continue  # its own check covers this
        note = note_path.read_text()
        for partno in re.findall(r'partnumber="([^"]+)"', source):
            if partno not in note:
                stale.append(f"  parts/{d.name}/{d.name}.md does not mention {partno}")
    assert not stale, "Review notes out of date with the source:\n" + "\n".join(stale)
