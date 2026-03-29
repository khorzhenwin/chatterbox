-include .env
export HF_TOKEN

PYTHON ?= python3
VENV ?= .venv
VENV_PYTHON := $(VENV)/bin/python
VENV_PIP := $(VENV)/bin/pip
DOCKER_COMPOSE ?= docker compose
SELECTED_ENGINES := $(filter chatterbox fish,$(MAKECMDGOALS))
FISH_SERVER_MODE ?= docker
FISH_HEALTH_URL ?= $(patsubst %/v1/tts,%/v1/health,$(FISH_SERVER_URL))
FISH_MODEL_SUBDIR ?= fish-speech-1.5
FISH_MODEL_PATH := $(FISH_CHECKPOINT_DIR)/$(FISH_MODEL_SUBDIR)
FISH_DECODER_FILENAME ?= firefly-gan-vq-fsq-8x1024-21hz-generator.pth

ifeq ($(words $(SELECTED_ENGINES)),0)
ENGINE := chatterbox
else ifeq ($(words $(SELECTED_ENGINES)),1)
ENGINE := $(SELECTED_ENGINES)
else
$(error Choose only one engine: `chatterbox` or `fish`)
endif

SCRIPT_chatterbox := generate_audio.py
SCRIPT_fish := generate_fish_audio.py

RUN_DEPS := install

ifeq ($(ENGINE),fish)
ifeq ($(FISH_SERVER_MODE),docker)
RUN_DEPS += fish-checkpoints-check fish-server-up fish-server-wait
endif
endif

.PHONY: install run chatterbox fish fish-download fish-checkpoints-check fish-server-up fish-server-down fish-server-logs fish-server-wait

$(VENV_PYTHON):
	$(PYTHON) -m venv $(VENV)

install: $(VENV_PYTHON)
	$(VENV_PIP) install -r requirements.txt

run: $(RUN_DEPS)
	$(VENV_PYTHON) $(SCRIPT_$(ENGINE)) $(if $(FILE),--file "$(FILE)",) $(if $(AUDIO_PROMPT),--audio-prompt "$(AUDIO_PROMPT)",)

chatterbox fish:
	@:

fish-download:
	@sh -c 'test -n "$$HF_TOKEN" || { echo "Missing HF_TOKEN in .env or shell environment." >&2; exit 1; }'
	@mkdir -p "$(FISH_CHECKPOINT_DIR)"
	hf download "$(FISH_HF_MODEL)" --local-dir "$(FISH_MODEL_PATH)"

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
