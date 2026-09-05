# tai image tools — key-free image generation via Google Gemini (web)

These let the agent generate images by driving **Gemini on the web** in a
headless Chrome, instead of paying for an image API. No API key. You just log
in to your Google account **once** into a dedicated browser profile.

## Files
- `start-chrome.sh` — launch headless Chrome/Chromium with a persistent profile + CDP on :9222 (Linux + macOS)
- `gemini-image.mjs` — drive Gemini to generate an image from a prompt, save PNG
- `gemini-grab.mjs` — fallback: re-fetch the last Gemini image via a same-origin tab (used when the canvas is cross-origin "tainted")
- `package.json` — the one dependency (`playwright-core`)

Installed by `install.sh` into `~/.tai-browser/` (deps fetched with `npm install` if `node`+`npm` are present).

## One-time login
```
# 1. start the browser (headless)
~/.tai-browser/start-chrome.sh
# 2. drive it to log in — easiest: run once WITHOUT --headless on a desktop,
#    or use a remote-debugging client. Log into your Google account at
#    https://gemini.google.com  — the session persists in ~/.tai-browser/profile
```
On a headless server, do the one-time login by port-forwarding :9222 to a
machine with a browser, or start Chrome without `--headless=new` over a remote
desktop, log in, then close. The profile keeps the session afterwards.

## Generate an image
```
node ~/.tai-browser/gemini-image.mjs "Generate an image: a friendly cartoon fox mascot, flat vector, white background, no text" /tmp/out.png
# if it reports a tainted canvas:
node ~/.tai-browser/gemini-grab.mjs /tmp/out.png
```

## Requirements
- `node` + `npm` (for `playwright-core`)
- `google-chrome` or `chromium` on PATH (or set `CHROME_BIN`)
- A Google account logged into the profile (free Gemini is enough)
