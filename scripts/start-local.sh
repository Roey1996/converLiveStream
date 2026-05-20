#!/usr/bin/env sh
set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
MEDIAMTX_BIN="${MEDIAMTX_BIN:-$ROOT_DIR/.local/bin/mediamtx}"
API_HOST="${API_HOST:-0.0.0.0}"
API_PORT="${API_PORT:-8236}"

if [ ! -x "$MEDIAMTX_BIN" ]; then
  echo "MediaMTX binary not found: $MEDIAMTX_BIN" >&2
  echo "Download it from https://github.com/bluenviron/mediamtx/releases and set MEDIAMTX_BIN if needed." >&2
  exit 1
fi

cd "$ROOT_DIR"

cleanup() {
  if [ -n "${MEDIAMTX_PID:-}" ]; then
    kill "$MEDIAMTX_PID" 2>/dev/null || true
  fi
}
trap cleanup INT TERM EXIT

"$MEDIAMTX_BIN" mediamtx.yml &
MEDIAMTX_PID="$!"

MEDIAMTX_API_BASE="${MEDIAMTX_API_BASE:-http://localhost:9997}" \
PUBLIC_WEBRTC_BASE="${PUBLIC_WEBRTC_BASE:-http://localhost:8237}" \
API_HOST="$API_HOST" \
API_PORT="$API_PORT" \
python3 -m src.rtsp_webrtc_api
