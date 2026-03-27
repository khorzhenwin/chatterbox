from __future__ import annotations

import argparse
from pathlib import Path

import torch
import torchaudio as ta
from chatterbox.tts import ChatterboxTTS


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "output"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert .txt files in the data folder to .wav files."
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help="Directory containing .txt files to convert.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory where generated .wav files will be saved.",
    )
    parser.add_argument(
        "--audio-prompt",
        type=Path,
        default=None,
        help="Optional reference speaker audio file for voice cloning.",
    )
    parser.add_argument(
        "--file",
        dest="selected_files",
        action="append",
        type=Path,
        default=None,
        help=(
            "Optional .txt file under the data directory to process. "
            "Repeat this flag to process multiple files."
        ),
    )
    return parser.parse_args()


def resolve_device() -> str:
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def load_text_files(data_dir: Path) -> list[Path]:
    return sorted(path for path in data_dir.rglob("*.txt") if path.is_file())


def resolve_text_files(
    data_dir: Path, selected_files: list[Path] | None
) -> list[Path]:
    if not selected_files:
        return load_text_files(data_dir)

    resolved_files: list[Path] = []
    for selected_file in selected_files:
        text_file = (data_dir / selected_file).resolve()
        try:
            text_file.relative_to(data_dir)
        except ValueError as exc:
            raise ValueError(
                f"Selected file must be inside the data directory: {selected_file}"
            ) from exc

        if text_file.suffix.lower() != ".txt":
            raise ValueError(f"Selected file must be a .txt file: {selected_file}")
        if not text_file.exists() or not text_file.is_file():
            raise FileNotFoundError(f"Selected file not found: {selected_file}")

        if text_file not in resolved_files:
            resolved_files.append(text_file)

    return sorted(resolved_files)


def main() -> None:
    args = parse_args()
    data_dir = args.data_dir.resolve()
    output_dir = args.output_dir.resolve()
    audio_prompt = args.audio_prompt.resolve() if args.audio_prompt else None

    if not data_dir.exists():
        raise FileNotFoundError(f"Data directory not found: {data_dir}")
    if audio_prompt and not audio_prompt.exists():
        raise FileNotFoundError(f"Audio prompt not found: {audio_prompt}")

    text_files = resolve_text_files(data_dir, args.selected_files)
    if not text_files:
        raise FileNotFoundError(f"No .txt files found in: {data_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)

    device = resolve_device()
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
        if audio_prompt:
            wav = model.generate(text, audio_prompt_path=str(audio_prompt))
        else:
            wav = model.generate(text)

        if wav.dim() == 1:
            wav = wav.unsqueeze(0)

        ta.save(str(output_file), wav.cpu(), model.sr)
        print(f"Saved {output_file}")


if __name__ == "__main__":
    main()
