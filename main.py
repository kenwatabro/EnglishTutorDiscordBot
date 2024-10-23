import discord
from discord.ext import commands, tasks
import aiosqlite
from datetime import datetime, timedelta, time
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import pytz
import os
import re
import asyncio
from dotenv import load_dotenv


# 日本時間のタイムゾーン設定
JST = pytz.timezone("Asia/Tokyo")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# デフォルトのhelpコマンドを削除
bot.remove_command("help")

DATABASE = "words.db"

# 忘却曲線のインターバル（日数）
INTERVALS = [1, 4, 10, 17, 30]


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    await setup_database()
    scheduler.start()
    daily_reminder.start()


async def setup_database():
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS words (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                word TEXT,
                meaning TEXT,
                added_at TEXT,
                intervals_remaining TEXT
            )
        """
        )
        await db.commit()


@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if message.content.startswith(bot.command_prefix):
        await bot.process_commands(message)
        return

    if message.mentions and bot.user in message.mentions:
        # メッセージから単語と意味を抽出
        content = message.content.replace(f"<@!{bot.user.id}>", "").strip()
        lines = content.split("\n")
        registered_words = []
        async with aiosqlite.connect(DATABASE) as db:
            for line in lines:
                # 最初の区切り文字で分割し、英単語（熟語）と意味を取得
                match = re.match(r"^(.*?)[:，,、\s]+(.+)$", line)
                if match:
                    english_word = match.group(1).strip()
                    japanese_meaning = match.group(2).strip()
                    added_at = datetime.now(JST).isoformat()
                    intervals_remaining = ",".join(map(str, INTERVALS))
                    await db.execute(
                        """
                        INSERT INTO words (user_id, word, meaning, added_at, intervals_remaining)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            message.author.id,
                            english_word,
                            japanese_meaning,
                            added_at,
                            intervals_remaining,
                        ),
                    )
                    registered_words.append((english_word, japanese_meaning))
            await db.commit()
        
        if registered_words:
            confirmation = f"{message.author.mention} 以下の単語が登録されました：\n"
            for word, meaning in registered_words:
                confirmation += f"**英語:** {word} | **意味:** {meaning}\n"
            await message.channel.send(confirmation)
        else:
            await message.channel.send(f"{message.author.mention} 登録された単語がありませんでした。")

    await bot.process_commands(message)


# スケジューラーの設定
scheduler = AsyncIOScheduler()


def schedule_reminders():
    scheduler.remove_all_jobs()
    asyncio.create_task(schedule_all_reminders())


async def schedule_all_reminders():
    async with aiosqlite.connect(DATABASE) as db:
        async with db.execute(
            "SELECT id, user_id, word, added_at, intervals_remaining FROM words"
        ) as cursor:
            rows = await cursor.fetchall()
            for row in rows:
                word_id, user_id, word, added_at, intervals_remaining = row
                added_time = datetime.fromisoformat(added_at)
                intervals = list(map(int, intervals_remaining.split(",")))
                for interval in intervals:
                    remind_time = added_time + timedelta(days=interval)
                    scheduler.add_job(
                        send_reminder,
                        "date",
                        run_date=remind_time,
                        args=[user_id, word],
                        id=f"{word_id}_{interval}",
                    )


async def send_reminder(user_id, word):
    user = bot.get_user(user_id)
    if user:
        channel = user.dm_channel
        if channel is None:
            channel = await user.create_dm()
        await channel.send(f"覚えている単語を復習しましょう: **{word}**")


# 毎日21時にリマインダーを送信
@tasks.loop(time=time(hour=21, minute=0, tzinfo=JST))
async def daily_reminder():
    async with aiosqlite.connect(DATABASE) as db:
        now = datetime.now(JST)
        for interval in INTERVALS:
            target_date = now - timedelta(days=interval)
            async with db.execute(
                """
                SELECT user_id, word FROM words
                WHERE date(added_at) = date(?)
            """,
                (target_date.isoformat(),),
            ) as cursor:
                rows = await cursor.fetchall()
                if rows:
                    users_words = {}
                    for user_id, word in rows:
                        users_words.setdefault(user_id, []).append(word)
                    for user_id, words in users_words.items():
                        user = bot.get_user(user_id)
                        if user:
                            channel = user.dm_channel
                            if channel is None:
                                channel = await user.create_dm()
                            await channel.send(
                                f"{user.mention} 以下の単語を復習してください:\n"
                                + "\n".join(words)
                            )
    # スケジュールを再設定
    schedule_reminders()


@daily_reminder.before_loop
async def before_daily_reminder():
    await bot.wait_until_ready()


# メッセージが送信されなかった場合の催促
@tasks.loop(time=time(hour=22, minute=0, tzinfo=JST))
async def check_reminders():
    async with aiosqlite.connect(DATABASE) as db:
        now = datetime.now(JST)
        # 21時に送信されたか確認（実装は具体的な送信状況のトラッキングが必要）
        # 簡易的に当日のリマインダーが存在しなかった場合に催促
        # ここでは詳細な実装は省略します
        pass


@check_reminders.before_loop
async def before_check_reminders():
    await bot.wait_until_ready()


# 編集機能の実装
@bot.command()
async def edit(ctx, word_id: int, new_word: str = None, new_meaning: str = None):
    async with aiosqlite.connect(DATABASE) as db:
        async with db.execute(
            "SELECT user_id FROM words WHERE id = ?", (word_id,)
        ) as cursor:
            row = await cursor.fetchone()
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
        await db.commit()
        await ctx.send("単語が更新されました。")


@bot.command()
async def show(ctx):
    async with aiosqlite.connect(DATABASE) as db:
        async with db.execute(
            "SELECT id, word, meaning FROM words WHERE user_id = ?", (ctx.author.id,)
        ) as cursor:
            rows = await cursor.fetchall()
            if rows:
                response = "あなたの登録した単語一覧:\n"
                for row in rows:
                    response += f"ID: {row[0]}, 英語: {row[1]}, 意味: {row[2]}\n"
                await ctx.send(response)
            else:
                await ctx.send("登録された単語がありません。")

@bot.command()
async def delete(ctx, *, english_word: str):
    """
    ユーザーが指定した英単語を自身の辞書から削除します。
    
    使用方法:
    !deleteword <英単語>
    """
    async with aiosqlite.connect(DATABASE) as db:
        # ユーザーIDと英単語で該当するレコードを検索
        async with db.execute(
            "SELECT id, word, meaning FROM words WHERE user_id = ? AND word = ?",
            (ctx.author.id, english_word)
        ) as cursor:
            rows = await cursor.fetchall()
        
        if not rows:
            await ctx.send(f"{ctx.author.mention} 該当する単語が見つかりませんでした。")
            return
        
        # 該当するレコードを削除
        await db.execute(
            "DELETE FROM words WHERE user_id = ? AND word = ?",
            (ctx.author.id, english_word)
        )
        await db.commit()
        
        # 削除した単語の一覧を表示
        deleted_words = "\n".join([f"**英語:** {row[1]} | **意味:** {row[2]}" for row in rows])
        await ctx.send(f"{ctx.author.mention} 以下の単語が削除されました：\n{deleted_words}")

@bot.command()
async def help(ctx):
    help_text = (
        "**コマンド一覧:**\n"
        "`!delete <英単語>` - 指定した英単語を辞書から削除します。\n"
        "`!edit <ID> [新しい英単語] [新しい意味]` - 指定したIDの単語を編集します。\n"
        "`!show` - 自分が登録した単語一覧を表示します。\n"
    )
    await ctx.send(help_text)

# ボットの起動
load_dotenv()
bot.run(os.getenv("DISCORD_BOT_TOKEN"))
