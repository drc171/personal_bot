#!/usr/bin/env python3
"""
Telegram бот — личный ассистент на базе Claude (Anthropic API)
"""

import subprocess, sys

def install(pkg, import_name=None):
    try:
        __import__(import_name or pkg)
    except ImportError:
        print(f"Installing {pkg}...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", pkg, "-q"])

install("anthropic")
install("python-telegram-bot", "telegram")

import os

# ─── НАСТРОЙКИ (задаются через переменные окружения в Railway) ─────────────────
BOT_TOKEN     = os.environ["BOT_TOKEN"].strip()
ANTHROPIC_KEY = os.environ["ANTHROPIC_KEY"].strip()

# Кто может пользоваться ботом (telegram_id)
ALLOWED_USERS = {
    979032659:  "Константин",
    982389128:  "Maria",
    7949309805: "Eva",
    8643765516: "Juna",
}
# ──────────────────────────────────────────────────────────────────────────────

import anthropic
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes

client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

# История разговора отдельная для каждого пользователя
histories: dict[int, list[dict]] = {}

SYSTEM = """Ты — семейный ИИ-ассистент.
Отвечай на том языке, на котором написано сообщение (русский, эстонский или английский).
Будь дружелюбным, конкретным и кратким."""


GREETINGS = {
    979032659: "Привет, Константин! Готов помочь. Пиши что нужно.",
    982389128: (
        "Привет, Maria! 👋\n"
        "Я ИИ-ассистент, которого Константин настроил для семьи.\n"
        "Спрашивай что угодно — помогу с переводом, идеями, вопросами или просто поболтаем.\n"
        "Пиши на любом языке — отвечу на том же.\n\n"
        "🔒 Наш чат приватный — никто из семьи и никакие посторонние люди не могут читать твою переписку."
    ),
    7949309805: (
        "Привет, Eva! 👋\n"
        "Я ИИ-ассистент, которого папа настроил для семьи.\n"
        "Спрашивай что угодно — помогу с учёбой, переводом, идеями или просто поболтаем.\n"
        "Пиши на любом языке — отвечу на том же.\n\n"
        "🔒 Наш чат приватный — никто из семьи и никакие посторонние люди не могут читать твою переписку."
    ),
    8643765516: (
        "Привет, Juna! 👋\n"
        "Я ИИ-ассистент, которого папа настроил для семьи.\n"
        "Спрашивай что угодно — помогу с учёбой, переводом, идеями или просто поболтаем.\n"
        "Пиши на любом языке — отвечу на том же.\n\n"
        "🔒 Наш чат приватный — никто из семьи и никакие посторонние люди не могут читать твою переписку."
    ),
}


async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ALLOWED_USERS:
        return
    await update.message.reply_text(GREETINGS[user_id])


async def reset(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ALLOWED_USERS:
        return
    histories[user_id] = []
    await update.message.reply_text("История очищена. Начинаем заново.")


async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ALLOWED_USERS:
        return

    if user_id not in histories:
        histories[user_id] = []

    history = histories[user_id]
    history.append({"role": "user", "content": update.message.text})
    trimmed = history[-20:]

    await ctx.bot.send_chat_action(update.effective_chat.id, "typing")

    try:
        resp = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=1024,
            system=SYSTEM,
            messages=trimmed,
        )
        reply = resp.content[0].text
    except Exception as e:
        reply = f"Ошибка: {e}"

    history.append({"role": "assistant", "content": reply})
    await update.message.reply_text(reply)


def main():
    print("Бот запущен. Остановить: Ctrl+C")
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()


if __name__ == "__main__":
    main()
