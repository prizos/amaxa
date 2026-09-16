# amaxa hardware: Makefile front end for board design and verification.
#
#   make tools       fetch pinned uv + Python, build the atopile venv
#   make versions    print every tool version and check the pinned ones
#   make build       turn .ato source into KiCad files
#   make check       run the design checks against what the build produced
#   make drift       fail if the committed board no longer matches its source
#   make help        list all targets
#
# Two stages, deliberately separated:
#   generate  (atopile)      turns .ato source into KiCad files. Needs the venv.
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
# atopile writes KiCad 9 file format (20241229), so KiCad 9 is what we pin.
UV_VERSION       := 0.12.15
PYTHON_VERSION   := 3.14
ATOPILE_VERSION  := 0.15.9
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
ATO    ?= $(VENV)/bin/ato

# uv keeps its downloaded Pythons here, so nothing touches the system Python.
export UV_PYTHON_INSTALL_DIR := $(abspath $(TOOLS_DIR)/pythons)

KICAD_CLI ?= $(shell command -v kicad-cli 2>/dev/null)
NGSPICE   ?= $(shell command -v ngspice 2>/dev/null)

.PHONY: help tools versions build check drift clean distclean

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

# atopile publishes no Linux arm64 wheel, so on arm64 this builds it from
# source (~2 min). uv's own Python is used because it ships the headers that
# build needs; Ubuntu's system Python does not.
$(ATO): $(UV) requirements/atopile.lock
	@echo "Creating $(VENV) on Python $(PYTHON_VERSION) and installing atopile $(ATOPILE_VERSION)"
	@$(UV) python install $(PYTHON_VERSION)
	@$(UV) venv --python $(PYTHON_VERSION) $(VENV)
	@$(UV) pip install --python $(VENV)/bin/python -r requirements/atopile.lock
	@touch $@

tools: $(ATO) ## Fetch pinned uv + Python and build the atopile venv
	@$(MAKE) --no-print-directory versions

versions: ## Print tool versions and check the pinned ones
	@printf "  uv        %s\n" "$$($(UV) --version 2>/dev/null | awk '{print $$2}')"
	@printf "  python    %s\n" "$$($(VENV)/bin/python --version 2>/dev/null | awk '{print $$2}')"
	@printf "  atopile   %s\n" "$$($(ATO) --version 2>/dev/null)"
	@printf "  kicad-cli %s\n" "$$([ -n "$(KICAD_CLI)" ] && $(KICAD_CLI) version || echo '(not installed)')"
	@printf "  ngspice   %s\n" "$$([ -n "$(NGSPICE)" ] && $(NGSPICE) -v 2>/dev/null | sed -n 's/.*ngspice-\([0-9.]*\).*/\1/p' | head -1 || echo '(not installed)')"
	@fail=0; \
	ato_v=$$($(ATO) --version 2>/dev/null); \
	if [ "$$ato_v" != "$(ATOPILE_VERSION)" ]; then \
		echo "ERROR: atopile is '$$ato_v', expected $(ATOPILE_VERSION). Run: make tools" >&2; fail=1; fi; \
	if [ -z "$(KICAD_CLI)" ]; then \
		echo "ERROR: kicad-cli not found. Install KiCad $(KICAD_REQUIRED) (see README.md)" >&2; fail=1; \
	else \
		kv=$$($(KICAD_CLI) version 2>/dev/null); \
		case "$$kv" in $(KICAD_REQUIRED).*) ;; *) \
			echo "ERROR: kicad-cli is $$kv, expected $(KICAD_REQUIRED).x — atopile writes KiCad 9 files" >&2; fail=1;; \
		esac; fi; \
	if [ -z "$(NGSPICE)" ]; then \
		echo "ERROR: ngspice not found. Install ngspice $(NGSPICE_REQUIRED) (see README.md)" >&2; fail=1; \
	else \
		nv=$$($(NGSPICE) -v 2>/dev/null | sed -n 's/.*ngspice-\([0-9.]*\).*/\1/p' | head -1); \
		if [ "$$nv" != "$(NGSPICE_REQUIRED)" ]; then \
			echo "WARNING: ngspice is $$nv, pinned $(NGSPICE_REQUIRED); simulation numbers may differ" >&2; fi; \
	fi; \
	exit $$fail

# --- generate ---------------------------------------------------------------

build: $(ATO) ## Turn .ato source into KiCad files for BOARD
	@cd $(BOARD) && ../$(ATO) build

# --- verify -----------------------------------------------------------------

check: ## Run the design checks against what the build produced
	@$(VENV)/bin/python -m pytest checks/ -q --board $(BOARD)

# Ignores KiCad object UUIDs, which atopile regenerates for the board outline
# on every build. See tools/check_drift.py.
drift: ## Fail if the committed board no longer matches its source
	@python3 tools/check_drift.py --all

clean: ## Remove build outputs
	rm -rf */build out

distclean: clean ## Also remove the venv and downloaded tools
	rm -rf $(VENV) $(TOOLS_DIR)
