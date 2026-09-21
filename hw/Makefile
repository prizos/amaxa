# amaxa hardware: Makefile front end for board design and verification.
#
#   make tools       fetch pinned uv + Python, build the design virtualenv
#   make versions    print every tool version and check the pinned ones
#   make build       turn the SKiDL design source into KiCad files
#   make layout      apply the board's placement and routing, then fill the plane
#   make pins        check the MCU pin map against the silicon (boards with an MCU)
#   make check       run the design checks against what the build produced
#   make reproducible  build twice and check both runs describe the same board
#   make sim         run the ngspice decks and check their measurements
#   make offline     prove the build reaches nothing over the network
#   make outputs     renders, 3D model, gerbers and drill files into out/
#   make help        list all targets
#
# Two stages, deliberately separated:
#   generate  (SKiDL)        turns the design source into KiCad files.
#   verify    (kicad-cli,    consumes committed files. Runs anywhere, and is
#              pytest,        what gates CI.
#              ngspice)
#
# KiCad is NOT downloaded: it is located on PATH, because it installs through
# the system package manager. See README.md for the one-line install.

SHELL := /bin/bash
.DEFAULT_GOAL := help

BOARD   ?= led12
TOOLS_DIR := .tools
VENV      := .venv

# --- pinned versions --------------------------------------------------------
# We write the KiCad 9 file format (20241229) ourselves, so KiCad 9 is what we
# pin. The format changed twenty-two times inside the v10 cycle alone, which
# makes each major version a scheduled migration rather than an upgrade.
UV_VERSION       := 0.12.15
PYTHON_VERSION   := 3.14
SKIDL_VERSION    := 2.3.0
KICAD_REQUIRED   := 9.0
NGSPICE_REQUIRED := 45.2

HOST_ARCH := $(shell uname -m)
ifeq ($(HOST_ARCH),x86_64)
  UV_ARCH   := x86_64
  UV_SHA256 := f97935763c04be3e692460a7aaeaaab8fc3b78fcf8b389da820b38ae7423a638
else ifneq ($(filter aarch64 arm64,$(HOST_ARCH)),)
  UV_ARCH   := aarch64
  UV_SHA256 := 0e9a3499b0587d449c9ff684c0160da607826e4af1cee220bc87f378702d3e08
else
  $(error Unsupported build host architecture: $(HOST_ARCH))
endif

UV_DIR := $(TOOLS_DIR)/uv-$(UV_VERSION)
UV     := $(UV_DIR)/uv
PY     ?= $(VENV)/bin/python

# uv keeps its downloaded Pythons here, so nothing touches the system Python.
export UV_PYTHON_INSTALL_DIR := $(abspath $(TOOLS_DIR)/pythons)

# What a board declares about itself, if it needs to. `ROUTING := incomplete`
# lets DRC pass on a board still being drawn, as long as nothing drawn is wrong;
# `SIM := none` says the board has no simulation decks. Both have to be said,
# in the board's own directory, rather than inferred from what is missing.
ROUTING := complete
SIM     := decks
-include $(BOARD)/board.mk

LAYOUT_DIR := $(BOARD)/elec/layout/default
DRU        := $(LAYOUT_DIR)/default.kicad_dru

KICAD_CLI ?= $(shell command -v kicad-cli 2>/dev/null)
NGSPICE   ?= $(shell command -v ngspice 2>/dev/null)

.PHONY: help tools versions build layout rules pins pins-write check drc reproducible sim offline outputs clean distclean

help: ## List targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-12s %s\n", $$1, $$2}'
	@echo "  Variables: BOARD=$(BOARD)"

# --- pinned tools -----------------------------------------------------------

$(UV):
	@mkdir -p $(UV_DIR)
	@echo "Downloading uv $(UV_VERSION) ($(UV_ARCH))"
	@curl -fsSL -o $(UV_DIR)/uv.tar.gz \
		https://github.com/astral-sh/uv/releases/download/$(UV_VERSION)/uv-$(UV_ARCH)-unknown-linux-gnu.tar.gz
	@echo "$(UV_SHA256)  $(UV_DIR)/uv.tar.gz" | sha256sum -c --quiet
	@tar -xzf $(UV_DIR)/uv.tar.gz -C $(UV_DIR) --strip-components=1
	@rm -f $(UV_DIR)/uv.tar.gz
	@touch $@

# SKiDL is pure Python, so this is the same on every architecture - no wheel
# to be missing and nothing to build from source.
$(PY): $(UV) requirements/skidl.lock
	@echo "Creating $(VENV) on Python $(PYTHON_VERSION) from requirements/skidl.lock"
	@$(UV) python install $(PYTHON_VERSION)
	@$(UV) venv --clear --python $(PYTHON_VERSION) $(VENV)
	@$(UV) pip install --python $(PY) -r requirements/skidl.lock
	@touch $@

tools: $(PY) ## Fetch pinned uv + Python and build the design virtualenv
	@$(MAKE) --no-print-directory versions

versions: ## Print tool versions and check the pinned ones
	@printf "  uv        %s\n" "$$($(UV) --version 2>/dev/null | awk '{print $$2}')"
	@printf "  python    %s\n" "$$($(VENV)/bin/python --version 2>/dev/null | awk '{print $$2}')"
	@printf "  skidl     %s\n" "$$($(PY) -c 'import skidl; print(skidl.__version__)' 2>/dev/null || echo '(not installed)')"
	@printf "  kicad-cli %s\n" "$$([ -n "$(KICAD_CLI)" ] && $(KICAD_CLI) version || echo '(not installed)')"
	@printf "  ngspice   %s\n" "$$([ -n "$(NGSPICE)" ] && $(NGSPICE) -v 2>/dev/null | sed -n 's/.*ngspice-\([0-9.]*\).*/\1/p' | head -1 || echo '(not installed)')"
	@printf "  pcbnew    %s\n" "$$(python3 -c 'import pcbnew; print(pcbnew.GetBuildVersion())' 2>/dev/null || echo '(not importable)')"
	@fail=0; \
	skidl_v=$$($(PY) -c 'import skidl; print(skidl.__version__)' 2>/dev/null); \
	if [ "$$skidl_v" != "$(SKIDL_VERSION)" ]; then \
		echo "ERROR: skidl is '$$skidl_v', expected $(SKIDL_VERSION). Run: make tools" >&2; fail=1; fi; \
	if [ -z "$(KICAD_CLI)" ]; then \
		echo "ERROR: kicad-cli not found. Install KiCad $(KICAD_REQUIRED) (see README.md)" >&2; fail=1; \
	else \
		kv=$$($(KICAD_CLI) version 2>/dev/null); \
		case "$$kv" in $(KICAD_REQUIRED).*) ;; *) \
			echo "ERROR: kicad-cli is $$kv, expected $(KICAD_REQUIRED).x — we write KiCad 9 files" >&2; fail=1;; \
		esac; fi; \
	if ! python3 -c 'import pcbnew' >/dev/null 2>&1; then \
		echo "ERROR: KiCad's pcbnew Python module is not importable. It ships in the" >&2; \
		echo "       kicad package itself and is what fills copper pours; kicad-cli cannot." >&2; \
		fail=1; fi; \
	if [ -z "$(NGSPICE)" ]; then \
		echo "ERROR: ngspice not found. Install ngspice $(NGSPICE_REQUIRED) (see README.md)" >&2; fail=1; \
	else \
		nv=$$($(NGSPICE) -v 2>/dev/null | sed -n 's/.*ngspice-\([0-9.]*\).*/\1/p' | head -1); \
		if [ "$$nv" != "$(NGSPICE_REQUIRED)" ]; then \
			echo "WARNING: ngspice is $$nv, pinned $(NGSPICE_REQUIRED); simulation numbers may differ" >&2; fi; \
	fi; \
	exit $$fail

# --- generate ---------------------------------------------------------------

# Two steps, and the split is the point. The board's own source knows SKiDL and
# writes design.json - parts, nets and parameters, in a schema we own. The board
# writer reads only that, so nothing downstream is coupled to a design tool.
#
# Always from scratch: the board is output, and a stale elec/ is how a build
# ends up half describing a design that no longer exists.
build: $(PY) ## Turn the design source into KiCad files for BOARD
	@rm -rf $(BOARD)/elec $(BOARD)/build
	@mkdir -p $(BOARD)/build
	@cd $(BOARD) && ../$(PY) $(BOARD).py
	@python3 tools/board.py $(BOARD)

# The board writer leaves every part at the origin and nothing routed. This
# puts the board
# together from $(BOARD)/layout.py, then fills the copper pours - kicad-cli
# cannot fill them, and DRC reads whatever fill is already in the file, so an
# unfilled plane reports every ground pad as unconnected.
# The rules file is regenerated here, not only by `drc`, because `build` starts
# by deleting elec/ - which is where the generated rules live. Without this, a
# kicad-cli run that does not go through `make drc` silently checks the board
# against no custom rules at all and reports a clean board.
# The fill is retried once because KiCad's own zone filler segfaults on this
# board perhaps one run in four, and only on 9.0.9 - the version CI installs
# from the PPA. It has never done it on the 9.0.8 this repository's `make
# versions` reports, across hundreds of runs, so it cannot be reproduced or
# bisected here. A crash happens inside ZONE_FILLER::Fill, before SaveBoard,
# so the board file is untouched and a retry starts from the same input; if
# the second attempt crashes too, the build fails as it should. The retry says
# so on stdout rather than hiding it, because a fill that starts needing two
# goes every time is a different problem from one that needs two occasionally.
layout: build $(DRU) ## Apply the board's placement and routing, then fill the plane
	@python3 tools/layout.py $(BOARD)
	@python3 tools/fill_zones.py $(LAYOUT_DIR)/default.kicad_pcb \
	    || { echo "zone fill crashed; retrying once (see Makefile)"; \
	         python3 tools/fill_zones.py $(LAYOUT_DIR)/default.kicad_pcb; }

# hw/README.md claims a build reaches nothing over the network. This is what
# makes that a claim rather than a memory: the design source is run with every
# way out of the process raising.
offline: $(PY) ## Build the design source with the network blocked
	@$(PY) tools/no_network.py $(BOARD)
	@rm -f $(BOARD)/no_network_sklib.py

# KiCad reads one rules file per board, named after it and beside it. Ours is
# the shared fab limits followed by the board's own intent, so that a rule about
# what PCBWay can etch lives in one place across every board.
rules: $(DRU) ## Regenerate the board's design-rules file

$(DRU): fab/pcbway.kicad_dru $(BOARD)/rules.kicad_dru
	@mkdir -p $(LAYOUT_DIR)
	@{ echo "# Generated by 'make rules'. Edit fab/pcbway.kicad_dru or"; \
	   echo "# $(BOARD)/rules.kicad_dru instead; this file is overwritten."; \
	   echo; \
	   cat fab/pcbway.kicad_dru; \
	   echo; \
	   sed '1d' $(BOARD)/rules.kicad_dru; } > $@
	@echo "wrote $@"

# What we write is byte-identical from one build to the next: the design source
# is deterministic, and both the board writer and the layout engine derive every
# UUID from the object it belongs to. The remaining churn is KiCad's - filling
# the copper pours goes through pcbnew, which reassigns identifiers on save, and
# moves about six hundred lines that mean nothing.
#
# So the comparison is of the design rather than the file: where each part sits,
# what copper joins what, what the nets are called. If that ever stops holding,
# the pipeline has become a random number generator and nothing downstream means
# anything.
reproducible: layout ## Build twice and check both runs describe the same board
	@cp $(LAYOUT_DIR)/default.kicad_pcb $(BOARD)/.first.kicad_pcb
	@$(MAKE) --no-print-directory layout >/dev/null
	@python3 tools/fingerprint.py $(BOARD)/.first.kicad_pcb $(LAYOUT_DIR)/default.kicad_pcb
	@rm -f $(BOARD)/.first.kicad_pcb

# --- verify -----------------------------------------------------------------

# KiCad's own rule checker: shorts, clearances, the fab limits and the board's
# own rules. Exit code 5 means violations were found.
#
# A board whose routing is declared incomplete still fails on any violation:
# a short, a clearance, a hole too small. What it may have is connections not
# yet drawn, and those are counted, not hidden.
drc: layout $(DRU) ## Run KiCad DRC against the fab and board rules
	@test -s $(DRU) || { echo "ERROR: $(DRU) is missing or empty, so DRC would" >&2; \
		echo "       run against no custom rules and pass regardless." >&2; exit 1; }
ifeq ($(ROUTING),complete)
	@$(KICAD_CLI) pcb drc --format json --severity-error --exit-code-violations \
		--output $(LAYOUT_DIR)/drc.json $(LAYOUT_DIR)/default.kicad_pcb
else ifeq ($(ROUTING),incomplete)
	@$(KICAD_CLI) pcb drc --format json --severity-error \
		--output $(LAYOUT_DIR)/drc.json $(LAYOUT_DIR)/default.kicad_pcb >/dev/null
	@python3 tools/drc_report.py $(LAYOUT_DIR)/drc.json
else
	$(error ROUTING must be complete or incomplete, not $(ROUTING))
endif

# The MCU pin map against ST's data, and the firmware header generated from it.
# No build needed, so it runs on its own and before anything else is drawn.
pins: $(PY) ## Check the board's MCU pin map against the silicon
	@$(PY) -m pytest $(BOARD)/checks/test_pinmap.py -q --import-mode=importlib --board $(BOARD)

pins-write: ## Regenerate the firmware pin header from the board's pin map
	@python3 tools/mcu_pins.py $(BOARD)

# Depends on build so the checks can never pass against stale output. Two
# directories: hw/checks/ applies to every board, $(BOARD)/checks/ to this one.
# importlib mode lets two boards each have a test_electrical.py.
check: layout ## Run the common and board-specific design checks
	@$(PY) -m pytest checks/ $(BOARD)/checks/ -q --import-mode=importlib --board $(BOARD)

mutate: check ## Change every declared number and report which ones nothing notices
	@$(PY) tools/mutate.py $(BOARD)

# The decks take their component values from the build's design.json, so
# there is no second copy of the design to fall out of step with the first.
#
# It depends on layout rather than build even though it only reads
# design.json, because build starts by deleting elec/ - so a target that stops at
# build leaves the board generated but unplaced and unrouted, which is a
# confusing thing to find in the tree afterwards.
sim: layout ## Run the ngspice decks and check their measurements
ifeq ($(SIM),none)
	@echo "$(BOARD) declares no simulation decks (SIM := none in $(BOARD)/board.mk)"
else
	@python3 tools/simulate.py $(BOARD)
endif

REVIEW := $(BOARD)/review

# A snapshot of the board as pictures, committed so it can be looked at without
# a KiCad install. `outputs` writes the same kind of thing into the gitignored
# out/; this writes the few files worth keeping in the tree, and regenerating it
# is how they stay honest - a stale picture of a board is worse than none.
#
# The copper layers are plotted one at a time rather than stacked, because a
# stacked plot of a board with three filled planes is a solid rectangle.
review: drc ## Per-layer plots and renders into <board>/review/, committed
	@mkdir -p $(REVIEW)
	@# `basic` rather than the `high` that out/ gets: the raytracer samples
	@# randomly, so two runs over an unchanged board produce two different PNGs.
	@# A committed file that churns on every regeneration cannot be diffed, and
	@# "regenerate and check nothing moved" stops being a gate. On a board whose
	@# parts have no 3D models to raytrace, it costs nothing to look at either.
	@$(KICAD_CLI) pcb render --side top --width 1600 --height 1280 \
		--quality basic --output $(REVIEW)/top.png $(LAYOUT_DIR)/default.kicad_pcb
	@$(KICAD_CLI) pcb render --side bottom --width 1600 --height 1280 \
		--quality basic --output $(REVIEW)/bottom.png $(LAYOUT_DIR)/default.kicad_pcb
	@# Every copper layer the board has, read from the board rather than listed,
	@# for the same reason the gerber list is.
	@for layer in $$(grep -oE '"(F|B|In[0-9]+)\.Cu" signal' $(LAYOUT_DIR)/default.kicad_pcb \
			| cut -d'"' -f2); do \
		$(KICAD_CLI) pcb export svg --page-size-mode 2 --exclude-drawing-sheet \
			--black-and-white --layers "$$layer,Edge.Cuts" \
			--output $(REVIEW)/$$(echo $$layer | tr . _).svg \
			$(LAYOUT_DIR)/default.kicad_pcb >/dev/null; \
	done
	@$(KICAD_CLI) pcb export svg --page-size-mode 2 --exclude-drawing-sheet \
		--layers F.SilkS,F.Fab,Edge.Cuts \
		--output $(REVIEW)/assembly.svg $(LAYOUT_DIR)/default.kicad_pcb >/dev/null
	@# Two things KiCad's SVG needs before it can be read on a web page. The
	@# DOCTYPE references a DTD on w3.org, which is a network fetch nobody asked
	@# for and which some renderers refuse outright. And the plot is black lines
	@# on a transparent ground, which vanishes against a dark theme - GitHub
	@# renders these in whichever theme the reader has - so it gets an opaque
	@# sheet behind it, the colour a plot is supposed to be on.
	@for f in $(REVIEW)/*.svg; do python3 tools/svg_sheet.py $$f; done
	@python3 tools/review.py $(BOARD)
	@ls -1 $(REVIEW) | sed 's/^/    /'

OUT := out/$(BOARD)

# Everything a person or a fab needs to look at. Renders and the 3D model are
# for review; the gerbers and drill files are what gets ordered.
outputs: drc ## Renders, 3D model, gerbers and drill files into out/
	@mkdir -p $(OUT)/fab
	@$(KICAD_CLI) pcb render --side top --width 1600 --height 1280 \
		--quality high --output $(OUT)/top.png $(LAYOUT_DIR)/default.kicad_pcb
	@$(KICAD_CLI) pcb render --side bottom --width 1600 --height 1280 \
		--quality high --output $(OUT)/bottom.png $(LAYOUT_DIR)/default.kicad_pcb
	@$(KICAD_CLI) pcb export svg --page-size-mode 2 --exclude-drawing-sheet \
		--layers F.Cu,F.SilkS,F.Mask,Edge.Cuts \
		--output $(OUT)/front.svg $(LAYOUT_DIR)/default.kicad_pcb
	@$(KICAD_CLI) pcb export step --subst-models --no-dnp \
		--output $(OUT)/$(BOARD).step $(LAYOUT_DIR)/default.kicad_pcb
	@$(KICAD_CLI) pcb export pos --format csv --units mm --side both \
		--output $(OUT)/positions.csv $(LAYOUT_DIR)/default.kicad_pcb
	@# Every copper layer the board has, read from the board rather than listed:
	@# a fixed F.Cu,B.Cu list silently leaves a 4-layer board's planes out of
	@# the package the fab builds from.
	@$(KICAD_CLI) pcb export gerbers --output $(OUT)/fab/ \
		--layers "$$(grep -oE '"(F|B|In[0-9]+)\.Cu" signal' $(LAYOUT_DIR)/default.kicad_pcb \
			| cut -d'"' -f2 | paste -sd,),F.Silkscreen,B.Silkscreen,F.Mask,B.Mask,F.Paste,B.Paste,Edge.Cuts" \
		$(LAYOUT_DIR)/default.kicad_pcb
	@$(KICAD_CLI) pcb export drill --format excellon --output $(OUT)/fab/ \
		$(LAYOUT_DIR)/default.kicad_pcb
	@$(KICAD_CLI) pcb export ipcd356 \
		--output $(OUT)/fab/$(BOARD).d356 $(LAYOUT_DIR)/default.kicad_pcb
	@cp $(BOARD)/build/bom.csv $(OUT)/bom.csv
	@echo "wrote $(OUT)/"
	@ls -1 $(OUT) $(OUT)/fab | sed 's/^/    /'

clean: ## Remove build outputs
	rm -rf */build */elec */sim/.run out

distclean: clean ## Also remove the venv and downloaded tools
	rm -rf $(VENV) $(TOOLS_DIR)
