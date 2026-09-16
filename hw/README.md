# amaxa hardware

Boards designed as code: **SKiDL** is the design source, **KiCad** holds the layout and runs the rule checks, **ngspice** simulates the analog behaviour, and CI gates all of it. The reasoning behind the original choices is in [`docs/research/09-board-design-pipeline.md`](../docs/research/09-board-design-pipeline.md); why the design source changed is under [Why not atopile](#why-not-atopile).

**Nothing in this pipeline needs a network.** Not a parts service, not a registry, not an account. `make tools` fetches a pinned `uv` and a pinned Python, and after that a build reaches nothing — verified by running one with `socket.connect` and `getaddrinfo` raising.

The first board, `led12`, is a 12 V LED board with no processor. It exists to prove the pipeline end to end before the STM32H743 control board depends on it.

**Status:** the board builds from source, is placed and routed, passes KiCad DRC
with no errors, and its analog behaviour is simulated. Thirty-three design checks
and thirteen simulated measurements gate it, and CI runs all of it, publishing
renders, a 3D model and a fab package. It has never been fabricated: what is
proven is the pipeline, not the physical board.

## Quick start

Needs Linux (x86_64 or arm64) with `make`, `curl`, `tar` and `sudo` for the KiCad install.

```sh
sudo apt install kicad ngspice    # KiCad 9.x and ngspice; see "What is pinned"
make tools                        # pinned uv + Python + the design virtualenv
make versions                     # confirms every tool matches its pin
```

`make tools` downloads nothing into your system: `uv`, its Python and the virtualenv all live under `hw/.tools/` and `hw/.venv/`, both git-ignored. `make distclean` removes them.

## What is pinned

| Component | Version | Where | Notes |
|---|---|---|---|
| uv | 0.12.15 | `Makefile` (sha256 per architecture) | Fetches Python and installs the lock |
| Python | 3.14 (uv-managed) | `Makefile` | Nothing requires it specifically any more; it is pinned so local and CI match |
| SKiDL | 2.3.0 | `requirements/skidl.lock` (31 packages, hash-pinned) | Pure Python, so identical on every architecture |
| KiCad | **9.0.x** | system package | **Must be 9, not 10** — see below |
| ngspice | 45.2 | system package | Version differences change simulation numbers, so `make versions` warns on a mismatch |

### Why KiCad 9 and not 10

We write the KiCad **9** file format (`20241229`) ourselves, in `tools/board.py`. The format changed twenty-two times inside the v10 cycle alone, which makes each major version a scheduled migration rather than an upgrade. `make versions` fails if `kicad-cli` is not 9.x.

Ubuntu 26.04 ships KiCad 9.0.8 directly. On Ubuntu 24.04 (what CI uses), add `ppa:kicad/kicad-9.0-releases`, which publishes 9.0.9.

## Two stages

The pipeline splits in half deliberately:

- **Generate** — `led12/led12.py` builds the circuit and writes `design.json`; `tools/board.py` turns that into KiCad files. Needs the virtualenv.
- **Verify** — `kicad-cli`, pytest and ngspice consume what was generated. Only the first step needs the virtualenv at all.

One file knows SKiDL exists. Everything downstream reads `design.json`, a schema we own, and KiCad files. That indirection is the lesson from the tool this replaced, whose printed output had quietly become the interface half the pipeline read — so every place we read it was a place it could hurt us.

## Layout

```
hw/
├── Makefile                 front end: tools, versions, build, check, drift
├── requirements/            hash-pinned dependency lock
├── checks/                  the design checks, as pytest
├── tools/                   the engines: board writer, layout, simulation
└── led12/
    ├── parts/               one directory per footprint library
    │   └── <LIB>/           footprint + <LIB>.md review note
    ├── led12.py             the circuit: the only file that knows SKiDL
    ├── parts.py             every part as data — symbol, footprint, part number
    ├── board.kicad_pro      netclasses and the clearances DRC enforces
    ├── layout.py            the board: size, placement, routing, pour
    ├── rules.kicad_dru      design intent, on top of the fab limits
    ├── elec/                generated KiCad files — not committed
    └── build/               generated reports — not committed
```

## The checks

`make check` is where the electrical reasoning lives. It reads what the build
produced — `design.json`, which carries every resolved parameter per instance,
and the board file, which carries each part's number and position — and never
hard-codes a value the design already states.

**`test_build_gates.py`** reads what was generated rather than what was
described, because a part can be specified perfectly and still reach the board
wrong: one supplier part number carrying two different parts (checked against
the board, not the BOM, because the BOM merges those rows and hides it); a BOM
line with no supplier code; a footprint with no designator; a designator used
twice; a pad with no net.

**`test_symbols.py`** checks that each part's symbol exists and that its pin
numbers match its footprint's pads. Nothing else does, and a part wired to the
wrong leg passes every other gate — it builds, routes and clears DRC.

**`test_electrical.py`** checks the claims that relate two quantities: LED current across the supply range, series
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

**Electrical rule checking** runs in the design source itself, before anything
is placed: `make build` fails on any ERC message, **warnings included**. SKiDL
calls an unconnected passive pin a warning, which is precisely the mistake worth
catching, and this board sits at zero of both. A warning that appears later has
to be silenced deliberately, on the net or pin that earns it, which is a line in
a diff rather than a message nobody reads.

**`test_check_count.py`** is the guard on the guards, and covers the two ways a
suite quietly stops checking. Removing a check fails until the expected count is
updated in the same commit. And **every value in the design that is not a part
parameter has to be read by a check or a deck** — intent is a promise the board
makes, and one nobody reads is indistinguishable from one that passes. That is
the same failure the previous design source had, where an `assert` could parse,
resolve and do nothing; owning the schema does not make it stop being possible.
It caught the 3.3 V rail, declared as 3.234 to 3.366 V and read by nothing at
all for the whole life of the board.

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

`make layout` applies `led12/layout.py` — the board's size, a placement table and
a list of routes — to the board `tools/board.py` wrote, then fills the ground
pour. Routes name pads
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
package, and which KiCad warns on import is **deprecated and due for removal**.
That is the one remaining place this pipeline depends on it, and the only
reason the board is not byte-identical from build to build: `pcbnew` reassigns
object identifiers when it saves, moving about six hundred meaningless lines.
Everything we write ourselves is stable.

And **silkscreen needs deliberate placement**: a stock footprint puts its
designator on top of the part it names, the fab clips silk that lands on a pad,
and the board comes back with unlabelled parts.

## Simulation

`make sim` runs the ngspice decks in `led12/sim/` and checks every measurement
against a band in `sim/limits.py`, each with a sentence saying why it is where
it is. A band with no reason behind it is a number somebody widens the next time
it fails.

**The decks do not restate the design.** Where a deck needs a component value it
writes `@power.out.voltage:max@` — an instance path and which end of its range
to take — and the runner fills it in from the build's `design.json`. Changing a
resistor in a part definition moves the simulation with it, because there is no
second copy of the design to fall out of step.

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

The 3.3 V deck is the newest and exists for a different reason: the rail's
promised voltage was declared in the design and **read by nothing**. Its
regulator model carries dropout and a current limit as well as a setpoint,
because a model that merely held 3.3 V would report the setpoint under every
condition — including ones the real part cannot survive — and the deck would
prove nothing. Overload it and the rail folds back; starve its input and the
output follows the input down.

Models live in `sim/models/`, and `SOURCE.md` there records where each came from
and how far it can be trusted. The LED's is a fit to the one number its
datasheet states legibly, not a vendor model, and that is written down. So is
what the regulator model leaves out: **startup, inrush into the output
capacitor, loop stability, transient response and temperature are not simulated
by anything here** and stay on the bring-up list.

`sim/limits.py` is also the declaration of what must be simulated. A deck named
there with no file to run fails, and so does a change in the total number of
measurements — the same guard `test_check_count.py` is for the design checks,
because deleting a deck used to just shrink the glob and pass.

One trap worth knowing: **ngspice treats the first line of a deck as its title**,
so a deck that starts with a component definition silently loses it.

## The schematic, attempted and rejected

SKiDL can emit a `.kicad_sch`, which the previous design source could not. That
would have unlocked two gates: `kicad-cli sch erc`, and `pcb drc
--schematic-parity` — the interesting one, because with the schematic and the
board generated from the same circuit, parity checks **our own board writer**
for silently dropping something, which nothing else does.

It was tried and dropped. The generated schematic is one sheet per subcircuit,
which is the right shape, but KiCad's own ERC finds **36 errors** in it: 17
dangling labels, 17 hierarchical labels that cannot connect to a parent sheet,
and 2 undriven power pins. SKiDL warns that its point-to-point routing can fail
on densely connected circuits, and this is what that looks like. A gate that is
permanently red is not a gate, and parity against a broken schematic would be
worse than none.

Nothing downstream depended on it, so nothing was lost. It is worth revisiting
if SKiDL's schematic generation improves; the board writer would then need to
consume the schematic's symbol UUIDs, since parity matches on `(path ...)` and
nothing writes one today.

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
matter, Excellon drill data, an IPC-D-356 netlist so the assembler can
flying-probe the bare board against what we designed, the placement file, the
BOM, renders, a STEP model, a record of what it was built from and the tool
versions that built it, and the design fingerprint.

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

The design: `led12.py` and `parts.py`, the parts library with its review notes,
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

Measuring this afterwards showed the decision was not merely convenient. Two
builds on the same machine from identical sources still differ, though far less
than they used to: **what we write is byte-identical, and the remaining six
hundred lines of churn are KiCad's**, from filling the pours. Nothing about the
design moves.

So the board is compared as a design rather than as a file. `make reproducible`
builds twice and checks that both runs describe the same thing — the same parts
at the same coordinates, the same copper, the same net names. That is the
property worth holding, and unlike a byte comparison it is true.

If you ever want to take the board over by hand in KiCad, commit it at that
point and stop running `make layout` on it. Until then it is generated.

## Why not atopile

The pipeline was built on **atopile** and then moved off it. Keeping the record,
because it is the justification for the move and the reason several checks here
exist at all.

**Its authors abandoned the open-source project.** The public repo's default
branch has had no commits since **2026-03-11**, while PyPI shipped seventeen more
releases with no git tags; in August the maintainers closed roughly twenty of
their own in-flight PRs unmerged. Their own words, 2026-08-06: *"the public
repository has become stale, despite us working full-time on the project."* The
0.15 line is "soft-deprecated" with a removal date "to be announced", there is no
0.16 on PyPI, and the successor is a sign-in-only browser product speaking a
different language. The public documentation is gone.

**Every service of theirs that provided something is gone.**
`components.atopileapi.com` (the part picker), `packages.atopileapi.com` (the
registry dependencies came from) and `api.atopileapi.com` all fail to resolve.
`telemetry.atopileapi.com` resolves and answers.

**It reported telemetry by default**, to that endpoint, on a developer's machine:
an installation id, a hashed project id, error logs, build duration, the version,
and the git hash of the current commit. Opt-out, and documented in a docstring
rather than anywhere a user would look.

None of that broke the board — we used explicit parts and no cloud, and were
hash-pinned. But it was a dependency with a stated end of life, no documentation
for the version we were on, and no fixes ever.

### What it was like to get running

- **atopile has no Linux arm64 wheel**, in any of its 171 releases. On arm64 it builds from source in about two minutes, which works as long as uv's own Python (with headers) is used.
- **atopile's parts server is gone** (`components.atopileapi.com` no longer resolves), so its automatic part picker can't run. Parts are specified explicitly and committed instead, each with a review note.
- **atopile's public repo has been frozen since March 2026** while releases keep appearing. It's MIT licensed, so the fallback is forking and pinning. Deciding that is a later milestone.

### How it wanted parts laid out

Undocumented, and reverse-engineered from `faebryk/libs/part_lifecycle.py`:

- **A footprint file must sit in the same directory as the `.ato` file that declares the component.** atopile derives the KiCad library *name* from the footprint's parent directory but the library *path* from the declaring `.ato` file's directory. Keep a footprint anywhere else and the build fails with ``Footprint `X` doesn't exist in library `Y` ``.
- Consequently every part lived at `parts/<LIB>/<LIB>.ato` with its footprint beside it, and directories matching that shape were registered as footprint libraries on every build. The `parts/<LIB>/` shape survives — `tools/board.py` writes an `fp-lib-table` pointing at it — but the `.ato` files are gone.
- A part with no supplier code needs `has_part_removed`, not an empty `has_part_picked` — otherwise it warns "No part found" and silently leaves the part off the BOM anyway. `has_part_removed` says "deliberately not purchased" and is how test pads stay off the BOM.
- Only `lcsc` is accepted as a supplier id. Any other value raises.
- Names collide silently with the standard library. Our test pad was called `TestPoint`, which resolved to the stdlib `TestPoint` (it has `contact`, not `pad`) and failed with ``Field `tp_12v.pad` could not be resolved``.

### What its assertions actually checked

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

### What it did give us

- Deriving a part from a standard-library type (`component Res680 from Resistor`) brings real parameters, a designator prefix, `~>` bridging, and a populated BOM `Value` column. Hand-rolled components get an empty `Value`.
- It warns when **one part number carries two different values** ("Value is not the same for two equal partnumbers"). That is the single most valuable check it ships, because explicit parts make it easy to reuse a 680 Ω part number for a 10 kΩ resistor. We promote that warning to an error.
- `get_bbox_from_geos` ignores arcs and circles (`TODO` stubs upstream), so a footprint whose silkscreen is *only* a circle crashes the build with `min() iterable argument is empty`. Stock `TestPoint_Pad_D1.5mm` is such a footprint; we use `TestPoint_Pad_1.5x1.5mm`, which draws its outline with lines.

## Commands

| Target | Does |
|---|---|
| `make help` | List targets |
| `make tools` | Fetch pinned uv and Python, build the design virtualenv |
| `make versions` | Print every tool version and fail if a pinned one is wrong |
| `make build` | Turn the SKiDL design source into KiCad files |
| `make layout` | Apply the placement and routing, then fill the ground pour |
| `make rules` | Regenerate the board's `.kicad_dru` from the fab and board rules |
| `make check` | Run the design checks against what the build produced |
| `make drc` | Run KiCad DRC against the fab limits and the board's own rules |
| `make sim` | Run the ngspice decks and check every measurement against its band |
| `make reproducible` | Build twice and check both runs describe the same board |
| `make outputs` | Renders, 3D model, gerbers, drill and netlist into `out/` |
| `make clean` | Remove build outputs |
| `make distclean` | Also remove the venv and downloaded tools |

`make outputs` runs `drc`, not `check` or `sim`. CI runs all three; so should you
before ordering.

`BOARD=<name>` selects the board; it defaults to `led12`.
