# bot/cogs/reminders.py
from discord.ext import commands, tasks
from bot.utils.database import Database
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timedelta, time
import pytz
import asyncio
import logging
import os

# ログファイルのディレクトリを設定
log_dir = 'logs'
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

# ログファイルの名前を日付で設定
log_file = os.path.join(log_dir, f'bot_{datetime.now().strftime("%Y-%m-%d")}.log')

# ロギングの設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler()  # コンソールにも出力
    ]
)

INTERVALS = [1, 4, 10, 17, 30]


class Reminders(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.setup_complete = False
        self.scheduler = None
        self.db = None  # データベースインスタンスを保持

    async def initialize_database(self):
        """データベース接続を初期化する"""
        try:
            self.db = await Database.get_instance()
            logging.info("Database connection initialized successfully")
            return True
        except Exception as e:
            logging.error(f"Failed to initialize database: {e}")
            return False

    async def initialize_scheduler(self):
        """スケジューラを初期化し、必要なジョブをセットアップする"""
        try:
            # データベース接続を確認
            if not self.db:
                db_initialized = await self.initialize_database()
                if not db_initialized:
                    logging.error("Failed to initialize scheduler: Database connection failed")
                    return False

            if self.scheduler is None:
                self.scheduler = AsyncIOScheduler(timezone=self.bot.JST)
                self.scheduler.start()
                await self.schedule_reminders()
                self.daily_reminder.start()
                self.check_reminders.start()
                logging.info("Scheduler initialized and tasks started")
                return True
        except Exception as e:
            logging.error(f"Error initializing scheduler: {e}")
            return False

    @commands.Cog.listener()
    async def on_ready(self):
        """Botが準備完了した時に呼ばれる"""
        if not self.setup_complete:
            try:
                # データベース初期化を最初に行う
                if await self.initialize_database():
                    #
                    if await self.initialize_scheduler():
                        self.setup_complete = True
                        logging.info("Reminders Cog setup completed successfully")
                    else:
                        logging.error("Failed to complete setup")
            except Exception as e:
                logging.error(f"Error in on_ready: {e}")

    @tasks.loop(time=time(hour=21, minute=0, tzinfo=pytz.timezone("Asia/Tokyo")))
    async def daily_reminder(self):
        try:
            logging.info(f"Starting daily reminder task at {datetime.now(self.bot.JST)}")
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
            logging.error(f"Error in daily_reminder: {e}", exc_info=True)
            # エラー発生時に再試行
            await asyncio.sleep(300)  # 5分待機
            try:
                await self.daily_reminder()
            except Exception as retry_e:
                logging.error(f"Retry failed in daily_reminder: {retry_e}", exc_info=True)

    @daily_reminder.before_loop
    async def before_daily_reminder(self):
        await self.bot.wait_until_ready()
        # 次の実行時刻まで待機
        now = datetime.now(self.bot.JST)
        next_run = now.replace(hour=21, minute=0, second=0, microsecond=0)
        if now.time() >= time(21, 0):
            next_run += timedelta(days=1)
        
        wait_seconds = (next_run - now).total_seconds()
        logging.info(f"Daily reminder will start in {wait_seconds} seconds (at {next_run})")

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
    reminder_cog = Reminders(bot)
    await bot.add_cog(reminder_cog)
    logging.info("Reminders Cog has been added to the bot")
