# bot/cogs/commands.py
from discord.ext import commands
from bot.utils.database import Database
import logging
import google.generativeai as genai
import os


class Commands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def edit(
        self, ctx, word_id: int, new_word: str = None, new_meaning: str = None
    ):
        db = await Database.get_instance()
        row = await db.fetchone("SELECT user_id FROM words WHERE id = ?", (word_id,))
        if row is None:
            await ctx.send("指定されたIDの単語が見つかりません。")
            return
        if row[0] != ctx.author.id:
            await ctx.send("この単語を編集する権限がありません。")
            return
        if new_word:
            await db.execute(
                "UPDATE words SET word = ? WHERE id = ?", (new_word, word_id)
            )
        if new_meaning:
            await db.execute(
                "UPDATE words SET meaning = ? WHERE id = ?", (new_meaning, word_id)
            )
        await ctx.send("単語が更新されました。")

    @commands.command()
    async def show(self, ctx):
        db = await Database.get_instance()
        rows = await db.fetchall(
            "SELECT id, word, meaning FROM words WHERE user_id = ?", (ctx.author.id,)
        )
        if rows:
            response = "あなたの登録した単語一覧:\n"
            for row in rows:
                response += f"ID: {row[0]}, 英語: {row[1]}, 意味: {row[2]}\n"
            await ctx.send(response)
        else:
            await ctx.send("登録された単語がありません。")

    @commands.command()
    async def delete(self, ctx, *, english_word: str):
        """
        ユーザーが指定した英単語を自身の辞書から削除します。

        使用方法:
        !delete <英単語>
        """
        db = await Database.get_instance()
        rows = await db.fetchall(
            "SELECT id, word, meaning FROM words WHERE user_id = ? AND word = ?",
            (ctx.author.id, english_word),
        )

        if not rows:
            await ctx.send(f"{ctx.author.mention} 該当する単語が見つかりませんでした。")
            return

        await db.execute(
            "DELETE FROM words WHERE user_id = ? AND word = ?",
            (ctx.author.id, english_word),
        )

        deleted_words = "\n".join(
            [f"**英語:** {row[1]} | **意味:** {row[2]}" for row in rows]
        )
        await ctx.send(
            f"{ctx.author.mention} 以下の単語が削除されました：\n{deleted_words}"
        )

    @commands.command()
    async def help(self, ctx):
        help_text = (
            "**コマンド一覧:**\n"
            "`!delete <英単語>` - 指定した英単語を辞書から削除します。\n"
            "`!edit <ID> [新しい英単語] [新しい意味]` - 指定したIDの単語を編集します。\n"
            "`!show` - 自分が登録した単語一覧を表示します。\n"
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
            model = genai.GenerativeModel("gemini-1.5-flash")
            response = model.generate_content(
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

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandNotFound):
            await ctx.send("そのコマンドは存在しません。`!help` を参照してください。")
        else:
            logging.error(f"Unhandled error: {error}")
            await ctx.send("エラーが発生しました。管理者に報告してください。")


async def setup(bot):
    await bot.add_cog(Commands(bot))
