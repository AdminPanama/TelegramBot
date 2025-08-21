import os
import random
import string
import asyncpg
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
DATABASE_URL = os.getenv("DATABASE_URL")

if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN не задан в переменных окружения")
if not ADMIN_ID:
    raise ValueError("❌ ADMIN_ID не задан в переменных окружения")
if not TON_WALLET:
    raise ValueError("❌ TON_WALLET не задан в переменных окружения")
if not CHANNEL_USERNAME:
    raise ValueError("❌ CHANNEL_USERNAME не задан в переменных окружения")
if not DATABASE_URL:
    raise ValueError("❌ DATABASE_URL не задан в переменных окружения")

ADMIN_ID = int(ADMIN_ID)
# ====================

PRICE_PER_STAR = 0.00475  # Цена за 1 звезду в TON
MIN_STARS = 50
MAX_STARS = 10000
REF_BONUS = 10  # бонус за приглашенного


# === БД ===
async def init_db():
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        telegram_id BIGINT UNIQUE,
        username TEXT,
        invited_by BIGINT,
        balance INT DEFAULT 0,
        total_ref_earned INT DEFAULT 0,
        created_at TIMESTAMP DEFAULT NOW()
    );
    """)
    await conn.execute("""
    CREATE TABLE IF NOT EXISTS orders (
        id SERIAL PRIMARY KEY,
        user_id BIGINT,
        stars INT,
        amount NUMERIC,
        status TEXT,
        created_at TIMESTAMP DEFAULT NOW()
    );
    """)
    await conn.close()


async def get_user(telegram_id):
    conn = await asyncpg.connect(DATABASE_URL)
    user = await conn.fetchrow("SELECT * FROM users WHERE telegram_id=$1", telegram_id)
    await conn.close()
    return user


async def add_user(telegram_id, username, invited_by=None):
    conn = await asyncpg.connect(DATABASE_URL)
    user = await conn.fetchrow("SELECT * FROM users WHERE telegram_id=$1", telegram_id)
    if not user:
        await conn.execute(
            "INSERT INTO users (telegram_id, username, invited_by) VALUES ($1,$2,$3)",
            telegram_id, username, invited_by
        )
    await conn.close()


async def add_order(user_id, stars, amount, status="Ожидает подтверждения"):
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute(
        "INSERT INTO orders (user_id, stars, amount, status) VALUES ($1,$2,$3,$4)",
        user_id, stars, amount, status
    )
    await conn.close()


async def update_order_status(user_id, tx_id, status):
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute(
        "UPDATE orders SET status=$1 WHERE user_id=$2 AND id=$3",
        status, user_id, tx_id
    )
    await conn.close()


async def add_bonus(inviter_id, bonus=REF_BONUS):
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute(
        "UPDATE users SET balance = balance + $1, total_ref_earned = total_ref_earned + $1 WHERE telegram_id=$2",
        bonus, inviter_id
    )
    await conn.close()


async def get_balance_refstats_invites(user_id):
    conn = await asyncpg.connect(DATABASE_URL)
    row = await conn.fetchrow("SELECT balance, total_ref_earned FROM users WHERE telegram_id=$1", user_id)
    invites = await conn.fetchval("SELECT COUNT(*) FROM users WHERE invited_by=$1", user_id)
    await conn.close()
    if row:
        return row["balance"], row["total_ref_earned"], invites
    return 0, 0, 0


# === Генерация ID заявки ===
def generate_tx_id():
    return ''.join(random.choices(string.digits, k=6))


# === Команда /start ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    username = update.message.from_user.username

    ref_id = None
    if context.args:  # если /start с реф ссылкой
        try:
            ref_id = int(context.args[0])
        except:
            pass

    await add_user(user_id, username, ref_id)

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
        [InlineKeyboardButton("👥 Реферальная система", callback_data="ref_system")],
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
        user_id = query.from_user.id
        conn = await asyncpg.connect(DATABASE_URL)
        rows = await conn.fetch("SELECT * FROM orders WHERE user_id=$1 ORDER BY created_at DESC LIMIT 10", user_id)
        await conn.close()
        if rows:
            text = "📜 Ваша история покупок:\n\n" + "\n".join(
                [f"№{r['id']} | ⭐ {r['stars']} | {r['amount']} TON | {r['status']}" for r in rows]
            )
        else:
            text = "📜 Ваша история покупок пока пуста."
        await query.message.reply_text(text)

    elif query.data == "ref_system":
        user_id = query.from_user.id
        balance, total_ref_earned, invites = await get_balance_refstats_invites(user_id)
        ref_link = f"https://t.me/{context.bot.username}?start={user_id}"

        text = (
            f"👥 *Реферальная система*\n\n"
            f"🔗 Ваша личная ссылка:\n{ref_link}\n\n"
            f"👤 Приглашено друзей: *{invites}*\n"
            f"💎 Баланс: *{balance}* ⭐\n"
            f"🌟 Всего заработано от друзей: *{total_ref_earned}* ⭐\n\n"
            f"⚡ За первую покупку приглашённого вы получаете +{REF_BONUS} ⭐!\n\n"
            f"⏳ Вывод бонусов будет доступен *скоро*. Продолжайте приглашать друзей 🚀"
        )

        keyboard = [[InlineKeyboardButton("🏠 Главное меню", callback_data="continue_menu")]]
        await query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif query.data == "fake_buy":
        phrases = [
            "🚫 Нет денег — нет конфетки 🍭",
            "🤗 Всё ещё впереди! Иди работай 💼",
            "🥲 Халявы нет, брат… только работа и TON 💎",
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

            await add_order(update.message.from_user.id, stars, amount_ton)

            text = (
                f"💰 Заявка №{tx_id}\n"
                f"⭐ Кол-во звёзд: {stars}\n"
                f"💎 Сумма: {amount_ton:.2f} TON\n\n"
                f"🔗 Отправьте {amount_ton:.2f} TON на кошелёк:\n"
                f"`{TON_WALLET}`\n\n"
                "📸 После перевода отправьте скриншот!"
            )
            await update.message.reply_text(text, parse_mode="Markdown")

            context.user_data["pending_order"] = {"id": tx_id, "stars": stars, "amount": amount_ton}

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

        # 🔥 Вернул полное уведомление админу
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

        await update.message.reply_text("📤 Скриншот получен! Ожидайте подтверждения администратора.")


# === Админ подтверждает/отклоняет ===
async def admin_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data.startswith("confirm_"):
        _, user_id, tx_id = query.data.split("_")
        user_id = int(user_id)

        await update_order_status(user_id, tx_id, "✅ Подтверждено")

        # проверим, есть ли пригласитель и это первая покупка
        user = await get_user(user_id)
        if user and user["invited_by"]:
            conn = await asyncpg.connect(DATABASE_URL)
            cnt = await conn.fetchval("SELECT COUNT(*) FROM orders WHERE user_id=$1 AND status='✅ Подтверждено'", user_id)
            await conn.close()
            if cnt == 1:  # первая успешная покупка
                await add_bonus(user["invited_by"])

        # 🔥 Сообщение пользователю с деталями
        await context.bot.send_message(
            user_id,
            f"✅ Оплата подтверждена!\n"
            f"⭐ Начислено звёзд: {tx_id}\n"
            f"🆔 Заявка №{tx_id}"
        )
        await query.message.reply_text("✅ Оплата подтверждена.")

    elif query.data.startswith("reject_"):
        _, user_id, tx_id = query.data.split("_")
        user_id = int(user_id)

        await update_order_status(user_id, tx_id, "❌ Отклонено")

        # 🔥 Сообщение пользователю с деталями
        await context.bot.send_message(
            user_id,
            f"❌ Оплата отклонена.\n🆔 Заявка №{tx_id}"
        )
        await query.message.reply_text("❌ Оплата отклонена.")


# === Команда /stats для админа ===
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id == ADMIN_ID:
        conn = await asyncpg.connect(DATABASE_URL)
        users_count = await conn.fetchval("SELECT COUNT(*) FROM users")
        orders_count = await conn.fetchval("SELECT COUNT(*) FROM orders")
        await conn.close()
        await update.message.reply_text(f"📊 Статистика:\n👥 Пользователей: {users_count}\n🛒 Заявок: {orders_count}")


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
    import asyncio
    asyncio.run(init_db())
    main()
