# /// script
# requires-python = ">=3.11"
# dependencies = ["requests"]
# ///
import argparse
import os
import sys

import requests

# DEFAULT_VOICE_ID = "g10k86KeEUyBqW9lcKYg" # no longer allowed as of 2026-01-31: status 402: {"detail":{"status":"payment_required","message":"Free users cannot use library voices via the API. Please upgrade your subscription to use this voice"}}
DEFAULT_VOICE_ID = "JBFqnCBsd6RMkjVDRZzb"
DEFAULT_OUTPUT_FORMAT = "mp3_44100_128"
DEFAULT_MODEL_ID = "eleven_flash_v2_5"
DEFAULT_LANGUAGE_CODE = "es"
DEFAULT_SPEED = 0.8
DEFAULT_TIMEOUT_SECONDS = 30


class ElevenLabsError(Exception):
    pass


def text_to_speech(
    api_key: str,
    text: str,
    voice_id: str = DEFAULT_VOICE_ID,
    output_format: str = DEFAULT_OUTPUT_FORMAT,
    model_id: str = DEFAULT_MODEL_ID,
    language_code: str = DEFAULT_LANGUAGE_CODE,
    speed: float = DEFAULT_SPEED,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> bytes:
    """Request TTS audio from ElevenLabs API."""
    endpoint = (
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream"
        f"?output_format={output_format}"
    )
    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
    }
    payload = {
        "text": text,
        "model_id": model_id,
        "language_code": language_code,
        "voice_settings": {
            "speed": speed,
        },
    }

    response = requests.post(
        endpoint,
        headers=headers,
        json=payload,
        timeout=timeout_seconds,
    )

    if response.status_code != 200:
        raise ElevenLabsError(
            f"TTS request failed: {response.status_code} {response.text}"
        )

    return response.content


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate TTS audio using ElevenLabs API."
    )
    parser.add_argument(
        "--text",
        required=True,
        help="Text to convert to speech",
    )
    parser.add_argument(
        "-o",
        "--output",
        required=True,
        help="Output file path for the audio (e.g., /tmp/audio.mp3)",
    )
    parser.add_argument(
        "--voice-id",
        default=DEFAULT_VOICE_ID,
        help=f"ElevenLabs voice ID (default: {DEFAULT_VOICE_ID})",
    )
    parser.add_argument(
        "--model-id",
        default=DEFAULT_MODEL_ID,
        help=f"Model ID (default: {DEFAULT_MODEL_ID})",
    )
    parser.add_argument(
        "--language-code",
        default=DEFAULT_LANGUAGE_CODE,
        help=f"Language code (default: {DEFAULT_LANGUAGE_CODE})",
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=DEFAULT_SPEED,
        help=f"Speech speed (default: {DEFAULT_SPEED})",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"HTTP timeout in seconds (default: {DEFAULT_TIMEOUT_SECONDS})",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)

    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        raise ElevenLabsError("ELEVENLABS_API_KEY environment variable is not set.")

    audio_bytes = text_to_speech(
        api_key=api_key,
        text=args.text,
        voice_id=args.voice_id,
        model_id=args.model_id,
        language_code=args.language_code,
        speed=args.speed,
        timeout_seconds=args.timeout,
    )

    with open(args.output, "wb") as output_file:
        output_file.write(audio_bytes)

    print(f"Saved audio to {args.output}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except ElevenLabsError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
