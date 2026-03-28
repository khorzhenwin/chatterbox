from __future__ import annotations

import argparse
import time

import torch
import torchaudio as ta
from audio_generation_common import (
    CHATTERBOX_OUTPUT_DIR,
    add_shared_arguments,
    format_real_time_factor,
    format_seconds,
    prepare_generation_inputs,
)
from chatterbox.tts import ChatterboxTTS


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert .txt files in the data folder to .wav files."
    )
    add_shared_arguments(parser, default_output_dir=CHATTERBOX_OUTPUT_DIR)
    return parser.parse_args()


def resolve_device() -> str:
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"

def main() -> None:
    args = parse_args()
    data_dir, output_dir, audio_prompt, text_files = prepare_generation_inputs(
        data_dir=args.data_dir,
        output_dir=args.output_dir,
        audio_prompt=args.audio_prompt,
        selected_files=args.selected_files,
    )

    device = resolve_device()
    run_started_at = time.perf_counter()
    generated_files = 0
    total_audio_seconds = 0.0

    print(f"Loading Chatterbox model on {device}...")
    model = ChatterboxTTS.from_pretrained(device=device)

    for text_file in text_files:
        text = text_file.read_text(encoding="utf-8").strip()
        if not text:
            print(f"Skipping empty file: {text_file.name}")
            continue

        relative_path = text_file.relative_to(data_dir)
        output_file = output_dir / relative_path.with_suffix(".wav")
        output_file.parent.mkdir(parents=True, exist_ok=True)

        print(f"Generating audio for {relative_path}...")
        started_at = time.perf_counter()
        if audio_prompt:
            wav = model.generate(text, audio_prompt_path=str(
                audio_prompt), cfg_weight=0.6)
        else:
            wav = model.generate(text, cfg_weight=0.6)

        if wav.dim() == 1:
            wav = wav.unsqueeze(0)

        elapsed_seconds = time.perf_counter() - started_at
        audio_seconds = wav.shape[-1] / model.sr
        total_audio_seconds += audio_seconds
        generated_files += 1

        ta.save(str(output_file), wav.cpu(), model.sr)
        print(
            f"Saved {output_file} "
            f"({format_seconds(elapsed_seconds)}, "
            f"audio {format_seconds(audio_seconds)}, "
            f"RTF {format_real_time_factor(elapsed_seconds, audio_seconds)})"
        )

    total_elapsed_seconds = time.perf_counter() - run_started_at
    print(
        "Chatterbox summary: "
        f"{generated_files} file(s), "
        f"{format_seconds(total_elapsed_seconds)} total, "
        f"{format_seconds(total_audio_seconds)} audio, "
        f"RTF {format_real_time_factor(total_elapsed_seconds, total_audio_seconds)}"
    )


if __name__ == "__main__":
    main()
