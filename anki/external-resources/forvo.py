# /// script
# requires-python = ">=3.11"
# dependencies = ["requests"]
# ///
import argparse
import json
import os
import sys
import time
import urllib.parse

import requests

DEFAULT_API_URL_FREE = "https://apifree.forvo.com/"
DEFAULT_API_URL_COMMERCIAL = "https://apicommercial.forvo.com/"
DEFAULT_API_URL_CORPORATE = "https://apicorporate.forvo.com/api2/v1.1/"
ENDPOINT_URLS = {
    "free": DEFAULT_API_URL_FREE,
    "commercial": DEFAULT_API_URL_COMMERCIAL,
    "corporate": DEFAULT_API_URL_CORPORATE,
}

DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:85.0) "
    "Gecko/20100101 Firefox/85.0"
)


class ForvoError(Exception):
    pass


def build_request_url(
    api_url: str,
    api_key: str,
    text: str,
    language: str,
    gender: str | None = None,
    country_code: str | None = None,
) -> str:
    encoded_text = urllib.parse.quote(text)
    sex_param = f"/sex/{gender}" if gender else ""
    country_param = f"/country/{country_code}" if country_code else ""
    is_corporate = api_url == DEFAULT_API_URL_CORPORATE

    if is_corporate:
        return (
            f"{api_url}{api_key}/word-pronunciations/word/{encoded_text}"
            f"/language/{language}{sex_param}/order/rate-desc/limit/1{country_param}"
        )

    return (
        f"{api_url}/key/{api_key}/format/json/action/word-pronunciations"
        f"/word/{encoded_text}/language/{language}{sex_param}"
        f"/order/rate-desc/limit/1{country_param}"
    )


def get_forvo_audio(
    api_key: str,
    text: str,
    language: str,
    api_url: str = DEFAULT_API_URL_FREE,
    gender: str | None = None,
    country_code: str | None = None,
    throttle_seconds: float = 0.0,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> bytes:
    if throttle_seconds > 0:
        time.sleep(throttle_seconds)

    headers = {"User-Agent": DEFAULT_USER_AGENT}
    url = build_request_url(
        api_url=api_url,
        api_key=api_key,
        text=text,
        language=language,
        gender=gender,
        country_code=country_code,
    )

    response = requests.get(url, headers=headers, timeout=timeout_seconds)
    if response.status_code != 200:
        raise ForvoError(f"Request failed: {response.status_code} {response.content!r}")

    try:
        data = response.json()
    except json.JSONDecodeError as exc:
        raise ForvoError(f"Could not decode JSON: {exc}") from exc

    is_corporate = api_url == DEFAULT_API_URL_CORPORATE
    items = data["data"]["items"] if is_corporate else data["items"]
    if not items:
        raise ForvoError("No pronunciations found for the requested term.")

    audio_url = items[0]["pathmp3"]
    audio_request = requests.get(audio_url, headers=headers, timeout=timeout_seconds)
    if audio_request.status_code != 200:
        raise ForvoError(
            f"Audio download failed: {audio_request.status_code} {audio_request.content!r}"
        )

    return audio_request.content


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch Forvo pronunciation audio.")
    parser.add_argument(
        "--api-key",
        help="Forvo API key (defaults to FORVO_API_KEY env var)",
    )
    parser.add_argument(
        "--endpoint",
        choices=sorted(ENDPOINT_URLS.keys()),
        default="free",
        help="Forvo endpoint (free, commercial, corporate)",
    )
    parser.add_argument("--text", required=True, help="Text to pronounce")
    parser.add_argument("--language", required=True, help="Forvo language code")
    parser.add_argument("--gender", help="Gender filter (e.g., male, female)")
    parser.add_argument("--country", dest="country_code", help="Country filter (e.g., US)")
    parser.add_argument(
        "--throttle-seconds",
        type=float,
        default=0.0,
        help="Sleep before API request to avoid rate limiting",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="HTTP timeout in seconds",
    )
    parser.add_argument(
        "--output",
        help="Write mp3 to this path (omit to use --stdout)",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Write mp3 to stdout",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    api_key = args.api_key or os.environ.get("FORVO_API_KEY")
    if not api_key:
        raise ForvoError("Provide --api-key or set FORVO_API_KEY.")
    if not args.output and not args.stdout:
        raise ForvoError("Provide --output or use --stdout.")
    if args.output and args.stdout:
        raise ForvoError("Choose only one of --output or --stdout.")

    audio_bytes = get_forvo_audio(
        api_key=api_key,
        text=args.text,
        language=args.language,
        api_url=ENDPOINT_URLS[args.endpoint],
        gender=args.gender,
        country_code=args.country_code,
        throttle_seconds=args.throttle_seconds,
        timeout_seconds=args.timeout_seconds,
    )

    if args.stdout:
        sys.stdout.buffer.write(audio_bytes)
    else:
        with open(args.output, "wb") as output_file:
            output_file.write(audio_bytes)

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except ForvoError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
