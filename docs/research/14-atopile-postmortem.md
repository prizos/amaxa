# atopile: why the hardware pipeline moved off it

The board design pipeline was built on **atopile** and then moved to SKiDL in
September 2026. This is the record of why, and of what was learned reverse-
engineering a tool whose documentation had been taken down.

It is kept because it is the justification for the move, because several checks
in `hw/checks/` exist only because of what is below, and because the same
failure pattern will happen again with some other dependency.

Nothing here describes how the pipeline works today — see
[`hw/README.md`](../../hw/README.md) for that.

## The project was abandoned

**Its authors abandoned the open-source project.** The public repo's default
branch has had no commits since **2026-03-11**, while PyPI shipped seventeen more
releases with no git tags; in August the maintainers closed roughly twenty of
their own in-flight PRs unmerged. Their own words, 2026-08-06: *"the public
repository has become stale, despite us working full-time on the project."* The
0.15 line is "soft-deprecated" with a removal date "to be announced", there is no
0.16 on PyPI, and the successor is a sign-in-only browser product speaking a
different language. The public documentation is gone.

**Every service that provided something is gone.**
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

## What it was like to get running

- **atopile has no Linux arm64 wheel**, in any of its 171 releases. On arm64 it builds from source in about two minutes, which works as long as uv's own Python (with headers) is used.
- **atopile's parts server is gone** (`components.atopileapi.com` no longer resolves), so its automatic part picker can't run. Parts are specified explicitly and committed instead, each with a review note.
- **atopile's public repo has been frozen since March 2026** while releases keep appearing. It's MIT licensed, so the fallback is forking and pinning. Deciding that is a later milestone.

## How it wanted parts laid out

Undocumented, and reverse-engineered from `faebryk/libs/part_lifecycle.py`:

- **A footprint file must sit in the same directory as the `.ato` file that declares the component.** atopile derives the KiCad library *name* from the footprint's parent directory but the library *path* from the declaring `.ato` file's directory. Keep a footprint anywhere else and the build fails with ``Footprint `X` doesn't exist in library `Y` ``.
- Consequently every part lived at `parts/<LIB>/<LIB>.ato` with its footprint beside it, and directories matching that shape were registered as footprint libraries on every build. The `parts/<LIB>/` shape survives — `tools/board.py` writes an `fp-lib-table` pointing at it — but the `.ato` files are gone.
- A part with no supplier code needs `has_part_removed`, not an empty `has_part_picked` — otherwise it warns "No part found" and silently leaves the part off the BOM anyway. `has_part_removed` says "deliberately not purchased" and is how test pads stay off the BOM.
- Only `lcsc` is accepted as a supplier id. Any other value raises.
- Names collide silently with the standard library. Our test pad was called `TestPoint`, which resolved to the stdlib `TestPoint` (it has `contact`, not `pad`) and failed with ``Field `tp_12v.pad` could not be resolved``.

## What its assertions actually checked

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

## What it did give us

- Deriving a part from a standard-library type (`component Res680 from Resistor`) brings real parameters, a designator prefix, `~>` bridging, and a populated BOM `Value` column. Hand-rolled components get an empty `Value`.
- It warns when **one part number carries two different values** ("Value is not the same for two equal partnumbers"). That is the single most valuable check it ships, because explicit parts make it easy to reuse a 680 Ω part number for a 10 kΩ resistor. We promote that warning to an error.
- `get_bbox_from_geos` ignores arcs and circles (`TODO` stubs upstream), so a footprint whose silkscreen is *only* a circle crashes the build with `min() iterable argument is empty`. Stock `TestPoint_Pad_D1.5mm` is such a footprint; we use `TestPoint_Pad_1.5x1.5mm`, which draws its outline with lines.

