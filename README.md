## EnglishTutorDiscordBot

Discord bot that helps register English words, sends spaced-repetition reminders, and can generate explanations and short texts using Gemini.

### Setup
- Python 3.10+
- Create and populate `.env` (do not commit secrets):
  - `DISCORD_BOT_TOKEN=...`
  - `GEMINI_API_KEY=...` (optional; required for AI features)
- Install dependencies: `pip install -r requirements.txt`
- Run: `python -m bot.main`

Notes:
- If `GEMINI_API_KEY` is not set, AI features (`!kaisetu`, `!bunshou`, reply generation) are disabled gracefully.
- The SQLite DB file is `words.db` in the repo root and is auto-created.

### Commands
- `/show` — Show your registered words (paginates).
- `/edit <id> [new_word] [new_meaning]` — Edit your word.
- `/delete <words>` — Delete one or more words (space-separated).
- `/help` — Show usage (ephemeral).
- `/kaisetu <word>` — Explain a word (Gemini).
- `/bunshou [style]` — Generate a short text (Gemini).

Legacy prefix commands (`!show`, `!edit`, `!delete`, `!kaisetu`, `!bunshou`) still work, but slash commands are recommended for discoverability and autocomplete.

### Reminders
- Daily word reminders at 21:00 JST for words at intervals `[1,4,10,17,30,60]` days.
- Inactivity reminder at 22:00 JST for users without registrations that day.

### Systemd (optional)
- reload: `sudo systemctl daemon-reload`
- start: `sudo systemctl start discordbot.service`
- enable: `sudo systemctl enable discordbot.service`
- status: `sudo systemctl status discordbot.service`
- logs: `journalctl -u discordbot.service -f`
- disable: `sudo systemctl disable discordbot.service`
- stop: `sudo systemctl stop discordbot.service`
- restart: `sudo systemctl restart discordbot.service`
