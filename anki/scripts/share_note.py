#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""Produce shareable Anki + preview URLs for a note, deterministically.

Avoids the recurring c1/c2 mislabeling bug: card IDs from findCards are NOT
ordered by cloze number, so instead of assuming ID order this script maps each
card ID through cardsInfo and sorts by its real `ord` field before labeling.

Usage:
  uv run scripts/share_note.py --id NID

Output (stdout):
  c1: http://<lan-ip>:4367/<cid>
  c2: http://<lan-ip>:4367/<cid>
  ...
  Anki: anki://x-callback-url/browser?search=nid%3A<NID>

Starts the card preview server on port 4367 if it is not already running.
"""
from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ANKI_URL = "http://127.0.0.1:8765"
PORT = 4367
SCRIPT_DIR = Path(__file__).resolve().parent


def anki_request(action: str, **params):
    body = json.dumps({"action": action, "version": 6, "params": params}).encode()
    req = urllib.request.Request(ANKI_URL, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        payload = json.loads(resp.read())
    if payload.get("error"):
        raise RuntimeError(f"AnkiConnect error: {payload['error']}")
    return payload["result"]


def lan_ip() -> str:
    try:
        out = subprocess.check_output(["hostname", "-I"], text=True, stderr=subprocess.DEVNULL).split()
        if out:
            return out[0]
    except Exception:
        pass
    for iface in ("en0", "en1"):
        try:
            out = subprocess.check_output(["ipconfig", "getifaddr", iface], text=True, stderr=subprocess.DEVNULL).strip()
            if out:
                return out
        except Exception:
            pass
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        pass
    finally:
        s.close()
    return "127.0.0.1"


def server_up(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=2) as resp:
            return resp.status == 200
    except Exception:
        return False


def ensure_server(port: int) -> bool:
    if server_up(port):
        return True
    cmd = [sys.executable, str(SCRIPT_DIR / "card_server.py"), "--port", str(port)]
    log = open("/tmp/card_server.log", "ab")
    subprocess.Popen(cmd, stdout=log, stderr=log, start_new_session=True)
    for _ in range(100):
        time.sleep(0.2)
        if server_up(port):
            return True
    return False


def share(nid: int) -> int:
    cards = anki_request("findCards", query=f"nid:{nid}")
    if not cards:
        print(f"error: no cards for note {nid}", file=sys.stderr)
        return 1
    info = anki_request("cardsInfo", cards=cards)
    ordered = sorted(info, key=lambda c: c["ord"])

    if not ensure_server(PORT):
        print(f"error: card server not reachable on port {PORT}", file=sys.stderr)
        return 1
    ip = lan_ip()

    for card in ordered:
        label = f"c{card['ord'] + 1}"
        print(f"{label}: http://{ip}:{PORT}/{card['cardId']}")
    print(f"Anki: anki://x-callback-url/browser?search=nid%3A{nid}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Emit per-card preview URLs (ordered by cloze number) plus the note's Anki URL")
    p.add_argument("--id", type=int, required=True, help="Anki note ID")
    args = p.parse_args()
    try:
        return share(args.id)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())