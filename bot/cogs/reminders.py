# bot/cogs/reminders.py
from discord.ext import commands, tasks
from bot.utils.database import Database
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timedelta, time, timezone
import pytz
import asyncio
import logging
import os
from discord import app_commands
from bot.utils.review import ReminderView

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

    # --- Internal runners for reuse by tasks and test command ---
    async def _run_daily_reminder_once(self):
        logging.info(f"daily_reminder manual run at: {datetime.now(JST)}")
        db = await Database.get_instance()
        now = datetime.now(self.bot.JST)

        all_users_words = {}
        rows = await db.fetchall("SELECT user_id, id, word, meaning, added_at, intervals_remaining FROM words")
        for user_id, word_id, word, meaning, added_at, intervals_remaining in rows:
            try:
                added_time = datetime.fromisoformat(added_at).astimezone(self.bot.JST)
            except Exception:
                # Fallback if timezone conversion fails
                added_time = datetime.fromisoformat(added_at)
            days_passed = (now.date() - added_time.date()).days
            if intervals_remaining == 'done':
                continue
            if days_passed in INTERVALS:
                all_users_words.setdefault(user_id, []).append((word_id, word, meaning))

        users_sent = 0
        total_words = 0
        for user_id, items in all_users_words.items():
            if not items:
                continue
            user = self.bot.get_user(user_id)
            if user:
                channel = user.dm_channel or await user.create_dm()
                preview = [f"・{w}" for (_, w, _) in items[:10]]
                more = "\n…" if len(items) > 10 else ""
                message = f"{user.mention} お兄ちゃん、今日の単語だよ！\n" + "\n".join(preview) + more
                view = ReminderView(user_id, items, str(self.bot.JST))
                await channel.send(message, view=view)
                logging.info(f"Sent daily reminder to user {user_id}: {[w for (_, w, _) in items]}")
                users_sent += 1
                total_words += len(items)
            else:
                logging.warning(f"User {user_id} not found")
        logging.info("Daily reminder run completed")
        return users_sent, total_words

    async def _run_check_reminders_once(self):
        db = await Database.get_instance()
        now = datetime.now(self.bot.JST)
        today = now.date()
        rows = await db.fetchall("SELECT DISTINCT user_id FROM words")
        all_users = {row[0] for row in rows}
        today_rows = await db.fetchall(
            "SELECT DISTINCT user_id FROM words WHERE date(added_at) = date(?)",
            (today.isoformat(),),
        )
        active_users = {row[0] for row in today_rows}
        inactive_users = all_users - active_users
        users_sent = 0
        for user_id in inactive_users:
            user = self.bot.get_user(user_id)
            if user:
                channel = user.dm_channel or await user.create_dm()
                await channel.send(
                    f"{user.mention} お兄ちゃん、今日はまだ単語の登録してないよ！\n"
                    "新しい単語を覚えて、もっと賢くなろうね！ (｀・ω・´)ゞ"
                )
                logging.info(f"Sent reminder to inactive user {user_id}")
                users_sent += 1
            else:
                logging.warning(f"User {user_id} not found")
        logging.info("Inactivity reminder run completed")
        return users_sent

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
            await self._run_daily_reminder_once()
        except Exception as e:
            logging.error(f"Error in daily_reminder: {e}", exc_info=True)
            await asyncio.sleep(300)
            try:
                await self._run_daily_reminder_once()
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
            await self._run_check_reminders_once()
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

    # --- Admin/Test slash command ---
    @app_commands.command(name="test_reminders", description="(Admin) リマインダーを今すぐテスト実行するよ！")
    @app_commands.describe(public="結果をチャンネルに表示する（デフォルトは自分だけ）")
    async def test_reminders(self, interaction, public: bool = False):
        # Restrict to admins in guild; allow in DMs only for the bot owner (optional future)
        if interaction.guild and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("管理者だけが使えるコマンドだよ！", ephemeral=True)
            return
        await interaction.response.defer(thinking=True, ephemeral=not public)
        try:
            daily_users, daily_words = await self._run_daily_reminder_once()
            inactive_users = await self._run_check_reminders_once()
            msg = (
                "リマインダーを実行したよ！\n"
                f"・今日の単語リマインド: {daily_users}人 / 合計{daily_words}語\n"
                f"・未登録ユーザー通知: {inactive_users}人\n"
                "詳しくはログも見てね！"
            )
            await interaction.followup.send(msg, ephemeral=not public)
        except Exception as e:
            logging.error(f"Failed to run test_reminders: {e}", exc_info=True)
            await interaction.followup.send("ごめんね、実行に失敗しちゃった…(>_<)", ephemeral=not public)


async def setup(bot):
    reminder_cog = Reminders(bot)
    await bot.add_cog(reminder_cog)
    logging.info("Reminders Cog has been added to the bot")

    
