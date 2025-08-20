import os
import random
import string
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

# ====================
# Настройки из Render Environment
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
TON_WALLET = os.getenv("TON_WALLET")

if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN не задан в переменных окружения")
if not ADMIN_ID:
    raise ValueError("❌ ADMIN_ID не задан в переменных окружения")
if not TON_WALLET:
    raise ValueError("❌ TON_WALLET не задан в переменных окружения")

ADMIN_ID = int(ADMIN_ID)
# ====================

PRICE_PER_STAR = 0.00475  # Цена за 1 звезду в TON
MIN_STARS = 50
MAX_STARS = 10000

# === Фразы для шутливого режима ===
JOKES = [
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

# === Генерация ID заявки ===
def generate_tx_id():
    return ''.join(random.choices(string.digits, k=6))  # например: 384920


# === Команда /start ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("⭐ Купить звезды", callback_data="buy_stars")],
        [InlineKeyboardButton("📜 История покупок", callback_data="history")],
        [InlineKeyboardButton("😂 Купить без денег", callback_data="fake_buy")]
    ]
    await update.message.reply_text(
        "👋 Добро пожаловать! Выберите действие:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# === Кнопки меню и обработка админских действий ===
async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "buy_stars":
        await query.message.reply_text(
            f"⭐ Минимальное количество звёзд: {MIN_STARS}\n"
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
        joke = random.choice(JOKES)
        keyboard = [[InlineKeyboardButton("🏠 Вернуться в меню", callback_data="main_menu")]]
        await query.message.reply_text(
            joke,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif query.data.startswith("confirm_"):
        tx_id = query.data.split("_")[1]

        for user_id, data in context.application.user_data.items():
            if isinstance(data, dict) and "history" in data:
                for i, record in enumerate(data["history"]):
                    if f"#{tx_id}" in record and "⏳" in record:
                        data["history"][i] = record.replace("⏳ ожидает подтверждения", "✅ подтверждено")

                        keyboard = [[InlineKeyboardButton("🏠 Вернуться в меню", callback_data="main_menu")]]
                        await context.bot.send_message(
                            chat_id=user_id,
                            text=f"✅ Ваша заявка #{tx_id} подтверждена!\nЗвёзды скоро будут начислены 🎉",
                            reply_markup=InlineKeyboardMarkup(keyboard)
                        )

                        await query.message.reply_text(f"✅ Оплата по заявке #{tx_id} подтверждена!")
                        return

    elif query.data.startswith("reject_"):
        tx_id = query.data.split("_")[1]

        for user_id, data in context.application.user_data.items():
            if isinstance(data, dict) and "history" in data:
                for i, record in enumerate(data["history"]):
                    if f"#{tx_id}" in record and "⏳" in record:
                        data["history"][i] = record.replace("⏳ ожидает подтверждения", "❌ отклонено")

                        keyboard = [[InlineKeyboardButton("🏠 Вернуться в меню", callback_data="main_menu")]]
                        await context.bot.send_message(
                            chat_id=user_id,
                            text=f"❌ Ваша заявка #{tx_id} была отклонена.\nЕсли это ошибка — свяжитесь с поддержкой.",
                            reply_markup=InlineKeyboardMarkup(keyboard)
                        )

                        await query.message.reply_text(f"❌ Оплата по заявке #{tx_id} отклонена!")
                        return

    elif query.data == "main_menu":
        keyboard = [
            [InlineKeyboardButton("⭐ Купить звезды", callback_data="buy_stars")],
            [InlineKeyboardButton("📜 История покупок", callback_data="history")],
            [InlineKeyboardButton("😂 Купить без денег", callback_data="fake_buy")]
        ]
        await query.message.reply_text("🏠 Главное меню:", reply_markup=InlineKeyboardMarkup(keyboard))


# === Ввод количества звёзд ===
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("waiting_for_stars"):
        try:
            amount = int(update.message.text)
            if amount < MIN_STARS:
                await update.message.reply_text(f"❌ Минимум {MIN_STARS}⭐")
                return
            if amount > MAX_STARS:
                await update.message.reply_text(f"❌ Максимум {MAX_STARS}⭐")
                return

            price = amount * PRICE_PER_STAR

            await update.message.reply_text(
                f"💳 За {amount}⭐ нужно оплатить <b>{price:.4f} TON</b>\n\n"
                f"Перевод отправляй на кошелек:\n<code>{TON_WALLET}</code>\n\n"
                "⚠️ Звезды приходят до 2-х часов (обычно в течение 15 минут).\n"
                "Если не пришли — напиши в поддержку.",
                parse_mode="HTML"
            )

            await update.message.reply_text(
                "⚠️ ВАЖНО!\n\n"
                "После оплаты отправьте сюда:\n"
                "1️⃣ Скриншот перевода\n"
                "2️⃣ Ваш @юзернейм\n"
                "3️⃣ Количество ⭐ звёзд, которые вы оплатили"
            )

            context.user_data["waiting_for_stars"] = False
            context.user_data["last_amount"] = amount

        except ValueError:
            await update.message.reply_text("❌ Введите корректное число.")


# === Получение скриншота оплаты ===
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo = update.message.photo[-1].file_id
    user = update.message.from_user
    username = f"@{user.username}" if user.username else f"ID:{user.id}"
    user_id = user.id
    amount = context.user_data.get("last_amount", "❓")

    tx_id = generate_tx_id()

    caption = (
        f"💰 Новая оплата!\n"
        f"📌 Заявка: #{tx_id}\n"
        f"👤 Пользователь: {username}\n"
        f"⭐ Оплатил: {amount} звёзд\n"
        f"⏳ Статус: ожидает подтверждения"
    )

    if "history" not in context.user_data:
        context.user_data["history"] = []
    context.user_data["history"].append(f"[Заявка #{tx_id}] {amount}⭐ — ⏳ ожидает подтверждения")

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Подтвердить", callback_data=f"confirm_{tx_id}"),
        InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{tx_id}")
    ]])
    await context.bot.send_photo(chat_id=ADMIN_ID, photo=photo, caption=caption, reply_markup=keyboard)

    await update.message.reply_text(
        f"💰 Оплата получена! ✅\nВаша заявка #{tx_id} зарегистрирована.\nОжидайте проверки администратора."
    )


# === Если не фото ===
async def handle_other(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("waiting_for_stars"):
        await update.message.reply_text("❌ Пожалуйста, отправь скриншот оплаты или выбери действие в меню.")


# === Основная функция ===
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(menu_handler))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.ALL & ~filters.PHOTO, handle_other))

    app.run_polling(close_loop=False)


if __name__ == "__main__":
    main()
