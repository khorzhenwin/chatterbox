from __future__ import annotations

import argparse
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_ROOT_DIR = PROJECT_ROOT / "output"
CHATTERBOX_OUTPUT_DIR = OUTPUT_ROOT_DIR / "chatterbox"
FISH_AUDIO_OUTPUT_DIR = OUTPUT_ROOT_DIR / "fish-audio"


def add_shared_arguments(
    parser: argparse.ArgumentParser,
    *,
    default_output_dir: Path,
) -> argparse.ArgumentParser:
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help="Directory containing .txt files to convert.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=default_output_dir,
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
    return parser


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


def prepare_generation_inputs(
    *,
    data_dir: Path,
    output_dir: Path,
    audio_prompt: Path | None,
    selected_files: list[Path] | None,
) -> tuple[Path, Path, Path | None, list[Path]]:
    resolved_data_dir = data_dir.resolve()
    resolved_output_dir = output_dir.resolve()
    resolved_audio_prompt = audio_prompt.resolve() if audio_prompt else None

    if not resolved_data_dir.exists():
        raise FileNotFoundError(f"Data directory not found: {resolved_data_dir}")
    if resolved_audio_prompt and not resolved_audio_prompt.exists():
        raise FileNotFoundError(f"Audio prompt not found: {resolved_audio_prompt}")

    text_files = resolve_text_files(resolved_data_dir, selected_files)
    if not text_files:
        raise FileNotFoundError(f"No .txt files found in: {resolved_data_dir}")

    resolved_output_dir.mkdir(parents=True, exist_ok=True)
    return resolved_data_dir, resolved_output_dir, resolved_audio_prompt, text_files


def format_seconds(value: float) -> str:
    return f"{value:.2f}s"


def format_real_time_factor(elapsed_seconds: float, audio_seconds: float) -> str:
    if audio_seconds <= 0:
        return "n/a"
    return f"{elapsed_seconds / audio_seconds:.3f}"
