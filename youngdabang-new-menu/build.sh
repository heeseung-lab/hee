#!/bin/sh
# 청년다방 신메뉴 (수채화) — one command: picture → sound → master.  usage: sh build.sh
# Menu text lives in content.js. After changing it, this script re-fetches the font subsets for the new characters.
set -e
LIB=${LIB:-/root/lemo-opuscar}
HERE=$(cd "$(dirname "$0")" && pwd)
export LIB
[ -f "$LIB/core/render/video.mjs" ] || { echo "set LIB to the Lemo-Opuscar library folder"; exit 1; }
PY="$LIB/.venv/bin/python"
NAME=youngdabang-new-menu
mkdir -p "$HERE/out"

# 0. fonts: subset to exactly the characters in content.js (Google Fonts, OFL)
cd "$HERE" && "$PY" fetch_fonts.py

# 1. picture
cd "$LIB"
node core/render/readcheck.mjs "$HERE"
node core/render/events.mjs "$HERE"
node core/render/video.mjs "$HERE" --fps 60 --workers 4 --out "$HERE/out/video.mp4"

# 2. sound
"$PY" "$HERE/mix.py"

# 3. master to -14 LUFS and mux. mux.sh needs ffmpeg 7+; with ffmpeg 6 fall back to a two-pass loudnorm here.
if sh core/render/mux.sh "$HERE/out/video.mp4" "$HERE/out/mix.wav" "$HERE/$NAME.mp4" 60 1; then :; else
  echo "→ mux.sh unavailable (ffmpeg < 7?): mastering with a two-pass loudnorm"
  cd "$HERE"
  M=$(ffmpeg -hide_banner -nostats -i out/mix.wav -af loudnorm=I=-14:TP=-1.2:LRA=11:print_format=json -f null - 2>&1 | sed -n '/^{/,/^}/p')
  g() { echo "$M" | grep "\"$1\"" | sed 's/.*: "\(.*\)".*/\1/'; }
  ffmpeg -y -hide_banner -loglevel error -i out/mix.wav -af "loudnorm=I=-14:TP=-1.2:LRA=11:measured_I=$(g input_i):measured_TP=$(g input_tp):measured_LRA=$(g input_lra):measured_thresh=$(g input_thresh):offset=$(g target_offset):linear=true,aresample=48000" -ar 48000 -c:a pcm_s16le out/master.wav
  ffmpeg -y -hide_banner -loglevel error -i out/video.mp4 -i out/master.wav -map 0:v -map 1:a -c:v libx264 -preset slow -crf 17 -pix_fmt yuv420p -r 60 -c:a aac -b:a 256k -movflags +faststart -shortest "$NAME.mp4"
  ffmpeg -hide_banner -nostats -i "$NAME.mp4" -af ebur128=peak=true -f null - 2>&1 | grep -E '^\s+(I|Peak):'
fi
cd "$HERE"
ffmpeg -y -hide_banner -loglevel error -ss 29.0 -i "$NAME.mp4" -frames:v 1 -q:v 2 poster.jpg
echo "done: $HERE/$NAME.mp4"
