# Schematic and PCB "as code" tools

Researched 2026-09-16, against project docs and repositories (no web search available this session). **[U]** marks unverified claims.

**Conclusion:** only **atopile** matches the requirement (text source → CLI-proven → KiCad layout) for a 144-pin STM32H743 board today, with a caveat about its upstream. **SKiDL** is the low-risk fallback and the better answer for the power boards, because the same Python can be simulated.

## Comparison

| Tool | Produces | Layout / routing | Licence | Headless CI | Activity (verified 2026-09-16) | Verdict |
|---|---|---|---|---|---|---|
| **atopile** | Netlist, writes `.kicad_pcb` directly, BOM, pick-and-place, test points, power tree, docs | **None.** Place and route by hand in KiCad; module layout *reuse* only | MIT | Yes (`ato build`), Python **3.14 only** | Package index 0.15.9 (2026-09-12); **repo frozen since 2026-03-11**, last tag v0.14.1004 (2026-02-12); 3.9k stars | **Primary, as a pinned fork** |
| faebryk | – | – | MIT | – | **Archived 2024-12-10**, merged into atopile | Not a separate choice |
| **tscircuit** | circuit-json → gerbers, KiCad files, Specctra DSN, **SPICE**, STEP/glTF, SVG | Own engine and autorouter; coordinates still often manual | MIT | Yes | v0.0.2562 published 2026-09-15; ~290k downloads/month; 2.7k stars, 17 contributors | No for board 1; revisit for board 2 |
| **SKiDL** | KiCad netlist, optional board and generated schematic | Schematic placement only; no PCB routing | MIT | Yes (plain Python) | 2.3.0 (2026-07-28), commits 2026-08 | **Fallback + power-board simulation** |
| **JITX** | Schematic, board, constraint-driven autorouting | Automatic, solver-driven | Commercial, closed | Claimed [U] | Migrating from Stanza to Python | No — unverifiable |
| Horizon EDA | GUI project files | Manual; autorouting is an explicit non-goal | GPL-3.0 | CLI is development-only | v2.7.2 (2025-12-05), active | No — not code-first |
| LibrePCB | GUI project files | Manual | GPL-3.0 | **Good** (`--erc --drc`, exit 1) | 2.1.1 (2026-06-12) | No — a checker, not an author |
| kicad-skip | Edits KiCad files directly | n/a | LGPL-2.1 | Yes | **Last commit 2024-02-16** | Optional scalpel only |

## atopile

**What it produces.** A compiler for a declarative `.ato` language. It solves constraints, picks parts, runs checks, and updates the KiCad layout in place. Its own documented flow ends with "Layout — place and route in KiCad". There is no autorouter and no auto-placer; there is module layout *reuse*.

**Testability, the differentiator.** Real units, tolerances and a constraint solver:

```ato
assert r_top.resistance is (v_in - v_out) / max_current
assert my_vdiv.power.voltage is 10V +/- 1%
assert my_vdiv.output.reference.voltage within 3.3V +/- 10%
assert my_vdiv.max_current within 10uA to 100uA
```

Rail tolerances, divider ratios, CAN termination and series-resistor values become failing builds rather than review comments. Real assertions in their own projects include `assert shunt_heat_power < max_power_dissapation`.

**The 144-pin problem is handled two ways.** You connect interfaces, not pins:

```ato
i2c ~ nfc.i2c
power_3v3 ~ touch.power
led_data ~> level_shifter ~> leds[0] ~> leds[1] ~> leds[2]
```

And the part file itself is generated non-interactively (`ato create part --search "STM32H743VIT6" --accept-single`), carrying footprint, symbol and 3D model references plus a **checksum** proving nobody hand-edited it.

**CI determinism is first-class.** `ato build --frozen` means "the board must rebuild without changes", with `--keep-picked-parts`, `--keep-net-names` and `--keep-designators` so nothing churns between runs. Dependencies are version-pinned in `ato.yaml`.

**Agent-friendliness.** The repo ships an agent instructions file, and the CLI includes an MCP server (`ato mcp start`) and a language server.

**Evidence of real boards.** Their own repos include a Raspberry Pi CM5 smart speaker (~200 pins, plus DSP, amplifier and USB-PD parts), a servo drive, an 18-channel cell simulator, and hardware-in-the-loop boards.

**The caveat.** Public `main`'s newest commit is 2026-03-11 and the newest tag is 2026-02-12, yet the package index shipped 0.15.0 → 0.15.9 between April and September 2026 with no matching commits. The packages site now redirects to a sign-in-walled cloud workspace, and deep links in the project's own README 404. Read together: the open-source repo is a stale snapshot while the live product closes up. It is MIT licensed, so **fork it, pin it, vendor it, and treat it as a compiler we own**. Budget for its hard Python 3.14 requirement in the CI image.

## The others

**tscircuit** is the most active project assessed, with the best export list (`gerbers | kicad_pcb | kicad_sch | specctra-dsn | spice | step | glb | pcb-svg`) and a well-specified intermediate format. Three things rule it out for board 1: it is 0.0.x with 17 contributors; its registry has **no STM32H7 parts**, so we would author the LQFP144 part anyway; and its differentiator is an immature in-house autorouter on exactly the traces (Ethernet, USB, CAN) that need impedance control and length matching. Worth revisiting for the power board, where the SPICE and DSN exports are useful.

**SKiDL** is the boring hedge: generates a KiCad netlist, has built-in electrical rule checks, and leans on stock KiCad symbol libraries, which already contain STM32H7 symbols, so pin mapping comes by name. It has no units, tolerances, assertions or part picking. Its advantage for the power boards is `skidl.pyspice`: the same source can be netlisted **and** simulated.

**JITX** is the only tool that would actually route the board, with constraint-driven autorouting and a field-solver optimisation loop. But it is closed source, behind a login, with no published pricing, and its documentation site served only "this page has moved" during the research. Everything about its CI fitness is **[U]**. Worth a sales conversation for high-current layout later; not something to build a pipeline on unseen.

**Horizon EDA** and **LibrePCB** are healthy GUI packages, but neither supports design-as-code. LibrePCB has the cleanest exit-code contract of any EDA CLI (`--erc --drc` returns 1 on unapproved violations), but we get the same from KiCad.

**kicad-skip** gives Pythonic access to KiCad files, but its last commit was February 2024. Use it for one-off post-processing, not infrastructure.

## What none of them will do

Nothing open-source will place and route a 4–6 layer STM32H743 board with Ethernet, USB and CAN to a quality worth manufacturing. atopile does not try; tscircuit tries and is not there; Horizon calls it a non-goal. Plan for human layout with length matching and impedance control, and let the code own **connectivity, part selection, values and assertions**, which is where the diffs and the CI value are.
