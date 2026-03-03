import os
import random
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

TOKEN = os.getenv("TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

# --- Инициализация базы данных ---
conn = sqlite3.connect("database.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS words (
    word TEXT PRIMARY KEY,
    guessed_by TEXT
)
""")
conn.commit()

# --- Загружаем слова ---
with open("words.txt", "r", encoding="utf-8") as f:
    words_list = [w.strip().lower() for w in f.readlines()]

# Заполняем таблицу слов, если пусто
for w in words_list:
    cursor.execute("INSERT OR IGNORE INTO words(word, guessed_by) VALUES (?, ?)", (w, None))
conn.commit()


# --- Команды ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    username = update.message.from_user.username or update.message.from_user.first_name
    cursor.execute("INSERT OR IGNORE INTO users(user_id, username) VALUES (?, ?)", (user_id, username))
    conn.commit()
    await update.message.reply_text(
        "Привет! Я загадал слово. Попробуй угадать! 🔤"
    )

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cursor.execute("SELECT COUNT(*) FROM words WHERE guessed_by = ?", (update.message.from_user.username,))
    count = cursor.fetchone()[0]
    await update.message.reply_text(f"Ты угадал {count} слов(а)! 🎉")


# --- Проверка сообщений ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_guess = update.message.text.lower()
    username = update.message.from_user.username or update.message.from_user.first_name

    cursor.execute("SELECT guessed_by FROM words WHERE word = ?", (user_guess,))
    result = cursor.fetchone()

    if result:
        guessed_by = result[0]
        if guessed_by:
            await update.message.reply_text(f"⚠️ Слово уже отгадано пользователем @{guessed_by}")
        else:
            # Помечаем слово как отгаданное
            cursor.execute("UPDATE words SET guessed_by = ? WHERE word = ?", (username, user_guess))
            conn.commit()

            await update.message.reply_text("🎉 Поздравляю! Ты угадал слово!")

            # Уведомляем админа
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"Пользователь @{username} угадал слово: {user_guess}"
            )

            # Уведомляем всех других пользователей
            cursor.execute("SELECT user_id FROM users WHERE user_id != ?", (update.message.from_user.id,))
            for user_id in cursor.fetchall():
                try:
                    await context.bot.send_message(user_id[0], f"⚡ Слово '{user_guess}' уже было угадано!")
                except:
                    pass
    else:
        await update.message.reply_text("❌ Неправильно. Попробуй ещё!")

# --- Панель админа ---
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        return
    keyboard = [
        [InlineKeyboardButton("Показать все слова", callback_data="show_words")],
        [InlineKeyboardButton("Сбросить слова", callback_data="reset_words")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Панель администратора:", reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != ADMIN_ID:
        return

    if query.data == "show_words":
        cursor.execute("SELECT word, guessed_by FROM words")
        text = "\n".join([f"{w} — {g if g else 'не отгадано'}" for w, g in cursor.fetchall()])
        await query.edit_message_text(f"Слова:\n{text}")

    elif query.data == "reset_words":
        cursor.execute("UPDATE words SET guessed_by = NULL")
        conn.commit()
        await query.edit_message_text("✅ Все слова сброшены и могут быть отгаданы заново.")


# --- Запуск бота ---
app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("stats", stats))
app.add_handler(CommandHandler("admin", admin_panel))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
app.add_handler(CallbackQueryHandler(button_handler))

app.run_polling()