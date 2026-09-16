#!/usr/bin/env python3
"""
Fail if a rebuild changed the committed board in any way that matters.

The point of this gate is that the committed KiCad files are what the .ato
source actually produces. Run a build, then run this: if the board moved, the
commit is stale and the diff says how.

KiCad object UUIDs are ignored. atopile regenerates the board outline's
Edge.Cuts graphics with fresh UUIDs on every build, so comparing raw bytes
reports drift on a board nobody touched. UUIDs are identity for KiCad's own
UI and carry no design meaning: no net, footprint, position or value depends
on them.

    python3 tools/check_drift.py hw/led12/elec/layout/default/default.kicad_pcb
    python3 tools/check_drift.py --all        # every tracked file under hw/

Exit status is 0 when nothing drifted, 1 when something did, 2 on a usage or
git error.
"""

import argparse
import difflib
import re
import subprocess
import sys
from pathlib import Path

UUID_LINE = re.compile(r'\(uuid "[0-9a-fA-F-]{36}"\)')


def canonical(text: str) -> list[str]:
    """The file with UUID values masked, as lines, for comparison."""
    return [UUID_LINE.sub('(uuid "<masked>")', line) for line in text.splitlines()]


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], capture_output=True, text=True, cwd=REPO_ROOT
    )


def committed(path: Path) -> str | None:
    """The file's content at HEAD, or None if it is not tracked there."""
    rel = path.relative_to(REPO_ROOT).as_posix()
    result = git("show", f"HEAD:{rel}")
    return result.stdout if result.returncode == 0 else None


# Only what a build writes. Hand-edited sources under hw/ are not drift: they
# are the thing drift is measured against. Filtered here rather than with a git
# pathspec, because `*` in a pathspec does not cross a directory separator.
GENERATED_DIR = "/elec/"


def changed_files() -> list[Path]:
    result = git("diff", "--name-only", "HEAD", "--", "hw/")
    if result.returncode != 0:
        sys.exit(f"git diff failed: {result.stderr.strip()}")
    return [
        REPO_ROOT / line
        for line in result.stdout.split()
        if line and GENERATED_DIR in line
    ]


def check(path: Path) -> bool:
    """True when the file matches its committed form. Prints a diff if not."""
    before = committed(path)
    if before is None:
        print(f"DRIFT  {path}: generated but never committed")
        return False

    after = path.read_text() if path.is_file() else ""
    if not after:
        print(f"DRIFT  {path}: committed but no longer generated")
        return False

    old, new = canonical(before), canonical(after)
    if old == new:
        return True

    print(f"DRIFT  {path}")
    diff = difflib.unified_diff(old, new, "committed", "rebuilt", lineterm="", n=2)
    for i, line in enumerate(diff):
        if i > 60:
            print("  ... diff truncated")
            break
        print(f"  {line}")
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument(
        "--all",
        action="store_true",
        help="check every tracked file under hw/ that a rebuild changed",
    )
    args = parser.parse_args()

    if args.all:
        paths = changed_files()
        if not paths:
            print("No tracked file under hw/ changed. Board is up to date.")
            return 0
    elif args.paths:
        paths = [p.resolve() for p in args.paths]
    else:
        parser.error("give one or more paths, or --all")

    ok = all([check(p) for p in paths])
    if ok:
        print(f"Up to date: {len(paths)} file(s) match their committed form.")
        return 0

    print(
        "\nThe committed board no longer matches its source. "
        "Rebuild and commit the result:\n"
        "    make -C hw build && git add hw && git commit"
    )
    return 1


if __name__ == "__main__":
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True
    )
    if result.returncode != 0:
        sys.exit("not inside a git repository")
    REPO_ROOT = Path(result.stdout.strip())
    sys.exit(main())
