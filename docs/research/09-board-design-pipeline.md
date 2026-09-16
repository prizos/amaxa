# Board design pipeline (recommendation)

Researched 2026-09-16. How we design the boards: an agent authors the design as text in this repo, command-line tools prove it correct in CI, and humans review diffs and rendered artifacts.

Detail behind each choice: [10](10-schematic-as-code-tools.md) (authoring), [11](11-kicad-automation-and-ci.md) (checks), [12](12-circuit-simulation.md) (simulation), [13](13-hardware-ci-practice.md) (CI practice).

## The stack

| Layer | Tool | Why |
|---|---|---|
| Design source | **atopile** (`.ato`), forked and pinned | Declarative, with units and tolerances. Assertions become build failures; it picks parts against constraints and writes the KiCad files. Ships agent instructions and an MCP server |
| Fallback / power-board option | **SKiDL** (Python) | No assertions or part picking, but the same source can feed ngspice |
| Layout | **KiCad 10, by hand** | No open-source router is good enough for Ethernet, USB and CAN on 4–6 layers. Code owns connectivity and values; a human owns geometry |
| Blocking checks | **kicad-cli** (ERC, DRC, schematic parity), custom `.kicad_dru` rules, a pytest suite | Headless, JSON reports, non-zero exit codes |
| Review artifacts | **KiBot 1.9.1** (pinned Docker image, GitHub Action) | Schematic PDFs, board renders, 3D, interactive BOM, visual diffs against the previous commit |
| Parts | KiCad libraries pinned as submodules, the official library checker, a per-part review file | Where the real risk sits |
| Power simulation | **ngspice 45.2** with measurement assertions | 50 switching cycles in 1 s (measured); a suite runs in seconds |
| Control simulation | **Renode** stepping the firmware against a simplified plant model | Reuses the existing firmware pipeline |
| Later, if needed | PLECS (control loops, thermal), Xyce (hard convergence) | Commercial, or packaging friction |

## The authoring loop
1. **Write `.ato` source:** modules, connections between interfaces rather than 144 hand-typed pins, part constraints, and assertions (rail tolerances, divider ratios, CAN termination, crystal load caps).
2. **The compiler proves the arithmetic**, picks parts that satisfy the constraints, fails when none is in stock, and writes the KiCad netlist and board.
3. **A human routes the board in KiCad.** Repeated blocks (decoupling clusters, gate-drive loops) are laid out once and reused.
4. **CI rebuilds in frozen mode**, so it fails if the committed board no longer matches the source, then runs every gate below.
5. **The pull request carries the artifacts** a reviewer actually reads.

## What CI blocks on

| Gate | Catches |
|---|---|
| ERC | Unconnected or undriven pins, including supply pins never connected |
| DRC | Clearance, track width, annular ring, hole sizes, courtyard overlap, creepage (isolated power boards) |
| **Schematic-versus-board parity** | The board drifting from the schematic. The characteristic AI-authored failure |
| Custom rules (`.kicad_dru`) | Ethernet length and skew windows, USB differential pairs, via limits on clock nets, fab capability limits |
| Custom pytest checks | Every supply pin decoupled within a set distance, crystal caps, pull-ups, ADC reference filtering. What the rules language can't express |
| **Pin assignment versus silicon** | A machine-readable STM32H743 database gives all 144 pin positions and alternate-function numbers, so a wrong pin number fails the build |
| Firmware agreement | `firmware/bsp/.../board.h` is generated from the schematic; CI fails if the committed copy is stale |
| Simulation regressions | Power-board behaviour against committed golden values with tolerances |
| Check-count assertion | A check that silently didn't run (wrong path or runner label) fails the build |

Two gates come free rather than needing to be built: KiBot exits with distinct codes for **"diff too big"** and **"netlist changed"** against a git reference, which catches an agent quietly re-routing half the board, and KiKit's fab export runs DRC before packaging.

**Governance rule, more important than any single check:** severities and exclusions live in text files, so an agent silencing a failing check appears in the diff. Any change to `.kicad_pro`, `.kicad_dru` or the check scripts needs human approval. Separately, guard against **silent skips**: assert that the expected number of checks actually ran.

Non-blocking on each pull request: schematic PDF and SVG, board renders per variant, 3D model, interactive BOM, ERC/DRC reports in the job summary, and a BOM diff. **Publish these as a site rather than PR comments** — that is what every project doing this well does, and GitHub renders no EDA format natively ([13](13-hardware-ci-practice.md)).

One check we must write ourselves: **no off-the-shelf tool fails CI when a BOM line is out of stock.** Build a thin script over the exported BOM, and make it a warning on pull requests but an error on release tags, since vendor stock is nondeterministic.

## Simulation, in three tiers
1. **Circuit level (ngspice, seconds per test).** Dead-time, peak current, gate drive, overshoot, per-device loss. Safe-operating-area checking is free: any device beyond its ratings fails the build. Junction temperature is computed arithmetically from measured average power rather than simulated.
2. **Control level (Renode plus a plant model).** Step the real firmware, read its PWM decisions, advance a simplified model, feed back ADC values, assert on the trajectory. Run it at the control-loop rate, not the switching rate.
3. **Not automated: EMC and signal integrity.** Enforced by layout rules and human review.

Vendor device models are copied into the repo with a record of source URL, date and part number, because vendor sites move and block downloads.

## Human sign-off before fabrication
No pipeline we can build catches these:
- **Every footprint checked against its datasheet drawing**, including pin 1 and pad numbering. The most likely and most expensive failure.
- **Power-up sequencing and inrush.**
- **Connector genders, keying and mating orientation.**
- **Thermal path** for shunts and switches at high current.
- **Creepage and clearance across any isolation barrier**, against the standard rather than the number in our rules file.
- **A visual review of the exact gerbers being ordered.**

## Suggested order of work
1. **Prove the pipeline on a trivial board.** Repo skeleton, pinned atopile fork, pinned KiCad container, CI workflow. Deliberately break a rule and confirm the gates fail.
2. **Control board.** Rails, the H743 with decoupling and boot straps, crystal, SWD, USB, Ethernet, CAN, and the power-board interface. Custom rules and the pin-assignment check.
3. **Power board.** ngspice decks and assertions, creepage rules, vendored device models.
4. **Bring-up.** Extend `firmware/apps/hello_hw` into a self-test that reads every rail and exercises each PWM output.

**Design in from the start:** test points on every rail, Kelvin sense pads at the shunts, isolation links, and a Tag-Connect debug footprint (about the area of two or three small resistors, no connector fitted). Wire `kicad-cli pcb export ipcd356` into the release job to produce the flying-probe netlist. Don't count on JTAG boundary scan until ST's description file for the H743 is confirmed to exist — the vendor site blocked access during this research.

## Proposed repo layout

```
hw/
├── ctrl/                  control board
│   ├── src/*.ato          design source
│   ├── parts/             generated part files + a reviewed <mpn>.md per part
│   ├── layout/            KiCad project, board, custom rules
│   └── checks/            pytest design assertions
├── power/                 power boards (same shape)
│   └── sim/               ngspice decks, vendored device models, golden values
├── libs/                  KiCad libraries pinned as submodules
└── fab/                   fab capability rules (e.g. jlcpcb.kicad_dru)
```

## Open decisions
1. **Fab house.** Their capability limits become our rule file.
2. **atopile or SKiDL.** atopile is much better suited, but its upstream looks abandoned, so we would own a fork. SKiDL is duller and safer.
3. **Who routes the boards:** us, an agent working in KiCad, or a contractor.
4. **Whether to buy PLECS later** for control-loop and thermal work.

## There is no prior art to copy
A sweep of large open-hardware organisations found real KiCad sources almost everywhere and design-rule-gating CI almost nowhere. Of everything examined, only KiBot's own demo repository cleanly gates a merge on ERC and DRC. That cuts both ways: nothing to lean on, and no reason to assume the known gaps (footprint versus datasheet, power sequencing, thermal, EMC) have quietly been solved by someone else.

## Caveats on this research
- The session's web-search quota was exhausted, so the agents verified named tools against their docs, repos and real CI workflow files rather than discovering alternatives. A fresh session could search more broadly.
- The simulation findings were **measured** by installing and running ngspice ([12](12-circuit-simulation.md)). The rest comes from documentation and source repositories.
- **[U]** marks claims that were not verified.
