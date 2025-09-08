import discord
from typing import List, Tuple, Optional
from datetime import datetime
import logging
import random

from .database import Database
from .stats import record_result


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
        self.correct = 0
        self.incorrect = 0
        # Buttons: 1) 意味を見る -> then 覚えた/忘れた
        self.show_btn = discord.ui.Button(label="意味を見る", style=discord.ButtonStyle.primary)
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
        # Disable answer buttons until meaning is shown
        self.remembered_btn.disabled = not self.answer_shown
        self.forgot_btn.disabled = not self.answer_shown

    def current_prompt(self) -> str:
        if not self.items:
            return "(復習する単語がないみたい)"
        _id, word, meaning = self.items[self.index]
        if self.answer_shown:
            return f"Q{self.index + 1}/{len(self.items)}: {word}\n意味: {meaning}"
        return f"Q{self.index + 1}/{len(self.items)}: {word}"

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
            await record_result(_id, True, datetime.utcnow())
        except Exception as e:
            logging.error(f"Failed to mark learned: {e}")
        # Advance (meaning already visible)
        self.correct += 1
        self.index += 1
        self.answer_shown = False
        if self.index >= len(self.items):
            for item in self.children:
                if isinstance(item, discord.ui.Button):
                    item.disabled = True
            total = self.correct + self.incorrect
            rate = int((self.correct / total) * 100) if total else 0
            summary = (
                "おつかれさま！今日の復習はここまでだよ！\n"
                f"・正解: {self.correct} / 不正解: {self.incorrect} / 合計: {total}（正答率 {rate}%）"
            )
            await interaction.response.edit_message(content=summary, view=self)
            self.stop()
            return
        self._update_button_states()
        await interaction.response.edit_message(content=self.current_prompt(), view=self)

    async def on_forgot(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("これは発行者だけのセッションだよ！", ephemeral=True)
            return
        # Do not change DB; just advance
        try:
            _id, _, _ = self.items[self.index]
            await record_result(_id, False, datetime.utcnow())
        except Exception as e:
            logging.error(f"Failed to record incorrect: {e}")
        self.incorrect += 1
        self.index += 1
        self.answer_shown = False
        if self.index >= len(self.items):
            for item in self.children:
                if isinstance(item, discord.ui.Button):
                    item.disabled = True
            total = self.correct + self.incorrect
            rate = int((self.correct / total) * 100) if total else 0
            summary = (
                "今日はここまで！また一緒にがんばろうね！\n"
                f"・正解: {self.correct} / 不正解: {self.incorrect} / 合計: {total}（正答率 {rate}%）"
            )
            await interaction.response.edit_message(content=summary, view=self)
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
        self.start_btn = discord.ui.Button(label="今すぐ全部復習", style=discord.ButtonStyle.primary)
        self.snooze_btn = discord.ui.Button(label="あとで（1時間後）", style=discord.ButtonStyle.secondary)
        self.start_btn.callback = self.on_start
        self.snooze_btn.callback = self.on_snooze
        self.add_item(self.start_btn)
        self.add_item(self.snooze_btn)

    async def on_start(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("これは発行者だけが使えるよ！", ephemeral=True)
            return
        # Start a session with all due items
        view = ReviewSession(self.user_id, self.items)
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


# ----- Text-command quiz session (DM) -----
class QuizState:
    def __init__(self, user_id: int, items: List[Tuple[int, str, str]]):
        self.user_id = user_id
        self.items = items
        self.index = 0
        self.correct = 0
        self.incorrect = 0

    def prompt(self) -> str:
        if not self.items:
            return "（出題する単語がないみたい…）"
        _id, word, _ = self.items[self.index]
        return f"Q{self.index + 1}/{len(self.items)}: {word}\nこの単語、覚えてる？ /覚えた または /忘れた を選んでね！"


_QUIZ_SESSIONS: dict[int, QuizState] = {}


def start_quiz_session(user_id: int, items: List[Tuple[int, str, str]]) -> str:
    _QUIZ_SESSIONS[user_id] = QuizState(user_id, items)
    return _QUIZ_SESSIONS[user_id].prompt()


async def quiz_memorized(user_id: int) -> str:
    st = _QUIZ_SESSIONS.get(user_id)
    if not st or not st.items:
        return "いま進行中のクイズはないみたい。/復習 や /クイズ で始めてね！"
    _id, word, meaning = st.items[st.index]
    try:
        db = await Database.get_instance()
        await db.execute("UPDATE words SET intervals_remaining = 'done' WHERE id = ? AND user_id = ?", (_id, user_id))
        await record_result(_id, True, datetime.utcnow())
    except Exception:
        pass
    st.correct += 1
    st.index += 1
    if st.index >= len(st.items):
        total = st.correct + st.incorrect
        rate = int((st.correct / total) * 100) if total else 0
        del _QUIZ_SESSIONS[user_id]
        return (
            f"正解！『{word}』= {meaning}\n\nおつかれさま！クイズおしまいっ！\n"
            f"・正解: {st.correct} / 不正解: {st.incorrect} / 合計: {total}（正答率 {rate}%）"
        )
    return f"正解！『{word}』= {meaning}\n\n" + st.prompt()


async def quiz_forgot(user_id: int) -> str:
    st = _QUIZ_SESSIONS.get(user_id)
    if not st or not st.items:
        return "いま進行中のクイズはないみたい。/復習 や /クイズ で始めてね！"
    _id, word, meaning = st.items[st.index]
    try:
        await record_result(_id, False, datetime.utcnow())
    except Exception:
        pass
    st.incorrect += 1
    st.index += 1
    if st.index >= len(st.items):
        total = st.correct + st.incorrect
        rate = int((st.correct / total) * 100) if total else 0
        del _QUIZ_SESSIONS[user_id]
        return (
            f"残念… 正解は『{word}』= {meaning} だよ\n\n今日はここまで！また一緒にがんばろうね！\n"
            f"・正解: {st.correct} / 不正解: {st.incorrect} / 合計: {total}（正答率 {rate}%）"
        )
    return f"残念… 正解は『{word}』= {meaning} だよ\n\n" + st.prompt()


def quiz_stop(user_id: int) -> str:
    st = _QUIZ_SESSIONS.pop(user_id, None)
    if not st:
        return "いま進行中のクイズはないみたい。/復習 や /クイズ で始めてね！"
    total = st.correct + st.incorrect
    return (
        "途中で終了したよ！\n"
        f"・正解: {st.correct} / 不正解: {st.incorrect} / 合計: {total}"
    )

class ChoiceQuizSession(discord.ui.View):
    """Multiple-choice quiz from a pool of saved words.

    Presents a word and several meaning options; tracks score and shows summary at end.
    Items are tuples of (id, word, meaning).
    """

    def __init__(self, user_id: int, items: List[Tuple[int, str, str]], count: int = 5, timeout: Optional[float] = 600):
        super().__init__(timeout=timeout)
        self.user_id = user_id
        self.pool = items
        self.count = max(1, min(count, len(items)))
        self.indices = random.sample(range(len(items)), self.count)
        self.q_index = 0
        self.correct = 0
        self.incorrect = 0
        self.options: List[str] = []
        self.cur_id = 0
        self.cur_word = ""
        self.cur_meaning = ""
        self._build_question()

    def _build_question(self):
        self.clear_items()
        # Prepare current question
        idx = self.indices[self.q_index]
        self.cur_id, self.cur_word, self.cur_meaning = self.pool[idx]
        # Determine number of choices (up to 4 if possible)
        max_choices = 4 if len(self.pool) >= 4 else max(2, len(self.pool))
        # Pick distractors
        distractor_indices = [i for i in range(len(self.pool)) if i != idx]
        random.shuffle(distractor_indices)
        distractors = [self.pool[i][2] for i in distractor_indices[: max_choices - 1]]
        options = distractors + [self.cur_meaning]
        random.shuffle(options)
        self.options = options
        # Create buttons and bind callbacks
        for i, label in enumerate(options):
            btn = discord.ui.Button(label=label[:80], style=discord.ButtonStyle.primary)

            def make_cb(choice_idx: int):  # factory to capture choice index
                async def _cb(interaction: discord.Interaction):
                    if interaction.user.id != self.user_id:
                        await interaction.response.send_message("これは発行者だけのセッションだよ！", ephemeral=True)
                        return
                    is_correct = self.options[choice_idx] == self.cur_meaning
                    if is_correct:
                        self.correct += 1
                        feedback = f"正解！『{self.cur_word}』= {self.cur_meaning}"
                    else:
                        self.incorrect += 1
                        feedback = f"残念… 正解は『{self.cur_word}』= {self.cur_meaning} だよ"
                    # Move to next or finish
                    self.q_index += 1
                    if self.q_index >= self.count:
                        for item in self.children:
                            if isinstance(item, discord.ui.Button):
                                item.disabled = True
                        total = self.correct + self.incorrect
                        rate = int((self.correct / total) * 100) if total else 0
                        summary = (
                            f"{feedback}\n\nおつかれさま！クイズおしまいっ！\n"
                            f"・正解: {self.correct} / 不正解: {self.incorrect} / 合計: {total}（正答率 {rate}%）"
                        )
                        await interaction.response.edit_message(content=summary, view=self)
                        self.stop()
                        return
                    # Next question
                    self._build_question()
                    await interaction.response.edit_message(content=self.current_prompt(), view=self)

                return _cb

            btn.callback = make_cb(i)
            self.add_item(btn)

    def current_prompt(self) -> str:
        return (
            f"Q{self.q_index + 1}/{self.count}: 『{self.cur_word}』の意味はどれ？\n"
            "ボタンから答えを選んでね！"
        )
