import os
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"👋 Привет! Чтобы оплатить услугу, отправь скриншот перевода на кошелек:\n\n`{TON_WALLET}`",
        parse_mode="Markdown"
    )

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка присланного скриншота"""
    photo = update.message.photo[-1].file_id
    caption = f"📸 Скриншот платежа от @{update.message.from_user.username or update.message.from_user.id}"
    await context.bot.send_photo(chat_id=ADMIN_ID, photo=photo, caption=caption)
    await update.message.reply_text("✅ Скриншот получен, ожидай подтверждения.")

async def handle_other(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Если прислан не скриншот"""
    await update.message.reply_text("❌ Пожалуйста, отправь скриншот платежа.")

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.ALL & ~filters.PHOTO, handle_other))

    app.run_polling(close_loop=False)  # 👈 ключ для Render

if __name__ == "__main__":
    main()
