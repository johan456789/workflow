#!/usr/bin/env python3
import argparse
import glob
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ANKI_CONNECT = "http://127.0.0.1:8765"

PAGE_CSS = """
body { margin: 0; padding: 32px 16px; background: #2b2d31; font-family: arial; }
.box { max-width: 720px; margin: 0 auto 40px; background: #fff; border-radius: 10px; overflow: hidden; box-shadow: 0 6px 24px rgba(0,0,0,.35); }
.box-title { background: #5865F2; color: #fff; padding: 8px 18px; font: 700 14px/1.3 arial; letter-spacing: .5px; }
.box-body { padding: 32px 24px; }
.tag { text-align: center; color: #888; font-size: 13px; padding-bottom: 24px; }
.landing { max-width: 720px; margin: 0 auto; background: #fff; border-radius: 10px; padding: 40px; box-shadow: 0 6px 24px rgba(0,0,0,.35); color: #222; }
.landing h1 { margin-top: 0; font-size: 22px; }
.landing code { background: #eee; padding: 2px 6px; border-radius: 4px; }
img { max-width: 100%; }
audio { margin: 8px 0; }
a.hint { color: #5865F2; font-weight: 700; text-decoration: none; }
"""

MIME = {
    ".mp3": "audio/mpeg", ".ogg": "audio/ogg", ".wav": "audio/wav",
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".gif": "image/gif", ".svg": "image/svg+xml", ".webp": "image/webp",
    ".mp4": "video/mp4", ".webm": "video/webm",
    ".css": "text/css", ".js": "text/javascript", ".json": "application/json",
    ".woff": "font/woff", ".woff2": "font/woff2", ".ttf": "font/ttf",
    ".apkg": "application/octet-stream", ".txt": "text/plain",
}
DEFAULT_MIME = "application/octet-stream"

STATUS_NAMES = {0: "new", 1: "learn", 2: "due", 3: "review"}


def anki(action, **params):
    req = urllib.request.Request(
        ANKI_CONNECT,
        data=json.dumps({"action": action, "version": 6, "params": params}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        body = json.load(resp)
    if body.get("error"):
        raise RuntimeError(body["error"])
    return body.get("result")


def find_media_dir():
    candidates = [
        Path.home() / ".local/share/Anki2",
        Path.home() / "Library/Application Support/Anki2",
        Path.home() / "AppData/Roaming/Anki2",
    ]
    for base in candidates:
        matches = sorted(
            glob.glob(str(base / "*/collection.media")),
            key=os.path.getmtime,
            reverse=True,
        )
        if matches:
            return Path(matches[0])
    return None


SOUND_RE = re.compile(r"\[sound:([^\]]+)\]")
PLAY_RE = re.compile(r"\[anki:play:(q|a):(\d+)\]")
URL_RE = re.compile(r'url\(([\'"]?)(?!https?://|data:)([^\'")]+)\1\)')
SRC_RE = re.compile(r'src=([\'"])(?!https?://|data:)(.*?)\1')


def collect_sounds(fields):
    sounds = []
    for f in fields.values():
        sounds.extend(SOUND_RE.findall(f.get("value", "")))
    return sounds


def replace_audio(html, sounds):
    def tag(idx, controls, autoplay):
        if idx >= len(sounds):
            return ""
        attrs = ""
        if controls:
            attrs += " controls"
        if autoplay:
            attrs += " autoplay"
        return '<audio%s src="/media/%s"></audio>' % (attrs, urllib.parse.quote(sounds[idx]))

    hidden = re.compile(r'(<div[^>]*style="display:none;"[^>]*>)\s*\[anki:play:(q|a):(\d+)\]')
    html = hidden.sub(lambda m: m.group(1) + tag(int(m.group(3)), False, True), html)
    html = PLAY_RE.sub(lambda m: tag(int(m.group(2)), True, False), html)
    return html


def rewrite_media(html):
    html = URL_RE.sub(r"url(\1/media/\2\1)", html)
    html = SRC_RE.sub(r"src=\1/media/\2\1", html)
    return html


def card_page(card):
    fields = card["fields"]
    sounds = collect_sounds(fields)
    question = replace_audio(rewrite_media(card["question"]), sounds)
    answer = replace_audio(rewrite_media(card["answer"]), sounds)
    status = STATUS_NAMES.get(card.get("type"), "?")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Anki card {card['cardId']}</title>
<style>{PAGE_CSS}</style>
</head>
<body>
<div class="box">
  <div class="box-title">QUESTION</div>
  <div class="box-body card">{question}</div>
</div>
<div class="box">
  <div class="box-title">ANSWER</div>
  <div class="box-body card">{answer}</div>
</div>
<p class="tag">card {card['cardId']} — {card['deckName']} — {card['modelName']} — {status}</p>
</body>
</html>"""


def landing_page():
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Anki card server</title>
<style>{PAGE_CSS}</style>
</head>
<body>
<div class="landing">
<h1>Anki card server</h1>
<p>Renders any card from your Anki collection via AnkiConnect (<code>cardsInfo</code>), resolves media from <code>collection.media</code>, and serves faithful HTML.</p>
<p>Open <code>/&lt;card-id&gt;</code> to view a card, e.g. <code>/1759181638178</code>.</p>
<p>Find card ids with the AnkiConnect search, e.g. <code>findCards deck:"*::_Languages::_Spanish🇪🇸::Daily life"</code>.</p>
</div>
</body>
</html>"""


def error_page(status, message):
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{status}</title>
<style>{PAGE_CSS}</style>
</head>
<body>
<div class="landing">
<h1>{status}</h1>
<p>{message}</p>
</div>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    server_version = "AnkiCardServer/0.1"

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def send_html(self, code, body):
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_error_page(self, code, message):
        self.send_html(code, error_page(code, message))

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = urllib.parse.unquote(parsed.path)

        if path == "/" or path == "/index.html":
            self.send_html(200, landing_page())
            return

        if path.startswith("/media/"):
            self.serve_media(path[len("/media/"):])
            return

        m = re.fullmatch(r"/(\d+)", path)
        if not m:
            self.send_error_page(404, "Not found. Use <code>/&lt;card-id&gt;</code> or <code>/media/&lt;file&gt;</code>.")
            return

        self.serve_card(int(m.group(1)))

    def serve_card(self, cid):
        try:
            cards = anki("cardsInfo", cards=[cid])
        except Exception as exc:
            self.send_error_page(503, "AnkiConnect unreachable: %s" % exc)
            return
        if not cards or "fields" not in cards[0]:
            self.send_error_page(404, "Card <code>%d</code> not found." % cid)
            return
        try:
            self.send_html(200, card_page(cards[0]))
        except Exception as exc:
            self.send_error_page(500, "Render error: %s" % exc)

    def serve_media(self, rel):
        if self.server.media_dir is None:
            self.send_error_page(404, "Media directory not found.")
            return
        target = (self.server.media_dir / rel).resolve()
        try:
            target.relative_to(self.server.media_dir.resolve())
        except ValueError:
            self.send_error_page(403, "Forbidden.")
            return
        if not target.is_file():
            self.send_error_page(404, "Media file not found: %s" % rel)
            return
        data = target.read_bytes()
        ctype = MIME.get(target.suffix.lower(), DEFAULT_MIME)
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main():
    parser = argparse.ArgumentParser(description="Serve rendered Anki cards at /:card_id")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=4367)
    parser.add_argument("--media-dir", default=None, help="Anki collection.media path (auto-detected)")
    args = parser.parse_args()

    media_dir = Path(args.media_dir) if args.media_dir else find_media_dir()
    if media_dir is None:
        print("warning: could not auto-detect collection.media; media will 404", file=sys.stderr)
    else:
        print("media dir: %s" % media_dir, file=sys.stderr)

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.media_dir = media_dir
    print("serving on http://%s:%d/ — try /<card-id>" % (args.host, args.port), file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
