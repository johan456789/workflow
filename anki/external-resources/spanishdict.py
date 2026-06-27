# /// script
# requires-python = ">=3.11"
# dependencies = ["requests", "beautifulsoup4", "python-jsonpath", "ffmpeg-python"]
# ///
import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path

import ffmpeg
import requests
from bs4 import BeautifulSoup

SPANISHDICT_BASE_URL = "https://www.spanishdict.com/pronunciation"
VIDEO_URL_TEMPLATE = (
    "https://sd-pronunciation-processed-videos.sdcdns.com/mobile/"
    "lang_es_pron_{id}_speaker_{speakerId}_syllable_all_version_{version}.mp4"
)

DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) "
    "Gecko/20100101 Firefox/120.0"
)


class SpanishDictError(Exception):
    pass


def fetch_pronunciation_page(query: str, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> str:
    """Fetch the pronunciation page HTML for a given query."""
    url = f"{SPANISHDICT_BASE_URL}/{query}"
    headers = {"User-Agent": DEFAULT_USER_AGENT}
    response = requests.get(url, headers=headers, timeout=timeout)
    if response.status_code != 200:
        raise SpanishDictError(
            f"Failed to fetch pronunciation page: {response.status_code}"
        )
    return response.text


def extract_component_data(html: str) -> dict:
    """Extract window.SD_COMPONENT_DATA from the HTML."""
    soup = BeautifulSoup(html, "html.parser")

    # Method 1: Try the specific selector
    script_tag = soup.select_one("body > script:nth-child(11)")
    if script_tag and "window.SD_COMPONENT_DATA" in script_tag.get_text():
        return parse_component_data_script(script_tag.get_text())

    # Method 2: Fallback - search all script tags
    for script in soup.find_all("script"):
        text = script.get_text()
        if "window.SD_COMPONENT_DATA" in text:
            return parse_component_data_script(text)

    raise SpanishDictError("Could not find window.SD_COMPONENT_DATA in the page")


def parse_component_data_script(script_text: str) -> dict:
    """Parse the JSON from window.SD_COMPONENT_DATA = {...}"""
    match = re.search(r"window\.SD_COMPONENT_DATA\s*=\s*(\{.*?\});?\s*$", script_text, re.DOTALL)
    if not match:
        raise SpanishDictError("Could not parse window.SD_COMPONENT_DATA JSON")
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise SpanishDictError(f"Invalid JSON in SD_COMPONENT_DATA: {exc}") from exc


def get_pronunciations(data: dict) -> list[dict]:
    """Extract pronunciations from page data."""
    pronunciations = data.get("pronunciationProps", {}).get("pronunciations", [])
    if not pronunciations:
        raise SpanishDictError("No pronunciations found in the page data")
    return pronunciations


def select_pronunciation(pronunciations: list[dict], region: str) -> dict:
    """Select pronunciation based on region preference."""
    if region == "auto":
        # Prefer LATAM, fallback to SPAIN
        for pron in pronunciations:
            if pron.get("region") == "LATAM":
                return pron
        for pron in pronunciations:
            if pron.get("region") == "SPAIN":
                return pron
        # If neither found, return first available
        return pronunciations[0]
    else:
        # Find specific region
        region_upper = region.upper()
        for pron in pronunciations:
            if pron.get("region") == region_upper:
                return pron
        raise SpanishDictError(f"No pronunciation found for region: {region}")


def build_video_url(pronunciation: dict) -> str:
    """Build the video URL from pronunciation data."""
    return VIDEO_URL_TEMPLATE.format(
        id=pronunciation["id"],
        speakerId=pronunciation["speakerId"],
        version=pronunciation["version"],
    )


def build_video_filename(pronunciation: dict) -> str:
    """Build the original video filename without extension."""
    return (
        f"lang_es_pron_{pronunciation['id']}_speaker_{pronunciation['speakerId']}"
        f"_syllable_all_version_{pronunciation['version']}"
    )


def download_video(url: str, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> bytes:
    """Download video content from URL."""
    headers = {"User-Agent": DEFAULT_USER_AGENT}
    response = requests.get(url, headers=headers, timeout=timeout)
    if response.status_code != 200:
        raise SpanishDictError(f"Failed to download video: {response.status_code}")
    return response.content


def extract_audio_to_mp3(video_bytes: bytes, output_path: str) -> None:
    """Extract audio from video and save as MP3 using ffmpeg-python."""
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp_video:
        tmp_video.write(video_bytes)
        tmp_video_path = tmp_video.name

    try:
        (
            ffmpeg
            .input(tmp_video_path)
            .output(output_path, acodec="libmp3lame", ac=2, ar="44100")
            .overwrite_output()
            .run(capture_stdout=False, capture_stderr=True)
        )
    finally:
        os.unlink(tmp_video_path)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download SpanishDict pronunciation audio."
    )
    parser.add_argument(
        "query",
        help="Word or phrase to look up",
    )
    parser.add_argument(
        "--region",
        choices=["auto", "latam", "spain"],
        default="auto",
        help="Region preference: auto (LATAM first, then SPAIN), latam, or spain (default: auto)",
    )
    parser.add_argument(
        "--output-dir",
        default=".",
        help="Directory to save the output file (default: current directory)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="HTTP timeout in seconds (default: 30)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output pronunciation data as JSON instead of downloading",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)

    # Fetch and parse the pronunciation page
    html = fetch_pronunciation_page(args.query, timeout=args.timeout)
    data = extract_component_data(html)
    pronunciations = get_pronunciations(data)

    # If --json flag, output JSON and exit
    if args.json:
        print(json.dumps(pronunciations, indent=2))
        return 0

    # Select pronunciation based on region
    pronunciation = select_pronunciation(pronunciations, args.region)

    # Build URLs and filenames
    video_url = build_video_url(pronunciation)
    video_filename = build_video_filename(pronunciation)
    region_lower = pronunciation["region"].lower()
    output_filename = f"sd_{region_lower}_{args.query}_{video_filename}.mp3"
    output_path = str(Path(args.output_dir) / output_filename)

    # Download video and extract audio
    print(f"Downloading pronunciation for '{args.query}' ({pronunciation['region']})...", file=sys.stderr)
    video_bytes = download_video(video_url, timeout=args.timeout)

    print(f"Extracting audio to {output_path}...", file=sys.stderr)
    extract_audio_to_mp3(video_bytes, output_path)

    print(output_path)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except SpanishDictError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
