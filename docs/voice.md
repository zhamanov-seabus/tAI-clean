# Voice in → voice out (optional)

If the owner sends a Telegram voice message, reply with text **and** a voice note.

- **Transcribe** incoming voice with a local whisper.cpp pipeline.
- **Synthesize** replies with `edge-tts` (free, no key), e.g. a Russian voice:
  `edge-tts --voice ru-RU-DmitryNeural --file reply.txt --write-media reply.mp3`
- Attach the mp3 in the Telegram reply.

Add these as small helper scripts on the host and reference them from CLAUDE.md.
