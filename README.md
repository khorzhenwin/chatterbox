# Chatterbox Text-to-Audio

This project reads every `.txt` file in the `data/` folder and generates a matching `.wav` file with the [ResembleAI Chatterbox model](https://huggingface.co/ResembleAI/chatterbox).

## Setup

```bash
make install
```

## Add text files

Place one or more `.txt` files inside `data/`.

Each generated audio file has a hard input limit of `1000` tokens. Keep every `.txt` file at or under that limit, and split longer scripts into multiple files before running generation.

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

To run a specific file under `data/`:

```bash
make run FILE=intro.txt
```

The script will:

- scan `data/` for `.txt` files
- load the Chatterbox model
- generate one `.wav` file per input text file
- write the audio files into `output/`, preserving subfolders

Example output:

```text
output/
  intro.wav
  scenes/
    scene-1.wav
```

## Optional voice prompt

If you want to clone the voice from a reference clip, pass an audio file:

```bash
make run AUDIO_PROMPT=path/to/reference.wav
```

You can combine both:

```bash
make run FILE=scenes/scene-1.txt AUDIO_PROMPT=path/to/reference.wav
```

## Notes

- The first run will download the model from Hugging Face.
- The script automatically uses `cuda`, then `mps`, then `cpu`, depending on what is available.
