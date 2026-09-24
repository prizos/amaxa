#!/usr/bin/env python3
"""
Change every number the design declares, and see which ones anything notices.

`test_every_declared_parameter_is_read` and its sibling for design intent both
ask whether a value is *looked up*. That is not the same question as whether
anything is *asserted* about it. A check can read a figure, put it in a message
and compare something else; a check can take the maximum of seven identical
parts, so that changing one of them changes nothing; a check can hold a number
against a limit it clears by four orders of magnitude. All three read the
value, and all three would go on passing if the value were wrong.

So this perturbs each one - to zero, and to something absurd - and runs the
checks that read it. What comes out is the list of numbers the repository is
not actually holding to anything.

**It is a diagnostic, not a gate.** Most of what it reports is legitimate and
will stay reported:

  - a resistor that dissipates nothing is unmoved by its power rating, because
    there is genuinely nothing to check;
  - one of thirty-eight bypass capacitors is unmoved by a check that sums the
    rail's total, because the sum has margin;
  - one of seven identical comparators is unmoved by a check that takes the
    worst of them, because the other six still answer.

Turning that into an allow-list would be a table of beliefs, which is the one
thing this repository does not do. Read the output instead, and look for the
entry that does not have one of those explanations.

    make -C hw BOARD=cpu1 mutate

**Re-run it after any commit that removes an assertion.** The headline below
went stale within a day: a commit withdrew an Ethernet bound that could not
fail and left its intent band declared, and the band then sat there being
read into a message - which `test_every_design_intent_is_read_by_something`
accepts, because it asks whether a value is looked up. This is the thing that
notices, and it only notices when it is run.

Measured on cpu1, with every reader probed:

    0 of 67 intent bands change no outcome
    68 of 799 part parameters, of which
        39  unmoved by every check that reads them
        13  read only by a simulation deck, which this does not run
        16  read by no check's call phase at all

**The 68 was 164 before the reader map was fixed**, and the difference is not
a change to the board. This used to record one reader per parameter - see the
note on the plugin below - and probe that one, so ninety-six parameters were
reported as held to nothing while checks that do hold them were never asked.
`safety.r_gate_kill_drain.resistance` was on that list, and setting it to
zero makes `test_the_gate_kill_stays_inside_its_ratings` fail.

**Cost.** A parameter's readers run in one pytest invocation: about a second
for a single cheap check, ten for one with five readers, against twenty-five
for the whole suite. A full sweep is therefore hours rather than minutes, and
the one wall-clock figure measured here - 59945 s - was taken while other
work was running on the same machine and is an overestimate of what it costs
alone. `--intent-only` is the short version: 67 bands, one suite run each.

**What it still cannot see.** Only the checks the plugin recorded as reading
a value are probed, so a check that reaches a figure some way the recorder
misses would be missed too. Three of the 39 were re-tested against the whole
suite by hand and were quiet there as well, which is evidence and not proof.
Running the whole suite per probe would be exact, and at twenty-five seconds
a run it is not obviously worse than ten; it is the next thing to try.
"""

import argparse
import json
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
HW = HERE.parent

# Attributes each parameter to the first test whose *call* phase reads it, so
# the sweep can run one test rather than the whole suite. Session fixtures read
# during setup are not attributed, which is why a parameter read only there
# comes out as "no test reads it" - on cpu1 that set is exactly the declared
# exemptions.
PLUGIN = '''
import json, pathlib
import pytest

MAP = {}


def _seen(config):
    for plugin in config.pluginmanager.get_plugins():
        if hasattr(plugin, "PARAMETERS_READ"):
            return plugin.PARAMETERS_READ
    return set()


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    # **Empty it, not diff it.** `PARAMETERS_READ` is one cumulative set for
    # the whole session, so `after - before` is non-empty only for the *first*
    # test that reads a value - every later reader sees the key already there
    # and registers nothing. This recorded one reader per parameter and the
    # sweep then probed that one, which is how a resistor whose value makes
    # `test_the_gate_kill_stays_inside_its_ratings` fail was reported as
    # changing no outcome.
    store = _seen(item.config)
    union = set(store)
    store.clear()
    yield
    mine = set(store)
    for key in mine:
        MAP.setdefault(f"{key[0]}.{key[1]}", []).append(item.nodeid)
    store.clear()
    store.update(union | mine)


def pytest_sessionfinish(session, exitstatus):
    pathlib.Path(__file__).with_name("whoreads.json").write_text(json.dumps(MAP))
'''


def _run(target: str, board: str) -> str:
    """The last line of a pytest run, which says whether anything failed."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", *target.split(), "--board", board,
         "-q", "--no-header", "-p", "no:cacheprovider"],
        capture_output=True, text=True, cwd=HW)
    lines = result.stdout.strip().splitlines()
    return lines[-1] if lines else "error"


def _noticed(line: str) -> bool:
    return "failed" in line or "error" in line


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("board")
    ap.add_argument("--intent-only", action="store_true")
    args = ap.parse_args()

    design = HW / args.board / "build" / "design.json"
    if not design.is_file():
        sys.exit(f"no {design}; run `make BOARD={args.board} build` first")

    scratch = HW / ".mutate"
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
    data = json.loads(original)
    values = data["values"]
    parts = set(data["parts"])

    # Intent bands are everything that is not a part's own parameter, and they
    # are few enough to run the whole suite against.
    bands = [key for key in values if key.rpartition(".")[0] not in parts]
    parameters = [key for key in values if key.rpartition(".")[0] in parts]

    quiet: list[tuple[str, str]] = []
    try:
        for key in bands:
            kept = list(values[key])
            if not any(_probe(design, data, values, key, probe, everything, args.board)
                       for probe in _probes(kept)):
                quiet.append((key, "no check in the suite notices"))
            values[key] = kept
        print(f"{len(quiet)} of {len(bands)} intent bands change no outcome")

        if not args.intent_only:
            before = len(quiet)
            decks = _simulation_text(HW / args.board)
            for key in parameters:
                readers = who.get(key) or []
                if not readers:
                    owner, _, name = key.rpartition(".")
                    if f"@{key}:" in decks or f'"{key}"' in decks:
                        quiet.append((key, "read only by a simulation deck, "
                                           "which this does not run"))
                    else:
                        quiet.append((key, "no test's call phase reads it"))
                    continue
                test = " ".join(sorted(set(readers)))
                kept = list(values[key])
                if not any(_probe(design, data, values, key, probe, test, args.board)
                           for probe in _probes(kept)):
                    quiet.append((key, f"unmoved in {test.rpartition('::')[2]}"))
                values[key] = kept
            print(f"{len(quiet) - before} of {len(parameters)} part parameters "
                  f"change no outcome")
    finally:
        design.write_text(original)

    for key, why in quiet:
        print(f"   {key:52s} {why}")
    return 0


def _simulation_text(board) -> str:
    """
    The decks and their limits, which name values this cannot probe.

    `make sim` is not run here, so a figure read only by a deck looks exactly
    like a figure nothing reads. That is a different thing and it is reported
    as a different thing - otherwise the sequencing figures the power-up deck
    needs would sit in this list looking like dead weight.
    """
    sim = board / "sim"
    if not sim.is_dir():
        return ""
    files = sorted(sim.glob("*.cir.in")) + sorted(sim.glob("limits.py"))
    return "\n".join(path.read_text() for path in files)


def _probes(kept: list[float]) -> list[list[float]]:
    """Zero, and far past anything the board could mean."""
    return [[0.0, 0.0], [abs(kept[1]) * 1e6 + 1e6] * 2]


def _probe(design, data, values, key, probe, target, board) -> bool:
    values[key] = probe
    design.write_text(json.dumps(data, indent=2))
    return _noticed(_run(target, board))


if __name__ == "__main__":
    sys.exit(main())
