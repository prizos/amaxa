# amaxa firmware: Makefile front end for the Bazel build.
#
#   make                 build the default app (hello_hw) into out/
#   make BOARD=amaxa_cpu1  build it for the cpu1 board instead
#   make toolchain       fetch Bazel and the arm-none-eabi toolchain, print versions
#   make flash           program the board (STM32CubeProgrammer, OpenOCD or st-flash)
#   make monitor         open the ST-LINK virtual COM port
#   make sim             run the firmware in the Renode emulator (no board needed)
#   make help            list all targets
#
# Everything except `make` itself is downloaded and pinned: Bazelisk (below),
# Bazel (.bazelversion) and the Arm GNU Toolchain plus vendor sources (MODULE.bazel).

SHELL := /bin/bash
.DEFAULT_GOAL := build

APP     ?= hello_hw
BOARD   ?= nucleo_h743zi2  # which bsp/ to build against: see bsp/BUILD.bazel
MODE    ?= opt             # Bazel compilation mode: opt | dbg | fastbuild
PORT    ?= /dev/ttyACM0    # ST-LINK virtual COM port
BAUD    ?= 115200
SIM_SECONDS ?= 5           # virtual seconds to emulate
SIM_KEYS    ?=             # console keys to type after boot, e.g. SIM_KEYS="+ + s b s"

OUT_DIR   := out
TOOLS_DIR := .tools

# --- Bazelisk (downloads the Bazel version pinned in .bazelversion) ----------
BAZELISK_VERSION := v1.29.0
HOST_ARCH := $(shell uname -m)
ifeq ($(HOST_ARCH),x86_64)
  BAZELISK_ARCH   := amd64
  BAZELISK_SHA256 := 5a408715e932c0250d28bd84555f12edbf70117de42f9181691c736eacc4a992
  TOOLCHAIN_REPO  := arm_gnu_toolchain_linux_x86_64
else ifneq ($(filter aarch64 arm64,$(HOST_ARCH)),)
  BAZELISK_ARCH   := arm64
  BAZELISK_SHA256 := e20e8b0f4f240091b7a55bf17b9398bd4f40ee70ae0208dff95dd4c445fb4010
  TOOLCHAIN_REPO  := arm_gnu_toolchain_linux_aarch64
else
  $(error Unsupported build host architecture: $(HOST_ARCH))
endif
BAZELISK := $(TOOLS_DIR)/bazelisk-$(BAZELISK_VERSION)-linux-$(BAZELISK_ARCH)
BAZEL    ?= $(BAZELISK)

# --- Renode emulator (portable build, only needed for `make sim`) -----------
RENODE_VERSION := 1.17.0
ifeq ($(BAZELISK_ARCH),amd64)
  RENODE_PKG    := renode-$(RENODE_VERSION).linux-portable.tar.gz
  RENODE_SHA256 := 92a33d6aa79d3c8bf74c0d934447a048dbc76102def675d2e53de901acf300eb
else
  RENODE_PKG    := renode-$(RENODE_VERSION).linux-arm64-portable.tar.gz
  RENODE_SHA256 := e9051578411441bfb47b77de0381cfba3badce03663367fab561472fd7807f1f
endif
RENODE ?= $(TOOLS_DIR)/renode_$(RENODE_VERSION)-portable/renode

BAZEL_FLAGS := --config=stm32 --compilation_mode=$(strip $(MODE)) \
               --define board=$(strip $(BOARD))
IMAGE       := //apps/$(APP):$(APP)

.PHONY: help build toolchain size flash monitor sim clean distclean

help: ## List targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-12s %s\n", $$1, $$2}'
	@echo "  Variables: APP=$(APP) MODE=$(strip $(MODE)) PORT=$(strip $(PORT))"

$(BAZELISK):
	@mkdir -p $(TOOLS_DIR)
	@echo "Downloading Bazelisk $(BAZELISK_VERSION) ($(BAZELISK_ARCH))"
	@curl -fsSL -o $@.tmp https://github.com/bazelbuild/bazelisk/releases/download/$(BAZELISK_VERSION)/bazelisk-linux-$(BAZELISK_ARCH)
	@echo "$(BAZELISK_SHA256)  $@.tmp" | sha256sum -c --quiet
	@chmod +x $@.tmp && mv $@.tmp $@

build: $(BAZELISK) ## Build $(APP) and copy .elf/.bin/.hex/.lst/.size.txt to out/
	$(BAZEL) build $(BAZEL_FLAGS) $(IMAGE)
	@mkdir -p $(OUT_DIR)
	@for f in $$($(BAZEL) cquery $(BAZEL_FLAGS) --output=files $(IMAGE) 2>/dev/null); do \
		cp -fL $$f $(OUT_DIR)/ && chmod u+w $(OUT_DIR)/$$(basename $$f); done
	@echo "Artifacts in $(OUT_DIR)/:" && ls -1 $(OUT_DIR)/$(APP).*
	@tail -n 2 $(OUT_DIR)/$(APP).size.txt

toolchain: $(BAZELISK) ## Fetch Bazel + arm-none-eabi toolchain and print their versions
	@$(BAZEL) --version
	@$(BAZEL) fetch --repo=@$(TOOLCHAIN_REPO) >/dev/null
	@gcc=$$(ls -d $$($(BAZEL) info output_base 2>/dev/null)/external/*$(TOOLCHAIN_REPO))/bin/arm-none-eabi-gcc; \
		echo "$$gcc"; "$$gcc" --version | head -1

size: build ## Show section sizes of $(APP)
	@cat $(OUT_DIR)/$(APP).size.txt

flash: build ## Program $(APP) over the ST-LINK
	@elf=$(OUT_DIR)/$(APP).elf; \
	if command -v STM32_Programmer_CLI >/dev/null; then \
		STM32_Programmer_CLI -c port=SWD -w $$elf -v -rst; \
	elif command -v openocd >/dev/null; then \
		openocd -f interface/stlink.cfg -f target/stm32h7x.cfg -c "program $$elf verify reset exit"; \
	elif command -v st-flash >/dev/null; then \
		st-flash --reset write $(OUT_DIR)/$(APP).bin 0x08000000; \
	else \
		echo "No flasher found: install STM32CubeProgrammer, openocd or stlink-tools" >&2; exit 1; \
	fi

monitor: ## Open the virtual COM port (picocom, or Python's miniterm)
	@if command -v picocom >/dev/null; then picocom -b $(BAUD) $(strip $(PORT)); \
	else python3 -m serial.tools.miniterm $(strip $(PORT)) $(BAUD); fi

$(TOOLS_DIR)/renode_$(RENODE_VERSION)-portable/renode:
	@mkdir -p $(TOOLS_DIR)
	@echo "Downloading Renode $(RENODE_VERSION) ($(BAZELISK_ARCH))"
	@curl -fsSL -o $(TOOLS_DIR)/$(RENODE_PKG) https://builds.renode.io/$(RENODE_PKG)
	@echo "$(RENODE_SHA256)  $(TOOLS_DIR)/$(RENODE_PKG)" | sha256sum -c --quiet
	@tar -xzf $(TOOLS_DIR)/$(RENODE_PKG) -C $(TOOLS_DIR) && rm -f $(TOOLS_DIR)/$(RENODE_PKG)
	@touch $@

sim: build $(RENODE) ## Emulate $(APP) in Renode for SIM_SECONDS, typing SIM_KEYS; prints the console
	@set -f -o pipefail; \
	cmds='set elf @$(abspath $(OUT_DIR)/$(APP).elf); set repl @$(abspath renode/nucleo_h743zi2.repl); include @$(abspath renode/nucleo_h743zi2.resc); emulation RunFor "1.1";'; \
	for key in $(SIM_KEYS); do \
		cmds="$$cmds sysbus.usart3 WriteChar $$(printf '%d' "'$$key"); emulation RunFor \"0.2\";"; \
	done; \
	cmds="$$cmds emulation RunFor \"$(strip $(SIM_SECONDS))\"; quit"; \
	timeout $$(( $(strip $(SIM_SECONDS)) * 20 + 60 )) $(RENODE) --console --disable-gui --port -1 -e "$$cmds" </dev/null 2>&1 \
		| sed -uE 's/\x1b\[[0-9;]*m//g' \
		| sed -unE 's/^.*usart3: \[host[^]]*\] ?//p; /\[(ERROR|WARNING)\] (watchdog|cpu)|error executing|Exception/p'

clean: ## Remove build outputs
	-@[ -x $(BAZELISK) ] && $(BAZEL) clean
	rm -rf $(OUT_DIR)

distclean: clean ## Also remove Bazel caches for this workspace and downloaded tools
	-@[ -x $(BAZELISK) ] && $(BAZEL) clean --expunge
	rm -rf $(TOOLS_DIR)
