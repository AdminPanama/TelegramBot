import os
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from datetime import datetime

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


# === Команда админа для общей истории ===
async def all_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    all_purchases = context.application.bot_data.get("all_purchases", [])
    if not all_purchases:
        await update.message.reply_text("📜 Общая история пуста.")
        return

    total_confirmed = 0
    text_lines = []
    for entry in all_purchases:
        line = f"{entry['date']} | @{entry['username']} | {entry['amount']}⭐ — {entry['status']}"
        text_lines.append(line)
        if entry["status"] == "✅ подтверждено":
            total_confirmed += entry["amount"]

    text = "📜 Общая история покупок:\n\n" + "\n".join(text_lines)
    text += f"\n\n🌟 Всего подтверждено: {total_confirmed}⭐"

    await update.message.reply_text(text)


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

    elif query.data.startswith("confirm_"):
        user_id = int(query.data.split("_")[1])
        amount = int(query.data.split("_")[2])

        if "history" in context.application.user_data.get(user_id, {}):
            history = context.application.user_data[user_id]["history"]
            for i in range(len(history)):
                if history[i].startswith(f"{amount}⭐ — ⏳"):
                    history[i] = f"{amount}⭐ — ✅ подтверждено"

        # обновляем в общей истории
        all_purchases = context.application.bot_data.get("all_purchases", [])
        for entry in all_purchases:
            if entry["user_id"] == user_id and entry["amount"] == amount and entry["status"] == "⏳ ожидает подтверждения":
                entry["status"] = "✅ подтверждено"

        await query.message.reply_text(f"✅ Оплата пользователя {user_id} подтверждена!")

        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"✅ Ваша оплата {amount}⭐ подтверждена!\nЗвёзды скоро будут начислены 🎉"
            )
        except:
            pass

    elif query.data.startswith("reject_"):
        user_id = int(query.data.split("_")[1])
        amount = int(query.data.split("_")[2])

        if "history" in context.application.user_data.get(user_id, {}):
            history = context.application.user_data[user_id]["history"]
            for i in range(len(history)):
                if history[i].startswith(f"{amount}⭐ — ⏳"):
                    history[i] = f"{amount}⭐ — ❌ отклонено"

        # обновляем в общей истории
        all_purchases = context.application.bot_data.get("all_purchases", [])
        for entry in all_purchases:
            if entry["user_id"] == user_id and entry["amount"] == amount and entry["status"] == "⏳ ожидает подтверждения":
                entry["status"] = "❌ отклонено"

        await query.message.reply_text(f"❌ Оплата пользователя {user_id} отклонена!")

        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"❌ Ваша оплата {amount}⭐ была отклонена.\nЕсли это ошибка — свяжитесь с поддержкой."
            )
        except:
            pass


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

            # 🔥 ВАЖНОЕ СООБЩЕНИЕ
            await update.message.reply_text(
                "⚠️ ВАЖНО!\n\n"
                "После оплаты отправьте сюда:\n"
                "1️⃣ Скриншот перевода\n"
                "2️⃣ Ваш @юзернейм\n"
                "3️⃣ Количество ⭐ звёзд, которые вы оплатили"
            )

            context.user_data["waiting_for_stars"] = False
            context.user_data["last_amount"] = amount  # сохраняем для админа

        except ValueError:
            await update.message.reply_text("❌ Введите корректное число.")


# === Получение скриншота оплаты ===
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo = update.message.photo[-1].file_id
    username = update.message.from_user.username or update.message.from_user.id
    user_id = update.message.from_user.id
    amount = context.user_data.get("last_amount", "❓")

    date = datetime.now().strftime("%Y-%m-%d %H:%M")

    caption = (
        f"📸 Скриншот оплаты\n"
        f"👤 Пользователь: @{username}\n"
        f"⭐ Оплатил: {amount} звёзд\n"
        f"📅 Дата: {date}"
    )

    # Сохраняем покупку в личную историю
    if "history" not in context.user_data:
        context.user_data["history"] = []
    context.user_data["history"].append(f"{amount}⭐ — ⏳ ожидает подтверждения")

    # Сохраняем в общую историю
    if "all_purchases" not in context.application.bot_data:
        context.application.bot_data["all_purchases"] = []
    context.application.bot_data["all_purchases"].append({
        "user_id": user_id,
        "username": username,
        "amount": amount,
        "status": "⏳ ожидает подтверждения",
        "date": date
    })

    # Отправка админу с кнопками
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Подтвердить", callback_data=f"confirm_{user_id}_{amount}"),
        InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{user_id}_{amount}")
    ]])
    await context.bot.send_photo(chat_id=ADMIN_ID, photo=photo, caption=caption, reply_markup=keyboard)

    # Подтверждение пользователю
    await update.message.reply_text("💰 Оплата получена! ✅\nОжидайте проверки администратора.")


# === Если не фото ===
async def handle_other(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("waiting_for_stars"):
        await update.message.reply_text("❌ Пожалуйста, отправь скриншот оплаты или выбери действие в меню.")


# === Основная функция ===
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("all_history", all_history))  # 👈 команда для админа
    app.add_handler(CallbackQueryHandler(menu_handler))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.ALL & ~filters.PHOTO, handle_other))

    app.run_polling(close_loop=False)


if __name__ == "__main__":
    main()
