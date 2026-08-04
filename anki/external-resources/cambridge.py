# /// script
# requires-python = ">=3.11"
# dependencies = ["requests", "beautifulsoup4"]
# ///
"""
Download US/UK pronunciations from Cambridge Dictionary.

Scraping approach (CSS selectors, URL structure) adapted from
https://github.com/chenelias/cambridge-dictionary-api (MIT License).

MIT License

Copyright (c) EliasChen

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""
import argparse
import json
import re
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

SITE_BASE_URL = "https://dictionary.cambridge.org"
PAGE_URL_TEMPLATE = SITE_BASE_URL + "/{nation}/dictionary/english/{entry}"

DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


class CambridgeError(Exception):
    pass


def sanitize_query(query: str) -> str:
    """Sanitize a query into a URL-safe entry slug."""
    slug = re.sub(r"[^a-zA-Z0-9'\- ]", "", query).strip().lower()
    return re.sub(r"\s+", "-", slug)


def fetch_dictionary_page(entry: str, nation: str, timeout: int) -> str:
    """Fetch the Cambridge Dictionary page HTML for a given entry and nation."""
    url = PAGE_URL_TEMPLATE.format(nation=nation, entry=entry)
    headers = {"User-Agent": DEFAULT_USER_AGENT}
    response = requests.get(url, headers=headers, timeout=timeout)
    if response.status_code != 200:
        raise CambridgeError(
            f"Failed to fetch dictionary page ({url}): {response.status_code}"
        )
    return response.text


def extract_pronunciations(html: str) -> list[dict]:
    """Extract pronunciation entries from page HTML."""
    soup = BeautifulSoup(html, "html.parser")
    pronunciations: list[dict] = []

    for header in soup.select(".pos-header.dpos-h"):
        pos_node = header.select_one(".dpos-g") or header.select_one(".dpos")
        pos = pos_node.get_text(strip=True) if pos_node else ""

        if "phrasal verb" in pos.lower():
            continue

        for node in header.select(".dpron-i"):
            audio_src = node.select_one("audio source")
            pron_node = node.select_one(".pron.dpron")
            if not audio_src or not pron_node:
                continue
            region_node = node.select_one(".region.dreg")
            pronunciations.append(
                {
                    "pos": pos,
                    "lang": region_node.get_text(strip=True) if region_node else "",
                    "url": SITE_BASE_URL + audio_src.get("src"),
                    "pron": pron_node.get_text(strip=True),
                }
            )

    if not pronunciations:
        raise CambridgeError(
            "No pronunciations found on the page (phrasal verb entries are skipped "
            "because Cambridge only records audio for the headword, not the phrase)"
        )

    return pronunciations


def select_pronunciations(
    pronunciations: list[dict], nation: str
) -> list[dict]:
    """Select pronunciation(s) for a requested nation."""
    if nation == "both":
        selected: list[dict] = []
        for lang in ("us", "uk"):
            matches = [p for p in pronunciations if p["lang"] == lang]
            if matches:
                selected.append(matches[0])
        if not selected:
            raise CambridgeError("No US or UK pronunciations found")
        return selected

    matches = [p for p in pronunciations if p["lang"] == nation]
    if not matches:
        raise CambridgeError(f"No {nation.upper()} pronunciation found")
    return [matches[0]]


def download_audio(url: str, timeout: int) -> bytes:
    """Download audio content from URL."""
    headers = {"User-Agent": DEFAULT_USER_AGENT}
    response = requests.get(url, headers=headers, timeout=timeout)
    if response.status_code != 200:
        raise CambridgeError(f"Failed to download audio: {response.status_code}")
    return response.content


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download Cambridge Dictionary pronunciation audio."
    )
    parser.add_argument(
        "query",
        help="Word or phrase to look up",
    )
    parser.add_argument(
        "--nation",
        choices=["us", "uk", "both"],
        default="both",
        help="Accent to download: us, uk, or both (default: both)",
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
        help="Output pronunciation data as JSON instead of downloading",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    entry = sanitize_query(args.query)

    html = fetch_dictionary_page(entry, "us", timeout=args.timeout)
    pronunciations = extract_pronunciations(html)

    if args.json:
        print(json.dumps(pronunciations, indent=2))
        return 0

    selected = select_pronunciations(pronunciations, args.nation)

    Path(args.output_dir).mkdir(parents=True, exist_ok=True)

    for pronunciation in selected:
        lang = pronunciation["lang"]
        output_filename = f"cd_{lang}_{args.query}.mp3"
        output_path = str(Path(args.output_dir) / output_filename)

        print(
            f"Downloading {lang.upper()} pronunciation for '{args.query}' "
            f"({pronunciation['pron']})...",
            file=sys.stderr,
        )
        audio_bytes = download_audio(pronunciation["url"], timeout=args.timeout)
        Path(output_path).write_bytes(audio_bytes)
        print(output_path)

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except CambridgeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
