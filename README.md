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
 - You can tune LLM tone with `PROMPT_TONE` env var: `playful` (default) or `concise`.

### Commands
- `/show` — Show your registered words (paginates).
- `/edit <id> [new_word] [new_meaning]` — Edit your word.
- `/delete <words>` — Delete one or more words (space-separated).
- `/help` — Show usage (ephemeral).
- `/kaisetu <word>` — Explain a word (Gemini).
- `/bunshou [style]` — Generate a short text (Gemini).
 - `/add <word> <meaning>` — Add a single word.
 - `/bulk_add <pairs>` — Add multiple pairs like `apple:りんご; take off:離陸する`.
 - `/progress` — Show your personal progress summary.
 - `/find <query>` — Search your words by text.

Legacy prefix commands (`!show`, `!edit`, `!delete`, `!kaisetu`, `!bunshou`) still work, but slash commands are recommended for discoverability and autocomplete.

### Reminders
- Daily word reminders at 21:00 JST for words at intervals `[1,4,10,17,30,60]` days.
- Inactivity reminder at 22:00 JST for users without registrations that day.
- You can register by mentioning the bot with `word:meaning` (recommended). `/add` and `/bulk_add` are optional shortcuts.

DM reminder UX:
- Reminder DMs include buttons: “今すぐ5問だけ復習” to start a short review, and “あとで（1時間後）” to snooze.
- During review, tap “答えを表示” then “覚えた/忘れた”. “覚えた” marks a word as learned and removes it from future reminders.

Registration UX:
- Mentioning the bot with `word:meaning` now also updates the meaning if the word already exists.
- After registering/updating, the bot replies with an Undo button (to revert new adds and updates) and a quick Edit option via a modal.

### Systemd (optional)
- reload: `sudo systemctl daemon-reload`
- start: `sudo systemctl start discordbot.service`
- enable: `sudo systemctl enable discordbot.service`
- status: `sudo systemctl status discordbot.service`
- logs: `journalctl -u discordbot.service -f`
- disable: `sudo systemctl disable discordbot.service`
- stop: `sudo systemctl stop discordbot.service`
- restart: `sudo systemctl restart discordbot.service`
