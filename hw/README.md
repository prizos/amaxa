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

Facts established while setting this up, worth not rediscovering:

- **atopile has no Linux arm64 wheel**, in any of its 171 releases. On arm64 it builds from source in about two minutes, which works as long as uv's own Python (with headers) is used.
- **atopile's parts server is gone** (`components.atopileapi.com` no longer resolves), so its automatic part picker can't run. Parts are specified explicitly and committed instead, each with a review note.
- **atopile's public repo has been frozen since March 2026** while releases keep appearing. It's MIT licensed, so the fallback is forking and pinning. Deciding that is a later milestone.

## Commands

| Target | Does |
|---|---|
| `make help` | List targets |
| `make tools` | Fetch pinned uv and Python, build the atopile venv |
| `make versions` | Print every tool version and fail if a pinned one is wrong |
| `make clean` | Remove build outputs |
| `make distclean` | Also remove the venv and downloaded tools |
