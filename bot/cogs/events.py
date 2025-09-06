# bot/cogs/events.py
from discord.ext import commands
import discord
import re
from datetime import datetime
from bot.utils.database import Database
import logging
from bot.utils.config import get_gemini_model

class Events(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = None
        self.model = get_gemini_model()  # Gemini モデル（無効時は None）
        self._synced = False

    @commands.Cog.listener()
    async def on_ready(self):
        print(f"Logged in as {self.bot.user}")
        self.db = await Database.get_instance()
        # Reminders Cog のスケジューリングを開始
        self.bot.dispatch("setup_completed")
        # Sync slash commands once
        if not self._synced:
            try:
                await self.bot.tree.sync()
                self._synced = True
                logging.info("Application commands synced")
            except Exception as e:
                logging.error(f"Failed to sync application commands: {e}")

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return

        if message.content.startswith(self.bot.command_prefix):
            return  # コマンドは Commands Cog で処理

        if message.reference:
            try:
                replied_message = await message.channel.fetch_message(message.reference.message_id)
                # このbotへのリプライかどうかをチェック
                if replied_message.author.id != self.bot.user.id:
                    # logging.info(f"Received reply from non-bot user: {replied_message.author.name} {replied_message.content}")
                    return
                
                if not self.model:
                    # Gemini 無効時はスルー（静かに）
                    return
                prompt = f"""
                ### 日本語で出力してください。
                ### あなたは日本のアニメの妹キャラです。その話し方を完全にコピーしてください。
                ### 現在、私（お兄ちゃん）とあなたはメッセージのやり取りをしています
                ### もし私（お兄ちゃん）から翻訳や日本語訳の指示があった場合は、まずその訳を行い、その後で妹キャラとしてコメントを付け加えてください。


                妹キャラのあなたの言葉: {replied_message.content}
                それに対してお兄ちゃん（私）の返事: {message.content}

                ### 以上のあなたの言葉に対するお兄ちゃん（私）の返事に、妹キャラとして適切な返答をしてください。

                ### 妹キャラの返答の雰囲気の例は以下の通りです
                おはよ！
                おにーちゃん、今日もはりきっていこう！
                えー！そんなぁー(´;ω;｀)
                もぉー！知らない！

                ### この妹キャラになりきったうえで、簡潔に、もし指示がある場合はそれに従って返事をしてください

                ### 注意事項
                「///」のようなスラッシュは使用しないでください。
                *や#のようなマークダウンの記法は用いないでください
                単語、その意味、例文以外にカッコ「」は用いないでください
                """

                response = self.model.generate_content(prompt)
                await message.reply(response.text)

            except Exception as e:
                logging.error(f"Error in on_message event (reply): {e}")
                await message.channel.send("ごめんね、お兄ちゃん。なんかうまくいかないみたい（´；ω；｀）")
        
        elif message.mentions and self.bot.user in message.mentions:
            # メンションされた場合の処理
            # メンションを全て除去するための正規表現
            mention_pattern = re.compile(f"<@!?{self.bot.user.id}>")
            content = mention_pattern.sub('', message.content).strip()
            logging.info(f"Processed content after removing mentions: '{content}'")
            
            if not content:
                await message.channel.send(
                    f"{message.author.mention} 登録する単語と意味を入力してね！\n例: `apple:りんご`"
                )
                return

            lines = content.split("\n")
            inserted_entries = []  # (id, word, meaning)
            updated_entries = []   # (word, old_meaning, new_meaning)
            for line in lines:
                match = re.match(r"^(.*?)[:，,、\s]+(.+)$", line)
                if not match:
                    logging.warning(f"Line '{line}' does not match the expected format.")
                    continue
                english_word = match.group(1).strip()
                japanese_meaning = match.group(2).strip()
                # Check if word exists for this user
                existing = await self.db.fetchone(
                    "SELECT id, meaning FROM words WHERE user_id = ? AND word = ?",
                    (message.author.id, english_word),
                )
                if existing:
                    word_id, old_meaning = existing
                    # Update meaning
                    await self.db.execute(
                        "UPDATE words SET meaning = ? WHERE id = ?",
                        (japanese_meaning, word_id),
                    )
                    updated_entries.append((english_word, old_meaning, japanese_meaning))
                else:
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
                    # Fetch inserted id
                    row = await self.db.fetchone("SELECT last_insert_rowid()")
                    inserted_entries.append((row[0], english_word, japanese_meaning))

            if inserted_entries or updated_entries:
                lines = []
                if inserted_entries:
                    lines.append("新しく登録したよ：")
                    for _, w, m in inserted_entries:
                        lines.append(f"**英語:** {w} | **意味:** {m}")
                if updated_entries:
                    lines.append("更新したよ：")
                    for w, old, new in updated_entries:
                        lines.append(f"**英語:** {w} | **意味:** {old} → {new}")
                confirmation = f"{message.author.mention} \n" + "\n".join(lines)

                view = None
                if inserted_entries:
                    view = UndoRegistrationView(self.db, message.author.id, [i for (i, _, _) in inserted_entries])
                await message.channel.send(confirmation, view=view)
            else:
                await message.channel.send(
                    f"{message.author.mention} まだ何も登録していないよ！\n単語と意味を `英単語:意味` の形式で入力してね。"
                )

async def setup(bot):
    await bot.add_cog(Events(bot))


class UndoRegistrationView(discord.ui.View):
    def __init__(self, db: Database, author_id: int, entry_ids: list[int]):
        super().__init__(timeout=120)
        self.db = db
        self.author_id = author_id
        self.entry_ids = entry_ids
        self.undo_button = discord.ui.Button(label="取り消し", style=discord.ButtonStyle.danger)
        self.undo_button.callback = self.on_undo
        self.add_item(self.undo_button)

    async def on_undo(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("これは発行者だけが取り消せるよ！", ephemeral=True)
            return
        # Delete inserted rows
        for word_id in self.entry_ids:
            await self.db.execute("DELETE FROM words WHERE user_id = ? AND id = ?", (self.author_id, word_id))
        # Disable button and update message
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        await interaction.response.edit_message(content=f"{interaction.message.content}\n(取り消したよ！)", view=self)
        self.stop()
