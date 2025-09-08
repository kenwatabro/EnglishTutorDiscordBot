# bot/cogs/events.py
from discord.ext import commands
import discord
import re
from datetime import datetime
from bot.utils.database import Database
import logging
from bot.utils.config import get_gemini_model, get_prompt_tone
from bot.utils.prompts import build_reply_prompt
from bot.utils import words as words_util
from bot.utils import stats as stats_util
from bot.utils.review import start_quiz_session

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
        # Sync slash commands (global + per-guild for immediate availability)
        if not self._synced:
            try:
                # Global sync (may take time to propagate)
                await self.bot.tree.sync()
                # Per-guild sync for instant availability
                for g in self.bot.guilds:
                    try:
                        self.bot.tree.copy_global_to(guild=g)
                        await self.bot.tree.sync(guild=g)
                        logging.info(f"Commands synced to guild: {g.name} ({g.id})")
                    except Exception as ge:
                        logging.error(f"Failed to sync to guild {g.id}: {ge}")
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

        # DM内のクイズ 起動/操作（テキスト）
        if message.guild is None:
            cmd = message.content.strip()
            # 起動: クイズ [n]
            import re as _re
            m_quiz = _re.match(r"^/?クイズ(?:\s+(\d+))?(?:\s+(\S+))?$", cmd)
            m_review = _re.match(r"^/?復習(?:\s+(\d+))?$", cmd)
            if m_quiz or m_review:
                try:
                    # For 復習: no number -> review all due today.
                    if m_review and (m_review.group(1) is None):
                        n = None
                    else:
                        n = int((m_quiz or m_review).group(1) or 5)
                        n = max(1, min(n, 20))
                except Exception:
                    n = None if m_review else 5
                try:
                    # Build pool
                    rows = await words_util.fetch_user_words(message.author.id)
                    if not rows:
                        await message.channel.send("まだ単語が登録されていないみたい… /add で登録してね！")
                        return
                    pool = [(r[0], r[1], r[2]) for r in rows]
                    if m_review:
                        now = datetime.now(self.bot.JST)
                        due = words_util.compute_due_today(rows, now)
                        items = due if (n is None) else due[:n]
                        if not items:
                            import random as _rand
                            backup_n = (n if n is not None else 5)
                            items = _rand.sample(pool, min(backup_n, len(pool)))
                            note = "今日の復習対象はなかったから、ランダムに出題するね！"
                        else:
                            note = None
                        from bot.utils.review import ReviewSession
                        view = ReviewSession(message.author.id, items)
                        head = "じゃあ、はじめよっか！" + ("\n" + note if note else "")
                        await message.channel.send(head + "\n" + view.current_prompt(), view=view)
                        return
                    # クイズ（難しいもの優先）
                    # 第二引数で優先度バイアスを受け付け（数値 or 弱め/普通/強め）
                    bias_raw = m_quiz.group(2) if m_quiz else None
                    b = 1.0
                    if bias_raw:
                        mapping = {"弱め": 0.5, "普通": 1.0, "強め": 2.0}
                        b = mapping.get(bias_raw, None)
                        if b is None:
                            try:
                                b = float(bias_raw)
                            except Exception:
                                b = 1.0
                        b = max(0.0, min(3.0, b))
                    stats_map = await stats_util.fetch_stats_map(rows)
                    def weight_of(item):
                        wid = item[0]
                        attempts, corrects, ease = stats_map.get(wid, (0, 0, 2.5))
                        acc = (corrects / attempts) if attempts else 0.0
                        return 1.0 + b * (attempts * (1.0 - acc) + (3.0 - ease))
                    weights = [weight_of(it) for it in pool]
                    import random as _rand
                    selected, items_cpy, ws = [], pool[:], weights[:]
                    for _ in range(min(n, len(items_cpy))):
                        tw = sum(ws)
                        r = _rand.random() * tw
                        up = 0.0
                        idx = 0
                        for i, w in enumerate(ws):
                            up += w
                            if r <= up:
                                idx = i
                                break
                        selected.append(items_cpy.pop(idx))
                        ws.pop(idx)
                    from bot.utils.review import ReviewSession
                    view = ReviewSession(message.author.id, selected)
                    await message.channel.send("クイズ行くよ！\n" + view.current_prompt(), view=view)
                    return
                except Exception as e:
                    logging.error(f"DM quiz start failed: {e}")
                    await message.channel.send("ごめんね…クイズの開始に失敗しちゃった…")

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
                prompt = build_reply_prompt(replied_message.content, message.content, tone=get_prompt_tone())
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
            updated_entries = []   # (id, word, old_meaning, new_meaning)
            recent_items = []      # (id, word, meaning) for quick edit
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
                    updated_entries.append((word_id, english_word, old_meaning, japanese_meaning))
                    recent_items.append((word_id, english_word, japanese_meaning))
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
                    recent_items.append((row[0], english_word, japanese_meaning))

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

                view = RegistrationActionsView(
                    self.db,
                    message.author.id,
                    inserted_ids=[i for (i, _, _) in inserted_entries],
                    updated=updated_entries,
                    recent_items=recent_items,
                )
                await message.channel.send(confirmation, view=view)
            else:
                await message.channel.send(
                    f"{message.author.mention} まだ何も登録していないよ！\n単語と意味を `英単語:意味` の形式で入力してね。"
                )

async def setup(bot):
    await bot.add_cog(Events(bot))


class EditWordModal(discord.ui.Modal, title="単語を編集するよ！"):
    def __init__(self, db: Database, author_id: int, word_id: int, current_word: str, current_meaning: str):
        super().__init__()
        self.db = db
        self.author_id = author_id
        self.word_id = word_id
        self.word = discord.ui.TextInput(label="英単語", default=current_word, required=True, max_length=100)
        self.meaning = discord.ui.TextInput(label="意味", default=current_meaning, required=True, style=discord.TextStyle.long, max_length=500)
        self.add_item(self.word)
        self.add_item(self.meaning)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            await self.db.execute(
                "UPDATE words SET word = ?, meaning = ? WHERE id = ? AND user_id = ?",
                (str(self.word.value).strip(), str(self.meaning.value).strip(), self.word_id, self.author_id),
            )
            await interaction.response.send_message("更新したよ！", ephemeral=True)
        except Exception:
            await interaction.response.send_message("ごめんね、更新に失敗しちゃった…", ephemeral=True)


class RegistrationActionsView(discord.ui.View):
    def __init__(self, db: Database, author_id: int, inserted_ids: list[int], updated: list[tuple[int, str, str, str]], recent_items: list[tuple[int, str, str]]):
        super().__init__(timeout=180)
        self.db = db
        self.author_id = author_id
        self.inserted_ids = inserted_ids
        self.updated = updated
        self.recent_map = {wid: (w, m) for wid, w, m in recent_items}

        # Undo button (for both inserted and updated)
        self.undo_button = discord.ui.Button(label="取り消し", style=discord.ButtonStyle.danger)
        self.undo_button.callback = self.on_undo
        self.add_item(self.undo_button)

        # Select for quick edit
        if self.recent_map:
            options = [discord.SelectOption(label=w, description=(m[:90] + '…' if len(m) > 90 else m), value=str(wid)) for wid, (w, m) in self.recent_map.items()][:25]
            self.selector = discord.ui.Select(placeholder="編集する単語を選んでね", options=options, min_values=1, max_values=1)
            self.selector.callback = self.on_select
            self.add_item(self.selector)

        # Edit button
        self.edit_button = discord.ui.Button(label="編集", style=discord.ButtonStyle.primary)
        self.edit_button.callback = self.on_edit
        self.add_item(self.edit_button)
        self.selected_id: int | None = None

    async def on_select(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("これは発行者だけが操作できるよ！", ephemeral=True)
            return
        self.selected_id = int(self.selector.values[0])
        await interaction.response.defer()  # no visible change

    async def on_edit(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("これは発行者だけが操作できるよ！", ephemeral=True)
            return
        if not self.selected_id or self.selected_id not in self.recent_map:
            await interaction.response.send_message("まずは編集する単語を選んでね！", ephemeral=True)
            return
        w, m = self.recent_map[self.selected_id]
        await interaction.response.send_modal(EditWordModal(self.db, self.author_id, self.selected_id, w, m))

    async def on_undo(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("これは発行者だけが取り消せるよ！", ephemeral=True)
            return
        # Delete inserted rows
        for word_id in self.inserted_ids:
            await self.db.execute("DELETE FROM words WHERE user_id = ? AND id = ?", (self.author_id, word_id))
        # Revert updated rows
        for word_id, word, old_meaning, new_meaning in self.updated:
            await self.db.execute("UPDATE words SET meaning = ? WHERE user_id = ? AND id = ?", (old_meaning, self.author_id, word_id))
        # Disable buttons
        for item in self.children:
            if isinstance(item, discord.ui.Button) or isinstance(item, discord.ui.Select):
                item.disabled = True
        await interaction.response.edit_message(content=f"{interaction.message.content}\n(取り消したよ！)", view=self)
        self.stop()
