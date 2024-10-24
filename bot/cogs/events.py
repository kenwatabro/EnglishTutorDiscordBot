# bot/cogs/events.py
from discord.ext import commands
import re
from datetime import datetime
from bot.utils.database import Database


class Events(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print(f"Logged in as {self.bot.user}")
        self.db = await Database.get_instance()
        # Reminders Cog のスケジューリングを開始
        self.bot.dispatch("setup_completed")

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return

        if message.content.startswith(self.bot.command_prefix):
            return  # コマンドは Commands Cog で処理

        if message.mentions and self.bot.user in message.mentions:
            # メンションされた場合の処理
            content = message.content.replace(f"<@!{self.bot.user.id}>", "").strip()
            lines = content.split("\n")
            registered_words = []
            for line in lines:
                match = re.match(r"^(.*?)[:，,、\s]+(.+)$", line)
                if match:
                    english_word = match.group(1).strip()
                    japanese_meaning = match.group(2).strip()
                    added_at = datetime.now(self.bot.JST).isoformat()
                    intervals_remaining = ",".join(map(str, [1, 4, 10, 17, 30]))
                    await self.db.execute(
                        """
                        INSERT INTO words (user_id, word, meaning, added_at, intervals_remaining)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            message.author.id,
                            english_word,
                            japanese_meaning,
                            added_at,
                            intervals_remaining,
                        ),
                    )
                    registered_words.append((english_word, japanese_meaning))

            if registered_words:
                confirmation = (
                    f"{message.author.mention} 単語を登録したよ！：\n"
                )
                for word, meaning in registered_words:
                    confirmation += f"**英語:** {word} | **意味:** {meaning}\n"
                await message.channel.send(confirmation)
            else:
                await message.channel.send(
                    f"{message.author.mention} まだ何も登録していないよ！"
                )


async def setup(bot):
    await bot.add_cog(Events(bot))
