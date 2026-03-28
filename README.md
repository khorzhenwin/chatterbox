# Text-to-Audio Comparison

This project reads every `.txt` file in the `data/` folder and generates matching `.wav` files with either:

- the [ResembleAI Chatterbox model](https://huggingface.co/ResembleAI/chatterbox)
- the [Fish Audio S2 Pro model family](https://huggingface.co/fishaudio/s2-pro) via a self-hosted Fish Speech server

## Setup

```bash
make install
```

## Add text files

Place one or more `.txt` files inside `data/`.

Each generated audio file has a hard input limit of `800` tokens. Keep every `.txt` file at or under that limit, and split longer scripts into multiple files before running generation.

Example:

```text
data/
  intro.txt
  scenes/
    scene-1.txt
```

## Run

```bash
make run
```

That defaults to the Chatterbox script and writes files into `output/chatterbox/`.

To run Chatterbox explicitly:

```bash
make run chatterbox
```

To run Fish Audio:

```bash
make run fish
```

That now auto-starts a local Dockerized Fish Speech server from this repo when `FISH_SERVER_MODE=docker` in `.env`. By default it targets `http://127.0.0.1:8080/v1/tts`.

To run a specific file under `data/`:

```bash
make run chatterbox FILE=intro.txt
```

The script will:

- scan `data/` for `.txt` files
- load the selected engine
- generate one `.wav` file per input text file
- write the audio files into `output/`, preserving subfolders under the engine name
- print simple timing stats so you can compare generation speed

Example output:

```text
output/
  chatterbox/
    intro.wav
    scenes/
      scene-1.wav
  fish-audio/
    intro.wav
    scenes/
      scene-1.wav
```

## Optional voice prompt

If you want to clone the voice from a reference clip, pass an audio file:

```bash
make run chatterbox AUDIO_PROMPT=path/to/reference.wav
```

You can combine both:

```bash
make run fish FILE=scenes/scene-1.txt AUDIO_PROMPT=path/to/reference.wav
```

For Fish Audio, put the model weights under `fish-checkpoints/s2-pro/` first, then run:

```bash
make run fish
```

One simple way to place them there is:

```bash
hf download fishaudio/s2-pro --local-dir fish-checkpoints/s2-pro
```

The project will run `docker compose up -d fish-server`, wait for `/v1/health`, and then call the local server.

Useful server commands:

```bash
make fish-server-up
make fish-server-logs
make fish-server-down
```

By default the script calls `http://127.0.0.1:8080/v1/tts`.

If you pass `AUDIO_PROMPT` to Fish Audio, also create a transcript text file next to it using either the same stem or the full filename plus `.txt`. For example, `reference.wav` can use `reference.txt` or `reference.wav.txt`.

## Notes

- The first run will download the model from Hugging Face.
- Chatterbox automatically uses `cuda`, then `mps`, then `cpu`, depending on what is available.
- Fish Audio local serving in this repo uses the official `fishaudio/fish-speech` Docker image.
- The default Docker image is CPU-only for compatibility. It is convenient for wiring things up, but real performance will usually require a Linux GPU host. If you have one, switch `FISH_DOCKER_IMAGE` to `fishaudio/fish-speech:server-cuda`.
