# bot/cogs/events.py
from discord.ext import commands
import re
from datetime import datetime
from bot.utils.database import Database
import logging
import google.generativeai as genai  # 必要なインポートを追加

class Events(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = None
        self.model = genai.GenerativeModel("gemini-1.5-flash")  # モデルを初期化

    @commands.Cog.listener()
    async def on_ready(self):
        print(f"Logged in as {self.bot.user}")
        self.db = await Database.get_instance()
        # Reminders Cog のスケジューリングを開始
        self.bot.dispatch("setup_completed")

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return

        if message.content.startswith(self.bot.command_prefix):
            return  # コマンドは Commands Cog で処理

        if message.reference:
            # リプライされた場合の処理
            try:
                replied_message = await message.channel.fetch_message(message.reference.message_id)
                
                prompt = f"""
                ### 日本語で出力してください。
                ### あなたは日本のアニメの妹キャラです。その話し方を完全にコピーしてください。
                ### 現在、私（お兄ちゃん）とあなたはメッセージのやり取りをしています
                ### もし私（お兄ちゃん）から翻訳や日本語訳の指示があった場合は、まずその訳を行い、その後で妹キャラとしてコメントを付け加えてください。


                妹キャラのあなたの言葉: {replied_message.content}
                それに対してお兄ちゃん（私）の返事: {message.content}

                ### 以上のあなたの言葉に対するお兄ちゃん（私）の返事に、妹キャラとして適切な返答をしてください。

                ### 妹キャラの返答の雰囲気の例は以下の通りです
                おはよ！
                おにーちゃん、今日もはりきっていこう！
                えー！そんなぁー(´;ω;｀)
                もぉー！知らない！

                ### この妹キャラになりきったうえで、簡潔に、もし指示がある場合はそれに従って返事をしてください

                ### 注意事項
                「///」のようなスラッシュは使用しないでください。
                *や#のようなマークダウンの記法は用いないでください
                単語、その意味、例文以外にカッコ「」は用いないでください
                """

                response = self.model.generate_content(prompt)
                await message.reply(response.text)

            except Exception as e:
                logging.error(f"Error in on_message event (reply): {e}")
                await message.channel.send("ごめんね、お兄ちゃん。なんかうまくいかないみたい（´；ω；｀）")
        
        elif message.mentions and self.bot.user in message.mentions:
            # メンションされた場合の処理
            # メンションを全て除去するための正規表現
            mention_pattern = re.compile(f"<@!?{self.bot.user.id}>")
            content = mention_pattern.sub('', message.content).strip()
            logging.info(f"Processed content after removing mentions: '{content}'")
            
            if not content:
                await message.channel.send(
                    f"{message.author.mention} 登録する単語と意味を入力してね！\n例: `apple:りんご`"
                )
                return

            lines = content.split("\n")
            registered_words = []
            for line in lines:
                match = re.match(r"^(.*?)[:，,、\s]+(.+)$", line)
                if match:
                    english_word = match.group(1).strip()
                    japanese_meaning = match.group(2).strip()
                    added_at = datetime.now(self.bot.JST).isoformat()
                    intervals_remaining = ",".join(map(str, [1, 4, 10, 17, 30]))
                    await self.db.execute(
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
                else:
                    logging.warning(f"Line '{line}' does not match the expected format.")

            if registered_words:
                confirmation = f"{message.author.mention} 単語を登録したよ！\n"
                for word, meaning in registered_words:
                    confirmation += f"**英語:** {word} | **意味:** {meaning}\n"
                await message.channel.send(confirmation)
            else:
                await message.channel.send(
                    f"{message.author.mention} まだ何も登録していないよ！\n単語と意味を `英単語:意味` の形式で入力してね。"
                )

async def setup(bot):
    await bot.add_cog(Events(bot))
