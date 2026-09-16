# Hardware CI in practice

Researched 2026-09-16 by reading real CI workflow files in public repositories. **[U]** marks unverified claims.

**Headline:** real KiCad sources are everywhere and design-rule-gating CI is almost nowhere. What we are building is ahead of open-hardware practice, which cuts both ways: no prior art to lean on, and no reason to assume the known gaps have quietly been solved by someone else.

## Check catalogue

| Check | Catches | Tool | Can gate CI? |
|---|---|---|---|
| ERC | Unconnected and undriven pins, power inputs never driven, duplicate references, bus and label conflicts, symbols that drifted from the library | `kicad-cli sch erc --exit-code-violations` | **Yes** |
| DRC | Clearance, track width, annular ring, hole sizes, edge clearance, courtyard overlap, silkscreen, **creepage**, copper slivers | `kicad-cli pcb drc --exit-code-violations` | **Yes** |
| **Schematic ↔ board parity** | Missing, extra or duplicated footprints; pad nets that don't match the schematic | `kicad-cli pcb drc --schematic-parity` | **Yes — the anti-drift gate** |
| Custom design rules | Net-class track widths, differential-pair gap and uncoupled length, per-path length and skew, thermal relief, plus arbitrary boolean assertions | `.kicad_dru` in-repo | **Yes** |
| Design assertions rules can't express | Every supply pin decoupled within N mm, crystal load caps, pull-ups, ADC reference filtering | Custom pytest over the exported netlist and the board file | **Yes, but we write it** |
| **Pin assignment vs silicon** | Wrong pin number on a 144-pin symbol; a peripheral on a pin that doesn't support it; wrong alternate-function number in firmware | Machine-readable STM32H743 data (all 144 positions, alternate functions, and the 11 VDD / 9 VSS / VDDA / VREF+ / VBAT / 2 VCAP / USB supply pins) | **Yes — highest-value custom check** |
| Firmware agreement | `board.h` drifting from the schematic | Generate it, then `git diff --exit-code` | **Yes** |
| Unresolved TODOs | Work an agent left unfinished | KiCad error text variables raise named violations | **Yes** |
| BOM, lifecycle, stock | End-of-life, no stock, no alternates, cost | See the negative result below | **Yes, as a warning on PRs and an error on release** |
| Variants / do-not-fit | "Fitted on rev A, not fitted on rev B" mistakes | KiCad 10 native variants; export and render every variant | **Yes** |
| Stackup and impedance | Track widths inconsistent with the ordered stackup | No open field solver worth gating on. Pin the numbers as rules and assert the stackup file matches what was ordered | Partially |
| Fab capability | Features below the fab's limits | Transcribe the fab's limits into a rules file | Yes, once transcribed |
| Simulation regression | Drift in power-stage behaviour | pytest with committed golden values and explicit tolerances ([12](12-circuit-simulation.md)) | Yes |
| Visual regression | Unintended layout or schematic change | Committed SVG snapshots, or KiBot's built-in diff exit codes | Yes |

**Two useful defaults found:** KiBot stops on ERC/DRC errors out of the box, and KiKit's fab export runs DRC by default, so the export step itself refuses to package a board with violations.

## Real pipelines

| Project | What it runs | Gates merges? |
|---|---|---|
| **KiBot's own demo repo** (`kibot_variants_arduprog`) | Separate ERC and DRC jobs, then three variant builds that each depend on both passing. A separate workflow publishes the result site to GitHub Pages | **Yes** — the only cleanly merge-gating example found |
| **atopile projects** (servo drive, hardware-in-the-loop, speaker board) | `ato build` on every push and PR, artifacts uploaded | Yes, on build success |
| **tscircuit** | `tsci build` fails on design-rule violations by default; ~24 named checks run inside every build; SVG snapshots committed and diffed, with the difference image uploaded on failure | Yes |
| **Zener (`diodeinc/pcb`)** | In-language `check()` / `error()` / `warn()`; a companion action detects boards and builds them in parallel | Yes |
| **Opulo LumenPnP** | KiBot gerbers for 8 boards plus mechanical exports | **No** — release and manual runs only |
| **ElectronicCats KiCad template** | Schematic PDF, interactive BOM, BOM CSV, fab packages for two vendors | Build success on PRs |
| **etrommer/ultramote** | KiBot outputs auto-committed, then a static site deploys | Yes, on push and PR. Closest match to "reviewers get a published site" |
| **efabless chip precheck** | Licence, documentation, consistency, XOR against the user area, Magic DRC, KLayout checks, layout-versus-schematic | **Every failure blocks tapeout.** The closest analogue to what we want |
| **lowRISC OpenTitan** | Self-hosted FPGA runners that flash bitstreams and power-cycle USB | Yes, genuine hardware-in-the-loop |

**What `ato build` actually gates on** (verified in its source): assertions compile to real interval-solver constraints; a five-stage check pipeline; its own electrical rule checks (shorted power nets, shorted passives, multiple sources shorted); a real `kicad-cli pcb drc` invocation; and the part picker fails the build when no stocked part satisfies the constraints.

**Negative results, and they matter.** A sweep of large hardware organisations found real KiCad sources with no design-rule CI at all: OLIMEX (12 repos, no CI), Oxide Computer's board repos, SparkFun (documentation publishing only), Nitrokey, keyboardio, Precursor. Two corrections worth recording: **Adafruit's product boards are Eagle, not KiCad**, and **ODrive designs in Altium**, so neither is a KiCad-CI datapoint. Of everything checked, only KiBot's own demo repo cleanly gates a merge on ERC and DRC.

**One pattern worth stealing:** Winterbloom's synth boards use a local pre-commit hook that fails the commit when the schematic PDF is stale after a schematic change. That is the same "generated artifact is up to date" check we want for `board.h`, run client-side.

## Review artifacts

- **GitHub renders no ECAD format.** It renders images, STL (interactive 3D), CSV, PDF and Markdown, and diffs none of the EDA formats. A committed STL gets a free 3D viewer but no diff.
- **Publish a site, don't post comments.** Every real project that surfaces results uses GitHub Pages or release assets. Sticky PR-comment bots were searched for across ~15 hardware repos and **not found**. KiBot's `navigate_results` builds the browsable index; its demo site shows the target contents: DRC and ERC reports, an embedded board viewer, schematic diffs, PDFs and renders, board statistics, per-vendor fab packages, position files, interactive BOM, 3D models, and BOM in several formats.
- **Diff gates are built in.** KiBot's diff output compares against a git reference and has exit codes for "diff too big" (29) and "netlist changed" (30). That catches an agent quietly re-routing half the board, without building anything ourselves. KiRi gives a browsable side-by-side diff; KiDiff can also install as a `git diff` driver for board files.

## Bring-up and post-fabrication

- **Export the test netlist.** `kicad-cli pcb export ipcd356` produces the bare-board netlist that flying-probe testers use, natively.
- **Bare-board test economics.** Eurocircuits: electrical test is standard for boards of two or more layers; flying probe tests every net but is slow, while a fixture-based tester cuts test time by about 90% once a known-good board exists. Flying probe has no fixture cost, so it suits prototypes; fixtures amortise only over volume **[U on break-even]**.
- **Assembly inspection.** JLCPCB performs automated optical inspection on both service tiers, and states X-ray inspection is required for packages with hidden joints such as BGA, QFN and LGA. Their flying-probe or in-circuit test offerings weren't found **[U]**.
- **Boundary scan.** OpenOCD can play back standard boundary-scan vector files, so it's a legitimate tool, not just a debugger. It catches opens, shorts and dead or reversed digital parts, including under BGAs, but not analog nets, passive values or most supply pins. **The STM32H743 boundary-scan description file could not be verified because the vendor site blocked access [U]** — confirm before relying on it.
- **Debug connector.** Tag-Connect's spring-pin footprint takes about the space of two or three small resistors, needs no connector fitted on the board, and is rated beyond 100,000 operations. Verified in real use as a drop-in for the standard ARM header.
- **Precedents for structured bring-up:** Opulo publishes a sequenced pass/fail bring-up flow with per-failure diagnosis; Winterbloom has real factory tooling that flashes, waits for enumeration and resets; ODrive's calibration measures motor resistance, inductance and encoder offset on real hardware; Zephyr runs board test suites on real silicon.

**Design in from the start** (recommendation, not a verified standard): test points on every rail, Kelvin sense pads at the shunts, isolation links, a Tag-Connect debug footprint, and a self-test built on `firmware/apps/hello_hw` that reads back every rail through the ADC and exercises each PWM output.

## Negative result on BOM checks

**No off-the-shelf "fail CI if a BOM line is out of stock" tool exists.** The nearest project is a scheduled catalogue builder for LCSC parts, not something you point at your own BOM. Fab exporters do format conversion from a user-supplied field with no live stock check. So that row in the table is buildable but **we would be writing it**, most practically as a thin script over KiCost or the Nexar API (free tier: 100 matched parts) consuming the exported BOM. Keep it a warning on pull requests and an error on release tags, because vendor stock is nondeterministic and would otherwise redden unrelated changes.

## Review and sign-off flow

**Blocking on every pull request:** ERC, DRC with schematic parity, custom rules, custom pytest assertions, the pin-assignment check, generated-header freshness, the firmware build and its emulator tests, and a TODO-marker check.

**Non-blocking artifacts:** schematic PDF and SVG, board renders per variant, 3D model, interactive BOM, reports in the job summary, BOM diff, and a published review site.

**Governance:** severities and exclusions live in text files, so an agent downgrading or excluding a check shows up in the diff. **Require human approval on any diff touching the project file, the rules file, or the check scripts.** Treat that as the single most important review rule.

**Guard against silent skips.** A check that no-ops because a path or runner label didn't match is worse than no check. Assert that the expected number of checks actually ran. One real project tags its hardware tests to a specific machine, so on a normal runner every hardware test silently skips.

## Residual risks

Catchable: schematic-to-layout drift, unconnected supply pins, clearance and creepage, differential-pair skew, BOM and placement inconsistency for unfitted parts, stale generated headers, dead parts, silenced checks.

**Not catchable by any pipeline we can build:**
- **Footprint versus datasheet.** Nothing verifies a footprint's dimensions against a PDF. Highest-frequency, highest-cost AI failure. Mitigate with vendor-supplied footprints, a pad-count-versus-pin-count check, and a human.
- **Power sequencing and soft start.** A temporal property; only simulation or bench proves it.
- **Thermal.** No CI thermal solve. At 300 A, copper weight, via stitching and airflow are engineering judgement.
- **EMC.** Untestable before fabrication, and the dominant risk on a switching power board.
- **Gate-driver layout:** loop area, Kelvin returns, bootstrap placement. Geometrically checkable only if a human writes the rule first.
- **Connector orientation and keying**, or a shunt sense tapped on the wrong side of a device: schematically legal, physically wrong.
