# /// script
# requires-python = ">=3.11"
# dependencies = ["jsonschema"]
# ///
"""Gatekeeper in front of AnkiConnect.

All note modifications must pass through this script. It validates the
proposed field values against a per-model schema (scripts/schemas.json)
and only forwards the change to AnkiConnect when every field is valid.

Usage:
  uv run anki_edit.py update --id NID --fields '{"Example sentence (Spanish)": "..."}'
  uv run anki_edit.py add --model "Cloze" --deck "DECK" --fields '{...}' --tags '["x"]'
  uv run anki_edit.py check  --id NID            # lint an existing note, no write

Media (preferred):
  uv run anki_edit.py add --model Cloze --deck "..." --fields '{...}' \
    --audio '[{"path": "/tmp/a.mp3", "filename": "a.mp3", "fields": ["Extra"]}]'
  # AnkiConnect inserts a correct [sound:...] tag — do not hand-write [sound:...].

Flags:
  --normalize   auto-fix normalizable issues (e.g. join lines with <br>)
                before validating. Without it, violations are rejected.

Exit code is non-zero when a field fails validation, so it can gate a
tool/agent from writing bad data.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

from jsonschema import Draft7Validator

SCHEMA_PATH = Path(__file__).with_name("schemas.json")
ANKI_URL = "http://localhost:8765"


def anki_request(action: str, **params):
    body = json.dumps({"action": action, "version": 6, "params": params}).encode()
    req = urllib.request.Request(ANKI_URL, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read())
    if payload.get("error"):
        raise RuntimeError(f"AnkiConnect error: {payload['error']}")
    return payload["result"]


def load_schemas() -> dict:
    return json.loads(SCHEMA_PATH.read_text())


def model_for_note(nid: int) -> str:
    info = anki_request("notesInfo", notes=[nid])
    if not info:
        raise RuntimeError(f"note {nid} not found")
    return info[0]["modelName"]


def meta_for(model_schema: dict, field: str) -> dict:
    return model_schema.get("properties", {}).get(field, {}).get("x-meta", {})


def normalize_field(value: str, meta: dict) -> str:
    join_with = meta.get("join_with")
    if join_with:
        value = value.replace("\n", join_with).replace("\r", "")
    return value


def sentence_set(value: str) -> set[str]:
    """Split HTML field into normalized, deduplicated sentence/hunk set."""
    out: set[str] = set()
    for part in re.split(r"<br\s*/?>", value):
        clean = re.sub(r"<[^>]+>", "", part).strip().lower()
        clean = re.sub(r"\s+", " ", clean)
        if clean:
            out.add(clean)
    return out


CLOZE_MARKER_RE = re.compile(r"\{\{c")
CLOZE_OPEN_RE = re.compile(r"\{\{c\d+::")


def cloze_syntax_violations(value: str) -> list[str]:
    """Return violations for malformed or unclosed Anki cloze markers."""
    violations: list[str] = []
    markers = list(CLOZE_MARKER_RE.finditer(value))

    for index, marker in enumerate(markers):
        opening = CLOZE_OPEN_RE.match(value, marker.start())
        if not opening:
            violations.append(
                f"malformed cloze opening at character {marker.start()}; "
                "expected '{{cN::...}}'"
            )
            continue

        close = value.find("}}", opening.end())
        next_marker = markers[index + 1] if index + 1 < len(markers) else None
        if close == -1 or (next_marker and close > next_marker.start()):
            violations.append(
                f"unclosed cloze opening at character {marker.start()}; "
                "expected a closing '}}'"
            )

    return violations


def sound_tag_violations(value: str) -> list[str]:
    """Return violations for malformed [sound:...] tags."""
    violations: list[str] = []
    for m in re.finditer(r"\[sound:([^\]]*)\]", value):
        inner = m.group(1)
        if inner == "":
            violations.append(f"empty [sound:] tag at {m.start()}")
        elif inner != inner.strip():
            violations.append(
                f"malformed [sound:{inner}] at {m.start()}: leading/trailing whitespace "
                f"(use [sound:{inner.strip()}])"
            )
        elif "/" in inner or "\\" in inner:
            violations.append(
                f"malformed [sound:{inner}] at {m.start()}: must not contain path separators"
            )
    # Catch spaced variants like `[sound :` or `[ sound:` that the regex above misses.
    for m in re.finditer(r"\[\s*sound\s*:", value):
        if m.group(0) != "[sound:":
            violations.append(
                f"malformed sound tag prefix {m.group(0)!r} at {m.start()} (use [sound:)"
            )
    return violations


def validate_field(field: str, value: str, model_schema: dict, normalize: bool,
                   context: dict | None = None) -> list[str]:
    """Return list of violation strings. Empty list means valid."""
    violations: list[str] = []
    meta = meta_for(model_schema, field)

    if normalize:
        value = normalize_field(value, meta)

    # Standard JSON Schema check for this single field.
    field_schema = model_schema.get("properties", {}).get(field)
    if field_schema:
        sub = {k: v for k, v in model_schema.items() if k in ("type", "required")}
        sub["properties"] = {field: field_schema}
        sub["additionalProperties"] = True
        errs = sorted(Draft7Validator(sub).iter_errors({field: value}), key=lambda e: e.path)
        for e in errs:
            violations.append(f"{field}: {e.message}")

    # Custom checks from x-meta.
    for bad in meta.get("forbid", []):
        if bad in value:
            violations.append(f"{field}: contains forbidden substring {bad!r}")
    for need in meta.get("require", []):
        if need not in value:
            violations.append(f"{field}: missing required substring {need!r}")
    if meta.get("cloze_syntax"):
        for violation in cloze_syntax_violations(value):
            violations.append(f"{field}: {violation}")

    # Generic media check: malformed [sound:...] tags (all fields, all models).
    for violation in sound_tag_violations(value):
        violations.append(f"{field}: {violation}")

    # Cross-field rule: a field must not share sentences with another field
    # (e.g. the Spanish field must contain no English sentences by comparing
    # against the paired bilingual field).
    other = meta.get("distinct_from")
    if other and context is not None and other in context:
        mine = sentence_set(value)
        theirs = sentence_set(context[other])
        shared = mine & theirs
        if shared:
            sample = ", ".join(sorted(shared)[:3])
            violations.append(f"{field}: overlaps with field {other!r}: {sample}")

    return violations


def validate_media_specs(specs: list, kind: str) -> list[str]:
    """Validate audio/picture/video specs for addNote/updateNoteFields."""
    violations: list[str] = []
    if not isinstance(specs, list):
        return [f"{kind}: must be a list"]
    for idx, entry in enumerate(specs):
        prefix = f"{kind}[{idx}]"
        if not isinstance(entry, dict):
            violations.append(f"{prefix}: must be an object")
            continue
        filename = entry.get("filename")
        if not isinstance(filename, str) or not filename.strip():
            violations.append(f"{prefix}.filename: must be a non-empty string")
        elif filename != filename.strip():
            violations.append(f"{prefix}.filename: leading/trailing whitespace (use {filename.strip()!r})")
        elif "/" in filename or "\\" in filename:
            violations.append(f"{prefix}.filename: must not contain path separators")
        has_path = "path" in entry
        has_url = "url" in entry
        has_data = "data" in entry
        if has_data:
            violations.append(f"{prefix}: 'data' (base64) is forbidden — use 'path' or 'url' with a real file")
        if not (has_path or has_url):
            violations.append(f"{prefix}: must have 'path' or 'url'")
        if has_path:
            p = Path(str(entry["path"]))
            if not p.is_file():
                violations.append(f"{prefix}.path: file does not exist: {entry['path']}")
            elif p.stat().st_size == 0:
                violations.append(f"{prefix}.path: file is empty: {entry['path']}")
        fields = entry.get("fields")
        if fields is not None:
            if not isinstance(fields, list) or not all(isinstance(f, str) for f in fields):
                violations.append(f"{prefix}.fields: must be a list of field names")
    return violations


def run_update(nid: int, fields: dict, normalize: bool, audio=None, picture=None, video=None):
    model = model_for_note(nid)
    schemas = load_schemas()
    model_schema = schemas.get(model)
    if not model_schema:
        print(f"no schema for model {model!r}; allowing write but consider adding one", file=sys.stderr)
    else:
        info = anki_request("notesInfo", notes=[nid])
        context = {f: d.get("value", "") for f, d in info[0]["fields"].items()}
        context.update(fields)
        if normalize:
            fields = {f: normalize_field(v, meta_for(model_schema, f)) for f, v in fields.items()}
            context.update(fields)
        all_v = []
        for f, v in fields.items():
            all_v += validate_field(f, v, model_schema, normalize, context)
        if all_v:
            print("REJECTED — field validation failed:", file=sys.stderr)
            for line in all_v:
                print(f"  - {line}", file=sys.stderr)
            return 2

    # Validate media specs even when no schema exists.
    for kind, specs in (("audio", audio), ("picture", picture), ("video", video)):
        if specs:
            mv = validate_media_specs(specs, kind)
            if mv:
                print("REJECTED — media validation failed:", file=sys.stderr)
                for line in mv:
                    print(f"  - {line}", file=sys.stderr)
                return 2

    note: dict = {"id": nid, "fields": fields}
    if audio:
        note["audio"] = audio
    if picture:
        note["picture"] = picture
    if video:
        note["video"] = video
    anki_request("updateNoteFields", note=note)
    anki_request("sync")
    print(f"ok: updated note {nid}")
    return 0


def run_add(model: str, deck: str, fields: dict, tags: list, normalize: bool, audio=None, picture=None, video=None):
    schemas = load_schemas()
    model_schema = schemas.get(model)
    if model_schema:
        if normalize:
            fields = {f: normalize_field(v, meta_for(model_schema, f)) for f, v in fields.items()}
        all_v = []
        for f, v in fields.items():
            all_v += validate_field(f, v, model_schema, normalize, context=fields)
        if all_v:
            print("REJECTED — field validation failed:", file=sys.stderr)
            for line in all_v:
                print(f"  - {line}", file=sys.stderr)
            return 2
    for kind, specs in (("audio", audio), ("picture", picture), ("video", video)):
        if specs:
            mv = validate_media_specs(specs, kind)
            if mv:
                print("REJECTED — media validation failed:", file=sys.stderr)
                for line in mv:
                    print(f"  - {line}", file=sys.stderr)
                return 2
    note: dict = {"deckName": deck, "modelName": model, "fields": fields, "tags": tags or []}
    if audio:
        note["audio"] = audio
    if picture:
        note["picture"] = picture
    if video:
        note["video"] = video
    nid = anki_request("addNote", note=note)
    anki_request("sync")
    print(f"ok: added note {nid}")
    return 0


def run_check(nid: int):
    info = anki_request("notesInfo", notes=[nid])[0]
    model = info["modelName"]
    schemas = load_schemas()
    model_schema = schemas.get(model)
    if not model_schema:
        print(f"no schema for model {model!r}")
        return 0
    bad = False
    fields_val = {f: d.get("value", "") for f, d in info["fields"].items()}
    for f, data in info["fields"].items():
        v = data.get("value", "")
        vs = validate_field(f, v, model_schema, normalize=False, context=fields_val)
        if vs:
            bad = True
            print(f"[{f}]")
            for line in vs:
                print(f"  - {line}")
    print("NOTE OK" if not bad else "NOTE HAS VIOLATIONS")
    return 1 if bad else 0


def main() -> int:
    p = argparse.ArgumentParser(description="Schema-gated Anki note editor")
    sub = p.add_subparsers(dest="cmd", required=True)

    up = sub.add_parser("update")
    up.add_argument("--id", type=int, required=True)
    up.add_argument("--fields", required=True, help="JSON object of field->value")
    up.add_argument("--normalize", action="store_true")
    up.add_argument("--audio", default="[]", help="JSON list of audio specs (AnkiConnect audio param)")
    up.add_argument("--picture", default="[]", help="JSON list of picture specs")
    up.add_argument("--video", default="[]", help="JSON list of video specs")

    ad = sub.add_parser("add")
    ad.add_argument("--model", required=True)
    ad.add_argument("--deck", required=True)
    ad.add_argument("--fields", required=True)
    ad.add_argument("--tags", default="[]")
    ad.add_argument("--normalize", action="store_true")
    ad.add_argument("--audio", default="[]", help="JSON list of audio specs (AnkiConnect audio param)")
    ad.add_argument("--picture", default="[]", help="JSON list of picture specs")
    ad.add_argument("--video", default="[]", help="JSON list of video specs")

    ck = sub.add_parser("check")
    ck.add_argument("--id", type=int, required=True)

    args = p.parse_args()
    if args.cmd == "update":
        return run_update(
            args.id, json.loads(args.fields), args.normalize,
            audio=json.loads(args.audio), picture=json.loads(args.picture), video=json.loads(args.video),
        )
    if args.cmd == "add":
        return run_add(
            args.model, args.deck, json.loads(args.fields), json.loads(args.tags), args.normalize,
            audio=json.loads(args.audio), picture=json.loads(args.picture), video=json.loads(args.video),
        )
    if args.cmd == "check":
        return run_check(args.id)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
