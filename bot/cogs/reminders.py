# bot/cogs/reminders.py
from discord.ext import commands, tasks
from bot.utils.database import Database
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timedelta, time
import pytz
import asyncio
import logging

# ロギングの設定
logging.basicConfig(level=logging.INFO)

INTERVALS = [1, 4, 10, 17, 30]


class Reminders(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.scheduler = AsyncIOScheduler(timezone=self.bot.JST)
        self.scheduler.start()
        # リスナー関数を手動で追加しない
        # self.bot.add_listener(self.setup_completed, "setup_completed")

    @commands.Cog.listener()
    async def setup_completed(self):
        await self.schedule_reminders()
        self.daily_reminder.start()
        self.check_reminders.start()

    @tasks.loop(time=time(hour=21, minute=0, tzinfo=pytz.timezone("Asia/Tokyo")))
    async def daily_reminder(self):
        try:
            logging.info("Starting daily reminder task")
            db = await Database.get_instance()
            now = datetime.now(self.bot.JST)
            for interval in INTERVALS:
                target_date = now - timedelta(days=interval)
                rows = await db.fetchall(
                    "SELECT user_id, word FROM words WHERE date(added_at) = date(?)",
                    (target_date.isoformat(),),
                )
                if rows:
                    users_words = {}
                    for user_id, word in rows:
                        users_words.setdefault(user_id, []).append(word)
                    for user_id, words in users_words.items():
                        user = self.bot.get_user(user_id)
                        if user:
                            channel = user.dm_channel
                            if channel is None:
                                channel = await user.create_dm()
                            message = f"{user.mention} お兄ちゃん、今日の単語だよ！\n" + "\n".join(words)
                            await channel.send(message)
                            logging.info(f"Sent daily reminder to user {user_id}: {words}")
                        else:
                            logging.warning(f"User {user_id} not found")
            await self.schedule_reminders()
            logging.info("Daily reminder task completed")
        except Exception as e:
            logging.error(f"Error in daily_reminder: {e}")

    @daily_reminder.before_loop
    async def before_daily_reminder(self):
        await self.bot.wait_until_ready()
        logging.info("Bot is ready, daily_reminder can now start")

    @tasks.loop(time=time(hour=22, minute=0, tzinfo=pytz.timezone("Asia/Tokyo")))
    async def check_reminders(self):
        try:
            db = await Database.get_instance()
            now = datetime.now(self.bot.JST)
            today = now.date()
            
            # 本日の21時に送信されるべきだった単語を取得
            for interval in INTERVALS:
                target_date = today - timedelta(days=interval)
                expected_words = await db.fetchall(
                    "SELECT user_id, word FROM words WHERE date(added_at) = date(?)",
                    (target_date.isoformat(),)
                )
                
                if expected_words:
                    for user_id, word in expected_words:
                        user = self.bot.get_user(user_id)
                        if user:
                            channel = user.dm_channel or await user.create_dm()
                            
                            # 過去1時間のメッセージをチェック
                            async for message in channel.history(
                                limit=100,
                                after=datetime.now(self.bot.JST) - timedelta(hours=1)
                            ):
                                # botからのメッセージで、該当の単語が含まれているかチェック
                                if message.author == self.bot.user and word in message.content:
                                    break
                            else:  # 単語が見つからなかった場合
                                # 再送信
                                await channel.send(
                                    f"{user.mention} ごめんね、さっきの単語をもう一度送るね！\n"
                                    f"**{word}**"
                                )
                                logging.info(f"Resent reminder for word '{word}' to user {user_id}")
                                
        except Exception as e:
            logging.error(f"Error in check_reminders: {e}")

    @check_reminders.before_loop
    async def before_check_reminders(self):
        await self.bot.wait_until_ready()

    async def schedule_reminders(self):
        db = await Database.get_instance()
        rows = await db.fetchall(
            "SELECT id, user_id, word, added_at, intervals_remaining FROM words"
        )
        for row in rows:
            word_id, user_id, word, added_at, intervals_remaining = row
            added_time = datetime.fromisoformat(added_at).astimezone(self.bot.JST)
            intervals = list(map(int, intervals_remaining.split(",")))
            for interval in intervals:
                remind_time = added_time + timedelta(days=interval)
                if remind_time > datetime.now(self.bot.JST):
                    job_id = f"{word_id}_{interval}"
                    if not self.scheduler.get_job(job_id):
                        self.scheduler.add_job(
                            self.send_reminder,
                            "date",
                            run_date=remind_time,
                            args=[user_id, word],
                            id=job_id,
                        )

    async def send_reminder(self, user_id, word):
        try:
            user = self.bot.get_user(user_id)
            if user:
                channel = user.dm_channel
                if channel is None:
                    channel = await user.create_dm()
                await channel.send(f"復習の時間だー！: **{word}**")
        except Exception as e:
            logging.error(f"Error sending reminder to user {user_id}: {e}")


async def setup(bot):
    await bot.add_cog(Reminders(bot))
