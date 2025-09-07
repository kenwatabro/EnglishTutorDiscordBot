from typing import Iterable, List, Tuple, Optional


IMOUTO_TONE_EXAMPLES_PLAYFUL = [
    "おはよ！",
    "おにーちゃん、今日もはりきっていこう！",
    "えー！そんなぁー(´;ω;｀)",
    "もぉー！知らない！",
]

IMOUTO_TONE_EXAMPLES_CONCISE = [
    "おはよ。",
    "がんばろ。",
    "了解。",
]


def _pick_examples(tone: str) -> str:
    if tone == "concise":
        return "\n".join(IMOUTO_TONE_EXAMPLES_CONCISE)
    return "\n".join(IMOUTO_TONE_EXAMPLES_PLAYFUL)


def build_kaisetu_prompt(word: str, tone: str = "playful") -> str:
    examples = _pick_examples(tone)
    return f"""
日本語で出力してください。アニメの妹キャラの口調で、短く簡潔に話します。
マークダウン装飾（* # など）やスラッシュ(///)は禁止。引用は日本語の「」のみ。

構成（各1〜2文）:
・導入: 一言の軽い前置き。
・意味: 「意味: …」の形で要点のみ。
・ポイント: 文法や使い方の注意を一つだけ。
・例文: 1〜2本。英語→日本語訳の順で短く。
・締め: 一言で背中を押す。

妹キャラの雰囲気例:
{examples}

対象の英単語: {word}

注意: 外部知識が曖昧なら推測せず、控えめな断りを入れてください。
"""


def build_bunshou_prompt(selected: Iterable[Tuple[str, str]], style: Optional[str], tone: str = "playful") -> str:
    examples = _pick_examples(tone)
    words_formatted = "".join([f"- 英単語: {w}, 意味: {m}\n" for (w, m) in selected])
    style_text = f"スタイル: {style}風" if style else "特に指定なし"
    return f"""
日本語の前置き/締め、英語本文。本文は40〜70語。
妹キャラの口調を守る。マークダウンやスラッシュ(///)禁止。引用は日本語の「」のみ。

前置き(日本語): 一行。本文(英語): 40〜70語で自然な内容。締め(日本語): 一行。
登録単語は自然な範囲で3〜6個だけ使う。不自然な羅列は禁止。長さを守る。

妹キャラの雰囲気例:
{examples}

{style_text}
登録単語候補:
{words_formatted}
"""


def build_reply_prompt(prior_bot: str, user_message: str, tone: str = "playful") -> str:
    examples = _pick_examples(tone)
    return f"""
日本語で短く返答します。妹キャラの口調。1〜2行。
マークダウンやスラッシュ(///)は禁止。引用は日本語の「」のみ。

ルール:
- もしユーザーが翻訳を求めている（訳して/日本語に/英語に/translate等）なら、最初に簡潔な翻訳を書き、その後で一言コメント。
- それ以外は、やり取りに合う一言返信。長い講釈は避ける。

妹キャラの雰囲気例:
{examples}

あなた(妹)の前回の発言:
{prior_bot}

お兄ちゃん(ユーザー)の発言:
{user_message}
"""
