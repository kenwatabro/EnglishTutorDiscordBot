# bot/cogs/reminders.py
from discord.ext import commands, tasks
from bot.utils.database import Database
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timedelta, time, timezone
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

INTERVALS = [1, 4, 10, 17, 30, 60]
JST = timezone(timedelta(hours=9))  # タイムゾーンを定義

class Reminders(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = None
        self.scheduler = None
        self.setup_complete = False
        # タスクの状態を追跡
        self.daily_reminder_started = False
        self.check_reminders_started = False  # コメントアウトを解除
        self.startup_time = datetime.now(JST)
        logging.info(f"Bot startup time (JST): {self.startup_time}")
        logging.info("Reminders Cog initialized")

    async def initialize_database(self):
        """データベース接続を初期化する"""
        try:
            self.db = await Database.get_instance()
            # データベース接続が実際に確立されているか確認
            if not self.db or not self.db.db:
                logging.error("Database connection not properly established")
                return False
            logging.info("Database connection initialized successfully")
            return True
        except Exception as e:
            logging.error(f"Failed to initialize database: {e}")
            return False

    async def initialize_scheduler(self):
        """スケジューラを初期化し、必要なジョブをセットアップする"""
        try:
            if not self.db or not self.db.db:
                db_initialized = await self.initialize_database()
                if not db_initialized:
                    logging.error("Failed to initialize scheduler: Database connection failed")
                    return False

            if self.scheduler is None:
                logging.info(f"Initializing scheduler with timezone: {self.bot.JST}")
                self.scheduler = AsyncIOScheduler(timezone=str(self.bot.JST))
                self.scheduler.start()
                
                # タスクが開始されていない場合のみ開始
                if not self.daily_reminder_started:
                    self.daily_reminder.start()
                    self.daily_reminder_started = True
                
                if not self.check_reminders_started:
                    self.check_reminders.start()
                    self.check_reminders_started = True
                
                logging.info("Scheduler initialized and tasks started")
                return True
            
        except Exception as e:
            logging.error(f"Error initializing scheduler: {e}", exc_info=True)
            return False

    @commands.Cog.listener()
    async def on_ready(self):
        """Botが準備完了した時に呼ばれる"""
        if not self.setup_complete:
            try:
                current_time = datetime.now(JST)
                logging.info(f"Bot ready time (JST): {current_time}")
                logging.info("Starting Reminders Cog setup")
                # データベースの初期化を待機
                await asyncio.sleep(2)  # データベース接続が確立するまで少し待機
                
                self.db = await Database.get_instance()
                if not self.db or not self.db.db:  # データベース接続を確認
                    logging.error("Database connection not available")
                    return
                
                if await self.initialize_scheduler():
                    self.setup_complete = True
                    logging.info("Reminders Cog setup completed successfully")
                else:
                    logging.error("Failed to complete setup: Scheduler initialization failed")
            except Exception as e:
                logging.error(f"Error in on_ready: {e}", exc_info=True)

    @tasks.loop(time=time(hour=21, minute=0, tzinfo=JST))
    async def daily_reminder(self):
        """指定の時刻に実行される日次リマインダー"""
        if not self.setup_complete:
            return
        try:
            logging.info(f"daily_reminder が実行されました: {datetime.now(JST)}")
            db = await Database.get_instance()
            now = datetime.now(self.bot.JST)
            
            # ユーザーごとの単語を格納する辞書
            all_users_words = {}
            
            # 当日登録された単語も含めて、全ての単語をチェック
            rows = await db.fetchall(
                "SELECT user_id, word, added_at FROM words"
            )
            
            for user_id, word, added_at in rows:
                added_time = datetime.fromisoformat(added_at).astimezone(self.bot.JST)
                days_passed = (now - added_time).days
                
                # 指定の日数が経過している単語のみを追加
                if days_passed in INTERVALS:
                    all_users_words.setdefault(user_id, []).append(word)
            
            # まとめて送信
            for user_id, words in all_users_words.items():
                if not words:  # 送信する単語がない場合はスキップ
                    continue
                    
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
        """デイリーリマインダーの開始前処理"""
        await self.bot.wait_until_ready()
        logging.info("Daily reminder is about to start.")

    @tasks.loop(time=time(hour=22, minute=0, tzinfo=JST))
    async def check_reminders(self):
        """22:00に実行されるリマインダーチェック - その日に単語登録がないユーザーにメッセージを送信"""
        if not self.setup_complete:
            return
        try:
            db = await Database.get_instance()
            now = datetime.now(self.bot.JST)
            today = now.date()
            
            # 本日の単語登録状況をチェック
            all_users = set()  # すべてのユーザーのセット
            active_users = set()  # 今日単語を登録したユーザーのセット
            
            # すべてのユーザーを取得
            rows = await db.fetchall("SELECT DISTINCT user_id FROM words")
            all_users = {row[0] for row in rows}
            
            # 今日単語を登録したユーザーを取得
            today_rows = await db.fetchall(
                "SELECT DISTINCT user_id FROM words WHERE date(added_at) = date(?)",
                (today.isoformat(),)
            )
            active_users = {row[0] for row in today_rows}
            
            # 今日単語を登録していないユーザーを特定
            inactive_users = all_users - active_users
            
            # 単語を登録していないユーザーにメッセージを送信
            for user_id in inactive_users:
                user = self.bot.get_user(user_id)
                if user:
                    channel = user.dm_channel or await user.create_dm()
                    await channel.send(
                        f"{user.mention} お兄ちゃん、今日はまだ単語の登録してないよ！\n"
                        "新しい単語を覚えて、もっと賢くなろうね！ (｀・ω・´)ゞ"
                    )
                    logging.info(f"Sent reminder to inactive user {user_id}")
                else:
                    logging.warning(f"User {user_id} not found")
                    
        except Exception as e:
            logging.error(f"Error in check_reminders: {e}", exc_info=True)

    @check_reminders.before_loop
    async def before_check_reminders(self):
        """チェックリマインダーの開始前処理"""
        await self.bot.wait_until_ready()
        logging.info("Check reminders is about to start.")

    def cog_unload(self):
        """Cogがアンロードされる時の処理"""
        if self.daily_reminder_started:
            self.daily_reminder.cancel()
        if self.check_reminders_started:
            self.check_reminders.cancel()
        if self.scheduler:
            self.scheduler.shutdown()


async def setup(bot):
    reminder_cog = Reminders(bot)
    await bot.add_cog(reminder_cog)
    logging.info("Reminders Cog has been added to the bot")
