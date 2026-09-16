# amaxa hardware

Boards designed as code: **atopile** (`.ato`) is the design source, **KiCad** holds the layout and runs the rule checks, **ngspice** simulates the analog behaviour, and CI gates all of it. The reasoning behind these choices is in [`docs/research/09-board-design-pipeline.md`](../docs/research/09-board-design-pipeline.md).

The first board, `led12`, is a 12 V LED board with no processor. It exists to prove the pipeline end to end before the STM32H743 control board depends on it.

**Status:** the board builds from source, is placed and routed, passes KiCad DRC
with nothing reported at any severity, and its analog behaviour is simulated.
Twenty-eight design checks and nine simulated measurements gate it, and CI runs
all of it, publishing renders, a 3D model and a fab package.

## Quick start

Needs Linux (x86_64 or arm64) with `make`, `curl`, `tar` and `sudo` for the KiCad install.

```sh
sudo apt install kicad ngspice    # KiCad 9.x and ngspice; see "What is pinned"
make tools                        # pinned uv + Python + atopile venv
make versions                     # confirms every tool matches its pin
```

`make tools` downloads nothing into your system: `uv`, its Python and the atopile virtualenv all live under `hw/.tools/` and `hw/.venv/`, both git-ignored. `make distclean` removes them.

## What is pinned

| Component | Version | Where | Notes |
|---|---|---|---|
| uv | 0.12.15 | `Makefile` (sha256 per architecture) | Fetches Python and installs atopile |
| Python | 3.14 (uv-managed) | `Makefile` | atopile requires 3.14. uv's build ships the headers the install needs; Ubuntu's system Python does not |
| atopile | 0.15.9 | `requirements/atopile.lock` (123 packages) | Built from source on arm64, ~2 min; a prebuilt wheel exists only for x86_64 |
| KiCad | **9.0.x** | system package | **Must be 9, not 10** — see below |
| ngspice | 45.2 | system package | Version differences change simulation numbers, so `make versions` warns on a mismatch |

### Why KiCad 9 and not 10

atopile writes the KiCad **9** file format (`20241229`). If you open the board in KiCad 10 and save, the files are upgraded and the next atopile build may fail to read them. `make versions` fails if `kicad-cli` is not 9.x, and a later check will assert the file-format version inside the board itself.

Ubuntu 26.04 ships KiCad 9.0.8 directly. On Ubuntu 24.04 (what CI uses), add `ppa:kicad/kicad-9.0-releases`, which publishes 9.0.9.

## Two stages

The pipeline splits in half deliberately:

- **Generate** — atopile turns `.ato` source into KiCad files. Needs the virtualenv.
- **Verify** — `kicad-cli`, pytest and ngspice consume the committed files. Runs anywhere, and is what gates CI.

That split means a machine that can't run atopile can still verify the design, and it keeps the blocking checks free of heavyweight tooling.

## Layout

```
hw/
├── Makefile                 front end: tools, versions, build, check, drift
├── requirements/            atopile dependency lock
├── checks/                  the design checks, as pytest
├── tools/                   check_drift.py
└── led12/
    ├── ato.yaml             build targets
    ├── src/led12.ato        the board
    ├── parts/               one directory per footprint library
    │   └── <LIB>/           footprint + <LIB>.ato + <LIB>.md review note
    ├── layout.py            placement and routing
    ├── rules.kicad_dru      design intent, on top of the fab limits
    ├── elec/                generated KiCad files — not committed
    └── build/               generated reports — not committed
```

## The checks

`make check` is where the real electrical reasoning lives, because atopile's own
assertions cannot do it (see "What atopile's assertions actually check" below).
It reads what the build produced — the variable report and the board file, which
carries each part's number and every resolved parameter per instance — and never
hard-codes a value that the design already states.

**`test_build_gates.py`** turns problems atopile reports but tolerates into
failures: a parameter resolved to `<empty>`, meaning two constraints on it cannot
both hold; one supplier part number carrying two different parts (checked against
the board, not the BOM, because the BOM merges those rows and hides it); a BOM
line with no supplier code; a footprint with no designator; a designator used
twice; a pad with no net.

**`test_electrical.py`** checks the claims that relate two quantities, which is
exactly what atopile cannot do: LED current across the supply range, series
resistor dissipation against its rating, gate drive against the FET's threshold,
debounce time constants, fuse headroom over worst-case load, and that nothing on
the protected rail is rated below what the TVS lets through.

**`test_topology.py`** verifies the shape the electrical checks assume: that the
fuse really is first in the input path, that nothing bypasses the reverse
polarity FET, that each LED has its own resistor, that every rail has a test
point, and that the 12 V net reaches exactly the parts it should.

**`test_geometry.py`** reads the placed board rather than the netlist, which is
the only way to notice that a decoupling capacitor is on exactly the right net
and 40 mm from the thing it decouples.

**`test_parts.py`** keeps the library honest: every part has a review note, every
declared footprint file exists, no note still describes a part that was replaced.

**`test_check_count.py`** is the guard on the guards — removing a check fails the
suite until the expected count is updated in the same commit.

Each gate has been made to fail on purpose once. A gate that has never failed is
not a gate. Three found real defects the first time they ran:

- the LED series resistor was dissipating 104 % of its rated power at nominal,
  because 680 Ω is a 5 V habit and this is a 12 V rail;
- the regulator was rated 15 V against a TVS that clamps at 19.9 V, so a surge
  would have destroyed the part the protection exists to protect;
- the TVS itself was fitted backwards. `~>` bridges a diode anode to cathode, so
  `out.hv ~> tvs ~> out.lv` reads perfectly and shorts the rail through a
  forward-biased diode. DRC caught it as a short once the board was routed.

## Laying the board out

`make layout` applies `led12/layout.py` — a placement table and a list of routes
— to the board atopile generated, then fills the ground pour. Routes name pads
symbolically, as `power.q_rpp:3`, so moving a part in the placement table moves
the tracks that reach it; literal coordinates are only the corners in between.

It refuses to run unless every part on the board is placed deliberately, so a
part added to the source cannot quietly land at the origin. What it writes is
tagged with a recognisable UUID prefix and removed before being written again,
so the board reflects the description and never accumulated edits, and the UUIDs
are derived from the objects themselves, so a rebuild that changes nothing
produces no diff.

Two things about zones are worth knowing. **`kicad-cli` cannot fill them**, and
it runs DRC against whatever fill is already in the file — so an unfilled ground
plane reports every ground pad as unconnected while the render looks perfect.
Filling needs KiCad's own `pcbnew` Python module, which ships inside the `kicad`
package. And **silkscreen needs deliberate placement**: atopile puts each
designator on top of the part it names, the fab clips silk that lands on a pad,
and the board comes back with unlabelled parts.

## Simulation

`make sim` runs the ngspice decks in `led12/sim/` and checks every measurement
against a band in `sim/limits.py`, each with a sentence saying why it is where
it is. A band with no reason behind it is a number somebody widens the next time
it fails.

**The decks do not restate the design.** Where a deck needs a component value it
writes `@power.out.voltage:max@` — an atopile instance path and which end of its
resolved range to take — and the runner fills it in from the build's variable
report. Changing a resistor in a part definition moves the simulation with it,
because there is no second copy of the design to fall out of step.

Several measurements deliberately restate what `hw/checks/` computes
algebraically, so that a disagreement between the two methods fails rather than
going unnoticed. The LED branch is the clearest case: the design check draws a
straight line through the datasheet's forward-voltage band and gets 3.73 to
5.07 mA; the simulation uses a diode that actually curves and gets 3.95 to
5.01 mA. Two methods, one answer.

The debounce deck exists because the algebra is easy to get wrong in a
particular way. Pressing and releasing are not symmetric — pressing charges
through the series resistor with the pulldown in parallel, releasing opens the
circuit and leaves the capacitor to discharge through the pulldown alone — and a
deck that models the button as a voltage source gets the release badly wrong,
because the source pulls the gate down instead of letting go of it.

Models live in `sim/models/`, and `SOURCE.md` there records where each came from
and how far it can be trusted. The LED's is a fit to the one number its
datasheet states legibly, not a vendor model, and that is written down.

One trap worth knowing: **ngspice treats the first line of a deck as its title**,
so a deck that starts with a component definition silently loses it.

## Who has to look

`.github/CODEOWNERS` requires review on the files where a change quietly
weakens a gate rather than obviously breaking something: the fab limits and
board rules, the design checks and their count guard, the simulation limits and
the models under them, and the tooling the gates run through.

The risk is not carelessness. It is that **loosening a rule looks exactly like
fixing a failure**. A board that passes because a clearance was widened looks
identical to one that passes because it is correct, and the diff that did it is
one line.

## Releasing

Pushing a tag builds the orderable package: gerbers for the nine layers that
matter, Excellon drill data, the placement file, the BOM, renders, a STEP
model, a record of what it was built from and the tool versions that built it,
and the design fingerprint.

It is published as a CI artifact rather than attached to a GitHub release,
because the workflow should not create anything outward-facing on its own.

Two things that were considered and deliberately left out:

- **KiBot.** It would add a browsable index and image diffs, and a dependency.
  The outputs it produces we already produce, and for this pipeline the useful
  diff is not a picture — it is `layout.py`, which says a part moved and by how
  much, and the design fingerprint, which says what the board *is* in a form two
  runs can be compared by eye.
- **A live BOM stock check in CI.** Stock at the time each part was chosen is
  recorded in its review note, which is the number that justified the choice.
  Live stock belongs at the moment of ordering, not in a gate that fails because
  a distributor's API was slow.

## What is committed

The design: the `.ato` sources, the parts library with its review notes,
`layout.py`, and the rules files. Not the KiCad board.

That is deliberate, and it was not the first answer. The board was committed to
begin with, gated by a check that a rebuild did not move it. The check failed
the moment CI ran it — not because anything was wrong, but because CI's KiCad is
a different patch release from the one here, and `pcbnew` re-serialises the
whole file when it fills the pours. The bytes of a generated board depend on
which KiCad last touched it.

A gate that fails on a patch-version difference is noise, so the board became
what it always was: output. It cannot go stale, because it is built fresh every
time. What a reviewer reads is `layout.py` — a placement table and a list of
routes, which diffs far more usefully than a `.kicad_pcb` ever did — alongside
the renders and the DRC report CI publishes.

Measuring this afterwards showed the decision was not merely convenient. **Two
builds on the same machine from identical sources differ on more than five
thousand lines**: atopile emits footprints in a different order every run and
gives every object a fresh UUID. Nothing about the design moves. Every part is
in the same place, every track runs between the same points, the pour covers the
same copper.

So the board is compared as a design rather than as a file. `make reproducible`
builds twice and checks that both runs describe the same thing — the same parts
at the same coordinates, the same copper, the same net names. That is the
property worth holding, and unlike a byte comparison it is true.

If you ever want to take the board over by hand in KiCad, commit it at that
point and stop running `make layout` on it. Until then it is generated.

## Verified findings

Facts established while setting this up, worth not rediscovering.

### Getting it running

- **atopile has no Linux arm64 wheel**, in any of its 171 releases. On arm64 it builds from source in about two minutes, which works as long as uv's own Python (with headers) is used.
- **atopile's parts server is gone** (`components.atopileapi.com` no longer resolves), so its automatic part picker can't run. Parts are specified explicitly and committed instead, each with a review note.
- **atopile's public repo has been frozen since March 2026** while releases keep appearing. It's MIT licensed, so the fallback is forking and pinning. Deciding that is a later milestone.

### What atopile talks to

Worth knowing before depending on it, and checked on this machine rather than
read from the documentation:

- **It reports telemetry by default on a developer's machine**, to
  `telemetry.atopileapi.com`, a PostHog endpoint. It sends an installation id
  (or the logged-in user id), a hashed project id, error logs, how long the
  build took, the ato version, and **the git hash of the current commit**. It
  already stays quiet when `CI` is set, so this was only ever local builds.
  `make` turns it off via `FBRK_TELEMETRY`; pass `TELEMETRY=1` to allow it.
- **Every other service of theirs is gone.** `components.atopileapi.com` (the
  part picker), `packages.atopileapi.com` (the package registry that `ato`
  dependencies come from) and `api.atopileapi.com` all fail to resolve.
  `telemetry.atopileapi.com` resolves and answers.

That the only surviving service is the one that collects rather than provides is
the clearest signal available about where the project stands.

### How atopile wants parts laid out

Undocumented, and reverse-engineered from `faebryk/libs/part_lifecycle.py`:

- **A footprint file must sit in the same directory as the `.ato` file that declares the component.** atopile derives the KiCad library *name* from the footprint's parent directory but the library *path* from the declaring `.ato` file's directory. Keep a footprint anywhere else and the build fails with ``Footprint `X` doesn't exist in library `Y` ``.
- Consequently every part lives at `parts/<LIB>/<LIB>.ato` with its footprint beside it. Directories matching that shape are registered as footprint libraries automatically on every build.
- A part with no supplier code needs `has_part_removed`, not an empty `has_part_picked` — otherwise it warns "No part found" and silently leaves the part off the BOM anyway. `has_part_removed` says "deliberately not purchased" and is how test pads stay off the BOM.
- Only `lcsc` is accepted as a supplier id. Any other value raises.
- Names collide silently with the standard library. Our test pad was called `TestPoint`, which resolved to the stdlib `TestPoint` (it has `contact`, not `pad`) and failed with ``Field `tp_12v.pad` could not be resolved``.

### What atopile's assertions actually check

This one matters, because it decides what CI can gate on. Measured, not read:

| Written in `.ato` | What actually happens |
|---|---|
| `assert x within A to B` | Becomes the parameter's spec. Several of them intersect. |
| Two `within` asserts that contradict | Spec resolves to `<empty>` — detectable, **but the build still succeeds** |
| `assert x > A`, `< A`, `>=`, `<=` | **Silently ignored.** Contributes nothing at all, under either solver |
| `voltage`/`max_current` on connected `ElectricPower` rails | **Does not propagate.** Declared alias and sum "bus parameters" stay unconstrained |
| Cross-parameter arithmetic, e.g. `(V - Vf) / R within 10mA to 20mA` | Does not propagate, including with `FBRK_FULL_SOLVER=1` |
| A value assigned in a `component` body | Sets the parameter's **unit only**, never its value |

So atopile 0.15.9 gives us **single-parameter interval intersection and nothing else**. Every claim that relates two quantities — LED current from rail voltage and resistor value, gate drive against a threshold, fuse rating against load — has to be checked in the pytest tier against the exported netlist. That is what `hw/checks/` is for.

Two consequences we rely on:

- Because a contradiction shows up as `<empty>` rather than a failure, **`<empty>` is promoted to a build failure by our own gate**. Otherwise a contradicting assertion is indistinguishable from a passing one.
- Because `assert x > A` is silently dropped, an inequality in a `.ato` file is a **lie**. The check-count guard in `hw/checks/` exists so that a check which stops running gets noticed.

### Things atopile does give us for free

- Deriving a part from a standard-library type (`component Res680 from Resistor`) brings real parameters, a designator prefix, `~>` bridging, and a populated BOM `Value` column. Hand-rolled components get an empty `Value`.
- It warns when **one part number carries two different values** ("Value is not the same for two equal partnumbers"). That is the single most valuable check it ships, because explicit parts make it easy to reuse a 680 Ω part number for a 10 kΩ resistor. We promote that warning to an error.
- `get_bbox_from_geos` ignores arcs and circles (`TODO` stubs upstream), so a footprint whose silkscreen is *only* a circle crashes the build with `min() iterable argument is empty`. Stock `TestPoint_Pad_D1.5mm` is such a footprint; we use `TestPoint_Pad_1.5x1.5mm`, which draws its outline with lines.

## Commands

| Target | Does |
|---|---|
| `make help` | List targets |
| `make tools` | Fetch pinned uv and Python, build the atopile venv |
| `make versions` | Print every tool version and fail if a pinned one is wrong |
| `make build` | Turn `.ato` source into KiCad files |
| `make check` | Run the design checks against what the build produced |
| `make drift` | Fail if the committed board no longer matches its source |
| `make clean` | Remove build outputs |
| `make distclean` | Also remove the venv and downloaded tools |

`BOARD=<name>` selects the board; it defaults to `led12`.
