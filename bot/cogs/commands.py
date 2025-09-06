# bot/cogs/commands.py
from discord.ext import commands
from bot.utils.database import Database
import logging
from bot.utils.config import get_gemini_model
from bot.utils.pagination import chunk_lines_to_pages, SimplePaginator
import discord
from discord import app_commands
from typing import Optional, List
import re
import random


class Commands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.model = get_gemini_model()

    async def cog_load(self) -> None:
        # Ensure app commands are registered when the cog loads
        try:
            self.bot.tree.add_command(self.slash_show)
            self.bot.tree.add_command(self.slash_help)
            self.bot.tree.add_command(self.slash_edit)
            self.bot.tree.add_command(self.slash_delete)
            self.bot.tree.add_command(self.slash_kaisetu)
            self.bot.tree.add_command(self.slash_bunshou)
        except Exception as e:
            logging.error(f"Failed to add app commands: {e}")

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
        prompt = f"""
                日本語で出力してください。
                あなたは日本のアニメの妹キャラです。その話し方を完全にコピーしてください。
                返事の例は次の通りです。
                「おはよ！」
                「おにーちゃん、今日もはりきっていこう！」
                「えー！そんなぁー(´;ω;｀)」
                「もぉー！知らない！」
                試しにこの妹キャラになりきったうえで、次の英単語に関する文法的、意味的解説を英語の例文とともに簡潔にしてください。
                {word}

                注意事項
                「///」のようなスラッシュは使用しないでください。
                *や#のようなマークダウンの記法は用いないでください
                単語、その意味、例文以外にカッコ「」は用いないでください
                """
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
        style_text = f"スタイル: {style}風でお願いします。" if style else "特に指定なしのスタイルでお願いします。"
        word_list = "".join([f"- 英単語: {w}, 意味: {m}\n" for (w, m) in selected_rows])
        try:
            formatted_prompt = prompt.format(style_text=style_text, word_list=word_list)
            response = self.model.generate_content(formatted_prompt)
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
        help_text = (
            "**お兄ちゃん、コマンドの使い方教えるね！:**\n"
            "/show - 登録した単語一覧を見せちゃうよ！\n"
            "/edit <ID> [新しい英単語] [新しい意味] - 指定したIDの単語を編集できるんだ！\n"
            "/delete <英単語(スペース区切り)> - 指定した英単語を辞書から削除しちゃうよ！\n"
            "/kaisetu <英単語> - 指定した英単語を解説するよ！(Gemini)\n"
            "/bunshou [スタイル] - 登録単語で文章を作るよ！(Gemini)\n"
        )
        await interaction.response.send_message(help_text, ephemeral=True)

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
            style_text = f"スタイル: {style}風でお願いします。" if style else "特に指定���しのスタイルでお願いします。"

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
