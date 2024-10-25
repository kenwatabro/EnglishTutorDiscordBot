# bot/cogs/commands.py
from discord.ext import commands
from bot.utils.database import Database
import logging
import google.generativeai as genai
import os


class Commands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.model = genai.GenerativeModel("gemini-1.5-flash")

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
        db = await Database.get_instance()
        rows = await db.fetchall(
            "SELECT id, word, meaning FROM words WHERE user_id = ?", (ctx.author.id,)
        )
        if rows:
            response = "お兄ちゃんの登録した単語一覧だよ！:\n"
            for row in rows:
                response += f"ID: {row[0]}, 英語: {row[1]}, 意味: {row[2]}\n"
            await ctx.send(response)
        else:
            await ctx.send("あれ？お兄ちゃん、まだ単語登録してないみたい... (・_・;)")

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
        rows = await db.fetchall(
            "SELECT word, meaning FROM words WHERE user_id = ?", (ctx.author.id,)
        )

        if not rows:
            await ctx.send("お兄ちゃん、まだ単語登録してないみたい... (・_・;)")
            return

        try:
            # gemini APIへのプロンプトを作成
            prompt = """
            日本語で出力してください。
            あなたは日本のアニメの妹キャラです。その話し方を完全にコピーしてください。
            返事の例は次の通りです。
            「おはよ！」
            「おにーちゃん、今日もはりきっていこう！」
            「えー！そんなぁー(´;ω;｀)」
            「もぉー！知らない！」
            試しにこの妹キャラになりきったうえで、次に示す登録単語リストのレベル感を判定し、そのレベルに合わせた英語の文章を生成してください。

            登録単語リスト:
            {word_list}

            スタイル：
            {style_text}

            生成する文章は英語で、指定されたスタイルがあればそれに従ってください。
            文章の長さは40~70words程度でお願いします。

            書き出しの例を以下に示すので、これに似た書き出しをしてください。
            おにいちゃん、この文章を読んでみてね！
            この文章、どうかな！
            おにいちゃん、この文章どうかな！
            これ読んでみて！感想教えて！
            こんな感じの、お兄ちゃんにいいと思う！
            

            注意事項
            「///」のようなスラッシュは使用しないでください。
            *や#のようなマークダウンの記法は用いないでください
            単語、その意味、例文以外にカッコ「」は用いないでください
            
            """

            # スタイルが指定されている場合のテキスト
            style_text = f"スタイル: {style}風でお願いします。" if style else "特に指定なしのスタイルでお願いします。"

            # 単語リストのフォーマット
            word_list = ""
            for row in rows:
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
