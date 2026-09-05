#!/usr/bin/env python3
"""Claude Code Stop hook — Telegram delivery safety net.

When the daemon finishes a turn WITHOUT sending anything through the Telegram
reply tool, the model's text answer would otherwise stay in the local
transcript and never reach the user. This hook detects that case and forwards
the final text answer to Telegram via the Bot API, so a reply can never be
silently lost.

It does nothing when the turn already used the reply/edit_message tool, so it
never double-sends. A reaction alone does not count as "communicated".

Invoked by Claude Code with the hook payload JSON on stdin (contains
`transcript_path`). For manual testing:

    python3 hook-telegram-forward.py --transcript /path/to.jsonl --dry-run
"""

import hashlib
import json
import re
import sys
import urllib.parse
import urllib.request

ENV_FILE = "__HOME__/.claude/channels/telegram/.env"
STATE_FILE = "__TAI_HOME__/.tai-telegram-last-forward"


def _load_env_value(key):
    """Read KEY=value from the telegram channel .env (no secrets in this repo)."""
    try:
        with open(ENV_FILE, "r", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith(key + "="):
                    return line.split("=", 1)[1].strip()
    except OSError:
        pass
    return ""


# Owner's chat id comes from config, never hardcoded. Falls back to any
# chat_id found in the live transcript (see analyze()).
DEFAULT_CHAT_ID = _load_env_value("TELEGRAM_CHAT_ID")
TG_LIMIT = 4000  # Telegram hard limit is 4096; leave headroom.
# Telegram tool names that actually deliver text content to the user.
COMMUNICATED_TOOLS = (
    "mcp__plugin_telegram_telegram__reply",
    "mcp__plugin_telegram_telegram__edit_message",
)


def load_token():
    try:
        with open(ENV_FILE, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line.startswith("TELEGRAM_BOT_TOKEN="):
                    return line.split("=", 1)[1].strip()
    except OSError:
        pass
    return None


def is_real_user(entry):
    """True for an actual user message, False for a tool_result carrier."""
    if entry.get("type") != "user":
        return False
    content = entry.get("message", {}).get("content")
    if isinstance(content, str):
        return True
    if isinstance(content, list):
        # A real user turn has at least one non-tool_result block.
        return any(b.get("type") != "tool_result" for b in content if isinstance(b, dict))
    return False


def block_text(content):
    """Yield text from a string or a list of content blocks."""
    if isinstance(content, str):
        yield content
        return
    if isinstance(content, list):
        for b in content:
            if isinstance(b, dict) and b.get("type") == "text":
                yield b.get("text", "")


def analyze(entries):
    """Return (communicated, text, chat_id) for the most recent turn."""
    last_user = -1
    for i, e in enumerate(entries):
        if is_real_user(e):
            last_user = i

    chat_id = DEFAULT_CHAT_ID
    if last_user >= 0:
        for txt in block_text(entries[last_user].get("message", {}).get("content")):
            m = re.search(r'chat_id="(\d+)"', txt)
            if m:
                chat_id = m.group(1)
                break

    communicated = False
    texts = []
    for e in entries[last_user + 1:]:
        if e.get("type") != "assistant":
            continue
        content = e.get("message", {}).get("content")
        if not isinstance(content, list):
            continue
        for b in content:
            if not isinstance(b, dict):
                continue
            if b.get("type") == "text":
                t = b.get("text", "").strip()
                if t:
                    texts.append(t)
            elif b.get("type") == "tool_use" and b.get("name") in COMMUNICATED_TOOLS:
                communicated = True

    return communicated, "\n\n".join(texts).strip(), chat_id


def read_entries(path):
    entries = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


def already_forwarded(text):
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as fh:
            if fh.read().strip() == digest:
                return True, digest
    except OSError:
        pass
    return False, digest


def mark_forwarded(digest):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as fh:
            fh.write(digest)
    except OSError:
        pass


def send(token, chat_id, text):
    payload = urllib.parse.urlencode(
        {"chat_id": chat_id, "text": text[:TG_LIMIT]}
    ).encode("utf-8")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    req = urllib.request.Request(url, data=payload, method="POST")
    with urllib.request.urlopen(req, timeout=5) as resp:
        return resp.status


def main():
    dry_run = "--dry-run" in sys.argv
    transcript = None
    if "--transcript" in sys.argv:
        idx = sys.argv.index("--transcript")
        if idx + 1 < len(sys.argv):
            transcript = sys.argv[idx + 1]

    if transcript is None:
        try:
            payload = json.load(sys.stdin)
            transcript = payload.get("transcript_path")
        except (json.JSONDecodeError, ValueError):
            transcript = None

    if not transcript:
        return

    try:
        entries = read_entries(transcript)
    except OSError:
        return

    communicated, text, chat_id = analyze(entries)

    if communicated:
        if dry_run:
            print("DECISION: skip (reply/edit_message tool was used this turn)")
        return
    if not text:
        if dry_run:
            print("DECISION: skip (no text to forward)")
        return
    if not chat_id:
        if dry_run:
            print("DECISION: skip (no chat_id — set TELEGRAM_CHAT_ID in the channel .env)")
        return

    seen, digest = already_forwarded(text)
    if seen:
        if dry_run:
            print("DECISION: skip (identical text already forwarded)")
        return

    if dry_run:
        print(f"DECISION: WOULD SEND to chat_id={chat_id} ({len(text)} chars):")
        print("-" * 60)
        print(text[:TG_LIMIT])
        return

    token = load_token()
    if not token:
        return
    try:
        send(token, chat_id, text)
        mark_forwarded(digest)
    except Exception:
        # Never let the safety net crash the session.
        pass


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
