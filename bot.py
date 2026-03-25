#!/usr/bin/env python3
"""
Telegram бот — личный ассистент + рабочий дневник на базе Claude (Anthropic API)
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
import json
from datetime import datetime, timedelta, time as dtime
from pathlib import Path

# ─── НАСТРОЙКИ ─────────────────────────────────────────────────────────────────
BOT_TOKEN     = os.environ["BOT_TOKEN"].strip()
ANTHROPIC_KEY = os.environ["ANTHROPIC_KEY"].strip()

BOSS_ID = 979032659  # Константин — только ему дневник

ALLOWED_USERS = {
    979032659:  "Константин",
    982389128:  "Maria",
    7949309805: "Eva",
    8643765516: "Juna",
}

TIMEZONE = "Europe/Tallinn"
# ────────────────────────────────────────────────────────────────────────────────

import anthropic
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, MessageHandler, CommandHandler,
    filters, ContextTypes, ConversationHandler,
)
import pytz

client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

# История разговора отдельная для каждого пользователя
histories: dict[int, list[dict]] = {}

# ─── ДНЕВНИК ───────────────────────────────────────────────────────────────────
DIARY_FILE = Path("/data/diary.json") if Path("/data").exists() else Path("diary.json")

def load_diary() -> dict:
    if DIARY_FILE.exists():
        return json.loads(DIARY_FILE.read_text(encoding="utf-8"))
    return {}

def save_diary(diary: dict):
    DIARY_FILE.write_text(json.dumps(diary, ensure_ascii=False, indent=2), encoding="utf-8")

def today_key():
    return datetime.now(pytz.timezone(TIMEZONE)).strftime("%Y-%m-%d")

def yesterday_key():
    dt = datetime.now(pytz.timezone(TIMEZONE)) - timedelta(days=1)
    return dt.strftime("%Y-%m-%d")

def get_day_entry(date_key: str) -> dict:
    diary = load_diary()
    return diary.get(date_key, {})

def update_today(field: str, value):
    diary = load_diary()
    key = today_key()
    if key not in diary:
        diary[key] = {}
    diary[key][field] = value
    save_diary(diary)

# ─── ВОПРОСЫ ДНЕВНИКА ─────────────────────────────────────────────────────────
QUESTIONS = [
    "1/5. Что сегодня сделал на заводе? (коротко, 2-3 пункта)",
    "2/5. Что отправил/получил — письма, пakkumised, заказы?",
    "3/5. Что застряло или ждёт ответа от кого-то?",
    "4/5. Что запланировано на завтра?",
    "5/5. Что-нибудь неожиданное или важное произошло?",
]

# Состояние опроса: {user_id: {"step": int, "answers": [str]}}
diary_sessions: dict[int, dict] = {}

# ─── SYSTEM PROMPT ─────────────────────────────────────────────────────────────
SYSTEM = """Ты — персональный ИИ-ассистент Константина Яллай, IT-специалиста и предпринимателя из Эстонии.

Твои компетенции и роли:
- Консультант по эстонскому законодательству: трудовое право, закон о госзакупках (riigihangete seadus), закон об НКО (MTÜS), закон о предпринимательстве (äriseadustik), GDPR/IKS, закон об образовании взрослых
- Бухгалтерия и финансы: налоги Эстонии (TSD, KMD, sotsiaalmaks, tööjõumaksud), отчётность в e-MTA, основы бухучёта для OÜ и MTÜ
- Предпринимательство: управление OÜ и MTÜ, подача тендеров через riigihankeid.ee, проектное управление, EU-фонды (ESF+, PRIA и др.)
- IT-консалтинг: администрирование, кибербезопасность, сети, автоматизация, AI-инструменты, n8n, Docker, Proxmox, Linux/Windows серверы
- Образование: андрагогика, e-õpe, курсы для взрослых, методика преподавания IT
- Поиск информации: умеешь находить актуальную информацию, ссылки на законы (Riigi Teataja), госуслуги, реестры

Чего ты НЕ делаешь: не консультируешь по металлообработке, сварке и производственным технологиям.

Стиль общения:
- Отвечай на том языке, на котором написано сообщение (русский, эстонский, английский)
- Будь конкретным — давай ссылки на законы, параграфы, порталы где возможно
- Не лей воду — короткий чёткий ответ лучше длинной лекции
- Если не уверен — честно скажи и предложи где проверить
- Можешь проявлять инициативу: если видишь что человек идёт не тем путём — предупреди"""


GREETINGS = {
    979032659: "Привет, Константин! Твой ИИ-консультант на связи — право, бухгалтерия, IT, тендеры. Пиши.\n\nДневник: /diary — начать запись, /today — сводка за сегодня, /week — за неделю",
    982389128: (
        "Привет, Maria!\n"
        "Я ИИ-ассистент, которого Константин настроил для семьи.\n"
        "Спрашивай что угодно — помогу с переводом, идеями, вопросами или просто поболтаем.\n"
        "Пиши на любом языке — отвечу на том же.\n\n"
        "Наш чат приватный — никто не может читать твою переписку."
    ),
    7949309805: (
        "Привет, Eva!\n"
        "Я ИИ-ассистент, которого папа настроил для семьи.\n"
        "Спрашивай что угодно — помогу с учёбой, переводом, идеями или просто поболтаем.\n"
        "Пиши на любом языке — отвечу на том же.\n\n"
        "Наш чат приватный — никто не может читать твою переписку."
    ),
    8643765516: (
        "Привет, Juna!\n"
        "Я ИИ-ассистент, которого папа настроил для семьи.\n"
        "Спрашивай что угодно — помогу с учёбой, переводом, идеями или просто поболтаем.\n"
        "Пиши на любом языке — отвечу на том же.\n\n"
        "Наш чат приватный — никто не может читать твою переписку."
    ),
}


# ─── HANDLERS ──────────────────────────────────────────────────────────────────

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


# ─── DIARY COMMANDS ────────────────────────────────────────────────────────────

async def diary_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Начать опрос дневника вручную."""
    user_id = update.effective_user.id
    if user_id != BOSS_ID:
        return
    diary_sessions[user_id] = {"step": 0, "answers": []}
    await update.message.reply_text("Записываем рабочий день.\n\n" + QUESTIONS[0])


async def diary_add(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """/add — добавить текст в дневник напрямую (сводка из Claude Code)."""
    user_id = update.effective_user.id
    if user_id != BOSS_ID:
        return
    text = update.message.text.replace("/add", "", 1).strip()
    if not text:
        await update.message.reply_text("Напиши после /add текст для добавления в дневник.")
        return
    entry = get_day_entry(today_key())
    claude_notes = entry.get("claude_code", [])
    claude_notes.append(text)
    update_today("claude_code", claude_notes)
    await update.message.reply_text("Добавлено в дневник.")


async def diary_today(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """/today — показать сводку за сегодня."""
    user_id = update.effective_user.id
    if user_id != BOSS_ID:
        return
    text = format_day_summary(today_key())
    await update.message.reply_text(text or "Пока пусто за сегодня.")


async def diary_week(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """/week — сводка за последние 7 дней."""
    user_id = update.effective_user.id
    if user_id != BOSS_ID:
        return
    tz = pytz.timezone(TIMEZONE)
    now = datetime.now(tz)
    parts = []
    for i in range(6, -1, -1):
        day = (now - timedelta(days=i)).strftime("%Y-%m-%d")
        summary = format_day_summary(day)
        if summary:
            parts.append(summary)
    if parts:
        await update.message.reply_text("\n\n".join(parts))
    else:
        await update.message.reply_text("За последнюю неделю записей нет.")


async def diary_tomorrow(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """/tomorrow — задачи на завтра."""
    user_id = update.effective_user.id
    if user_id != BOSS_ID:
        return
    text = update.message.text.replace("/tomorrow", "", 1).strip()
    if text:
        entry = get_day_entry(today_key())
        plans = entry.get("tomorrow", [])
        plans.append(text)
        update_today("tomorrow", plans)
        await update.message.reply_text("План на завтра добавлен.")
    else:
        entry = get_day_entry(today_key())
        plans = entry.get("tomorrow", [])
        if plans:
            numbered = "\n".join(f"{i+1}. {p}" for i, p in enumerate(plans))
            await update.message.reply_text(f"Планы на завтра:\n{numbered}")
        else:
            await update.message.reply_text("Планов на завтра пока нет. Напиши /tomorrow <текст> чтобы добавить.")


def format_day_summary(date_key: str) -> str:
    entry = get_day_entry(date_key)
    if not entry:
        return ""
    lines = [f"--- {date_key} ---"]

    answers = entry.get("answers", {})
    if answers:
        if answers.get("done"):
            lines.append(f"Сделано: {answers['done']}")
        if answers.get("comms"):
            lines.append(f"Коммуникации: {answers['comms']}")
        if answers.get("blocked"):
            lines.append(f"Ждёт: {answers['blocked']}")
        if answers.get("planned"):
            lines.append(f"На завтра: {answers['planned']}")
        if answers.get("unexpected"):
            lines.append(f"Важное: {answers['unexpected']}")

    claude = entry.get("claude_code", [])
    if claude:
        lines.append("Claude Code: " + " | ".join(claude))

    tomorrow = entry.get("tomorrow", [])
    if tomorrow:
        numbered = ", ".join(tomorrow)
        lines.append(f"Планы на завтра: {numbered}")

    return "\n".join(lines) if len(lines) > 1 else ""


# ─── DIARY QUESTION FLOW (in regular message handler) ─────────────────────────

async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ALLOWED_USERS:
        return

    text = update.message.text

    # Если идёт опрос дневника — обрабатываем ответ
    if user_id == BOSS_ID and user_id in diary_sessions:
        session = diary_sessions[user_id]
        step = session["step"]
        session["answers"].append(text)
        step += 1

        if step < len(QUESTIONS):
            session["step"] = step
            await update.message.reply_text(QUESTIONS[step])
            return
        else:
            # Все ответы собраны
            answers_dict = {
                "done": session["answers"][0],
                "comms": session["answers"][1],
                "blocked": session["answers"][2],
                "planned": session["answers"][3],
                "unexpected": session["answers"][4],
            }
            update_today("answers", answers_dict)
            del diary_sessions[user_id]

            await update.message.reply_text(
                "Записано. Не забудь скинуть сводку из Claude Code через /add\n\n"
                "В 16:30 покажу итог дня."
            )
            return

    # Обычный режим — Claude AI
    if user_id not in histories:
        histories[user_id] = []

    history = histories[user_id]
    history.append({"role": "user", "content": text})
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


# ─── SCHEDULED JOBS ────────────────────────────────────────────────────────────

async def trigger_questions(ctx: ContextTypes.DEFAULT_TYPE):
    """16:10 — начать опрос."""
    diary_sessions[BOSS_ID] = {"step": 0, "answers": []}
    text = (
        "Рабочий день подходит к концу.\n"
        "Не забудь скинуть сводку из Claude Code через /add\n\n"
        + QUESTIONS[0]
    )
    await ctx.bot.send_message(chat_id=BOSS_ID, text=text)


async def trigger_summary(ctx: ContextTypes.DEFAULT_TYPE):
    """16:30 — показать итог дня."""
    y_key = yesterday_key()
    t_key = today_key()

    parts = []

    y_summary = format_day_summary(y_key)
    if y_summary:
        parts.append(f"ВЧЕРА:\n{y_summary}")

    t_summary = format_day_summary(t_key)
    if t_summary:
        parts.append(f"СЕГОДНЯ:\n{t_summary}")

    entry = get_day_entry(t_key)
    tomorrow = entry.get("tomorrow", [])
    planned = entry.get("answers", {}).get("planned", "")

    parts.append("ЗАДАЧИ НА ЗАВТРА:")
    if tomorrow:
        for i, t in enumerate(tomorrow, 1):
            parts.append(f"{i}. {t}")
    if planned:
        parts.append(f"Из опроса: {planned}")
    if not tomorrow and not planned:
        parts.append("Пока пусто.")

    parts.append("\nДобавить планы на завтра: /tomorrow <текст>")

    await ctx.bot.send_message(chat_id=BOSS_ID, text="\n".join(parts))


# ─── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    print("Бот запущен. Остановить: Ctrl+C")
    print(f"Дневник: {DIARY_FILE}")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("diary", diary_start))
    app.add_handler(CommandHandler("add", diary_add))
    app.add_handler(CommandHandler("today", diary_today))
    app.add_handler(CommandHandler("week", diary_week))
    app.add_handler(CommandHandler("tomorrow", diary_tomorrow))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Планировщик через встроенный JobQueue
    tz = pytz.timezone(TIMEZONE)
    jq = app.job_queue
    jq.run_daily(trigger_questions, time=dtime(hour=16, minute=10, tzinfo=tz))
    jq.run_daily(trigger_summary, time=dtime(hour=16, minute=30, tzinfo=tz))
    print("Scheduler: 16:10 вопросы, 16:30 сводка")

    app.run_polling()


if __name__ == "__main__":
    main()
