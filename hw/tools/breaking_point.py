#!/usr/bin/env python3
"""
For every figure a datasheet declined to bound, find where the board breaks.

Seven figures on cpu1 are typicals with no maximum, or maxima stated at one
temperature. The board multiplies each by `loads.unguaranteed_margin` - a
quarter - or, where the part's own table says worse, by
`typical_to_maximum_worst`. Both are stand-ins for a number the manufacturer
declined to give, and the review has called them "a measurement on the first
assembled board" since they were written.

**That framing was too narrow, and this tool is the reason.** A bench tells
you what one part does. What nobody had asked is the question that does not
need a bench: *how far can this figure travel before something on this board
actually stops working?* That is arithmetic over the checks that already
exist, and it turns "we added 25 % and hoped" into a ratio.

So: take each unguaranteed figure, scale it, and run the checks that read it.
Double until something fails, then bisect. What comes out is the multiplier
at which the board's own claims stop holding, printed beside the multiplier
the board currently assumes.

    hw/tools/breaking_point.py cpu1

Read the **ratio** column. A figure that survives to eight times its typical
is not worth measuring; one that breaks at 1.4 is the next thing to put on a
bench, and one that breaks below what the board already assumes is a defect
that the assumption is hiding.

**What this cannot do.** It does not bound the figure - no solver invents a
distribution a vendor withheld. It prices the exposure, which is a different
and cheaper thing, and it is the half that was being skipped.
"""

import argparse
import atexit
import json
import pathlib
import signal
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
HW = HERE.parent

sys.path.insert(0, str(HERE))
from mutate import PLUGIN, _noticed, _run  # noqa: E402

# The two naming conventions that mark a figure as not guaranteed over this
# board's conditions. They are the same ones `test_power.py` applies the
# margin by, and they are deliberately read from the name rather than from a
# list: a figure that is a real maximum over the full range is taken at face
# value, and one that is not says so in what it is called.
UNGUARANTEED = ("_typical", "_at_25c")

# Where to stop doubling. A figure that survives this is unbounded in
# practice - nothing on the board is holding it to anything - and saying so
# is more useful than a number.
CEILING = 1024.0

# How tightly to bisect. Half a per cent is far inside the precision of what
# is being estimated and costs about eight runs.
PRECISION = 0.005


def _scaled(design, data, values, key, kept, factor, target, board) -> bool:
    """
    True if the checks still pass with `key` multiplied by `factor`.

    **The margin is switched off while this runs**, and that is the whole
    reason the number means anything. A check that applies
    `loads.unguaranteed_margin` would otherwise see the figure twice over -
    scaled here and scaled again there - and the multiplier printed would be
    a multiple of the board's assumption rather than of the datasheet's own
    typical. With the margin neutralised, `factor` is exactly what it reads
    as: how many times the published figure the real part can be before
    something on this board stops holding.
    """
    values["loads.unguaranteed_margin"] = [0.0, 0.0]
    for name in list(values):
        if name.endswith(".typical_to_maximum_worst"):
            values[name] = [1.0, 1.0]
    values[key] = [kept[0] * factor, kept[1] * factor]
    design.write_text(json.dumps(data, indent=2))
    return not _noticed(_run(target, board))


def _breaks_at(design, data, values, key, kept, target, board) -> float | None:
    """
    The smallest multiplier at which something fails, or None if nothing does.

    Doubling first, because the interesting figures are the ones that break
    close in and the useless ones are the ones that never do; a bisection
    without a bracket would spend its whole budget proving the second kind.
    """
    if not _scaled(design, data, values, key, kept, 1.0, target, board):
        return 1.0                       # already failing, which is its own news

    low, high = 1.0, 2.0
    while high <= CEILING:
        if not _scaled(design, data, values, key, kept, high, target, board):
            break
        low, high = high, high * 2.0
    else:
        return None

    while (high - low) / low > PRECISION:
        middle = (low + high) / 2.0
        if _scaled(design, data, values, key, kept, middle, target, board):
            low = middle
        else:
            high = middle
    return high


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("board")
    ap.add_argument("--only", help="substring: probe just the keys matching it")
    args = ap.parse_args()

    design = HW / args.board / "build" / "design.json"
    if not design.is_file():
        sys.exit(f"no {design}; run `make BOARD={args.board} build layout` first")

    scratch = HW / ".breaking"
    scratch.mkdir(exist_ok=True)
    (scratch / "whoreads.py").write_text(PLUGIN)

    everything = f"{args.board}/checks checks"
    baseline = _run(everything, args.board)
    if _noticed(baseline):
        sys.exit(f"the checks do not pass to begin with: {baseline}")

    subprocess.run(
        [sys.executable, "-m", "pytest", *everything.split(), "--board", args.board,
         "-q", "--no-header", "-p", "whoreads"],
        capture_output=True, text=True, cwd=HW,
        env={**__import__("os").environ, "PYTHONPATH": f"{scratch}:{HW}"})
    who = json.loads((scratch / "whoreads.json").read_text())

    original = design.read_text()

    # **Put the file back however this ends.** A sweep leaves `design.json`
    # perturbed between probes, and the `finally` below only runs if the
    # process is allowed to finish. One was killed mid-run while writing to a
    # scratch directory that got cleaned underneath it, and what it left
    # behind was a build with the margin at zero and every ratio at one -
    # which the checks then *passed*, because the perturbation only ever
    # makes a bound looser. A corrupted build that fails loudly would have
    # been better; this is what stops it happening at all.
    atexit.register(lambda: design.write_text(original))
    for caught in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(caught, lambda *_: sys.exit(1))

    data = json.loads(original)
    values = data["values"]
    # Read before anything is perturbed: `_scaled` flattens both of these so
    # the multiplier it finds is a multiple of the datasheet figure, and the
    # numbers the board actually assumes have to be taken from the original.
    untouched = json.loads(original)["values"]

    keys = sorted(key for key in values
                  if key.endswith(UNGUARANTEED)
                  and (not args.only or args.only in key))
    if not keys:
        sys.exit("no unguaranteed figures on this board")

    # What the board currently assumes about each one, by the same rule the
    # checks use: the part's own worst published ratio where it declares one,
    # and the house quarter as a floor.
    floor = 1.0 + untouched["loads.unguaranteed_margin"][1]

    def assumed(key: str) -> float:
        owner = key.rpartition(".")[0]
        declared = untouched.get(f"{owner}.typical_to_maximum_worst")
        return max(floor, declared[1]) if declared else floor

    rows = []
    try:
        for key in keys:
            readers = who.get(key) or []
            target = " ".join(sorted(set(readers))) if readers else everything
            kept = list(values[key])
            found = _breaks_at(design, data, values, key, kept, target, args.board)
            values[key] = kept
            rows.append((key, assumed(key), found, len(set(readers))))
            where = "nothing notices" if found is None else f"{found:.2f}x"
            print(f"   {key:52s} assumed {assumed(key):5.2f}x  breaks {where}")
    finally:
        design.write_text(original)

    print()
    print(f"{'figure':52s} {'assumed':>8s} {'breaks':>8s} {'spare':>8s}  readers")
    for key, is_assumed, found, readers in rows:
        if found is None:
            print(f"{key:52s} {is_assumed:7.2f}x {'-':>8s} {'-':>8s}  {readers}")
        else:
            print(f"{key:52s} {is_assumed:7.2f}x {found:7.2f}x "
                  f"{found / is_assumed:7.2f}x  {readers}")
    print()
    print("Both columns are multiples of the figure the datasheet publishes. "
          "`assumed` is what\nthe board allows for it; `breaks` is where a "
          "check stops holding; `spare` is the gap.\nA figure that breaks "
          "nowhere is one nothing is holding, which is the other thing\n"
          "worth knowing - and `tools/mutate.py` is where that is chased.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
