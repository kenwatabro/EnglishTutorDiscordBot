import discord
from discord.ext import commands
from discord.ui import View, Button
from datetime import datetime
import random
from bot.utils.database import Database


class QuizView(View):
    def __init__(self, ctx, words, db):
        super().__init__(timeout=None)
        self.ctx = ctx
        self.words = words
        self.db = db
        self.current_index = 0
        self.message = None

    async def on_timeout(self):
        if self.message:
            await self.message.edit(
                content="クイズがタイムアウトしちゃったみたい…おつかれさま！", view=None
            )

    async def start_quiz(self):
        if not self.words:
            await self.ctx.send("クイズに出せる単語がないみたい… (´・ω・｀)")
            return
        self.current_index = 0
        question_text = self._get_question_text()
        self.message = await self.ctx.send(content=question_text, view=self)

    def _get_question_text(self):
        word_id, eng_word, meaning = self.words[self.current_index]
        return (
            f"**第 {self.current_index + 1} 問 / 全 {len(self.words)} 問**\n"
            f"英単語: {eng_word}\n"
            "わかるかな？"
        )

    async def _move_to_next(self, interaction: discord.Interaction):
        self.current_index += 1
        if self.current_index < len(self.words):
            question_text = self._get_question_text()
            await interaction.message.edit(content=question_text, view=self)
        else:
            await interaction.message.edit(
                content="クイズ終了！おつかれさま～！", view=None
            )
            self.stop()

    @discord.ui.button(label="⭕️ 分かった", style=discord.ButtonStyle.success, row=0)
    async def know_button(self, interaction: discord.Interaction, button: Button):
        word_id, eng_word, meaning = self.words[self.current_index]
        answer_text = (
            f"**第 {self.current_index + 1} 問の答え**\n"
            f"英単語: {eng_word}\n"
            f"意味: {meaning}\n\n"
            "分かったんだね！クイズ続ける？"
        )
        await interaction.response.edit_message(
            content=answer_text, view=ConfirmContinueView(self.ctx, self)
        )

    @discord.ui.button(label="❌ 分からない", style=discord.ButtonStyle.danger, row=0)
    async def not_know_button(self, interaction: discord.Interaction, button: Button):
        word_id, eng_word, meaning = self.words[self.current_index]
        now_str = datetime.utcnow().isoformat()
        await self.db.execute(
            "UPDATE words SET added_at = ? WHERE id = ?", (now_str, word_id)
        )
        answer_text = (
            f"**第 {self.current_index + 1} 問の答え**\n"
            f"英単語: {eng_word}\n"
            f"意味: {meaning}\n\n"
            "そっか…分からなかったんだね。クイズ続ける？"
        )
        await interaction.response.edit_message(
            content=answer_text, view=ConfirmContinueView(self.ctx, self)
        )

    @discord.ui.button(label="途中でやめる", style=discord.ButtonStyle.secondary, row=1)
    async def stop_quiz(self, interaction: discord.Interaction, button: Button):
        await interaction.response.edit_message(
            content="クイズを中断したよ。おつかれさまー！", view=None
        )
        self.stop()


class ConfirmContinueView(View):
    def __init__(self, ctx, quiz_view: QuizView):
        super().__init__(timeout=None)
        self.ctx = ctx
        self.quiz_view = quiz_view

    @discord.ui.button(label="⭕️ 続ける", style=discord.ButtonStyle.success)
    async def continue_quiz(self, interaction: discord.Interaction, button: Button):
        await interaction.response.edit_message(
            content="次の問題に行くよ～！", view=None
        )
        await self.quiz_view._move_to_next(interaction)

    @discord.ui.button(label="❌ やめる", style=discord.ButtonStyle.danger)
    async def quit_quiz(self, interaction: discord.Interaction, button: Button):
        await interaction.response.edit_message(
            content="クイズをやめるんだね。おつかれさま～！", view=None
        )
        self.quiz_view.stop()


class Quiz(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def quiz(self, ctx):
        """
        ランダムで最大10問出題するクイズ機能。
        """
        db = await Database.get_instance()
        rows = await db.fetchall(
            "SELECT id, word, meaning FROM words WHERE user_id = ? ORDER BY RANDOM() LIMIT 10",
            (ctx.author.id,),
        )
        if not rows:
            await ctx.send("お兄ちゃん、まだ単語登録してないみたい... (・_・;)")
            return

        quiz_view = QuizView(ctx, rows, db)
        await quiz_view.start_quiz()


async def setup(bot):
    await bot.add_cog(Quiz(bot))
