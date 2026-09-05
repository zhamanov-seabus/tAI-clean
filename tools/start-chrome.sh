#!/usr/bin/env bash
# Launch Chrome/Chromium headless with a persistent profile + CDP on :9222,
# so the agent can drive Google Gemini (web) to generate images without an API
# key. You log in to your Google account ONCE into this profile; the session
# persists in the profile dir. Works on Linux and macOS.
set -euo pipefail
PROFILE="${TAI_BROWSER_PROFILE:-$HOME/.tai-browser/profile}"
URL="${1:-https://gemini.google.com/app}"
mkdir -p "$PROFILE"

find_chrome() {
  for c in "$CHROME_BIN" google-chrome google-chrome-stable chromium chromium-browser \
           "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"; do
    [ -n "${c:-}" ] && command -v "$c" >/dev/null 2>&1 && { echo "$c"; return; }
    [ -x "$c" ] && { echo "$c"; return; }
  done
  return 1
}
CHROME="$(CHROME_BIN="${CHROME_BIN:-}" find_chrome)" || {
  echo "No Chrome/Chromium found. Install google-chrome or chromium, or set CHROME_BIN." >&2
  exit 1
}

# --headless=new keeps it GUI-less (works on a server). Drop it to log in with a
# visible window the first time if you have a desktop.
exec "$CHROME" \
  --headless=new \
  --remote-debugging-port=9222 \
  --remote-debugging-address=127.0.0.1 \
  --user-data-dir="$PROFILE" \
  --no-first-run \
  --no-default-browser-check \
  "$URL"
