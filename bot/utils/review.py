import discord
from typing import List, Tuple, Optional
from datetime import datetime
import logging

from .database import Database


class ReviewSession(discord.ui.View):
    """Interactive review for a user's words in DMs.

    Steps through (id, word, meaning) items with buttons to show answer and mark learned.
    """

    def __init__(self, user_id: int, items: List[Tuple[int, str, str]], timeout: Optional[float] = 300):
        super().__init__(timeout=timeout)
        self.user_id = user_id
        self.items = items
        self.index = 0
        self.answer_shown = False
        # Buttons
        self.show_btn = discord.ui.Button(label="答えを表示", style=discord.ButtonStyle.primary)
        self.remembered_btn = discord.ui.Button(label="覚えた", style=discord.ButtonStyle.success)
        self.forgot_btn = discord.ui.Button(label="忘れた", style=discord.ButtonStyle.secondary)
        self.stop_btn = discord.ui.Button(label="終了", style=discord.ButtonStyle.danger)
        self.show_btn.callback = self.on_show
        self.remembered_btn.callback = self.on_remembered
        self.forgot_btn.callback = self.on_forgot
        self.stop_btn.callback = self.on_stop
        self.add_item(self.show_btn)
        self.add_item(self.remembered_btn)
        self.add_item(self.forgot_btn)
        self.add_item(self.stop_btn)
        self._update_button_states()

    def _update_button_states(self):
        self.remembered_btn.disabled = not self.answer_shown
        self.forgot_btn.disabled = not self.answer_shown

    def current_prompt(self) -> str:
        if not self.items:
            return "(復習する単語がないみたい)"
        _id, word, meaning = self.items[self.index]
        if self.answer_shown:
            return f"Q: {word}\nA: {meaning}\n({self.index + 1}/{len(self.items)})"
        else:
            return f"Q: {word}\nA: （タップして表示）\n({self.index + 1}/{len(self.items)})"

    async def on_show(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("これは発行者だけのセッションだよ！", ephemeral=True)
            return
        self.answer_shown = True
        self._update_button_states()
        await interaction.response.edit_message(content=self.current_prompt(), view=self)

    async def on_remembered(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("これは発行者だけのセッションだよ！", ephemeral=True)
            return
        # Mark as learned by setting intervals_remaining='done'
        try:
            _id, _, _ = self.items[self.index]
            db = await Database.get_instance()
            await db.execute("UPDATE words SET intervals_remaining = 'done' WHERE id = ? AND user_id = ?", (_id, self.user_id))
        except Exception as e:
            logging.error(f"Failed to mark learned: {e}")
        # Advance
        self.index += 1
        self.answer_shown = False
        if self.index >= len(self.items):
            for item in self.children:
                if isinstance(item, discord.ui.Button):
                    item.disabled = True
            await interaction.response.edit_message(content="おつかれさま！今日の復習はここまでだよ！", view=self)
            self.stop()
            return
        self._update_button_states()
        await interaction.response.edit_message(content=self.current_prompt(), view=self)

    async def on_forgot(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("これは発行者だけのセッションだよ！", ephemeral=True)
            return
        # Do not change DB; just advance
        self.index += 1
        self.answer_shown = False
        if self.index >= len(self.items):
            for item in self.children:
                if isinstance(item, discord.ui.Button):
                    item.disabled = True
            await interaction.response.edit_message(content="今日はここまで！また一緒にがんばろうね！", view=self)
            self.stop()
            return
        self._update_button_states()
        await interaction.response.edit_message(content=self.current_prompt(), view=self)

    async def on_stop(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("これは発行者だけのセッションだよ！", ephemeral=True)
            return
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        await interaction.response.edit_message(content="また続きやろうね！", view=self)
        self.stop()


class ReminderView(discord.ui.View):
    """View attached to daily reminder message with Start and Snooze."""

    def __init__(self, user_id: int, items: List[Tuple[int, str, str]], tzlabel: str, timeout: Optional[float] = 3600):
        super().__init__(timeout=timeout)
        self.user_id = user_id
        self.items = items
        self.tzlabel = tzlabel
        self.start_btn = discord.ui.Button(label="今すぐ5問だけ復習", style=discord.ButtonStyle.primary)
        self.snooze_btn = discord.ui.Button(label="あとで（1時間後）", style=discord.ButtonStyle.secondary)
        self.start_btn.callback = self.on_start
        self.snooze_btn.callback = self.on_snooze
        self.add_item(self.start_btn)
        self.add_item(self.snooze_btn)

    async def on_start(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("これは発行者だけが使えるよ！", ephemeral=True)
            return
        # Take first 5 items
        subset = self.items[:5]
        view = ReviewSession(self.user_id, subset)
        await interaction.response.send_message("じゃあ、はじめよっか！", ephemeral=True)
        # Send a new message with the first prompt
        await interaction.followup.send(view.current_prompt(), view=view)

    async def on_snooze(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("これは発行者だけが使えるよ！", ephemeral=True)
            return
        await interaction.response.send_message("1時間後にまた声かけるね！", ephemeral=True)
        # Schedule a simple delayed reminder in DM
        async def delayed_send():
            try:
                await discord.utils.sleep_until(datetime.utcnow().replace(microsecond=0) + discord.utils.utcnow().tzinfo.utcoffset(datetime.utcnow()) if False else datetime.utcnow())
            except Exception:
                pass
        # Use create_task with asyncio.sleep for portability
        import asyncio

        async def task():
            try:
                await asyncio.sleep(3600)
                user = interaction.client.get_user(self.user_id)
                if user:
                    channel = user.dm_channel or await user.create_dm()
                    msg = "お兄ちゃん、さっきの続きやろっ！"
                    view = ReminderView(self.user_id, self.items, self.tzlabel)
                    await channel.send(msg, view=view)
            except Exception as e:
                logging.error(f"Snooze send failed: {e}")

        asyncio.create_task(task())

