from __future__ import annotations

import argparse
from collections.abc import Sequence

from dotenv import load_dotenv

from audio_generation_common import PROJECT_ROOT
from audio_generation_engines import (
    add_shared_engine_arguments,
    get_engine_definition,
    get_supported_engine_names,
)


def build_parser(
    *,
    engine_name: str,
    default_engine: str | None,
) -> argparse.ArgumentParser:
    engine = get_engine_definition(engine_name)
    parser = argparse.ArgumentParser(
        description=(
            "Generate `.wav` files from text files with the selected speech engine. "
            f"Current engine: {engine.display_name}."
        )
    )
    parser.add_argument(
        "--engine",
        choices=get_supported_engine_names(),
        default=default_engine or engine_name,
        help="Speech engine to use for this run.",
    )
    add_shared_engine_arguments(parser, engine_name)
    engine.add_arguments(parser)
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    default_engine: str | None = None,
) -> None:
    load_dotenv(PROJECT_ROOT / ".env")

    bootstrap = argparse.ArgumentParser(add_help=False)
    bootstrap.add_argument(
        "--engine",
        choices=get_supported_engine_names(),
        default=default_engine or "chatterbox",
    )
    known_args, _ = bootstrap.parse_known_args(argv)

    parser = build_parser(
        engine_name=known_args.engine,
        default_engine=default_engine,
    )
    args = parser.parse_args(argv)
    engine = get_engine_definition(args.engine)
    engine.run(args)


if __name__ == "__main__":
    main()
