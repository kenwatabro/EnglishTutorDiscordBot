# bot/cogs/commands.py
from discord.ext import commands
from bot.utils.database import Database
import logging


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

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandNotFound):
            await ctx.send("そのコマンドは存在しません。`!help` を参照してください。")
        else:
            logging.error(f"Unhandled error: {error}")
            await ctx.send("エラーが発生しました。管理者に報告してください。")


async def setup(bot):
    await bot.add_cog(Commands(bot))
