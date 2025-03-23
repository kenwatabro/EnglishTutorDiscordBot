# bot/main.py
import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
import pytz
import asyncio
import logging

# ロギングの設定
logging.basicConfig(level=logging.INFO)

# 環境変数のロード
load_dotenv()
TOKEN = os.getenv("DISCORD_BOT_TOKEN")

# 日本時間のタイムゾーン設定
JST = pytz.timezone("Asia/Tokyo")

# Intentsの設定
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

# Botの初期化
bot = commands.Bot(command_prefix="!", intents=intents)


async def main():
    try:
        logging.info("Starting bot initialization")
        # デフォルトのhelpコマンドを削除
        bot.remove_command("help")
        logging.info("Removed default help command")

        # Botにタイムゾーンを設定として追加
        bot.JST = JST
        logging.info("Set JST timezone")

        # Cog のロード
        logging.info("Loading extensions...")
        await bot.load_extension("bot.cogs.events")
        await bot.load_extension("bot.cogs.commands")
        await bot.load_extension("bot.cogs.quiz")
        await bot.load_extension("bot.cogs.reminders")
        logging.info("All extensions loaded successfully")

        # Botの起動
        logging.info("Starting bot...")
        await bot.start(TOKEN)
    except Exception as e:
        logging.error(f"Error during bot initialization: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
