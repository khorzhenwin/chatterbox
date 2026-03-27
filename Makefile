PYTHON ?= python3
VENV ?= .venv
VENV_PYTHON := $(VENV)/bin/python
VENV_PIP := $(VENV)/bin/pip

.PHONY: install run

$(VENV_PYTHON):
	$(PYTHON) -m venv $(VENV)

install: $(VENV_PYTHON)
	$(VENV_PIP) install -r requirements.txt

run: install
	$(VENV_PYTHON) generate_audio.py $(if $(FILE),--file "$(FILE)",) $(if $(AUDIO_PROMPT),--audio-prompt "$(AUDIO_PROMPT)",)
