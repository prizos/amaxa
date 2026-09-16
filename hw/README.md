# amaxa hardware

Boards designed as code. **SKiDL** is the design source, **KiCad** holds the
layout and runs the rule checks, **ngspice** simulates the analog behaviour, and
CI gates all of it.

The first board, [`led12`](led12/README.md), is a 12 V LED board with no
processor. It exists to prove the pipeline before the STM32H743 control board
depends on it.

**A build reaches nothing over the network** — no parts service, no registry, no
account. `make offline` proves it, by running the design source with every route
out of the process raising, and CI runs that.

## Quick start

Needs Linux (x86_64 or arm64) with `make`, `curl`, `tar`, and `sudo` for KiCad.

```sh
sudo apt install kicad ngspice    # KiCad 9.x — see "Pinned versions"
make tools                        # pinned uv + Python + the design virtualenv
make check                        # build the board and run the design checks
```

`make tools` puts everything under `hw/.tools/` and `hw/.venv/`, both
git-ignored; `make distclean` removes them. `make help` lists every target.

## Changing a board

Four files, and which one you want depends on what you are changing.

| To change | Edit | Then run |
|---|---|---|
| A part — value, package, part number, datasheet figures | `led12/parts.py` | `make check sim` |
| The circuit — what connects to what | `led12/led12.py` | `make check` |
| The board — where parts sit, how they route, the pour | `led12/layout.py` | `make drc` |
| What counts as correct | `checks/`, `led12/sim/limits.py`, `led12/rules.kicad_dru` | `make check sim drc` |

Then `make outputs` for renders, gerbers and the fab package.

**Adding a part** touches three places: a `PartSpec` in `parts.py`, an instance
in `led12.py`, and a position in `layout.py`'s `PLACEMENT`. If its package is
new, add `led12/parts/<LIB>/` with the footprint and a `<LIB>.md` review note —
several checks require the note, and one requires it to name the part numbers
`parts.py` actually uses.

Expect the checks to fail the first time, and read what they say. They are
written to name the two quantities that disagree, because the point is to be
told which assumption broke rather than that something did.

**Two rules the router will not bend:** a track may not cross a pad of another
net, which is why the power rails run on their own line above or below the parts
rather than through them; and the back copper belongs to the ground pour, so
every signal is on the front and every ground pad reaches the plane through its
own via.

## How it fits together

```
led12/parts.py  ─┐
                 ├─► led12/led12.py ─► design.json ─┬─► tools/board.py ─► .kicad_pcb
       SKiDL  ───┘                                  │                          │
                                                    ├─► checks/        tools/layout.py
                                                    └─► tools/simulate.py      │
                                                                  kicad-cli drc ┘
```

The pipeline splits in half deliberately. **Generate** — `led12.py` builds the
circuit and writes `design.json`; `tools/board.py` turns that into KiCad files.
**Verify** — `kicad-cli`, pytest and ngspice consume what was generated. Only
the first step needs the virtualenv.

One file knows SKiDL exists. Everything downstream reads `design.json`, a schema
we own, and KiCad files. That indirection is the lesson from the tool this
replaced, whose printed output had quietly become the interface half the
pipeline read — so every place we read it was a place it could hurt us.

## The gates

| | Catches |
|---|---|
| **ERC**, in the design source | Unconnected or undriven pins. Fails on warnings too, because SKiDL calls an unconnected passive pin a warning and that is the mistake worth catching |
| **`make check`** | Everything relating two quantities: currents, power margins, gate drive against thresholds, ratings against the TVS clamp, debounce time constants, net shape, part placement, symbol-to-footprint pin agreement |
| **`make sim`** | The analog behaviour, against bands in `led12/sim/limits.py` that each carry a sentence saying why |
| **`make drc`** | Clearances, track widths, annular rings, hole sizes, plus the board's own intent rules in `led12/rules.kicad_dru` |
| **`make reproducible`** | Two builds describing the same design |
| **`make offline`** | The build reaching the network |

Two properties matter more than any individual check.

**Expected values are derived, not written down.** A check that states the
answer can only confirm what you already believed. The reverse-polarity FET on
`led12` was wired backwards for the life of the board, and the check meant to
catch a part fitted backwards was holding it that way, because its expected
value was a hand-written table. Where a table is unavoidable, it says so.

**Nothing may be declared and left unread.** Every parameter in `parts.py` and
every design intent in `led12.py` has to be consumed by a check or a deck, or
exempted by name with a reason. Before that rule existed, ten datasheet figures
were inert — the bulk capacitor could go from 47 µF to 100 pF with every gate
still green.

`checks/test_check_count.py` is the guard on the guards: it counts checks that
will actually run, so `@pytest.mark.skip` cannot turn one off quietly.

## Pinned versions

| Component | Version | Where |
|---|---|---|
| uv | 0.12.15 | `Makefile` (sha256 per architecture) |
| Python | 3.14 (uv-managed) | `Makefile` |
| SKiDL | 2.3.0 | `requirements/skidl.lock`, hash-pinned |
| KiCad | **9.0.x** | system package |
| ngspice | 45.2 | system package |

`make versions` fails if a pinned tool is wrong.

**KiCad 9, not 10.** We write the KiCad 9 file format (`20241229`) ourselves in
`tools/board.py`. The format changed twenty-two times inside the v10 cycle
alone, which makes each major version a scheduled migration rather than an
upgrade. Ubuntu 26.04 ships 9.0.8; on 24.04 add `ppa:kicad/kicad-9.0-releases`.

## Things that will surprise you

- **`kicad-cli` cannot fill copper pours**, and it runs DRC against whatever
  fill is already in the file — so an unfilled ground plane reports every ground
  pad as unconnected while the render looks perfect. Filling needs KiCad's
  `pcbnew` Python module, which ships inside the `kicad` package and which KiCad
  warns on import is deprecated. That is the last place this pipeline needs it,
  and the only reason a board is not byte-identical between builds: `pcbnew`
  reassigns object identifiers when it saves, moving about six hundred
  meaningless lines. Everything we write ourselves is stable.
- **Silkscreen needs deliberate placement.** A stock footprint puts its
  designator on top of the part it names, the fab clips silk that lands on a
  pad, and the board comes back with that part unlabelled. `LABELS` in
  `layout.py` is where that is fixed.
- **ngspice treats the first line of a deck as its title**, so a deck starting
  with a component definition silently loses it.
- **The generated rules file lives in a directory `make build` deletes.** Run
  `kicad-cli` by hand and you may be checking against no custom rules at all,
  and getting a clean report. `make drc` regenerates it and refuses to run if it
  is missing or empty.

## The board is output, not source

Committed: `led12.py`, `parts.py`, `layout.py`, the parts library with its
review notes, and the rules files. **Not the `.kicad_pcb`.**

That was not the first answer. The board was committed to begin with, gated by a
check that a rebuild did not move it, and the check failed the moment CI ran it
— not because anything was wrong, but because CI's KiCad was a different patch
release. The bytes of a generated board depend on which KiCad last touched it.

So the board is compared as a design rather than as a file. `make reproducible`
builds twice and checks that both runs describe the same parts at the same
coordinates with the same copper and the same net names. What a reviewer reads
is `layout.py` — a placement table and a list of routes, which diffs far more
usefully than a `.kicad_pcb` ever did.

If you ever take a board over by hand in KiCad, commit it at that point and stop
running `make layout` on it.

## Releasing

Pushing a tag builds the orderable package: gerbers, Excellon drill data, an
IPC-D-356 netlist for flying-probe test, the placement file, the BOM, renders, a
STEP model, and a record of what it was built from. It is published as a CI
artifact rather than attached to a release, because the workflow should not
create anything outward-facing on its own.

`.github/CODEOWNERS` requires review on the files where a change quietly weakens
a gate rather than obviously breaking something — the rules files, the checks,
the simulation limits and the models under them. The risk is not carelessness;
it is that **loosening a rule looks exactly like fixing a failure**, and the diff
that does it is one line.

**Deliberately not done:** KiBot, and a live BOM stock check in CI. The outputs
KiBot produces we already produce, and stock belongs at the moment of ordering
rather than in a gate that fails because a distributor's API was slow.

## Also worth knowing

- **The schematic was attempted and rejected.** SKiDL can emit a `.kicad_sch`,
  which would unlock `kicad-cli sch erc` and `pcb drc --schematic-parity` —
  parity being the interesting one, because it would check our own board writer.
  The generated schematic draws 36 ERC errors: dangling and unconnectable
  hierarchical labels, which is what SKiDL's point-to-point routing does on a
  densely connected circuit. Worth revisiting if that improves.
- **Why not atopile.** This pipeline was built on it and moved off when its
  authors abandoned the open-source project. The record, and what it cost to
  reverse-engineer a tool whose documentation had been taken down, is in
  [`docs/research/14-atopile-postmortem.md`](../docs/research/14-atopile-postmortem.md).

`BOARD=<name>` selects the board; it defaults to `led12`.
