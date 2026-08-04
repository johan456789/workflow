# /// script
# requires-python = ">=3.11"
# dependencies = ["requests", "beautifulsoup4"]
# ///
"""
Download US/UK pronunciation audio from Oxford Learner's Dictionaries.

Scrapes the search page
(https://www.oxfordlearnersdictionaries.com/search/english/?q=<word>)
for the headword's audio buttons (`.webtop` container) and downloads the
mp3/ogg files.

Caveats:
- Only single headwords have audio. Phrases and phrasal verbs (e.g. "run out")
  return a valid entry page with NO pronunciation audio.
- Requires a browser User-Agent; the site returns empty/302 responses for
  default clients.
- The page embeds a "Word of the Day" widget (`.wotd-box` in the right column)
  whose audio buttons look identical — they are excluded by scoping the search
  to `.webtop`.
"""
import argparse
import json
import re
import sys
import urllib.parse
from pathlib import Path

import requests
from bs4 import BeautifulSoup

SEARCH_URL_TEMPLATE = "https://www.oxfordlearnersdictionaries.com/search/english/?q={query}"

DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

ACCENTS = ("us", "uk")
FORMATS = ("mp3", "ogg")


class OxfordError(Exception):
    pass


def fetch_search_page(query: str, timeout: int) -> str:
    """Fetch the Oxford Learner's search page HTML for a query."""
    url = SEARCH_URL_TEMPLATE.format(query=urllib.parse.quote(query))
    headers = {"User-Agent": DEFAULT_USER_AGENT}
    response = requests.get(url, headers=headers, timeout=timeout)
    if response.status_code != 200:
        raise OxfordError(
            f"Failed to fetch search page ({url}): {response.status_code}"
        )
    return response.text


def extract_audios(html: str) -> list[dict]:
    """Extract headword pronunciation entries from the page HTML.

    Returns one entry per accent, each with the mp3 and ogg URLs.
    Only `.webtop` audio buttons are considered, so sidebar-widget audio
    (Word of the Day) is ignored.
    """
    soup = BeautifulSoup(html, "html.parser")
    audios: list[dict] = []

    for button in soup.select("div.webtop div.sound.audio_play_button"):
        mp3 = button.get("data-src-mp3")
        ogg = button.get("data-src-ogg")
        if not mp3:
            continue
        classes = button.get("class") or []
        if "pron-uk" in classes:
            accent = "uk"
        elif "pron-us" in classes:
            accent = "us"
        else:
            continue
        audios.append(
            {
                "accent": accent,
                "mp3": mp3,
                "ogg": ogg or "",
            }
        )

    return audios


def select_audios(audios: list[dict], accent: str) -> list[dict]:
    """Select the first pronunciation entry for each requested accent."""
    if accent == "both":
        selected: list[dict] = []
        for requested in ACCENTS:
            matches = [a for a in audios if a["accent"] == requested]
            if matches:
                selected.append(matches[0])
        if not selected:
            raise OxfordError("No US or UK pronunciation found")
        return selected

    matches = [a for a in audios if a["accent"] == accent]
    if not matches:
        raise OxfordError(f"No {accent.upper()} pronunciation found")
    return [matches[0]]


def download_audio(url: str, timeout: int) -> bytes:
    """Download audio content from URL."""
    headers = {"User-Agent": DEFAULT_USER_AGENT}
    response = requests.get(url, headers=headers, timeout=timeout)
    if response.status_code != 200:
        raise OxfordError(f"Failed to download audio ({url}): {response.status_code}")
    return response.content


def filename_slug(query: str) -> str:
    """Lowercase query with whitespace collapsed to underscores."""
    return re.sub(r"\s+", "_", query.strip().lower())


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download Oxford Learner's Dictionary pronunciation audio."
    )
    parser.add_argument(
        "query",
        help="Single headword to look up (phrases/phrasal verbs have no audio)",
    )
    parser.add_argument(
        "--accent",
        choices=[*ACCENTS, "both"],
        default="us",
        help="Accent to download: us, uk, or both (default: us)",
    )
    parser.add_argument(
        "--format",
        choices=[*FORMATS, "both"],
        default="mp3",
        help="Audio format: mp3, ogg, or both (default: mp3)",
    )
    parser.add_argument(
        "--output-dir",
        default=".",
        help="Directory to save the output files (default: current directory)",
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
        help="Output available pronunciation URLs as JSON instead of downloading",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)

    html = fetch_search_page(args.query, timeout=args.timeout)
    audios = extract_audios(html)

    if not audios:
        raise OxfordError(
            f"No pronunciation audio found for '{args.query}'. "
            "Oxford Learner's only provides audio for single headwords, "
            "not phrases or phrasal verbs."
        )

    if args.json:
        print(json.dumps(audios, indent=2))
        return 0

    selected = select_audios(audios, args.accent)
    requested_formats = FORMATS if args.format == "both" else [args.format]

    Path(args.output_dir).mkdir(parents=True, exist_ok=True)
    slug = filename_slug(args.query)

    for entry in selected:
        accent = entry["accent"]
        for fmt in requested_formats:
            url = entry[fmt]
            if not url:
                raise OxfordError(
                    f"No {fmt.upper()} URL for the {accent.upper()} pronunciation"
                )
            output_path = str(
                Path(args.output_dir) / f"ox_{accent}_{slug}.{fmt}"
            )
            print(
                f"Downloading {accent.upper()} pronunciation for '{args.query}' "
                f"({fmt})...",
                file=sys.stderr,
            )
            audio_bytes = download_audio(url, timeout=args.timeout)
            Path(output_path).write_bytes(audio_bytes)
            print(output_path)

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except OxfordError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
