# Circuit and power simulation as CI tests

Researched 2026-09-16. Unlike the other tracks, **the ngspice findings here were measured**: the agent installed ngspice locally and ran the simulations. Runtimes are from an arm64 machine, single core. **[U]** marks unverified claims.

## Comparison

| Tool | Licence / cost | Linux CI | Scripting | Assert on | Switching runtime |
|---|---|---|---|---|---|
| **ngspice 45.2** | Open source | `apt install ngspice` | `.control` blocks, shared library, `spicelib` | `.meas` → stdout → parse | **1.0 s** for 50 cycles at 100 kHz (measured) |
| **Xyce 7.10** | GPL-3.0, free | **RHEL8 RPM only**, no Debian package | Netlist, `-remeasure` | `.MEASURE`, CSV output | Not run (no Ubuntu package) |
| PySpice 1.5 | GPL-3.0 | pip | Python | Python | **Unmaintained** (last release 2021) |
| **spicelib 1.6.3** | GPL-3.0 | pip | Python | Waveform and log parsing | Wrapper only |
| **PLECS** | Commercial | Yes (needs X libraries) | XML-RPC and JSON-RPC on port 1080 | Python arrays directly | Fast (ideal switches) |
| SIMBA | Free tier, then paid | **Windows and macOS only** | Python API, FMI | Python | – |
| SIMetrix/SIMPLIS | Free "Elements" tier | Windows-focused **[U]** | Own script language | – | Claims 10–50× SPICE |
| QSPICE | Free **[U]** | Vendor site blocked automated access | – | – | – |
| LTspice | Free, EULA-restricted **[U]** | Wine **[U]** | `spicelib` | `.meas` log | – |
| GeckoCIRCUITS | GPL-3.0 | Java, yes | Python wrapper | Python | – |

## Verified ngspice results

A 400 V, 100 kHz synchronous half-bridge with VDMOS devices, split turn-on/turn-off gate resistors, loop inductance and an output filter:

| Simulation | Timepoints | Wall clock |
|---|---|---|
| 500 µs (50 cycles) | 253 k | **1.0 s** |
| 5 ms (500 cycles) | 518 k | **2.2 s** |
| 3 ms with 2 electro-thermal devices | 619 k | **3.9 s** |

Fast enough that a whole suite of power-stage regressions runs in seconds. No convergence trouble at default settings.

**The assertion loop works end to end.** Measurements print to stdout, a ~30-line dependency-free Python script range-checks them and exits non-zero. Injecting a regression (dead-time cut from 150 ns to 40 ns) failed only the relevant assertion:

```
FAIL  deadtime   =    3.61e-08 s  (limit 1.2e-07 .. 2.2e-07)
```

Measured cleanly in the good case: switch-node peak 399 V, gate drive 12.0 V, peak current 37 A, dead-time 157.5 ns, output ripple 7.1 V.

## ngspice specifics worth knowing
- **Measurement types:** `TRIG/TARG`, `FIND/WHEN`, `AVG | MIN | MAX | PP | RMS | MIN_AT | MAX_AT`, `INTEG`, `DERIV`, `param`.
- **Safe-operating-area checking is a free CI gate.** Enable warnings and a SOA log, and put `Bv_max`, `Id_max`, `Pd_max`, `Te_max` on the model lines. A non-empty log fails the build. Gotcha: the option must be a dot-card, not inside a `.control` block.
- **Electro-thermal devices work.** A VDMOS with thermal nodes plus an external thermal network makes junction temperature a node voltage you can measure directly (measured 19.7 K and 24.7 K rise, 64.7 °C junction at 40 °C ambient).
- **Per-device loss:** save the device current, multiply by its voltage, take the average.
- **Vendor models:** a compatibility mode accepts LTspice and PSpice syntax; a PSpice-style subcircuit with a body diode parsed and ran unmodified.
- **Neither ngspice nor Xyce has a native IGBT model.** IGBTs must come from vendor subcircuit models.
- **Measurement fragility:** edge-index selectors silently picked non-adjacent edges and produced a *negative* dead-time. Constrain every measurement to a single switching period and assert the result is positive.

## Xyce

Free and GPL-3.0, with a **richer measurement set for power work**: besides the usual types it has `DUTY`, `FREQ`, `ON_TIME` and `OFF_TIME`, exactly the quantities you want to assert on a switching leg, plus CSV output and a mode that re-runs measurements on saved results **without re-simulating**. Its MOSFET level 18 is VDMOS, so power models port.

**Packaging is the problem:** Linux binaries are RHEL8 RPMs, serial only, and the project states they are known not to work on Debian or Ubuntu. Building from source or pinning a container would be needed. Add it only if ngspice fails to converge on something.

## Python layer

**PySpice is effectively dead** (last release 2021-05-15, 205 open issues). Do not build on it. **spicelib** (v1.6.3, 2026-07-21) is the live replacement and drives LTspice, ngspice, QSPICE and Xyce, parses waveforms and measurement logs, and can fan out across cores. That said, the zero-dependency "parse one result line" script was ~30 lines and needed no library at all. Start there.

## PLECS

The one commercial tool that fits CI properly: runs on Linux (needs X libraries, so a virtual display in CI **[U]**), exposes **XML-RPC and JSON-RPC on port 1080**, and supports FMI 2.0 and 3.0 import and export.

```python
proxy = xmlrpc.client.ServerProxy("http://localhost:1080")
proxy.plecs.load("/abs/path/model.plecs")
out = proxy.plecs.simulate("model", {"ModelVars": {"varL": 100e-6}})
# out["Time"], out["Values"] -> assert directly
```

Parameter sweeps don't touch the model file. It uses ideal switches, so it will not show gate ringing or switching edges: right for control loops and loss/thermal budgets, wrong for gate-drive integrity. **SIMBA** is disqualified for CI (Windows and macOS only) despite a good Python API. **SIMPLIS** is genuinely faster for closed-loop supplies but is Windows-focused with its own scripting language.

## Thermal, magnetics, EMC
- **Thermal: compute it, don't simulate it.** A 3 ms electro-thermal run took 3.9 s and had not reached steady state, because thermal time constants are milliseconds to seconds. The right pattern is to measure average device power over a few settled cycles and compute the temperature rise arithmetically from the thermal resistances. Keep electro-thermal devices only where self-heating feeds back into losses.
- **Magnetics:** FEMM is Windows-only (runs under Wine) with scripting toolboxes; XFEMM gives native Linux command-line magnetics. Use it once during design to extract inductance, leakage and AC resistance, hard-code those into the SPICE deck, and don't re-run field analysis in CI.
- **EMC and signal integrity: don't automate.** openEMS is a capable field solver, but for a 3.3 V control board it isn't worth it. Follow layout rules (ground plane continuity, return paths, minimal gate and power loop area) and check them with board rules instead. STM32H7 IBIS models could not be verified because the vendor site blocked access **[U]**.

## Firmware co-simulation

Renode's external control API is the hook, and we already run Renode headless. It exposes `run_for()` with sub-microsecond granularity, memory reads and writes, GPIO state, **setting ADC channel values**, and sending CAN messages.

That gives a hardware-in-the-loop loop in CI:
1. `run_for(Δt)` so the firmware computes a PWM update
2. read the PWM and GPIO state out of Renode
3. advance a plant model by Δt
4. write the resulting currents and voltages back as ADC values
5. repeat, and assert on the trajectory

**Use the control period (say 50 µs) as Δt, and an averaged plant model.** Co-simulating 100 kHz switching against firmware would be orders of magnitude too slow. Keep switching-level SPICE as a separate tier. The alternative path is FMI: OpenModelica 1.27.1 or PLECS export a model, and FMPy drives it from Python.

## Recommended stack

**Control board:** almost no circuit simulation. ngspice only for the few analog corners that exist: supply sequencing, reset and brownout thresholds, crystal drive level, and the ADC front end. Everything else is layout discipline plus the existing firmware tests.

**Power boards:**
1. **ngspice from the distribution, version pinned in CI.**
2. **Netlists as hand-written text in git**, parameterised. Authoring text is exactly what an agent suits.
3. **A measurement for every asserted quantity**, printed as one result line per deck.
4. **A ~30-line Python asserter** with a limits table.
5. **Safe-operating-area logging on every deck**; fail if the log is non-empty.
6. **Losses measured per device; junction temperature computed** from thermal resistances.
7. **Vendor models vendored into the repo**, each with a note recording download URL, date and part number. Vendor sites rewrite URLs constantly: several 404'd or blocked access during this research.
8. **Add PLECS later** for control-loop and thermal work, if budget allows. Don't buy it to start.

## What simulation will not catch

The sharpest lesson came from the agent's own first run: it converged happily and reported **800 V on a 400 V bus and 10 kA peak current**. Both were artifacts of the test setup, not physics. **SPICE will give a numerically converged, completely wrong answer and never flag it.** Every deck needs a sanity assertion on a boring quantity whose right answer you know independently, or the interesting assertions are worthless.

Also missed:
- **Layout parasitics.** Loop inductance in the deck is a guess until the board exists. Simulation tells you the *sensitivity* to it, not your value.
- **Switching-edge fidelity.** A measured 74 V/ns is implausible; generic models have crude Miller capacitance and no real driver output stage. Vendor models are usually fitted for conduction loss, not edges.
- **Common-mode currents, EMI, magnetics saturation**, creepage, thermal interfaces and airflow, solder-joint reliability.
- **Nothing about the PCB itself:** footprints, clearances, stackup, connector pinout. That is [11](11-kicad-automation-and-ci.md)'s territory, and where most real board bugs live.
