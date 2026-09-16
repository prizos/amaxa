# amaxa hardware

Boards designed as code: **atopile** (`.ato`) is the design source, **KiCad** holds the layout and runs the rule checks, **ngspice** simulates the analog behaviour, and CI gates all of it. The reasoning behind these choices is in [`docs/research/09-board-design-pipeline.md`](../docs/research/09-board-design-pipeline.md).

The first board, `led12`, is a 12 V LED board with no processor. It exists to prove the pipeline end to end before the STM32H743 control board depends on it.

**Status:** M1 — toolchain pinned and working. No board yet.

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
├── Makefile                 front end: tools, versions, (build/check/sim to come)
├── requirements/            atopile dependency lock
└── led12/                   the example board (M3 onwards)
```

## Verified findings

Facts established while setting this up, worth not rediscovering.

### Getting it running

- **atopile has no Linux arm64 wheel**, in any of its 171 releases. On arm64 it builds from source in about two minutes, which works as long as uv's own Python (with headers) is used.
- **atopile's parts server is gone** (`components.atopileapi.com` no longer resolves), so its automatic part picker can't run. Parts are specified explicitly and committed instead, each with a review note.
- **atopile's public repo has been frozen since March 2026** while releases keep appearing. It's MIT licensed, so the fallback is forking and pinning. Deciding that is a later milestone.

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
| `make clean` | Remove build outputs |
| `make distclean` | Also remove the venv and downloaded tools |
