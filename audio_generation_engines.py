from __future__ import annotations

import argparse
import io
import os
import re
import time
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from audio_generation_common import (
    CHATTERBOX_OUTPUT_DIR,
    FISH_AUDIO_OUTPUT_DIR,
    VIBE_VOICE_OUTPUT_DIR,
    add_shared_arguments,
    env_int,
    env_path,
    env_truthy,
    format_real_time_factor,
    format_seconds,
    prepare_generation_inputs,
    resolve_device,
    split_csv_values,
)


@dataclass(frozen=True)
class EngineDefinition:
    key: str
    display_name: str
    description: str
    default_output_dir: Path
    add_arguments: Callable[[argparse.ArgumentParser], None]
    run: Callable[[argparse.Namespace], None]


def add_chatterbox_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--device",
        choices=["cuda", "mps", "cpu"],
        default=os.getenv("CHATTERBOX_DEVICE"),
        help="Optional override for the Chatterbox inference device.",
    )
    parser.add_argument(
        "--cfg-weight",
        type=float,
        default=float(os.getenv("CHATTERBOX_CFG_WEIGHT", "0.6")),
        help="Classifier-free guidance weight used by Chatterbox.",
    )


def run_chatterbox(args: argparse.Namespace) -> None:
    import torchaudio as ta
    from chatterbox.tts import ChatterboxTTS

    data_dir, output_dir, audio_prompt, text_files = prepare_generation_inputs(
        data_dir=args.data_dir,
        output_dir=args.output_dir,
        audio_prompt=args.audio_prompt,
        selected_files=args.selected_files,
    )

    device = resolve_device(args.device)
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
            wav = model.generate(
                text,
                audio_prompt_path=str(audio_prompt),
                cfg_weight=args.cfg_weight,
            )
        else:
            wav = model.generate(text, cfg_weight=args.cfg_weight)

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


DEFAULT_FISH_SERVER_URL = "http://127.0.0.1:8080/v1/tts"


def add_fish_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--server-url",
        default=os.getenv("FISH_SERVER_URL", DEFAULT_FISH_SERVER_URL),
        help="Fish Speech TTS server URL.",
    )
    parser.add_argument(
        "--server-api-key",
        default=os.getenv("FISH_SERVER_API_KEY"),
        help="Optional bearer token for a Fish Speech server.",
    )
    parser.add_argument(
        "--reference-id",
        default=os.getenv("FISH_REFERENCE_ID"),
        help="Optional saved Fish reference ID to use instead of AUDIO_PROMPT.",
    )
    parser.add_argument(
        "--reference-text",
        type=Path,
        default=env_path("FISH_REFERENCE_TEXT"),
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


def load_reference_text(audio_prompt: Path, reference_text_path: Path | None) -> str:
    if reference_text_path is not None:
        if not reference_text_path.exists() or not reference_text_path.is_file():
            raise FileNotFoundError(
                f"Reference transcript not found: {reference_text_path}"
            )
        reference_text = reference_text_path.read_text(encoding="utf-8").strip()
        if not reference_text:
            raise ValueError(f"Reference transcript is empty: {reference_text_path}")
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


def build_fish_headers(server_api_key: str | None) -> dict[str, str]:
    headers = {"content-type": "application/msgpack"}
    if server_api_key:
        headers["authorization"] = f"Bearer {server_api_key}"
    return headers


def request_fish_audio(
    *,
    server_url: str,
    server_api_key: str | None,
    payload: dict[str, object],
) -> bytes:
    import ormsgpack
    import requests

    try:
        response = requests.post(
            server_url,
            params={"format": "msgpack"},
            data=ormsgpack.packb(payload),
            headers=build_fish_headers(server_api_key),
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


def run_fish(args: argparse.Namespace) -> None:
    data_dir, output_dir, audio_prompt, text_files = prepare_generation_inputs(
        data_dir=args.data_dir,
        output_dir=args.output_dir,
        audio_prompt=args.audio_prompt or env_path("FISH_AUDIO_PROMPT", "AUDIO_PROMPT"),
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
        audio_bytes = request_fish_audio(
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


SPEAKER_LINE_PATTERN = re.compile(r"^Speaker\s+(\d+):\s*(.*)$", re.IGNORECASE)


def get_default_vibe_model_source() -> str:
    configured_model_path = os.getenv("VIBE_MODEL_PATH")
    configured_hf_model = os.getenv("VIBE_HF_MODEL", "microsoft/VibeVoice-1.5B")
    if configured_model_path and Path(configured_model_path).exists():
        return configured_model_path
    return configured_hf_model


def add_vibe_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--model-path",
        default=get_default_vibe_model_source(),
        help="Local model directory or Hugging Face repo ID for VibeVoice.",
    )
    parser.add_argument(
        "--device",
        choices=["cuda", "mps", "cpu"],
        default=os.getenv("VIBE_DEVICE"),
        help="Optional override for the VibeVoice inference device.",
    )
    parser.add_argument(
        "--voice-sample",
        dest="voice_sample_paths",
        action="append",
        type=Path,
        default=None,
        help=(
            "Repeat to provide one voice sample per speaker. "
            "Order maps to Speaker 1, Speaker 2, and so on."
        ),
    )
    parser.add_argument(
        "--voice-samples",
        default=os.getenv("VIBE_VOICE_SAMPLES"),
        help="Optional comma-separated list of voice sample paths.",
    )
    parser.add_argument(
        "--disable-prefill",
        action="store_true",
        default=env_truthy("VIBE_DISABLE_PREFILL"),
        help="Disable speech prefill so VibeVoice runs without voice cloning.",
    )
    parser.add_argument(
        "--cfg-scale",
        type=float,
        default=float(os.getenv("VIBE_CFG_SCALE", "1.3")),
        help="Classifier-free guidance scale for VibeVoice generation.",
    )
    parser.add_argument(
        "--ddpm-steps",
        type=int,
        default=int(os.getenv("VIBE_DDPM_STEPS", "10")),
        help="Number of diffusion inference steps.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=env_int("VIBE_SEED"),
        help="Optional random seed for reproducible VibeVoice sampling.",
    )


def normalize_vibe_script(text: str) -> tuple[str, list[int]]:
    stripped_lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not stripped_lines:
        raise ValueError("VibeVoice input is empty after trimming whitespace.")

    speaker_ids: list[int] = []
    has_labeled_lines = False
    has_unlabeled_lines = False

    for line in stripped_lines:
        match = SPEAKER_LINE_PATTERN.match(line)
        if match:
            has_labeled_lines = True
            speaker_id = int(match.group(1))
            if speaker_id not in speaker_ids:
                speaker_ids.append(speaker_id)
        else:
            has_unlabeled_lines = True

    if has_labeled_lines and has_unlabeled_lines:
        raise ValueError(
            "VibeVoice requires either a plain single-speaker script or lines that "
            "all use the format `Speaker N: ...`."
        )

    if not has_labeled_lines:
        single_speaker_text = " ".join(stripped_lines)
        return f"Speaker 1: {single_speaker_text}", [1]

    return "\n".join(stripped_lines), speaker_ids


def resolve_vibe_voice_samples(args: argparse.Namespace) -> list[Path]:
    resolved_paths: list[Path] = []

    if args.audio_prompt:
        resolved_paths.append(args.audio_prompt)

    for raw_path in split_csv_values(args.voice_samples):
        resolved_paths.append(Path(raw_path))

    for path in args.voice_sample_paths or []:
        resolved_paths.append(path)

    unique_paths: list[Path] = []
    for path in resolved_paths:
        if path not in unique_paths:
            unique_paths.append(path)

    return unique_paths


def load_vibevoice_modules() -> tuple[object, object]:
    try:
        from vibevoice.modular.modeling_vibevoice_inference import (
            VibeVoiceForConditionalGenerationInference,
        )
        from vibevoice.processor.vibevoice_processor import VibeVoiceProcessor
    except ImportError as exc:
        raise RuntimeError(
            "VibeVoice dependencies are not installed. Run `make install` to "
            "install the `vibevoice` package and its Python requirements."
        ) from exc

    return VibeVoiceForConditionalGenerationInference, VibeVoiceProcessor


def run_vibe(args: argparse.Namespace) -> None:
    import torch

    VibeVoiceForConditionalGenerationInference, VibeVoiceProcessor = (
        load_vibevoice_modules()
    )

    default_audio_prompt = env_path("AUDIO_PROMPT")
    data_dir, output_dir, audio_prompt, text_files = prepare_generation_inputs(
        data_dir=args.data_dir,
        output_dir=args.output_dir,
        audio_prompt=args.audio_prompt or default_audio_prompt,
        selected_files=args.selected_files,
    )

    device = resolve_device(args.device)
    if device == "mps" and not torch.backends.mps.is_available():
        print("MPS is not available. Falling back to CPU.")
        device = "cpu"

    if args.seed is not None:
        print(f"Setting VibeVoice seed to {args.seed}")
        torch.manual_seed(args.seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(args.seed)

    voice_sample_paths = resolve_vibe_voice_samples(
        argparse.Namespace(
            audio_prompt=audio_prompt,
            voice_sample_paths=args.voice_sample_paths,
            voice_samples=args.voice_samples,
        )
    )
    for path in voice_sample_paths:
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"Voice sample not found: {path}")

    print(f"Loading VibeVoice processor and model from {args.model_path}...")
    processor = VibeVoiceProcessor.from_pretrained(args.model_path)

    if device == "mps":
        load_dtype = torch.float32
        attn_impl_primary = "sdpa"
        device_map = None
    elif device == "cuda":
        load_dtype = torch.bfloat16
        attn_impl_primary = "flash_attention_2"
        device_map = "cuda"
    else:
        load_dtype = torch.float32
        attn_impl_primary = "sdpa"
        device_map = "cpu"

    try:
        model = VibeVoiceForConditionalGenerationInference.from_pretrained(
            args.model_path,
            torch_dtype=load_dtype,
            device_map=device_map,
            attn_implementation=attn_impl_primary,
        )
        if device == "mps":
            model.to("mps")
    except Exception as exc:
        if attn_impl_primary != "flash_attention_2":
            raise
        print(
            "VibeVoice failed to load with flash_attention_2. Falling back to SDPA."
        )
        model = VibeVoiceForConditionalGenerationInference.from_pretrained(
            args.model_path,
            torch_dtype=load_dtype,
            device_map=device_map,
            attn_implementation="sdpa",
        )
        if device == "mps":
            model.to("mps")
        else:
            print(f"Original load error: {exc}")

    model.eval()
    model.set_ddpm_inference_steps(num_steps=args.ddpm_steps)

    sample_rate = getattr(getattr(processor, "audio_processor", None), "sampling_rate", 24000)
    run_started_at = time.perf_counter()
    generated_files = 0
    total_audio_seconds = 0.0

    for text_file in text_files:
        text = text_file.read_text(encoding="utf-8").strip()
        if not text:
            print(f"Skipping empty file: {text_file.name}")
            continue

        formatted_script, speaker_ids = normalize_vibe_script(text)
        use_prefill = not args.disable_prefill and bool(voice_sample_paths)
        if not voice_sample_paths:
            use_prefill = False

        if use_prefill and len(voice_sample_paths) < len(speaker_ids):
            raise ValueError(
                "VibeVoice voice cloning needs at least one voice sample per "
                f"speaker. Found {len(voice_sample_paths)} voice sample(s) for "
                f"{len(speaker_ids)} speaker(s)."
            )

        selected_voice_samples = [str(path) for path in voice_sample_paths[: len(speaker_ids)]]
        if len(voice_sample_paths) > len(speaker_ids):
            print(
                f"Using the first {len(speaker_ids)} VibeVoice voice sample(s) for "
                f"{text_file.name}."
            )

        relative_path = text_file.relative_to(data_dir)
        output_file = output_dir / relative_path.with_suffix(".wav")
        output_file.parent.mkdir(parents=True, exist_ok=True)

        processor_kwargs: dict[str, object] = {
            "text": [formatted_script],
            "padding": True,
            "return_tensors": "pt",
            "return_attention_mask": True,
        }
        if selected_voice_samples:
            processor_kwargs["voice_samples"] = [selected_voice_samples]

        inputs = processor(**processor_kwargs)
        target_device = device if device != "cpu" else "cpu"
        for key, value in inputs.items():
            if torch.is_tensor(value):
                inputs[key] = value.to(target_device)

        print(
            f"Generating audio for {relative_path} with VibeVoice "
            f"({len(speaker_ids)} speaker(s), prefill={'on' if use_prefill else 'off'})..."
        )
        started_at = time.perf_counter()
        outputs = model.generate(
            **inputs,
            max_new_tokens=None,
            cfg_scale=args.cfg_scale,
            tokenizer=processor.tokenizer,
            generation_config={"do_sample": False},
            verbose=True,
            is_prefill=use_prefill,
        )
        elapsed_seconds = time.perf_counter() - started_at

        speech_output = outputs.speech_outputs[0]
        if speech_output is None:
            raise RuntimeError(f"VibeVoice did not return audio for {relative_path}")

        processor.save_audio(speech_output, output_path=str(output_file))
        audio_samples = (
            speech_output.shape[-1] if hasattr(speech_output, "shape") else len(speech_output)
        )
        audio_seconds = audio_samples / sample_rate if sample_rate else 0.0
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
        "VibeVoice summary: "
        f"{generated_files} file(s), "
        f"{format_seconds(total_elapsed_seconds)} total, "
        f"{format_seconds(total_audio_seconds)} audio, "
        f"RTF {format_real_time_factor(total_elapsed_seconds, total_audio_seconds)}"
    )


ENGINE_REGISTRY: dict[str, EngineDefinition] = {
    "chatterbox": EngineDefinition(
        key="chatterbox",
        display_name="Chatterbox",
        description="ResembleAI Chatterbox local inference.",
        default_output_dir=CHATTERBOX_OUTPUT_DIR,
        add_arguments=add_chatterbox_arguments,
        run=run_chatterbox,
    ),
    "fish": EngineDefinition(
        key="fish",
        display_name="Fish Audio",
        description="Fish Speech via a self-hosted local server.",
        default_output_dir=FISH_AUDIO_OUTPUT_DIR,
        add_arguments=add_fish_arguments,
        run=run_fish,
    ),
    "vibe": EngineDefinition(
        key="vibe",
        display_name="VibeVoice",
        description="Microsoft VibeVoice 1.5B via the community runtime.",
        default_output_dir=VIBE_VOICE_OUTPUT_DIR,
        add_arguments=add_vibe_arguments,
        run=run_vibe,
    ),
}


def get_supported_engine_names() -> tuple[str, ...]:
    return tuple(ENGINE_REGISTRY.keys())


def get_engine_definition(engine_name: str) -> EngineDefinition:
    return ENGINE_REGISTRY[engine_name]


def add_shared_engine_arguments(
    parser: argparse.ArgumentParser,
    engine_name: str,
) -> argparse.ArgumentParser:
    default_audio_prompt = env_path("AUDIO_PROMPT")
    engine = get_engine_definition(engine_name)
    return add_shared_arguments(
        parser,
        default_output_dir=engine.default_output_dir,
        default_audio_prompt=default_audio_prompt,
    )
