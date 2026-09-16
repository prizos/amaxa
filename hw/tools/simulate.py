#!/usr/bin/env python3
"""
Run the ngspice decks for a board and check their measurements.

The decks do not restate the design. Where a deck needs a component value it
writes `@power.out.voltage:max@` — an atopile instance path and which end of its
range to take — and this fills it in from the variable report the build
produced. Change a resistor in the source and the simulation changes with it;
there is no second copy of the design to fall out of step.

What the results are checked against lives in sim/limits.py, as bands with a
sentence saying why each one is where it is.

    python3 tools/simulate.py led12            # every deck
    python3 tools/simulate.py led12 led_branch # just one

Exits 1 if a measurement lands outside its band, or if a deck names a parameter
the design does not have.
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

HW_DIR = Path(__file__).resolve().parent.parent
PLACEHOLDER = re.compile(r"@([A-Za-z0-9_.\[\]]+):(nom|min|max)([-+][\d.]+)?@")
MEASUREMENT = re.compile(r"^\s*([a-z_][a-z0-9_]*)\s*=\s*([-\d.eE+]+)", re.MULTILINE)

def design_values(board: Path) -> dict[str, tuple[float, float]]:
    """Every value the design states, as (low, high) in SI units."""
    report = board / "build" / "design.json"
    if not report.is_file():
        sys.exit(f"no design at {report}. Run `make -C hw build` first.")
    values = json.loads(report.read_text())["values"]
    return {key: (float(low), float(high)) for key, (low, high) in values.items()}


def render(template: str, values: dict[str, tuple[float, float]], name: str) -> str:
    """Substitute every @path:end@ with the number the design resolved."""
    missing = []

    def substitute(match: re.Match) -> str:
        path, end, adjust = match.group(1), match.group(2), match.group(3)
        if path not in values:
            missing.append(f"  {path} ({end})")
            return match.group(0)
        low, high = values[path]
        value = {"min": low, "max": high, "nom": (low + high) / 2}[end]
        # A trailing +0.2 or -0.2 nudges the value, for sweeping a little past
        # the range rather than stopping exactly on it.
        return repr(value + float(adjust) if adjust else value)

    rendered = PLACEHOLDER.sub(substitute, template)
    if missing:
        sys.exit(
            f"{name} asks for parameters the design does not resolve:\n"
            + "\n".join(missing)
            + "\nEither the path is wrong, or the part never asserts that value."
        )
    return rendered


def run(deck: Path) -> dict[str, float]:
    """Run one deck and return every .meas result it printed."""
    result = subprocess.run(
        ["ngspice", "-b", str(deck)],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=deck.parent,
    )
    output = result.stdout + result.stderr

    fatal = [
        line
        for line in output.splitlines()
        if re.search(r"\berror\b", line, re.I) and "no error" not in line.lower()
    ]
    if fatal:
        print(f"\n{deck.name}: ngspice reported a problem")
        for line in fatal[:10]:
            print(f"    {line.strip()}")
        return {}

    # `tmp_` names are intermediate quantities a deck needs in order to compute
    # a real one - a node voltage that only exists to be subtracted from
    # another. They are not results and are not checked.
    return {
        name: float(value)
        for name, value in MEASUREMENT.findall(output)
        if not name.startswith("tmp_")
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("board", help="board directory under hw/, e.g. led12")
    parser.add_argument("decks", nargs="*", help="deck names; default is all of them")
    args = parser.parse_args()

    board = HW_DIR / args.board
    sim_dir = board / "sim"
    if not sim_dir.is_dir():
        sys.exit(f"no simulation decks at {sim_dir}")

    sys.path.insert(0, str(sim_dir))
    try:
        limits = __import__("limits").LIMITS
    except ModuleNotFoundError:
        sys.exit(f"no limits at {sim_dir / 'limits.py'}")

    values = design_values(board)
    work = sim_dir / ".run"
    work.mkdir(exist_ok=True)

    templates = sorted(sim_dir.glob("*.cir.in"))
    if args.decks:
        wanted = set(args.decks)
        templates = [t for t in templates if t.name.removesuffix(".cir.in") in wanted]
        if not templates:
            sys.exit(f"no deck matching {sorted(wanted)}")

    failures = []
    rows = []
    for template in templates:
        name = template.name.removesuffix(".cir.in")
        deck = work / f"{name}.cir"
        deck.write_text(render(template.read_text(), values, template.name))

        results = run(deck)
        if not results:
            failures.append(f"{name}: produced no measurements")
            continue

        expected = limits.get(name)
        if expected is None:
            failures.append(f"{name}: no limits written for this deck")
            continue

        unchecked = set(results) - set(expected)
        for measurement, (low, high, why) in sorted(expected.items()):
            if measurement not in results:
                failures.append(f"{name}.{measurement}: the deck did not measure it")
                continue
            value = results[measurement]
            ok = low <= value <= high
            rows.append((name, measurement, value, low, high, ok))
            if not ok:
                failures.append(
                    f"{name}.{measurement} = {value:.6g}, outside "
                    f"{low:.6g} to {high:.6g}\n      {why}"
                )
        for measurement in sorted(unchecked):
            failures.append(
                f"{name}.{measurement} is measured but has no limit. "
                "A measurement nobody checks is decoration."
            )

    width = max((len(f"{n}.{m}") for n, m, *_ in rows), default=20)
    print(f"\n{'measurement'.ljust(width)}  {'value':>12}  {'band':>26}")
    for name, measurement, value, low, high, ok in rows:
        mark = "ok " if ok else "OUT"
        print(
            f"{mark} {f'{name}.{measurement}'.ljust(width - 4)}  {value:12.6g}  "
            f"{low:12.6g} to {high:<12.6g}"
        )

    if failures:
        print("\nSimulation checks failed:")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print(f"\n{len(rows)} measurements, all within their bands.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
