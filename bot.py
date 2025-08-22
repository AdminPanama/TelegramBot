import os
import json
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
REF_PERCENT = 0.01  # 1% бонуса пригласившему

USERS = {}   # user_id: {...}
ORDERS = {}  # order_id: {"user_id", "stars", "amount", "status"}

DATA_FILE = "users.json"


# === Работа с базой пользователей ===
def load_users():
    global USERS
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            USERS = json.load(f)
    else:
        USERS = {}


def save_users():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(USERS, f, ensure_ascii=False, indent=2)


# === Генерация ID заявки ===
def generate_tx_id():
    return ''.join(random.choices(string.digits, k=6))


# === Команда /start ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    user_id = str(user.id)
    referrer = None

    if context.args:
        referrer = context.args[0]

    if user_id not in USERS:
        USERS[user_id] = {
            "username": user.username or "",
            "balance": 0,
            "referrals": [],
            "ref_earned": 0,
            "inviter": referrer if referrer and referrer != user_id else None,
            "history": []
        }

        if referrer and referrer in USERS:
            USERS[referrer]["referrals"].append(user_id)

        save_users()

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
        [InlineKeyboardButton("🎁 Реферальная программа", callback_data="ref_system")],
        [InlineKeyboardButton("😂 Купить без денег", callback_data="fake_buy")]
    ])


# === Обработка меню ===
async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)

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
        history = USERS.get(user_id, {}).get("history", [])
        if history:
            text = "📜 Ваша история покупок:\n\n" + "\n".join(history)
        else:
            text = "📜 Ваша история покупок пока пуста."
        await query.message.reply_text(text)

    elif query.data == "ref_system":
        user = USERS.get(user_id, {})
        balance = user.get("balance", 0)
        earned = user.get("ref_earned", 0)
        ref_link = f"https://t.me/{context.bot.username}?start={user_id}"

        text = (
            f"🎁 Реферальная программа\n\n"
            f"👤 Ваш ID: {user_id}\n"
            f"💰 Баланс: {balance} ⭐\n"
            f"💎 Заработано с рефералов: {earned:.2f} ⭐\n\n"
            f"🔗 Ваша ссылка:\n{ref_link}\n\n"
            "📝 Вывод средств будет доступен SOON. Продолжайте приглашать друзей!"
        )
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

            order = {
                "id": tx_id,
                "user_id": update.message.from_user.id,
                "stars": stars,
                "amount": amount_ton,
                "status": "Ожидает подтверждения"
            }
            ORDERS[tx_id] = order

            text = (
                f"💰 Заявка №{tx_id}\n"
                f"⭐ Кол-во звёзд: {stars}\n"
                f"💎 Сумма: {amount_ton:.2f} TON\n\n"
                f"🔗 Отправьте {amount_ton:.2f} TON на кошелёк:\n"
                f"{TON_WALLET}\n\n"
                "📸 После перевода отправьте скриншот!"
            )
            await update.message.reply_text(text, parse_mode="Markdown")

        except ValueError:
            await update.message.reply_text("❌ Введите корректное число.")


# === Обработка фото (скриншот) ===
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)

    # берем последнюю заявку
    last_order = None
    for o in reversed(list(ORDERS.values())):
        if str(o["user_id"]) == user_id and o["status"] == "Ожидает подтверждения":
            last_order = o
            break

    if last_order:
        keyboard = [
            [
                InlineKeyboardButton("✅ Подтвердить", callback_data=f"confirm_{user_id}_{last_order['id']}"),
                InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{user_id}_{last_order['id']}")
            ]
        ]

        # теперь пересылаем скриншот админу
        photo_file = update.message.photo[-1].file_id
        await context.bot.send_photo(
            ADMIN_ID,
            photo=photo_file,
            caption=(
                f"💰 Новая оплата!\n"
                f"👤 Пользователь: @{update.message.from_user.username}\n"
                f"⭐ Кол-во звёзд: {last_order['stars']}\n"
                f"💎 Сумма: {last_order['amount']:.2f} TON\n"
                f"🆔 Заявка №{last_order['id']}\n"
                f"⏳ Статус: Ожидает подтверждения"
            ),
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
        user_id = str(user_id)
        order = ORDERS.get(tx_id)

        if order:
            order["status"] = "✅ Подтверждено"

            if user_id not in USERS:
                USERS[user_id] = {
                    "username": "",
                    "balance": 0,
                    "referrals": [],
                    "ref_earned": 0,
                    "inviter": None,
                    "history": []
                }

            USERS[user_id]["history"].append(
                f"⭐ {order['stars']} | {order['amount']:.2f} TON | ✅ Подтверждено"
            )
            save_users()

            await context.bot.send_message(
                int(user_id),
                "✅ Ваша заявка успешно принята и обработана!\n\n"
                "Спасибо за покупку, ожидайте поступления звёзд ✨"
            )
            await query.edit_message_text("✅ Оплата подтверждена (без автопополнения).")

    elif query.data.startswith("reject_"):
        _, user_id, tx_id = query.data.split("_")
        user_id = str(user_id)
        order = ORDERS.get(tx_id)

        if order:
            order["status"] = "❌ Отклонено"

            if user_id not in USERS:
                USERS[user_id] = {
                    "username": "",
                    "balance": 0,
                    "referrals": [],
                    "ref_earned": 0,
                    "inviter": None,
                    "history": []
                }

            USERS[user_id]["history"].append(
                f"⭐ {order['stars']} | {order['amount']:.2f} TON | ❌ Отклонено"
            )
            save_users()

            await context.bot.send_message(
                int(user_id),
                f"❌ Ваша заявка отклонена.\n🆔 Заявка №{order['id']}"
            )
            await query.edit_message_text("❌ Оплата отклонена.")


# === Команда /addstars для админа ===
async def add_stars(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        return

    try:
        user_id = str(context.args[0])
        stars = int(context.args[1])

        if user_id not in USERS:
            USERS[user_id] = {
                "username": "",
                "balance": 0,
                "referrals": [],
                "ref_earned": 0,
                "inviter": None,
                "history": []
            }

        USERS[user_id]["balance"] += stars
        USERS[user_id]["history"].append(f"🎁 Админ начислил {stars} ⭐")
        save_users()

        await update.message.reply_text(f"✅ Пользователю {user_id} начислено {stars} ⭐")
        await context.bot.send_message(int(user_id), f"🎁 Вам начислено {stars} ⭐ от администратора!")

    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")


# === Команда /massaddstars для админа ===
async def mass_add_stars(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        return

    try:
        stars = int(context.args[0])
        count = 0

        for user_id in USERS.keys():
            USERS[user_id]["balance"] += stars
            USERS[user_id]["history"].append(f"🎁 Массовое начисление {stars} ⭐")
            try:
                await context.bot.send_message(int(user_id), f"🎁 Вам начислено {stars} ⭐ (массовая раздача)")
            except:
                pass
            count += 1

        save_users()
        await update.message.reply_text(f"✅ Начислено по {stars} ⭐ всем ({count}) пользователям.")

    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")


# === Команда /stats для админа ===
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id == ADMIN_ID:
        await update.message.reply_text(
            f"📊 Статистика:\n"
            f"👥 Пользователей: {len(USERS)}\n"
            f"🛒 Заявок: {len(ORDERS)}"
        )


# === Основной запуск ===
def main():
    load_users()
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("addstars", add_stars))
    app.add_handler(CommandHandler("massaddstars", mass_add_stars))  # 🔥 массовая раздача

    app.add_handler(CallbackQueryHandler(admin_handler, pattern="^(confirm_|reject_)"))
    app.add_handler(CallbackQueryHandler(menu_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    app.run_polling()


if __name__ == "__main__":
    main()
