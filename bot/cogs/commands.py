# bot/cogs/commands.py
from discord.ext import commands
from bot.utils.database import Database
import logging
from bot.utils.config import get_gemini_model, get_prompt_tone
from bot.utils.pagination import chunk_lines_to_pages, SimplePaginator
import discord
from discord import app_commands
from typing import Optional, List
import re
import random
from datetime import datetime
from bot.utils import words as words_util
from bot.utils.prompts import build_kaisetu_prompt, build_bunshou_prompt
from bot.utils.review import ReviewSession, start_quiz_session, quiz_memorized, quiz_forgot, quiz_stop
from bot.utils import stats as stats_util


class Commands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.model = get_gemini_model()

    # ---------- Helpers ----------
    async def _build_show_pages(self, user_id: int) -> Optional[List[str]]:
        db = await Database.get_instance()
        rows = await db.fetchall(
            "SELECT id, word, meaning FROM words WHERE user_id = ? ORDER BY id ASC",
            (user_id,),
        )
        if not rows:
            return None
        header = "お兄ちゃんの登録した単語一覧だよ！:\n"
        lines = [f"ID: {r[0]} | 英語: {r[1]} | 意味: {r[2]}" for r in rows]
        pages = chunk_lines_to_pages(lines, max_chars=1900)
        return [header + p for p in pages]

    async def _edit_word_impl(self, user_id: int, word_id: int, new_word: Optional[str], new_meaning: Optional[str]) -> str:
        db = await Database.get_instance()
        row = await db.fetchone("SELECT user_id FROM words WHERE id = ?", (word_id,))
        if row is None:
            return "えっと、お兄ちゃん...そのIDの単語見つからないよ？ (´・ω・｀)"
        if row[0] != user_id:
            return "ごめんね、お兄ちゃんじゃその単語編集できないみたい... (>_<)"
        if new_word:
            await db.execute("UPDATE words SET word = ? WHERE id = ?", (new_word, word_id))
        if new_meaning:
            await db.execute("UPDATE words SET meaning = ? WHERE id = ?", (new_meaning, word_id))
        return "単語更新かんりょー！"

    async def _delete_words_impl(self, user_id: int, words: str) -> Optional[str]:
        cleaned_input = re.sub(r"[^a-zA-Z\s]", "", words)
        word_list = [w for w in cleaned_input.split() if w]
        if not word_list:
            return None
        db = await Database.get_instance()
        deleted_results = []
        not_found = []
        for word in word_list:
            rows = await db.fetchall(
                "SELECT id, word, meaning FROM words WHERE user_id = ? AND word = ?",
                (user_id, word),
            )
            if rows:
                await db.execute(
                    "DELETE FROM words WHERE user_id = ? AND word = ?",
                    (user_id, word),
                )
                deleted_results.extend(rows)
            else:
                not_found.append(word)
        response = []
        if deleted_results:
            deleted_words = "\n".join([f"**英語:** {r[1]} | **意味:** {r[2]}" for r in deleted_results])
            response.append(f"削除かんりょー！:\n{deleted_words}")
        if not_found:
            response.append(f"この単語は見つからなかったよ: {', '.join(not_found)}")
        return "\n\n".join(response) if response else ""

    async def _kaisetu_impl(self, word: str) -> Optional[str]:
        if not self.model:
            return None
        prompt = build_kaisetu_prompt(word, tone=get_prompt_tone())
        try:
            response = self.model.generate_content(prompt)
            return response.text
        except Exception as e:
            logging.error(f"Error in kaisetu: {e}")
            return "ごめんね、お兄ちゃん。なんかうまくいかないみたい（´；ω；｀）"

    async def _bunshou_impl(self, user_id: int, style: Optional[str]) -> Optional[str]:
        if not self.model:
            return None
        db = await Database.get_instance()
        rows = await db.fetchall(
            "SELECT word, meaning FROM words WHERE user_id = ?",
            (user_id,),
        )
        if not rows:
            return "お兄ちゃん、まだ単語登録してないみたい... (・_・;)"
        selected_rows = random.sample(rows, min(15, len(rows)))
        prompt = build_bunshou_prompt(selected_rows, style, tone=get_prompt_tone())
        try:
            response = self.model.generate_content(prompt)
            return response.text
        except Exception as e:
            logging.error(f"Error in bunshou: {e}")
            return "ごめんね、お兄ちゃん。なんかうまくいかないみたい（´；ω；｀）"

    @commands.command()
    async def edit(
        self, ctx, word_id: int, new_word: str = None, new_meaning: str = None
    ):
        db = await Database.get_instance()
        row = await db.fetchone("SELECT user_id FROM words WHERE id = ?", (word_id,))
        if row is None:
            await ctx.send("えっと、お兄ちゃん...そのIDの単語見つからないよ？ (´・ω・｀)")
            return
        if row[0] != ctx.author.id:
            await ctx.send("ごめんね、お兄ちゃんじゃその単語編集できないみたい... (>_<)")
            return
        if new_word:
            await db.execute(
                "UPDATE words SET word = ? WHERE id = ?", (new_word, word_id)
            )
        if new_meaning:
            await db.execute(
                "UPDATE words SET meaning = ? WHERE id = ?", (new_meaning, word_id)
            )
        await ctx.send("単語更新かんりょー！")

    @commands.command()
    async def show(self, ctx):
        pages = await self._build_show_pages(ctx.author.id)
        if not pages:
            await ctx.send("あれ？お兄ちゃん、まだ単語登録してないみたい... (・_・;)")
            return

        view = SimplePaginator(author_id=ctx.author.id, pages=pages)
        await ctx.send(view.current_content(), view=view)

    # Slash command version of show
    @app_commands.command(name="show", description="登録した単語一覧を表示するよ！")
    async def slash_show(self, interaction: discord.Interaction):
        pages = await self._build_show_pages(interaction.user.id)
        if not pages:
            await interaction.response.send_message(
                "あれ？お兄ちゃん、まだ単語登録してないみたい... (・_・;)",
                ephemeral=True,
            )
            return
        view = SimplePaginator(author_id=interaction.user.id, pages=pages)
        await interaction.response.send_message(view.current_content(), view=view, ephemeral=False)

    # Slash: help
    @app_commands.command(name="help", description="コマンドの使い方を表示するよ！")
    async def slash_help(self, interaction: discord.Interaction):
        is_dm = interaction.guild is None
        await interaction.response.defer(ephemeral=not is_dm, thinking=False)
        help_text = (
            "**お兄ちゃん、コマンドの使い方教えるね！:**\n"
            "/復習 [出題数] - 今日の復習（クイズ）を始めるよ！\n"
            "/クイズ [出題数] [優先度] - 登録単語からランダムにクイズを出すよ！優先度は 0〜3 の数値 or ‘弱め/普通/強め’（既定1）\n"
            "（英語名のスラッシュコマンドもそのまま使えるよ：/review, /quiz など）\n"
            "（DMでも同じコマンドで開始できるよ）\n"
            "/show - 登録した単語一覧を見せちゃうよ！\n"
            "/edit <ID> [新しい英単語] [新しい意味] - 指定したIDの単語を編集できるんだ！\n"
            "/delete <英単語(スペース区切り)> - 指定した英単語を辞書から削除しちゃうよ！\n"
            "/kaisetu <英単語> - 指定した英単語を解説するよ！(Gemini)\n"
            "/bunshou [スタイル] - 登録単語で文章を作るよ！(Gemini)\n"
            "/add <英単語> <意味> - 単語を1件登録するよ！\n"
            "/bulk_add <ペアの一覧> - 複数の単語をまとめて登録するよ！\n"
            "/progress - 進捗を表示するよ！\n"
            "/find <キーワード> - 単語や意味で検索するよ！\n"
        )
        await interaction.followup.send(help_text, ephemeral=not is_dm)

    # Slash: edit
    @app_commands.command(name="edit", description="登録した単語の内容を編集するよ！")
    @app_commands.describe(word_id="編集する単語のID", new_word="新しい英単語", new_meaning="新しい意味")
    async def slash_edit(
        self,
        interaction: discord.Interaction,
        word_id: int,
        new_word: Optional[str] = None,
        new_meaning: Optional[str] = None,
    ):
        await interaction.response.defer(thinking=True, ephemeral=True)
        msg = await self._edit_word_impl(interaction.user.id, word_id, new_word, new_meaning)
        await interaction.followup.send(msg, ephemeral=True)

    # Slash: delete
    @app_commands.command(name="delete", description="指定した英単語(複数可)を削除するよ！")
    @app_commands.describe(words="例: apple orange banana")
    async def slash_delete(self, interaction: discord.Interaction, words: str):
        await interaction.response.defer(thinking=True, ephemeral=True)
        result = await self._delete_words_impl(interaction.user.id, words)
        if not result:
            await interaction.followup.send("えっと...削除したい英単語を教えてほしいな！", ephemeral=True)
        else:
            await interaction.followup.send(result, ephemeral=True)

    # Slash: kaisetu (Gemini)
    @app_commands.command(name="kaisetu", description="英単語の解説をするよ！(Gemini)")
    async def slash_kaisetu(self, interaction: discord.Interaction, word: str):
        if not self.model:
            await interaction.response.send_message(
                "ごめんね、お兄ちゃん。今は解説機能が使えないみたい…(>_<)", ephemeral=True
            )
            return
        await interaction.response.defer(thinking=True)
        text = await self._kaisetu_impl(word)
        await interaction.followup.send(text or "うまくいかなかったみたい…", ephemeral=False)

    # Slash: bunshou (Gemini)
    @app_commands.command(name="bunshou", description="登録単語で文章を生成するよ！(Gemini)")
    @app_commands.describe(style="スタイル (例: ビジネス風)")
    async def slash_bunshou(self, interaction: discord.Interaction, style: Optional[str] = None):
        if not self.model:
            await interaction.response.send_message(
                "ごめんね、お兄ちゃん。今は文章生成が使えないみたい…(>_<)", ephemeral=True
            )
            return
        await interaction.response.defer(thinking=True)
        text = await self._bunshou_impl(interaction.user.id, style)
        await interaction.followup.send(text or "うまくいかなかったみたい…", ephemeral=False)

    async def _start_review(self, interaction: discord.Interaction, count: Optional[int] = 5):
        n = max(1, min(count or 5, 20))
        user_id = interaction.user.id
        # Build items due today; fallback to random sample if none
        rows = await words_util.fetch_user_words(user_id)
        if not rows:
            await interaction.response.send_message("お兄ちゃん、まだ単語登録してないみたい…まずは /add で登録してね！", ephemeral=True)
            return
        now = datetime.now(self.bot.JST)
        due = words_util.compute_due_today(rows, now)
        items = due[:n]
        note = None
        if not items:
            import random
            pool = [(r[0], r[1], r[2]) for r in rows]
            items = random.sample(pool, min(n, len(pool)))
            note = "今日の復習対象はなかったから、ランダムに出題するね！"
        # Send in DM or current DM channel with buttons
        is_dm = interaction.guild is None
        await interaction.response.send_message("DMでクイズを始めるね！", ephemeral=not is_dm)
        user = interaction.user
        channel = interaction.channel if is_dm else (user.dm_channel or await user.create_dm())
        view = ReviewSession(user_id, items)
        head = f"{user.mention} じゃあ、はじめよっか！\n"
        if note:
            head += note + "\n"
        try:
            await channel.send(head + view.current_prompt(), view=view)
        except Exception as e:
            logging.error(f"Failed to send review DM: {e}")
            await interaction.followup.send("ごめんね… DMに送れなかったよ。DMを受け取れる設定にしてね！", ephemeral=True)

    # Slash: review (quiz)
    @app_commands.command(name="review", description="今日の復習（クイズ）を始めるよ！")
    @app_commands.describe(count="出題数（1〜20）")
    async def slash_review(self, interaction: discord.Interaction, count: Optional[int] = 5):
        await self._start_review(interaction, count)

    # Internal: quiz (random pool weighted)
    async def _start_quiz(self, interaction: discord.Interaction, count: Optional[int] = 5, bias: Optional[float] = 1.0):
        user_id = interaction.user.id
        rows = await words_util.fetch_user_words(user_id)
        if not rows:
            await interaction.response.send_message("お兄ちゃん、まだ単語登録してないみたい…まずは /add で登録してね！", ephemeral=True)
            return
        pool = [(r[0], r[1], r[2]) for r in rows]
        n = max(1, min(count or 5, 20))
        b = bias if bias is not None else 1.0
        try:
            b = float(b)
        except Exception:
            b = 1.0
        b = max(0.0, min(3.0, b))
        is_dm = interaction.guild is None
        await interaction.response.send_message("DMでクイズを始めるね！", ephemeral=not is_dm)
        user = interaction.user
        channel = interaction.channel if is_dm else (user.dm_channel or await user.create_dm())
        # Weight selection by per-word difficulty stats (harder words appear more)
        stats_map = await stats_util.fetch_stats_map(rows)
        def weight_of(item):
            wid = item[0]
            attempts, corrects, ease = stats_map.get(wid, (0, 0, 2.5))
            acc = (corrects / attempts) if attempts else 0.0
            # Higher weight for lower accuracy and lower ease; scaled by bias
            return 1.0 + b * (attempts * (1.0 - acc) + (3.0 - ease))

        weights = [weight_of(it) for it in pool]
        # Sample without replacement using weights
        import random
        selected = []
        items = pool[:]
        ws = weights[:]
        for _ in range(min(n, len(items))):
            total_w = sum(ws)
            r = random.random() * total_w
            upto = 0.0
            idx = 0
            for i, w in enumerate(ws):
                upto += w
                if r <= upto:
                    idx = i
                    break
            selected.append(items.pop(idx))
            ws.pop(idx)

        view = ReviewSession(user_id, selected)
        try:
            await channel.send(f"{user.mention} クイズ行くよ！\n" + view.current_prompt(), view=view)
        except Exception as e:
            logging.error(f"Failed to send quiz DM: {e}")
            await interaction.followup.send("ごめんね… DMに送れなかったよ。DMを受け取れる設定にしてね！", ephemeral=True)

    @app_commands.command(name="quiz", description="登録単語からランダムでクイズを出すよ！")
    @app_commands.describe(count="出題数（1〜20）", bias="難しい単語を優先する度合い（0〜3、既定1）")
    async def slash_quiz(self, interaction: discord.Interaction, count: Optional[int] = 5, bias: Optional[float] = 1.0):
        await self._start_quiz(interaction, count, bias)

    # Japanese aliases for discoverability
    @app_commands.command(name="復習", description="今日の復習（クイズ）を始めるよ！")
    @app_commands.describe(count="出題数（1〜20）")
    async def slash_review_ja(self, interaction: discord.Interaction, count: Optional[int] = 5):
        await self._start_review(interaction, count)

    @app_commands.command(name="クイズ", description="登録単語からランダムにクイズを出すよ！")
    @app_commands.describe(count="出題数（1〜20）", bias="難しい単語を優先する度合い（0〜3、既定1）")
    async def slash_quiz_ja(self, interaction: discord.Interaction, count: Optional[int] = 5, bias: Optional[float] = 1.0):
        await self._start_quiz(interaction, count, bias)

    # (Removed separate DM slash actions; buttons are provided)

    # Slash: add single word
    @app_commands.command(name="add", description="英単語を1件登録するよ！")
    @app_commands.describe(word="英単語", meaning="意味")
    async def slash_add(self, interaction: discord.Interaction, word: str, meaning: str):
        now = datetime.now(self.bot.JST)
        count = await words_util.insert_pairs(interaction.user.id, [(word.strip(), meaning.strip())], now)
        await interaction.response.send_message(
            f"{interaction.user.mention} 単語を登録したよ！\n**英語:** {word} | **意味:** {meaning}",
            ephemeral=False,
        )

    # Slash: bulk add
    @app_commands.command(name="bulk_add", description="複数の単語をまとめて登録するよ！（例: apple:りんご; take off:離陸する）")
    @app_commands.describe(pairs="word:meaning を改行やセミコロンで区切って入力してね")
    async def slash_bulk_add(self, interaction: discord.Interaction, pairs: str):
        parsed = words_util.parse_pairs(pairs)
        if not parsed:
            await interaction.response.send_message(
                "ごめんね、登録できる形式じゃなかったみたい… 'apple: りんご; take off: 離陸する' みたいに書いてね！",
                ephemeral=True,
            )
            return
        now = datetime.now(self.bot.JST)
        count = await words_util.insert_pairs(interaction.user.id, parsed, now)
        preview = "\n".join([f"**英語:** {w} | **意味:** {m}" for (w, m) in parsed[:10]])
        more = "\n…" if len(parsed) > 10 else ""
        await interaction.response.send_message(
            f"{interaction.user.mention} 単語を{count}件登録したよ！\n" + preview + more,
            ephemeral=False,
        )

    # (Removed /due per product direction)

    # Slash: progress
    @app_commands.command(name="progress", description="進捗を表示するよ！")
    async def slash_progress(self, interaction: discord.Interaction):
        rows = await words_util.fetch_user_words(interaction.user.id)
        now = datetime.now(self.bot.JST)
        stats = words_util.compute_progress(rows, now)
        total = stats["total"]
        due = stats["due_today"]
        stage_counts = stats["stage_counts"]
        intervals = stats["intervals"]
        # Build a readable summary
        stage_lines = []
        for idx, count in enumerate(stage_counts):
            if idx == 0:
                name = "新規"
            elif idx <= len(intervals):
                name = f"{intervals[idx-1]}日以上"
            else:
                name = "完了"
            stage_lines.append(f"・{name}: {count}語")
        summary = (
            f"{interaction.user.mention} の進捗だよ！\n"
            f"合計: {total}語 / 今日の復習: {due}語\n" + "\n".join(stage_lines)
        )
        await interaction.response.send_message(summary, ephemeral=True)

    # Slash: find/search
    @app_commands.command(name="find", description="単語や意味で検索するよ！")
    @app_commands.describe(q="検索ワード（英単語または日本語の一部）")
    async def slash_find(self, interaction: discord.Interaction, q: str):
        db = await Database.get_instance()
        like = f"%{q}%"
        rows = await db.fetchall(
            "SELECT id, word, meaning FROM words WHERE user_id = ? AND (word LIKE ? OR meaning LIKE ?) ORDER BY id ASC",
            (interaction.user.id, like, like),
        )
        if not rows:
            await interaction.response.send_message("見つからなかったみたい…別のキーワードを試してね！", ephemeral=True)
            return
        header = f"『{q}』の検索結果だよ！\n"
        lines = [f"ID: {r[0]} | 英語: {r[1]} | 意味: {r[2]}" for r in rows]
        pages = chunk_lines_to_pages(lines, max_chars=1900)
        pages = [header + p for p in pages]
        view = SimplePaginator(author_id=interaction.user.id, pages=pages)
        await interaction.response.send_message(view.current_content(), view=view, ephemeral=False)

    @commands.command()
    async def delete(self, ctx, *, words: str):
        """
        ユーザーが指定した英単語（複数可）を自身の辞書から削除します。

        使用方法:
        !delete <英単語1> <英単語2> ...
        """
        # アルファベットとスペースのみを残し、複数のスペースを1つに置換して単語リストを作成
        import re
        cleaned_input = re.sub(r'[^a-zA-Z\s]', '', words)
        word_list = [w for w in cleaned_input.split() if w]

        if not word_list:
            await ctx.send(f"{ctx.author.mention} えっと...削除したい英単語を教えてほしいな！")
            return

        db = await Database.get_instance()
        deleted_results = []
        not_found = []

        for word in word_list:
            rows = await db.fetchall(
                "SELECT id, word, meaning FROM words WHERE user_id = ? AND word = ?",
                (ctx.author.id, word),
            )
            
            if rows:
                await db.execute(
                    "DELETE FROM words WHERE user_id = ? AND word = ?",
                    (ctx.author.id, word),
                )
                deleted_results.extend(rows)
            else:
                not_found.append(word)

        # 結果メッセージの作成
        response = []
        if deleted_results:
            deleted_words = "\n".join(
                [f"**英語:** {row[1]} | **意味:** {row[2]}" for row in deleted_results]
            )
            response.append(f"削除かんりょー！:\n{deleted_words}")
        
        if not_found:
            response.append(f"この単語は見つからなかったよ: {', '.join(not_found)}")

        if response:
            await ctx.send(f"{ctx.author.mention} " + "\n\n".join(response))

    @commands.command()
    async def help(self, ctx):
        help_text = (
            "**お兄ちゃん、コマンドの使い方教えるね！:**\n"
            "`!delete <英単語>` - 指定した英単語を辞書から削除しちゃうよ！\n"
            "`!edit <ID> [新しい英単語] [新しい意味]` - 指定したIDの単語を編集できるんだ！\n"
            "`!show` - お兄ちゃんが登録した単語一覧を見せちゃうよ！\n"
            "`!due` - 今日の復習対象を表示するよ！\n"
            "`!progress` - 進捗を表示するよ！\n"
        )
        await ctx.send(help_text)

    @commands.command()
    async def kaisetu(self, ctx, *, word: str):
        """
        指定された英単語の解説を妹キャラクターの口調で提供します。

        使用方法:
        !kaisetu <英単語>
        """
        if not self.model:
            await ctx.send("ごめんね、お兄ちゃん。今は解説機能が使えないみたい…(>_<)")
            return
        try:
            # Google AI APIを使用して解説を生成
            response = self.model.generate_content(
                f"""
                日本語で出力してください。
                あなたは日本のアニメの妹キャラです。その話し方を完全にコピーしてください。
                返事の例は次の通りです。
                「おはよ！」
                「おにーちゃん、今日もはりきっていこう！」
                「えー！そんなぁー(´;ω;｀)」
                「もぉー！知らない！」
                試しにこの妹キャラになりきったうえで、次の英単語に関する文法的、意味的解説を英語の例文とともに簡潔にしてください。
                {word}

                書き出しの例を以下に示すので、これに似た書き出しをしてください。
                この単語はねー
                この単語の意味はね！
                ほほーう、これはなかなか乙な単語だねぇ～（この表現を使うときは単語の難易度に関する率直な印象を「乙」以外にも「難しい」、「いい感じ」などのような表現を自分で考えたうえで付け加えてください）
                うーんと、これはね
                そうだね～
                

                注意事項
                「///」のようなスラッシュは使用しないでください。
                *や#のようなマークダウンの記法は用いないでください
                単語、その意味、例文以外にカッコ「」は用いないでください
                """
            )
            
            await ctx.send(response.text)
        except Exception as e:
            logging.error(f"Error in kaisetu command: {e}")
            await ctx.send("ごめんね、お兄ちゃん。なんかうまくいかないみたい（´；ω；｀）")

    @commands.command()
    async def bunshou(self, ctx, *, style: str = None):
        """
        登録した英単語を参照し、そのレベルをTOEIC、TOEFL、IELTSで判断し、
        レベルに合わせた文章を生成します。
        
        使用方法:
        !bunshou [スタイル]
        例:
        !bunshou ビジネス風
        !bunshou
        """
        db = await Database.get_instance()
        # すべての単語を取得
        rows = await db.fetchall(
            "SELECT word, meaning FROM words WHERE user_id = ?", (ctx.author.id,)
        )

        if not rows:
            await ctx.send("お兄ちゃん、まだ単語登録してないみたい... (・_・;)")
            return

        if not self.model:
            await ctx.send("ごめんね、お兄ちゃん。今は文章生成が使えないみたい…(>_<)")
            return
        try:
            # ランダムに15個（または全件数が15未満の場合は全件）を選択
            import random
            selected_rows = random.sample(rows, min(15, len(rows)))

            # gemini APIへのプロンプトを作成
            prompt = """
            
            ### 次に示す登録単語リストのレベル感を判定し、そのレベルに合わせた英語の文章を生成してください。

            登録単語リスト:
            {word_list}

            スタイル：
            {style_text}

            ### 生成する文章は英語で、指定されたスタイルがあればそれに従ってください。
            ### 文章の長さは40~70words程度でお願いします。
            
            ### あなたは日本のアニメの妹キャラです。その話し方をまねてください。
            ### 生成された英文の前後には、妹キャラのコメントを例に倣って、アレンジしつつ日本語でつけてください。
            ### 返事の例は次の通りです。
            「おはよ！」
            「おにーちゃん、今日もはりきっていこう！」
            「えー！そんなぁー(´;ω;｀)」
            「もぉー！知らない！」

            ### 書き出しの例
            おにいちゃん、この文章を読んでみてね！
            この文章、どうかな！
            おにいちゃん、この文章どうかな！
            これ読んでみて！感想教えて！
            こんな感じの、お兄ちゃんにいいと思う！
            
            ### 出力例
            これ読んでみて！感想教えてねー！
            < English sentences based on the style in the level of the words the user registered >
            なんだか面白いお話だね！

            注意事項
            「///」のようなスラッシュは使用しないでください。
            *や#のようなマークダウンの記法は用いないでください
            単語、その意味、例文以外にカッコ「」は用いないでください
            
            """

            # スタイルが指定されている場合のテキスト
            style_text = (
                f"スタイル: {style}風でお願いします。"
                if style
                else "特に指定なしのスタイルでお願いします。"
            )

            # 単語リストのフォーマット（選択された単語のみ）
            word_list = ""
            for row in selected_rows:
                word, meaning = row
                word_list += f"- 英単語: {word}, 意味: {meaning}\n"

            # プロンプトをフォーマット
            formatted_prompt = prompt.format(style_text=style_text, word_list=word_list)

            # gemini APIを使用して文章を生成
            response = self.model.generate_content(formatted_prompt)
            await ctx.send(response.text)
        except Exception as e:
            logging.error(f"bunshoコマンドでエラーが発生しました: {e}")
            await ctx.send("ごめんね、お兄ちゃん。なんかうまくいかないみたい（´；ω；｀）")

    # (Removed !due per product direction)

    # Prefix: progress
    @commands.command(name="progress")
    async def cmd_progress(self, ctx):
        rows = await words_util.fetch_user_words(ctx.author.id)
        now = datetime.now(self.bot.JST)
        stats = words_util.compute_progress(rows, now)
        total = stats["total"]
        due = stats["due_today"]
        stage_counts = stats["stage_counts"]
        intervals = stats["intervals"]
        stage_lines = []
        for idx, count in enumerate(stage_counts):
            if idx == 0:
                name = "新規"
            elif idx <= len(intervals):
                name = f"{intervals[idx-1]}日以上"
            else:
                name = "完了"
            stage_lines.append(f"・{name}: {count}語")
        summary = (
            f"{ctx.author.mention} の進捗だよ！\n"
            f"合計: {total}語 / 今日の復習: {due}語\n" + "\n".join(stage_lines)
        )
        await ctx.send(summary)

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandNotFound):
            await ctx.send("あれ？お兄ちゃん、そのコマンドないみたい... `!help` 見てみてね！")
        else:
            logging.error(f"Unhandled error: {error}")
            await ctx.send("うぅ...ごめんね、お兄ちゃん。なんかエラーが出ちゃった... (´；ω；｀) 管理者さんに教えてあげて！")

    # @commands.Cog.listener()
    # async def on_message(self, message):
    #     if message.author.bot or not message.reference:
    #         return

    #     try:
    #         replied_message = await message.channel.fetch_message(message.reference.message_id)
            
    #         prompt = f"""
    #         日本語で出力してください。
    #         あなたは日本のアニメの妹キャラです。その話し方を完全にコピーしてください。
    #         以下の会話に対して、妹キャラとして適切な返答をしてください。

    #         お兄ちゃん: {replied_message.content}
    #         私: {message.content}

    #         妹キャラの返事の例は以下の通りです
    #         「おはよ！」
    #         「おにーちゃん、今日もはりきっていこう！」
    #         「えー！そんなぁー(´;ω;｀)」
    #         「もぉー！知らない！」
    #         """

    #         response = self.model.generate_content(prompt)
    #         await message.reply(response.text)

    #     except Exception as e:
    #         logging.error(f"Error in on_message event: {e}")
    #         await message.channel.send("ごめんね、お兄ちゃん。なんかうまくいかないみたい（´；ω；｀）")

async def setup(bot):
    await bot.add_cog(Commands(bot))
