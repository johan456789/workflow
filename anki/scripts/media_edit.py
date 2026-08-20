# /// script
# requires-python = ">=3.11"
# ///
"""Gatekeeper in front of AnkiConnect media operations.

All media storage/removal MUST pass through this script. It only ever calls
AnkiConnect with the `path` (or `url`) parameter of storeMediaFile — never with
base64 `data`. Encoding binary media as base64 (e.g. via `jq --rawfile`) mangles
the bytes and corrupts the file, so this gatekeeper deliberately removes that
footgun by requiring a real on-disk file.

Usage:
  uv run media_edit.py store  --filename "audio.mp3" --file /path/to/audio.mp3
  uv run media_edit.py delete --filename "audio.mp3"
  uv run media_edit.py check  --filename "audio.mp3"

Flags:
  --no-sync   by default store/delete call `sync` afterwards (matching
              anki_edit.py, which always syncs on a write). Pass --no-sync to
              skip it.

Exit code is non-zero when the operation fails, so it can gate a tool/agent
from writing bad data.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

ANKI_URL = "http://localhost:8765"


def anki_request(action: str, **params):
    body = json.dumps({"action": action, "version": 6, "params": params}).encode()
    req = urllib.request.Request(ANKI_URL, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read())
    if payload.get("error"):
        raise RuntimeError(f"AnkiConnect error: {payload['error']}")
    return payload["result"]


def run_store(filename: str, file: str, no_sync: bool):
    path = Path(file)
    if not path.is_file():
        print(f"REJECTED — file does not exist: {file}", file=sys.stderr)
        return 2
    if path.stat().st_size == 0:
        print(f"REJECTED — file is empty: {file}", file=sys.stderr)
        return 2

    # Only the `path` param is used. No base64/`data` is ever passed here.
    anki_request("storeMediaFile", filename=filename, path=str(path))
    if not no_sync:
        anki_request("sync")
    print(f"ok: stored media {filename} from {file}")
    return 0


def run_delete(filename: str, no_sync: bool):
    anki_request("deleteMediaFile", filename=filename)
    if not no_sync:
        anki_request("sync")
    print(f"ok: deleted media {filename}")
    return 0


def run_check(filename: str):
    names = anki_request("getMediaFilesNames")
    if filename in names:
        print(f"present: {filename}")
        return 0
    print(f"absent: {filename}", file=sys.stderr)
    return 1


def main() -> int:
    p = argparse.ArgumentParser(description="Gatekeeper for Anki media storage")
    sub = p.add_subparsers(dest="cmd", required=True)

    st = sub.add_parser("store")
    st.add_argument("--filename", required=True, help="name the file will have inside Anki")
    st.add_argument("--file", required=True, help="path to a local file to upload (NOT base64)")
    st.add_argument("--no-sync", action="store_true", help="do not call sync afterwards")

    de = sub.add_parser("delete")
    de.add_argument("--filename", required=True)
    de.add_argument("--no-sync", action="store_true", help="do not call sync afterwards")

    ck = sub.add_parser("check")
    ck.add_argument("--filename", required=True)

    args = p.parse_args()
    if args.cmd == "store":
        return run_store(args.filename, args.file, args.no_sync)
    if args.cmd == "delete":
        return run_delete(args.filename, args.no_sync)
    if args.cmd == "check":
        return run_check(args.filename)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
