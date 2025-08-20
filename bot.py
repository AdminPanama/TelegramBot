import os
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


# === Команда /start ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("⭐ Купить звезды", callback_data="buy_stars")],
        [InlineKeyboardButton("📜 История покупок", callback_data="history")]
    ]
    await update.message.reply_text(
        "👋 Добро пожаловать! Выберите действие:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# === Кнопки меню ===
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
        await query.message.reply_text("📜 Ваша история покупок пока пуста.")


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

            price = amount * PRICE_PER_STAR  # цена в TON

            await update.message.reply_text(
                f"💳 За {amount}⭐ нужно оплатить **{price:.4f} TON**\n\n"
                f"Перевод отправляй на кошелек:\n`{TON_WALLET}`\n\n"
                "⚠️ Звезды приходят до 2-х часов (обычно в течение 15 минут).\n"
                "Если не пришли — напиши в поддержку.",
                parse_mode="Markdown"
            )

            context.user_data["waiting_for_stars"] = False

        except ValueError:
            await update.message.reply_text("❌ Введите корректное число.")


# === Получение скриншота оплаты ===
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo = update.message.photo[-1].file_id
    caption = (
        f"📸 Скриншот оплаты от @{update.message.from_user.username or update.message.from_user.id}"
    )

    # Отправка админу
    await context.bot.send_photo(chat_id=ADMIN_ID, photo=photo, caption=caption)

    # Подтверждение пользователю
    await update.message.reply_text("💰 Оплата получена! ✅\nОжидайте поступления звёзд.")


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
