---
name: chatterbox-direct-input-splitting
description: Prepare direct user-provided text for this Chatterbox project by saving it into `data/` as one or more `.txt` files and enforcing the project's hard `1000`-token limit per generated audio file. Use when the user pastes narration, story text, scripts, or other audio content directly into chat and wants input files or audio generation.
---

# Chatterbox Direct Input Splitting

## Instructions

When the user provides text directly in chat for this repository:

1. Treat `1000` tokens as a hard maximum for each generated audio file.
2. Never put a pasted script that may exceed that limit into a single `.txt` file.
3. Split long text into multiple sequential `.txt` files under `data/` before running generation.
4. Prefer splits at paragraph, sentence, or dialogue boundaries. If needed, use smaller clause-level breaks to stay under the limit.
5. If exact token counting is unavailable, split conservatively. It is better to create more files than to risk exceeding the limit.

## File creation rules

- Put generated text input files under `data/`.
- Preserve any user intent about naming.
- If the user gives a base name, use ordered suffixes such as `story-1.txt`, `story-2.txt`, `story-3.txt`.
- If matching an existing numbered pattern, continue that pattern consistently.
- Keep chunk order obvious from filenames.

## Working rule

Before generating audio from direct chat input, first decide whether the text needs splitting. If there is any reasonable chance a single file would cross the `1000`-token limit, split it immediately instead of asking for confirmation unless the user explicitly asked for a different structure.

## Output expectations

When you create split files from direct input:

- Mention that the text was split to respect the hard `1000`-token-per-audio limit.
- List the created files briefly.
- Preserve the original text content as closely as possible aside from safe chunk boundaries.

## Example

User provides a long horror script directly in chat and asks to generate audio.

Expected behavior:

1. Save the text into multiple files such as `data/horror-1.txt`, `data/horror-2.txt`, `data/horror-3.txt`.
2. Keep each chunk safely below the hard `1000`-token limit.
3. Only then proceed with the normal generation workflow.
