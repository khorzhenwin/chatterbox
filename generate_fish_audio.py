from __future__ import annotations

import argparse
import io
import os
import time
import wave
from pathlib import Path

import ormsgpack
import requests
from audio_generation_common import (
    FISH_AUDIO_OUTPUT_DIR,
    add_shared_arguments,
    format_real_time_factor,
    format_seconds,
    prepare_generation_inputs,
)
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_SERVER_URL = "http://127.0.0.1:8080/v1/tts"
load_dotenv(PROJECT_ROOT / ".env")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert .txt files with a local Fish Speech server."
    )
    add_shared_arguments(parser, default_output_dir=FISH_AUDIO_OUTPUT_DIR)
    parser.add_argument(
        "--server-url",
        default=os.getenv("FISH_SERVER_URL", DEFAULT_SERVER_URL),
        help="Fish Speech TTS server URL.",
    )
    parser.add_argument(
        "--server-api-key",
        default=os.getenv("FISH_SERVER_API_KEY"),
        help="Optional bearer token if your local Fish server was started with --api-key.",
    )
    parser.add_argument(
        "--reference-id",
        default=os.getenv("FISH_REFERENCE_ID"),
        help="Optional saved Fish server reference ID to use instead of AUDIO_PROMPT.",
    )
    parser.add_argument(
        "--reference-text",
        type=Path,
        default=None,
        help=(
            "Optional transcript file for AUDIO_PROMPT. Defaults to "
            "FISH_REFERENCE_TEXT, then <prompt>.txt or <prompt>.wav.txt."
        ),
    )
    parser.add_argument(
        "--latency",
        choices=["normal", "balanced"],
        default=os.getenv("FISH_LATENCY", "balanced"),
        help="Fish server latency mode.",
    )
    parser.add_argument(
        "--sample-rate",
        type=int,
        default=int(os.getenv("FISH_SAMPLE_RATE", "44100")),
        help="Requested output sample rate for generated wav files.",
    )
    args = parser.parse_args()

    default_audio_prompt = os.getenv("FISH_AUDIO_PROMPT")
    if args.audio_prompt is None and default_audio_prompt:
        args.audio_prompt = Path(default_audio_prompt)

    default_reference_text = os.getenv("FISH_REFERENCE_TEXT")
    if args.reference_text is None and default_reference_text:
        args.reference_text = Path(default_reference_text)

    return args


def load_reference_text(
    audio_prompt: Path,
    reference_text_path: Path | None,
) -> str:
    if reference_text_path is not None:
        if not reference_text_path.exists() or not reference_text_path.is_file():
            raise FileNotFoundError(
                f"Reference transcript not found: {reference_text_path}"
            )
        reference_text = reference_text_path.read_text(encoding="utf-8").strip()
        if not reference_text:
            raise ValueError(
                f"Reference transcript is empty: {reference_text_path}"
            )
        return reference_text

    transcript_candidates = [
        audio_prompt.with_suffix(".txt"),
        Path(f"{audio_prompt}.txt"),
    ]
    for candidate in transcript_candidates:
        if candidate.exists() and candidate.is_file():
            reference_text = candidate.read_text(encoding="utf-8").strip()
            if reference_text:
                return reference_text

    candidate_list = ", ".join(str(candidate.name) for candidate in transcript_candidates)
    raise FileNotFoundError(
        "Local Fish generation needs transcript text for AUDIO_PROMPT. "
        f"Create one of: {candidate_list}"
    )


def build_reference_payload(
    audio_prompt: Path | None,
    reference_text_path: Path | None,
) -> list[dict[str, object]] | None:
    if audio_prompt is None:
        return None

    with audio_prompt.open("rb") as audio_file:
        audio_bytes = audio_file.read()
    reference_text = load_reference_text(audio_prompt, reference_text_path)

    transcript_source = reference_text_path.name if reference_text_path else audio_prompt.name
    print(f"Using audio prompt with transcript for {transcript_source}")
    return [{"audio": audio_bytes, "text": reference_text}]


def build_headers(server_api_key: str | None) -> dict[str, str]:
    headers = {"content-type": "application/msgpack"}
    if server_api_key:
        headers["authorization"] = f"Bearer {server_api_key}"
    return headers


def request_audio(
    *,
    server_url: str,
    server_api_key: str | None,
    payload: dict[str, object],
) -> bytes:
    try:
        response = requests.post(
            server_url,
            params={"format": "msgpack"},
            data=ormsgpack.packb(payload),
            headers=build_headers(server_api_key),
            timeout=(10, 1800),
        )
    except requests.RequestException as exc:
        raise ConnectionError(
            "Could not reach the Fish server. Start it first and verify "
            f"the URL is correct: {server_url}"
        ) from exc

    if response.status_code != 200:
        error_details = response.text.strip() or f"HTTP {response.status_code}"
        raise RuntimeError(f"Fish server request failed: {error_details}")

    return response.content


def read_wav_duration(audio_bytes: bytes) -> float:
    with wave.open(io.BytesIO(audio_bytes), "rb") as wav_file:
        frame_rate = wav_file.getframerate()
        frame_count = wav_file.getnframes()
    if frame_rate <= 0:
        return 0.0
    return frame_count / frame_rate


def main() -> None:
    args = parse_args()
    data_dir, output_dir, audio_prompt, text_files = prepare_generation_inputs(
        data_dir=args.data_dir,
        output_dir=args.output_dir,
        audio_prompt=args.audio_prompt,
        selected_files=args.selected_files,
    )

    if args.reference_id and audio_prompt:
        raise ValueError("Use either --reference-id or --audio-prompt, not both.")

    references = build_reference_payload(audio_prompt, args.reference_text)

    run_started_at = time.perf_counter()
    generated_files = 0
    total_audio_seconds = 0.0

    print(f"Using local Fish server at {args.server_url}...")
    for text_file in text_files:
        text = text_file.read_text(encoding="utf-8").strip()
        if not text:
            print(f"Skipping empty file: {text_file.name}")
            continue

        relative_path = text_file.relative_to(data_dir)
        output_file = output_dir / relative_path.with_suffix(".wav")
        output_file.parent.mkdir(parents=True, exist_ok=True)

        request_kwargs: dict[str, object] = {
            "text": text,
            "format": "wav",
            "latency": args.latency,
            "sample_rate": args.sample_rate,
            "streaming": False,
        }
        if args.reference_id:
            request_kwargs["reference_id"] = args.reference_id
        elif references:
            request_kwargs["references"] = references

        print(f"Generating audio for {relative_path}...")
        started_at = time.perf_counter()
        audio_bytes = request_audio(
            server_url=args.server_url,
            server_api_key=args.server_api_key,
            payload=request_kwargs,
        )
        elapsed_seconds = time.perf_counter() - started_at

        output_file.write_bytes(audio_bytes)
        audio_seconds = read_wav_duration(audio_bytes)
        total_audio_seconds += audio_seconds
        generated_files += 1

        print(
            f"Saved {output_file} "
            f"({format_seconds(elapsed_seconds)}, "
            f"audio {format_seconds(audio_seconds)}, "
            f"RTF {format_real_time_factor(elapsed_seconds, audio_seconds)})"
        )

    total_elapsed_seconds = time.perf_counter() - run_started_at
    print(
        "Fish Audio summary: "
        f"{generated_files} file(s), "
        f"{format_seconds(total_elapsed_seconds)} total, "
        f"{format_seconds(total_audio_seconds)} audio, "
        f"RTF {format_real_time_factor(total_elapsed_seconds, total_audio_seconds)}"
    )


if __name__ == "__main__":
    main()
