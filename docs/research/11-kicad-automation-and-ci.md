# KiCad as the automation substrate

Verified 2026-09-16 against KiCad source at tag 10.0.6, project documentation, and repository metadata. **[U]** marks unverified claims.

## Version and CLI

**KiCad 10.0.6**, tagged 2026-08-28. 10.0.0 landed 2026-03-19. For Ubuntu runners there is a released PPA, and pinned Docker images exist (below).

`kicad-cli` is a console application, so ERC, DRC, plotting and export need **no X server**. Subcommands at 10.0.6:

- `sch erc`, `sch export {bom, netlist, pdf, svg, dxf, ps, hpgl}`, `sch upgrade`
- `pcb drc`, `pcb export {gerbers, drill, pos, pdf, svg, dxf, ps, gencad, ipc2581, ipcd356, odb, stats, step, stl, glb, ply, brep, vrml, xao}`, `pcb render`, `pcb import`, `pcb upgrade`
- `fp export svg`, `sym export svg`, `jobset run`, `version`

**Exit codes:** `0` OK, `1` bad arguments, `2` unknown, `3` bad input file, `4` output conflict, **`5` rule-check violations**, `6` jobset failed.

Key flags:
- `pcb drc`: `--format report|json`, `--exit-code-violations`, `--severity-all|-error|-warning`, **`--schematic-parity`**, `--all-track-errors`, `--refill-zones`
- `sch erc`: `--format`, `--severity-*`, `--exit-code-violations`
- `pcb export stats --format json`: machine-readable board statistics, useful as a CI tripwire

JSON reports plus non-zero exits are first-class for both ERC and DRC. `--schematic-parity` catches "the board no longer matches the schematic", which is the characteristic AI-authored failure.

## Custom design rules

`.kicad_dru` sits next to the project as plain, diffable text. All 35 constraint types at 10.0.6:

`assertion, clearance, creepage, hole_clearance, edge_clearance, hole_size, hole_to_hole, courtyard_clearance, silk_clearance, text_height, text_thickness, track_width, track_angle, track_segment_length, connection_width, annular_width, via_diameter, via_dangling, zone_connection, thermal_relief_gap, thermal_spoke_width, min_resolved_spokes, solder_mask_expansion, solder_mask_sliver, solder_paste_abs_margin, solder_paste_rel_margin, disallow, length, skew, via_count, diff_pair_gap, diff_pair_uncoupled, physical_clearance, physical_hole_clearance, bridged_mask`

Condition functions include `existsOnLayer()`, `isPlated()`, `intersectsCourtyard()`, `intersectsArea()`, `enclosedByArea()`, `isMicroVia()`, `memberOfGroup/Footprint/Sheet()`, `fromTo()`, `isCoupledDiffPair()`, `inDiffPair()`, `getField()`, `hasNetclass()`, `hasComponentClass()`, plus properties such as `A.NetClass`, `A.Type`, `A.Layer`, `A.Width`.

That is enough to encode the control board's intent mechanically: Ethernet `length`/`skew` windows, USB `diff_pair_gap` and `diff_pair_uncoupled`, `via_count` caps on clock nets, `memberOfSheet('/Power/')`-scoped `track_width`, and `creepage` plus `physical_clearance` for the power boards. `assertion` allows arbitrary boolean invariants. Severity and layer are per rule.

**Severities are text.** They live in the project file (`rule_severities`, `erc_exclusions`, `drc_exclusions`), so "which warnings are errors" is reviewable in a diff rather than hidden in a GUI. The same mechanism is how a violation gets silenced, so changes there need human sign-off.

## File formats and diffability

Schematic, board, symbol, footprint and rules files are S-expression text; the project file is JSON. The local UI state file should be git-ignored.

The diff problem is real but bounded: every object carries a random UUID and KiCad rewrites whole files on save. Moving one footprint rewrites its coordinates in place, which reads fine, but adding items or re-annotating churns UUIDs. So line diffs work for small targeted edits and not for large ones, which is why the visual-diff step is not optional. **Do not expect three-way merges to work**; serialise board edits on a branch.

## Ecosystem (verified live)

| Tool | Version | Notes |
|---|---|---|
| **KiBot** | 1.9.1 (2026-07-28) | Orchestration: declarative YAML of checks and outputs |
| **KiKit** | 1.8.1 (2026-08-05) | Panelisation, fab exports, stencils |
| **KiDiff** | 2.6.0 (2026-06-01) | PDF/PNG visual diff; installs as a `git diff` driver |
| **KiRi** | – | Browsable side-by-side schematic and board diff; CLI only, also a KiBot output |
| **InteractiveHtmlBom** | 2.12.0 (2026-09-10) | Interactive BOM for assembly and review |
| **freerouting** | 2.4.1 (2026-09-03) | Headless autorouting; see caveat |
| **easyeda2kicad** | 1.0.1 (2026-04-06) | Pulls LCSC/JLCPCB parts into KiCad libraries |
| **kicad-python (kipy)** | 0.8.0 (2026-08-30) | Bindings for the IPC API |

**KiBot** has 18 preflights, including `erc`, `drc`, `check_fields`, `check_zone_fills`, `fill_zones`, `filters`, `draw_stackup`, `update_stackup`, `set_text_variables`. Its DRC options include `schematic_parity` (default true), JSON output, `warnings_as_errors` and `all_track_errors`. It has a Docker-based GitHub Action (`INTI-CMNB/KiBot@v2_k10`) and current images: `ghcr.io/inti-cmnb/kicad10_auto:1.9.1`, plus a `_full` variant that adds Blender for renders.

Gating needs nothing special, because a non-zero exit fails the job. Its exit codes: `5` DRC error, `10` ERC error, `11` BOM error, **`29` diff too big**, **`30` netlist diff**, `36` warnings as errors, `39` warnings (only fatal with `--fail-on-warnings`). Codes 29 and 30 matter: the "how much changed since the last commit" gate is **built in**, not something to construct on top of the diff tool.

Two CI details from its documentation: pass `fetch-depth: 0` to checkout, or the diff outputs have nothing to compare against; and upload artifacts with `if: ${{ always() }}` so reports survive a failing check. `navigate_results` builds an HTML index of every output, which is the mechanism behind the published review sites in [13](13-hardware-ci-practice.md).

**Autorouting caveat:** `kicad-cli` has **no Specctra DSN export** (GUI only), so headless autorouting needs GUI automation. For a board with Ethernet and USB the router output is not review-grade anyway. Out of scope.

**IPC API caveat:** the KiCad 9/10 IPC API is protobuf over a socket and **requires a running KiCad instance**, so it is not a headless CI mechanism. A headless API server is expected in KiCad 11 **[U]**. The older scripting interface works headless in 9 and 10 but is removed in 11. For CI, prefer `kicad-cli` plus parsing the S-expressions or the exported netlist.

## CI shape

```yaml
jobs:
  verify:
    runs-on: ubuntu-24.04
    container: ghcr.io/inti-cmnb/kicad10_auto:1.9.1
    steps:
      - uses: actions/checkout@v7
        with: { fetch-depth: 0, submodules: recursive }   # libraries pinned as submodules

      # Gate 1: raw kicad-cli, fails the build
      - run: kicad-cli sch erc --severity-error --exit-code-violations
               --format json -o out/erc.json hw/ctrl/ctrl.kicad_sch
      - run: kicad-cli pcb drc --severity-error --exit-code-violations
               --schematic-parity --all-track-errors --refill-zones
               --format json -o out/drc.json hw/ctrl/ctrl.kicad_pcb

      # Gate 2: library provenance (KiCad's own library checker, JUnit output)
      - run: python3 libs/kicad-library-utils/klc-check/check_footprint.py
               --junit out/klc-fp.xml hw/ctrl/amaxa.pretty/*.kicad_mod

      # Gate 3: KiBot for artifacts and diffs
      - uses: INTI-CMNB/KiBot@v2_k10
        with: { config: hw/ctrl/amaxa.kibot.yaml, dir: out, additional_args: --fail-on-warnings }
```

Expect roughly **3–8 minutes** for a 6-layer board; DRC is the long pole and Blender renders add more **[U, not benchmarked on our design]**.

## Library correctness: what is mechanically checkable

This is where an AI-authored board is most likely to be wrong, and the honest answer is *partially*.

**Pinning.** The official symbol, footprint and 3D-model libraries are tagged in lockstep with KiCad (all at 10.0.6). Add them as submodules pinned to a tag and point the project's library tables at them, so libraries are part of the reviewable diff. Never rely on the runner's system libraries.

**Checkable.** KiCad's own `kicad-library-utils/klc-check/` provides footprint, symbol, library-table and 3D-coverage checks with JUnit output, plus `comparelibs.py` to diff a library against a baseline (which catches an agent silently mutating a shared symbol). These catch courtyard presence and clearance, silkscreen over pads, pad numbering conventions, missing 3D models, text on wrong layers, and missing datasheet fields. KiBot's `check_fields` enforces that every part carries a part number, LCSC code and datasheet matching a pattern.

**Not checkable.** Whether the footprint matches the datasheet. The library checker verifies *conventions*, not *dimensions*: nothing compares an LQFP144 land pattern to ST's recommendation, and nothing catches two pins swapped in a symbol. The LCSC converter's own README says its output "can't be guaranteed" and must be double-checked. Treat every generated part as needing a human datasheet check, recorded in the repo as a reviewed note naming the datasheet revision.

## Failure modes CI will not catch

1. **Wrong pin mapping or footprint dimensions.** The largest risk. ERC passes happily on a schematic wired to the wrong pins.
2. **Electrically wrong but legal schematics.** No check that each VCAP pin has its capacitor, that BOOT0 is strapped, or that CAN termination exists, unless we write that check.
3. **No simulation from the CLI.** KiCad's simulator is GUI-only, so analog verification happens in ngspice ([12](12-circuit-simulation.md)).
4. **Impedance.** The stackup is declared, not solved. Length and gap rules enforce only what we author.
5. **Power and thermal integrity.** No current density, copper weight or IR-drop checks.
6. **Component selection.** No derating, temperature grade or lifecycle checking.
7. **Creepage intent.** The constraint exists, but only enforces the rule we write. Author it from the standard by hand and protect the file.
8. **Silenced violations.** Exclusions and filters can turn a red build green.
