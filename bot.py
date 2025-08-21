import os
import logging
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters
)

# ==================== #
# Логирование
# ==================== #
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==================== #
# Настройки
# ==================== #
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

DB_PATH = "bot.db"
REF_PERCENT = 0.01  # 1% бонус от покупок рефералов

# ==================== #
# Работа с БД
# ==================== #
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # пользователи
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY,
        username TEXT,
        balance REAL DEFAULT 0,
        invited_by INTEGER,
        ref_balance REAL DEFAULT 0,
        total_ref_earned REAL DEFAULT 0
    )""")

    # заказы
    c.execute("""CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        amount REAL,
        status TEXT
    )""")

    conn.commit()
    conn.close()

def add_user(user_id, username, invited_by=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE id=?", (user_id,))
    if not c.fetchone():
        c.execute("INSERT INTO users (id, username, invited_by) VALUES (?, ?, ?)",
                  (user_id, username, invited_by))
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return {
            "id": row[0],
            "username": row[1],
            "balance": row[2],
            "invited_by": row[3],
            "ref_balance": row[4],
            "total_ref_earned": row[5]
        }
    return None

def update_balance(user_id, amount):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET balance = balance + ? WHERE id=?", (amount, user_id))
    conn.commit()
    conn.close()

def add_ref_bonus(user_id, bonus):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""UPDATE users 
                 SET ref_balance = ref_balance + ?, 
                     total_ref_earned = total_ref_earned + ? 
                 WHERE id=?""", (bonus, bonus, user_id))
    conn.commit()
    conn.close()

def add_order(user_id, amount):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO orders (user_id, amount, status) VALUES (?, ?, ?)",
              (user_id, amount, "⏳ Ожидание"))
    conn.commit()
    conn.close()
    return c.lastrowid

def update_order_status(order_id, status):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE orders SET status=? WHERE id=?", (status, order_id))
    conn.commit()
    conn.close()

# ==================== #
# Команды
# ==================== #
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ref_id = None

    # проверяем, есть ли рефка
    if context.args:
        try:
            ref_id = int(context.args[0])
        except ValueError:
            pass

    add_user(user.id, user.username, ref_id)

    keyboard = [
        [InlineKeyboardButton("⭐ Купить звёзды", callback_data="buy_stars")],
        [InlineKeyboardButton("🤝 Партнёрская программа", callback_data="ref_system")],
        [InlineKeyboardButton("🆘 Помощь", callback_data="help")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "Привет! 👋\n\n"
        "Это бот для покупки звёзд ⭐.\n"
        "Выберите действие:",
        reply_markup=reply_markup
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("ℹ️ Напишите админу для помощи.")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text("⛔ Команда доступна только админу")

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    users_count = c.fetchone()[0]
    conn.close()

    await update.message.reply_text(f"📊 Всего пользователей: {users_count}")

# ==================== #
# Кнопки
# ==================== #
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id

    if query.data == "buy_stars":
        await query.edit_message_text("💳 Отправьте сумму перевода (в звёздах).")
        context.user_data["awaiting_payment"] = True

    elif query.data == "ref_system":
        user = get_user(user_id)
        ref_link = f"https://t.me/{context.bot.username}?start={user_id}"
        await query.edit_message_text(
            f"🤝 Ваша реферальная ссылка:\n{ref_link}\n\n"
            f"💰 Текущий реферальный баланс: {user['ref_balance']:.2f} ⭐\n"
            f"🌟 Всего заработано: {user['total_ref_earned']:.2f} ⭐\n\n"
            "⚡ Вывод бонусов будет доступен скоро.\n"
            "Продолжайте приглашать друзей! 🚀"
        )

    elif query.data == "help":
        await query.edit_message_text("📩 Свяжитесь с админом для помощи.")

    elif query.data.startswith("confirm_"):
        _, user_id, order_id, amount = query.data.split("_")
        user_id, order_id, amount = int(user_id), int(order_id), float(amount)

        update_order_status(order_id, "✅ Подтверждено")
        update_balance(user_id, amount)

        # начисляем реф бонус
        user = get_user(user_id)
        if user and user["invited_by"]:
            bonus = amount * REF_PERCENT
            add_ref_bonus(user["invited_by"], bonus)

        await query.edit_message_text(f"✅ Заказ {order_id} подтверждён. Пользователю начислено {amount} ⭐.")

    elif query.data.startswith("reject_"):
        _, user_id, order_id = query.data.split("_")
        order_id = int(order_id)
        update_order_status(order_id, "❌ Отклонено")
        await query.edit_message_text(f"❌ Заказ {order_id} отклонён.")

# ==================== #
# Обработка сообщений
# ==================== #
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    # если ждём оплату
    if context.user_data.get("awaiting_payment"):
        try:
            amount = float(text)
        except ValueError:
            return await update.message.reply_text("Введите число (количество звёзд).")

        order_id = add_order(user_id, amount)
        context.user_data["awaiting_payment"] = False

        # уведомляем админа
        keyboard = [
            [
                InlineKeyboardButton("✅ Подтвердить", callback_data=f"confirm_{user_id}_{order_id}_{amount}"),
                InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{user_id}_{order_id}")
            ]
        ]
        markup = InlineKeyboardMarkup(keyboard)

        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"📩 Новый заказ #{order_id}\n"
                 f"Пользователь: {user_id}\n"
                 f"Сумма: {amount} ⭐",
            reply_markup=markup
        )

        await update.message.reply_text("🕐 Заказ отправлен на проверку. Ожидайте подтверждения.")
    else:
        await update.message.reply_text("Не понял сообщение. Используйте меню.")


# ==================== #
# Запуск
# ==================== #
def main():
    init_db()
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("stats", stats))

    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    application.run_polling()

if __name__ == "__main__":
    main()
