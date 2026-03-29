-include .env
export HF_TOKEN

PYTHON ?= python3
VENV_ROOT ?= .venvs
DOCKER_COMPOSE ?= docker compose
SUPPORTED_ENGINES := chatterbox fish vibe
SELECTED_ENGINES := $(filter $(SUPPORTED_ENGINES),$(MAKECMDGOALS))
FISH_SERVER_MODE ?= docker
FISH_HEALTH_URL ?= $(patsubst %/v1/tts,%/v1/health,$(FISH_SERVER_URL))
FISH_MODEL_SUBDIR ?= fish-speech-1.5
FISH_MODEL_PATH := $(FISH_CHECKPOINT_DIR)/$(FISH_MODEL_SUBDIR)
FISH_DECODER_FILENAME ?= firefly-gan-vq-fsq-8x1024-21hz-generator.pth
VIBE_HF_MODEL ?= microsoft/VibeVoice-1.5B
VIBE_MODEL_DIR ?= ./vibe-voice/models
VIBE_MODEL_SUBDIR ?= VibeVoice-1.5B
VIBE_MODEL_PATH ?= $(VIBE_MODEL_DIR)/$(VIBE_MODEL_SUBDIR)
VIBE_RUN_MODEL_SOURCE := $(if $(wildcard $(VIBE_MODEL_PATH)),$(VIBE_MODEL_PATH),$(VIBE_HF_MODEL))

ifeq ($(words $(SELECTED_ENGINES)),0)
ENGINE := chatterbox
else ifeq ($(words $(SELECTED_ENGINES)),1)
ENGINE := $(SELECTED_ENGINES)
else
$(error Choose only one engine: `chatterbox`, `fish`, or `vibe`)
endif

ENGINE_VENV := $(VENV_ROOT)/$(ENGINE)
ENGINE_PYTHON := $(ENGINE_VENV)/bin/python
ENGINE_PIP := $(ENGINE_VENV)/bin/pip
COMMON_REQUIREMENTS := requirements/common.txt
ENGINE_REQUIREMENTS := requirements/$(ENGINE).txt

ENGINE_PREP_TARGETS_chatterbox :=
ENGINE_PREP_TARGETS_fish :=
ENGINE_PREP_TARGETS_vibe :=

ifeq ($(ENGINE),fish)
ifeq ($(FISH_SERVER_MODE),docker)
ENGINE_PREP_TARGETS_fish += fish-checkpoints-check fish-server-up fish-server-wait
endif
endif

RUN_DEPS := install $(ENGINE_PREP_TARGETS_$(ENGINE))
RUNNER := run_generation.py

COMMON_RUN_ARGS := --engine "$(ENGINE)"
COMMON_RUN_ARGS += $(if $(FILE),--file "$(FILE)",)
COMMON_RUN_ARGS += $(if $(AUDIO_PROMPT),--audio-prompt "$(AUDIO_PROMPT)",)

ENGINE_RUN_ARGS_chatterbox :=
ENGINE_RUN_ARGS_chatterbox += $(if $(CHATTERBOX_DEVICE),--device "$(CHATTERBOX_DEVICE)",)
ENGINE_RUN_ARGS_chatterbox += $(if $(CHATTERBOX_CFG_WEIGHT),--cfg-weight "$(CHATTERBOX_CFG_WEIGHT)",)

ENGINE_RUN_ARGS_fish :=
ENGINE_RUN_ARGS_fish += $(if $(FISH_SERVER_URL),--server-url "$(FISH_SERVER_URL)",)
ENGINE_RUN_ARGS_fish += $(if $(FISH_SERVER_API_KEY),--server-api-key "$(FISH_SERVER_API_KEY)",)
ENGINE_RUN_ARGS_fish += $(if $(FISH_REFERENCE_ID),--reference-id "$(FISH_REFERENCE_ID)",)
ENGINE_RUN_ARGS_fish += $(if $(FISH_REFERENCE_TEXT),--reference-text "$(FISH_REFERENCE_TEXT)",)
ENGINE_RUN_ARGS_fish += $(if $(FISH_LATENCY),--latency "$(FISH_LATENCY)",)
ENGINE_RUN_ARGS_fish += $(if $(FISH_SAMPLE_RATE),--sample-rate "$(FISH_SAMPLE_RATE)",)

ENGINE_RUN_ARGS_vibe :=
ENGINE_RUN_ARGS_vibe += $(if $(VIBE_RUN_MODEL_SOURCE),--model-path "$(VIBE_RUN_MODEL_SOURCE)",)
ENGINE_RUN_ARGS_vibe += $(if $(VIBE_DEVICE),--device "$(VIBE_DEVICE)",)
ENGINE_RUN_ARGS_vibe += $(if $(VIBE_VOICE_SAMPLES),--voice-samples "$(VIBE_VOICE_SAMPLES)",)
ENGINE_RUN_ARGS_vibe += $(if $(VIBE_CFG_SCALE),--cfg-scale "$(VIBE_CFG_SCALE)",)
ENGINE_RUN_ARGS_vibe += $(if $(VIBE_DDPM_STEPS),--ddpm-steps "$(VIBE_DDPM_STEPS)",)
ENGINE_RUN_ARGS_vibe += $(if $(VIBE_SEED),--seed "$(VIBE_SEED)",)
ENGINE_RUN_ARGS_vibe += $(if $(filter 1 true TRUE yes YES on ON,$(VIBE_DISABLE_PREFILL)),--disable-prefill,)

.PHONY: install run chatterbox fish vibe fish-download vibe-download fish-checkpoints-check fish-server-up fish-server-down fish-server-logs fish-server-wait

$(ENGINE_PYTHON):
	$(PYTHON) -m venv $(ENGINE_VENV)

install: $(ENGINE_PYTHON)
	$(ENGINE_PIP) install -r "$(COMMON_REQUIREMENTS)" -r "$(ENGINE_REQUIREMENTS)"

run: $(RUN_DEPS)
	$(ENGINE_PYTHON) $(RUNNER) $(COMMON_RUN_ARGS) $(ENGINE_RUN_ARGS_$(ENGINE))

chatterbox fish vibe:
	@:

fish-download:
	@sh -c 'test -n "$$HF_TOKEN" || { echo "Missing HF_TOKEN in .env or shell environment." >&2; exit 1; }'
	@mkdir -p "$(FISH_CHECKPOINT_DIR)"
	hf download "$(FISH_HF_MODEL)" --local-dir "$(FISH_MODEL_PATH)"

vibe-download:
	@mkdir -p "$(VIBE_MODEL_DIR)"
	hf download "$(VIBE_HF_MODEL)" --local-dir "$(VIBE_MODEL_PATH)"

fish-checkpoints-check:
	@test -d "$(FISH_MODEL_PATH)" || ( \
		echo "Missing Fish checkpoint directory: $(FISH_MODEL_PATH)" >&2; \
		echo "Run \`make fish-download\` to download model weights into that folder." >&2; \
		exit 1 \
	)
	@test -f "$(FISH_MODEL_PATH)/$(FISH_DECODER_FILENAME)" || ( \
		echo "Missing Fish decoder checkpoint: $(FISH_MODEL_PATH)/$(FISH_DECODER_FILENAME)" >&2; \
		echo "Expected Fish weights under $(FISH_MODEL_PATH)." >&2; \
		exit 1 \
	)
	@test -n "$$(ls -A "$(FISH_MODEL_PATH)" 2>/dev/null)" || ( \
		echo "Fish checkpoint directory is empty: $(FISH_MODEL_PATH)" >&2; \
		exit 1 \
	)

fish-server-up:
	$(DOCKER_COMPOSE) up -d fish-server

fish-server-down:
	$(DOCKER_COMPOSE) down

fish-server-logs:
	$(DOCKER_COMPOSE) logs -f fish-server

fish-server-wait:
	@echo "Waiting for Fish server at $(FISH_HEALTH_URL)..."
	@for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24; do \
		if curl -fsS "$(FISH_HEALTH_URL)" >/dev/null; then \
			echo "Fish server is ready."; \
			exit 0; \
		fi; \
		sleep 5; \
	done; \
	echo "Timed out waiting for Fish server at $(FISH_HEALTH_URL)." >&2; \
	exit 1
