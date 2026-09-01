DEVKITSMS ?= ../devkitSMS
PYTHON ?= python3
CC := sdcc

PROG := hong-kong-97-sms
BUILD := build
GENERATED := generated
BANKDIR := $(GENERATED)/banked
SMSLIB_INCDIR := $(DEVKITSMS)/SMSlib/src
PEEP_RULES := $(SMSLIB_INCDIR)/peep-rules.txt
CRT0 := $(DEVKITSMS)/crt0/crt0_sms.rel
SMSLIB_LIB := $(SMSLIB_INCDIR)/SMSlib.lib
IHX2SMS ?= $(DEVKITSMS)/ihx2sms/Linux/ihx2sms-local
ASSETS2BANKS := $(PYTHON) $(abspath $(DEVKITSMS))/assets2banks/src/assets2banks.py
MIDI ?= assets/music/hk97.mid
CHEAT_ASSETS ?= ../hong-kong-97-genesis/res/egg
CHEAT_AVATAR := $(CHEAT_ASSETS)/avatar.jpg
CHEAT_LOGO := $(CHEAT_ASSETS)/logo.png
CHEAT_SOUND := $(CHEAT_ASSETS)/sound.mp3

SRCS := $(wildcard src/*.c)
OBJS := $(patsubst src/%.c,$(BUILD)/%.rel,$(SRCS))
OBJS += $(BUILD)/music_fixed.rel
CFLAGS := -mz80 -Isrc -I$(GENERATED) -I$(BANKDIR) -I$(SMSLIB_INCDIR) \
	--peep-file $(PEEP_RULES) $(EXTRA_CFLAGS)
LDFLAGS := -mz80 --no-std-crt0 --data-loc 0xC000

# Evaluated by the recursive `link` invocation, after assets2banks has emitted
# the bank files. This avoids a stale hard-coded bank range.
BANKRELS = $(shell printf '%s\n' $(wildcard $(BANKDIR)/bank*.rel) | sort -V)
BANKNUMS = $(patsubst $(BANKDIR)/bank%.rel,%,$(BANKRELS))
BANKFLAGS = $(foreach n,$(BANKNUMS),-Wl-b_BANK$(n)=0x8000)

.PHONY: all prepare assets build-code-fast link host-test test smoke smoke-flow verify clean FORCE

all: build-code-fast

prepare:
	@if [ -n "$(ROM)" ]; then $(PYTHON) tools/unpack_rom.py "$(ROM)"; \
	elif [ ! -f work/hk97.sfc ]; then echo "ROM is required: make prepare ROM=/path/to/hk97.sfc" >&2; exit 2; fi
	@test -f "$(MIDI)" || { echo "MIDI not found: $(MIDI)" >&2; exit 2; }
	@test -f "$(CHEAT_AVATAR)" -a -f "$(CHEAT_LOGO)" -a -f "$(CHEAT_SOUND)" || { \
		echo "Cheat assets not found in $(CHEAT_ASSETS)" >&2; \
		echo "Clone hong-kong-97-genesis beside this repository or set CHEAT_ASSETS=/path/to/res/egg" >&2; exit 2; }
	@$(MAKE) --no-print-directory assets

assets: $(GENERATED)/.stamp

work/hk97.sfc:
	@echo "Missing source ROM. Run: make prepare ROM=/path/to/hk97.sfc" >&2
	@exit 2

$(GENERATED)/.stamp: work/hk97.sfc tools/trace65816.py tools/extract_gfx.py \
	tools/extract_screens.py tools/extract_anims.py tools/gen_tables.py \
	tools/generate_cheat_assets.py tools/generate_sms_assets.py \
	tools/convert_midi_psg.py $(MIDI) $(CHEAT_AVATAR) $(CHEAT_LOGO) \
	$(CHEAT_SOUND)
	mkdir -p disasm $(GENERATED) $(BANKDIR)
	$(PYTHON) tools/trace65816.py work/hk97.sfc -o disasm/hk97_trace.asm
	$(PYTHON) tools/extract_gfx.py
	$(PYTHON) tools/extract_screens.py
	$(PYTHON) tools/generate_cheat_assets.py --source "$(CHEAT_ASSETS)"
	$(PYTHON) tools/extract_anims.py
	$(PYTHON) tools/gen_tables.py
	$(PYTHON) tools/generate_sms_assets.py
	$(PYTHON) tools/convert_midi_psg.py "$(MIDI)"
	cd $(GENERATED) && xxd -i music.psg > music_fixed.c
	sed -i -e 's/^unsigned char music_psg/const unsigned char music_psg/' \
		-e 's/^unsigned int music_psg_len/const unsigned int music_psg_len/' \
		$(GENERATED)/music_fixed.c
	rm -f $(BANKDIR)/*
	cp $(GENERATED)/bg/*.bin $(GENERATED)/bg/*.cram $(BANKDIR)/
	cp $(GENERATED)/sprites.cram $(GENERATED)/sprites0.tiles \
		$(GENERATED)/sprites1.tiles \
		$(GENERATED)/sprites_seed.tiles $(GENERATED)/cheat.pcm4 $(BANKDIR)/
	cd $(BANKDIR) && $(ASSETS2BANKS) . --firstbank=2 \
		--singleheader=banked_assets.h --compile
	touch $@

build-code-fast: assets host-test
	@$(MAKE) --no-print-directory link

link: $(BUILD)/$(PROG).sms

$(BUILD):
	mkdir -p $@

$(BUILD)/.cflags: FORCE | $(BUILD)
	@printf '%s' '$(CFLAGS)' | cmp -s - $@ || printf '%s' '$(CFLAGS)' > $@

$(BUILD)/%.rel: src/%.c src/main.h src/game.h src/audio.h \
	$(BUILD)/.cflags $(GENERATED)/.stamp | $(BUILD)
	$(CC) $(CFLAGS) -c $< -o $@

$(BUILD)/music_fixed.rel: $(GENERATED)/music_fixed.c $(BUILD)/.cflags | $(BUILD)
	$(CC) $(CFLAGS) -c $< -o $@

$(BUILD)/$(PROG).ihx: $(OBJS) $(BANKRELS) Makefile
	@test -n "$(BANKRELS)" || { echo "No generated asset banks found" >&2; exit 2; }
	$(CC) -o $@ $(LDFLAGS) $(BANKFLAGS) $(CRT0) $(OBJS) $(BANKRELS) $(SMSLIB_LIB)

$(BUILD)/$(PROG).sms: $(BUILD)/$(PROG).ihx
	@test -x "$(IHX2SMS)" || { echo "Missing $(IHX2SMS); build it from devkitSMS/ihx2sms/src" >&2; exit 2; }
	$(IHX2SMS) $< $@

host-test: | $(BUILD)
	cc -std=c99 -Wall -Wextra -Werror -Isrc src/game.c tests/test_game_logic.c \
		-o $(BUILD)/test_game_logic
	./$(BUILD)/test_game_logic

test: host-test
	$(PYTHON) -m unittest discover -v tests

smoke: build-code-fast
	./tools/smoke.sh --rom $(BUILD)/$(PROG).sms --frames 150 \
		--shot docs/screenshots/boot.png

smoke-flow: build-code-fast
	./tools/smoke.sh --rom $(BUILD)/$(PROG).sms --flow --frames 1800 \
		--shot docs/screenshots/gameplay.png

verify: test build-code-fast smoke smoke-flow
	$(PYTHON) tools/verify_build.py $(BUILD)/$(PROG).sms $(BUILD)/$(PROG).map

clean:
	rm -rf $(BUILD) $(GENERATED)

FORCE:
