import os
import random
import string
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

# ====================
# Настройки из Render Environment
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
TON_WALLET = os.getenv("TON_WALLET")
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME")  # имя канала без @

if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN не задан в переменных окружения")
if not ADMIN_ID:
    raise ValueError("❌ ADMIN_ID не задан в переменных окружения")
if not TON_WALLET:
    raise ValueError("❌ TON_WALLET не задан в переменных окружения")
if not CHANNEL_USERNAME:
    raise ValueError("❌ CHANNEL_USERNAME не задан в переменных окружения")

ADMIN_ID = int(ADMIN_ID)
# ====================

PRICE_PER_STAR = 0.00475  # Цена за 1 звезду в TON
MIN_STARS = 50
MAX_STARS = 10000

USERS = set()
TOTAL_ORDERS = 0

# === Генерация ID заявки ===
def generate_tx_id():
    return ''.join(random.choices(string.digits, k=6))

# === Команда /start ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    USERS.add(user_id)

    keyboard = [
        [InlineKeyboardButton("📢 Подписаться на канал", url=f"https://t.me/{CHANNEL_USERNAME}")],
        [InlineKeyboardButton("✅ Продолжить", callback_data="continue_menu")]
    ]
    await update.message.reply_text(
        f"👋 Добро пожаловать!\n\n"
        f"Чтобы пользоваться ботом, подпишитесь на наш канал 👉 @{CHANNEL_USERNAME}\n"
        f"После этого нажмите «Продолжить».",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# === Главное меню ===
def main_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⭐ Купить звезды", callback_data="buy_stars")],
        [InlineKeyboardButton("📜 История покупок", callback_data="history")],
        [InlineKeyboardButton("😂 Купить без денег", callback_data="fake_buy")]
    ])

# === Обработка меню ===
async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "continue_menu":
        await query.message.reply_text("🏠 Главное меню:", reply_markup=main_menu_keyboard())

    elif query.data == "buy_stars":
        await query.message.reply_text(
            f"⭐ Минимальное количество: {MIN_STARS}\n"
            f"⭐ Максимальное количество: {MAX_STARS}\n"
            f"💰 Цена за 1 звезду: {PRICE_PER_STAR} TON\n\n"
            "Введите количество звёзд, которое хотите купить:"
        )
        context.user_data["waiting_for_stars"] = True

    elif query.data == "history":
        history = context.user_data.get("history", [])
        if history:
            text = "📜 Ваша история покупок:\n\n" + "\n".join(history)
        else:
            text = "📜 Ваша история покупок пока пуста."
        await query.message.reply_text(text)

    elif query.data == "fake_buy":
        phrases = [
            "🚫 Нет денег — нет конфетки 🍭",
            "🤗 Всё ещё впереди! Иди работай 💼",
            "🥲 Халявы нет, брат… только работа и TON 💎",
            "🐒 Обезьяна тоже хотела бесплатно, но пошла бананы собирать 🍌",
            "🕺 Звёзды без денег? Это не астрономия, дружище 🌌",
            "😎 Работай, плати — получай звёзды. Всё просто 🚀",
            "🏚️ В кредит звёзды не выдаём, сорри 💳",
            "🤡 Ага, щас! Бесплатно только сыр… и то в мышеловке 🧀",
            "🧘 Терпение, молодец. Денег нет — значит время копить 🙏",
            "🪙 TON не растут на деревьях, их майнят 💻"
        ]
        keyboard = [[InlineKeyboardButton("🏠 Вернуться в меню", callback_data="continue_menu")]]
        await query.message.reply_text(random.choice(phrases), reply_markup=InlineKeyboardMarkup(keyboard))

# === Обработка текста (ввод кол-ва звёзд) ===
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("waiting_for_stars"):
        try:
            stars = int(update.message.text)
            if stars < MIN_STARS or stars > MAX_STARS:
                await update.message.reply_text(
                    f"❌ Введите число от {MIN_STARS} до {MAX_STARS}."
                )
                return

            amount_ton = stars * PRICE_PER_STAR
            tx_id = generate_tx_id()
            context.user_data["waiting_for_stars"] = False

            text = (
                f"💰 Заявка №{tx_id}\n"
                f"⭐ Кол-во звёзд: {stars}\n"
                f"💎 Сумма: {amount_ton:.2f} TON\n\n"
                f"🔗 Отправьте {amount_ton:.2f} TON на кошелёк:\n"
                f"`{TON_WALLET}`\n\n"
                "📸 После перевода отправьте скриншот!"
            )
            await update.message.reply_text(text, parse_mode="Markdown")

            context.user_data["pending_order"] = {
                "id": tx_id,
                "stars": stars,
                "amount": amount_ton,
                "status": "Ожидает подтверждения"
            }

        except ValueError:
            await update.message.reply_text("❌ Введите корректное число.")

# === Обработка фото (скриншот) ===
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "pending_order" in context.user_data:
        order = context.user_data["pending_order"]

        keyboard = [
            [
                InlineKeyboardButton("✅ Подтвердить", callback_data=f"confirm_{update.message.from_user.id}_{order['id']}"),
                InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{update.message.from_user.id}_{order['id']}")
            ]
        ]

        await context.bot.send_message(
            ADMIN_ID,
            f"💰 Новая оплата!\n"
            f"👤 Пользователь: @{update.message.from_user.username}\n"
            f"⭐ Кол-во звёзд: {order['stars']}\n"
            f"💎 Сумма: {order['amount']:.2f} TON\n"
            f"🆔 Заявка №{order['id']}\n"
            f"⏳ Статус: Ожидает подтверждения",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

        await update.message.reply_text(
            "📤 Скриншот получен! Ожидайте подтверждения администратора."
        )

# === Админ подтверждает/отклоняет ===
async def admin_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data.startswith("confirm_"):
        _, user_id, tx_id = query.data.split("_")
        user_id = int(user_id)

        order = context.user_data.get("pending_order")
        if order and order["id"] == tx_id:
            order["status"] = "✅ Подтверждено"
            context.user_data.setdefault("history", []).append(
                f"⭐ {order['stars']} | {order['amount']:.2f} TON | ✅ Подтверждено"
            )

            await context.bot.send_message(
                user_id,
                f"✅ Оплата подтверждена!\n"
                f"⭐ Вам начислено {order['stars']} звёзд.\n"
                f"🆔 Заявка №{order['id']}"
            )
            await query.message.reply_text("✅ Оплата подтверждена.")

    elif query.data.startswith("reject_"):
        _, user_id, tx_id = query.data.split("_")
        user_id = int(user_id)

        order = context.user_data.get("pending_order")
        if order and order["id"] == tx_id:
            order["status"] = "❌ Отклонено"
            context.user_data.setdefault("history", []).append(
                f"⭐ {order['stars']} | {order['amount']:.2f} TON | ❌ Отклонено"
            )

            await context.bot.send_message(
                user_id,
                f"❌ Оплата отклонена.\n"
                f"🆔 Заявка №{order['id']}"
            )
            await query.message.reply_text("❌ Оплата отклонена.")

# === Команда /stats для админа ===
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id == ADMIN_ID:
        await update.message.reply_text(
            f"📊 Статистика:\n"
            f"👥 Пользователей: {len(USERS)}\n"
            f"🛒 Заявок: {TOTAL_ORDERS}"
        )

# === Основной запуск ===
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CallbackQueryHandler(admin_handler, pattern="^(confirm_|reject_)"))
    app.add_handler(CallbackQueryHandler(menu_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    app.run_polling()

if __name__ == "__main__":
    main()
