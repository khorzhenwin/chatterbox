# Text-to-Audio Engines

This project reads `.txt` files from `data/` and generates matching `.wav` files through a shared engine runner. The repo currently supports:

- [ResembleAI Chatterbox](https://huggingface.co/ResembleAI/chatterbox)
- [Fish Speech 1.5](https://huggingface.co/fishaudio/fish-speech-1.5) through a self-hosted Fish server
- [Microsoft VibeVoice-1.5B](https://huggingface.co/microsoft/VibeVoice-1.5B)

The Python side is now engine-based, so new models can plug into the same CLI and `Makefile` flow instead of adding one-off scripts.

## Setup

```bash
make install
```

Each engine installs into its own virtualenv under `.venvs/` so model-specific dependency stacks can evolve independently.

## Add Text Files

Place one or more `.txt` files under `data/`.

Each generated audio file should stay at or under the project's hard `800`-token limit. Split longer scripts into multiple files before running generation.

Example:

```text
data/
  intro.txt
  scenes/
    scene-1.txt
```

## Run An Engine

```bash
make run
```

That defaults to Chatterbox and writes audio into `output/chatterbox/`.

Explicit engines:

```bash
make install chatterbox
make install fish
make install vibe

make run chatterbox
make run fish
make run vibe
```

Run a specific file:

```bash
make run vibe FILE=intro.txt
```

All engines share the same runner behavior:

- scan `data/` for `.txt` files
- load the selected engine
- generate one `.wav` file per input text file
- preserve subfolders under `output/<engine>/`
- print simple timing stats for each run

Example output:

```text
output/
  chatterbox/
    intro.wav
  fish-audio/
    intro.wav
  vibe-voice/
    intro.wav
```

## Voice Prompts

Single-speaker engines can use `AUDIO_PROMPT`:

```bash
make run chatterbox AUDIO_PROMPT=path/to/reference.wav
make run fish AUDIO_PROMPT=path/to/reference.wav
```

VibeVoice supports either plain single-speaker text or multi-speaker scripts.

Single-speaker VibeVoice:

```bash
make run vibe AUDIO_PROMPT=vibe-voice/voices/host.wav
```

Multi-speaker VibeVoice:

```text
Speaker 1: Welcome back to the show.
Speaker 2: Thanks for having me.
Speaker 1: Let's get started.
```

Provide one voice sample per speaker in order:

```bash
make run vibe VIBE_VOICE_SAMPLES=vibe-voice/voices/host.wav,vibe-voice/voices/guest.wav
```

If you want to skip voice cloning and let VibeVoice run without speech prefill:

```bash
make run vibe VIBE_DISABLE_PREFILL=1
```

## Fish Speech

Fish uses a local API server. When `FISH_SERVER_MODE=docker`, `make run fish` will:

1. check that the local checkpoints exist
2. run `docker compose up -d fish-server`
3. wait for `/v1/health`
4. generate audio through `http://127.0.0.1:8080/v1/tts`

Download checkpoints into `fish-checkpoints/` with:

```bash
make fish-download
```

Useful Fish commands:

```bash
make fish-server-up
make fish-server-logs
make fish-server-down
make fish-download
```

If you pass `AUDIO_PROMPT` to Fish, also create a transcript file next to it using either the same stem or the full filename plus `.txt`. For example, `reference.wav` can use `reference.txt` or `reference.wav.txt`.

## VibeVoice

This repo defaults to the official `microsoft/VibeVoice-1.5B` weights, but it uses the community-maintained `vibevoice` Python runtime because Microsoft removed the original TTS code from the public repo after release. The runtime remains compatible with the published model weights.

Project-local VibeVoice assets live under `vibe-voice/`:

- `vibe-voice/models/` for optional downloaded weights
- `vibe-voice/voices/` for optional speaker reference clips

To pre-download the official model into the repo instead of relying on the Hugging Face cache:

```bash
make vibe-download
```

If `vibe-voice/models/VibeVoice-1.5B/` exists, `make run vibe` will use it automatically. Otherwise it falls back to the Hugging Face repo ID.

## Environment

Copy `.env.example` to `.env` if you want persistent defaults for engine settings, model paths, or prompts.

## Notes

- Chatterbox automatically uses `cuda`, then `mps`, then `cpu`, unless you override the device.
- Fish local serving in this repo uses the official `fishaudio/fish-speech:v1.5.1` image.
- VibeVoice is optimized for long-form conversational speech and works best when multi-speaker scripts are labeled as `Speaker N:`.
- The VibeVoice model card notes that the public 1.5B release is intended for research usage and supports English and Chinese best: [model card](https://huggingface.co/microsoft/VibeVoice-1.5B).
