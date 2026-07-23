#!/usr/bin/env bash
# trim-silence.sh - Trim leading silence from MP3 files in place.
# Usage: trim-silence.sh [-j N] file.mp3 [file2.mp3 ...]
#   -j N    parallel jobs (default: nproc)
#
# Uses ffmpeg's silenceremove filter. Writes to a temp file and only
# mv's it over the original if the output is non-empty, so a failed
# trim cannot corrupt the input.
set -euo pipefail
JOBS=$(nproc 2>/dev/null || echo 4)
[[ "${1:-}" == "-j" ]] && { JOBS="$2"; shift 2; }
[[ $# -eq 0 ]] && { echo "usage: $0 [-j N] file.mp3 [...]" >&2; exit 1; }

trim_one() {
  local f="$1" tmp
  [[ -f "$f" ]] || { echo "MISSING: $f" >&2; return 0; }
  tmp=$(mktemp "${TMPDIR:-/tmp}/trim-silence.XXXXXX.mp3")
  if ffmpeg -hide_banner -loglevel error -y -i "$f" \
        -af "silenceremove=start_periods=1:start_silence=0.01:start_threshold=-40dB" \
        -c:a libmp3lame -b:a 128k "$tmp" 2>/dev/null && [[ -s "$tmp" ]]; then
    mv "$tmp" "$f"
  else
    echo "TRIM_FAILED: $f" >&2
    rm -f "$tmp"
  fi
}
export -f trim_one
printf '%s\0' "$@" | xargs -0 -P "$JOBS" -I {} bash -c 'trim_one "$@"' _ {}
