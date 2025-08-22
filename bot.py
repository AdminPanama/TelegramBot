import os
import random
import string
from typing import Optional, List

import asyncpg
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

# ==================== ENV ====================
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
TON_WALLET = os.getenv("TON_WALLET")
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME")  # имя канала без @
DATABASE_URL = os.getenv("DATABASE_URL")          # строка подключения Render Postgres

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

# ==================== CONSTANTS ====================
PRICE_PER_STAR = 0.00475  # Цена за 1 звезду в TON
MIN_STARS = 50
MAX_STARS = 10000
REF_PERCENT = 0.01  # 1% бонуса пригласившему (копим отдельно, вывод потом)

# ==================== DB POOL ====================
POOL: Optional[asyncpg.Pool] = None


async def init_db():
    global POOL
    POOL = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
    async with POOL.acquire() as conn:
        # users: хранит баланс, реф.доход, кто пригласил
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id   BIGINT PRIMARY KEY,
                username  TEXT,
                balance   INTEGER NOT NULL DEFAULT 0,
                ref_earned NUMERIC NOT NULL DEFAULT 0,
                inviter   BIGINT
            );
        """)
        # history: произвольные записи событий для пользователя
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS history (
                id        SERIAL PRIMARY KEY,
                user_id   BIGINT NOT NULL,
                record    TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
        """)
        # orders: заявки на покупку звёзд
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id        SERIAL PRIMARY KEY,
                order_id  TEXT UNIQUE NOT NULL,       -- наш 6-значный код
                user_id   BIGINT NOT NULL,
                stars     INTEGER NOT NULL,
                amount    NUMERIC NOT NULL,
                status    TEXT NOT NULL,              -- 'Ожидает подтверждения' | '✅ Подтверждено' | '❌ Отклонено'
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
        """)

# ==================== DB HELPERS ====================

async def ensure_user(user_id: int, username: str, inviter: Optional[int]):
    """Создать пользователя, если его нет. Не перезаписывает существующего."""
    async with POOL.acquire() as conn:
        await conn.execute("""
            INSERT INTO users (user_id, username, inviter)
            VALUES ($1, $2, $3)
            ON CONFLICT (user_id) DO NOTHING
        """, user_id, username, inviter)

async def update_username_if_changed(user_id: int, username: str):
    async with POOL.acquire() as conn:
        await conn.execute("UPDATE users SET username=$1 WHERE user_id=$2 AND username IS DISTINCT FROM $1",
                           username, user_id)

async def add_history(user_id: int, text: str):
    async with POOL.acquire() as conn:
        await conn.execute("INSERT INTO history (user_id, record) VALUES ($1, $2)", user_id, text)

async def get_user(user_id: int):
    async with POOL.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM users WHERE user_id=$1", user_id)

async def get_user_history(user_id: int) -> List[str]:
    async with POOL.acquire() as conn:
        rows = await conn.fetch("SELECT record FROM history WHERE user_id=$1 ORDER BY created_at DESC LIMIT 50", user_id)
        return [r["record"] for r in rows]

async def all_user_ids() -> List[int]:
    async with POOL.acquire() as conn:
        rows = await conn.fetch("SELECT user_id FROM users")
        return [r["user_id"] for r in rows]

async def change_balance(user_id: int, delta: int, history_text: Optional[str] = None):
    async with POOL.acquire() as conn:
        async with conn.transaction():
            await conn.execute("UPDATE users SET balance = balance + $1 WHERE user_id=$2", delta, user_id)
            if history_text:
                await conn.execute("INSERT INTO history (user_id, record) VALUES ($1, $2)", user_id, history_text)

async def add_ref_earn(inviter_id: int, amount_stars: float):
    # Копим реф.звёзды в ref_earned (не в баланс)
    async with POOL.acquire() as conn:
        await conn.execute("UPDATE users SET ref_earned = ref_earned + $1 WHERE user_id=$2", amount_stars, inviter_id)

async def create_order(user_id: int, stars: int, amount: float, order_id: str):
    async with POOL.acquire() as conn:
        await conn.execute("""
            INSERT INTO orders (order_id, user_id, stars, amount, status)
            VALUES ($1, $2, $3, $4, 'Ожидает подтверждения')
        """, order_id, user_id, stars, amount)

async def last_pending_order(user_id: int):
    async with POOL.acquire() as conn:
        return await conn.fetchrow("""
            SELECT * FROM orders
            WHERE user_id=$1 AND status='Ожидает подтверждения'
            ORDER BY created_at DESC
            LIMIT 1
        """, user_id)

async def set_order_status(order_id: str, new_status: str):
    async with POOL.acquire() as conn:
        await conn.execute("UPDATE orders SET status=$1 WHERE order_id=$2", new_status, order_id)

async def orders_count() -> int:
    async with POOL.acquire() as conn:
        row = await conn.fetchrow("SELECT COUNT(*) AS c FROM orders")
        return row["c"] if row else 0

# ==================== UTILS ====================

def generate_tx_id() -> str:
    return ''.join(random.choices(string.digits, k=6))

def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⭐ Купить звезды", callback_data="buy_stars")],
        [InlineKeyboardButton("📜 История покупок", callback_data="history")],
        [InlineKeyboardButton("🎁 Реферальная программа", callback_data="ref_system")],
        [InlineKeyboardButton("😂 Купить без денег", callback_data="fake_buy")]
    ])

# ==================== HANDLERS ====================

# /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    user_id = user.id
    referrer = None
    if context.args:
        # передаём только цифры
        try:
            ref_candidate = int(context.args[0])
            if ref_candidate != user_id:
                referrer = ref_candidate
        except:
            referrer = None

    await ensure_user(user_id, user.username or "", referrer)
    await update_username_if_changed(user_id, user.username or "")

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

# Кнопки меню
async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

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
        history = await get_user_history(user_id)
        if history:
            text = "📜 Ваша история:\n\n" + "\n".join(history)
        else:
            text = "📜 Ваша история пока пуста."
        await query.message.reply_text(text)

    elif query.data == "ref_system":
        user = await get_user(user_id)
        balance = user["balance"] if user else 0
        earned = float(user["ref_earned"]) if user else 0.0
        # username бота можно взять из контекста
        bot_username = (await context.bot.get_me()).username
        ref_link = f"https://t.me/{bot_username}?start={user_id}"

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

# Ввод количества звёзд
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("waiting_for_stars"):
        return

    try:
        stars = int(update.message.text.strip())
        if stars < MIN_STARS or stars > MAX_STARS:
            await update.message.reply_text(f"❌ Введите число от {MIN_STARS} до {MAX_STARS}.")
            return

        amount_ton = stars * PRICE_PER_STAR
        tx_id = generate_tx_id()
        context.user_data["waiting_for_stars"] = False

        await create_order(update.message.from_user.id, stars, amount_ton, tx_id)

        text = (
            f"💰 Заявка №{tx_id}\n"
            f"⭐ Кол-во звёзд: {stars}\n"
            f"💎 Сумма: {amount_ton:.2f} TON\n\n"
            f"🔗 Отправьте {amount_ton:.2f} TON на кошелёк:\n"
            f"{TON_WALLET}\n\n"
            "📸 После перевода отправьте скриншот!"
        )
        await update.message.reply_text(text)

    except ValueError:
        await update.message.reply_text("❌ Введите корректное число.")

# Скриншот оплаты
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    order = await last_pending_order(user_id)
    if not order:
        await update.message.reply_text("❗️У вас нет активной заявки. Сначала создайте заявку в меню покупки.")
        return

    # Кнопки админу
    keyboard = [
        [
            InlineKeyboardButton("✅ Подтвердить", callback_data=f"confirm_{user_id}_{order['order_id']}"),
            InlineKeyboardButton("❌ Отклонить",   callback_data=f"reject_{user_id}_{order['order_id']}")
        ]
    ]

    # Пересылаем фото админу
    photo_file = update.message.photo[-1].file_id
    caption = (
        f"💰 Новая оплата!\n"
        f"👤 Пользователь: @{update.message.from_user.username}\n"
        f"⭐ Кол-во звёзд: {order['stars']}\n"
        f"💎 Сумма: {float(order['amount']):.2f} TON\n"
        f"🆔 Заявка №{order['order_id']}\n"
        f"⏳ Статус: Ожидает подтверждения"
    )
    await context.bot.send_photo(
        ADMIN_ID,
        photo=photo_file,
        caption=caption,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

    await update.message.reply_text("📤 Скриншот получен! Ожидайте подтверждения администратора.")

# Подтверждение/отклонение админом
async def admin_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    # Безопасность: управлять оплатами может только админ
    if query.from_user.id != ADMIN_ID:
        await query.answer("Недостаточно прав.", show_alert=True)
        return

    data = query.data
    if data.startswith("confirm_"):
        _, user_id_str, tx_id = data.split("_")
        user_id = int(user_id_str)

        # Обновляем статус
        await set_order_status(tx_id, "✅ Подтверждено")

        # Добавляем запись в историю пользователя (без автозачисления, как раньше)
        async with POOL.acquire() as conn:
            order = await conn.fetchrow("SELECT * FROM orders WHERE order_id=$1", tx_id)
        if order:
            await add_history(user_id, f"⭐ {order['stars']} | {float(order['amount']):.2f} TON | ✅ Подтверждено")

            # Реферальный бонус 1% от купленных звёзд — в ref_earned приглашённого
            user_row = await get_user(user_id)
            inviter = user_row["inviter"] if user_row else None
            if inviter:
                ref_bonus = round(order["stars"] * REF_PERCENT, 2)
                if ref_bonus > 0:
                    await add_ref_earn(inviter, ref_bonus)

            await context.bot.send_message(
                user_id,
                "✅ Ваша заявка успешно принята и обработана!\n\n"
                "Спасибо за покупку, ожидайте поступления звёзд ✨"
            )

        await query.edit_message_text("✅ Оплата подтверждена (без автопополнения).")

    elif data.startswith("reject_"):
        _, user_id_str, tx_id = data.split("_")
        user_id = int(user_id_str)

        await set_order_status(tx_id, "❌ Отклонено")
        async with POOL.acquire() as conn:
            order = await conn.fetchrow("SELECT * FROM orders WHERE order_id=$1", tx_id)
        if order:
            await add_history(user_id, f"⭐ {order['stars']} | {float(order['amount']):.2f} TON | ❌ Отклонено")
            await context.bot.send_message(user_id, f"❌ Ваша заявка отклонена.\n🆔 Заявка №{tx_id}")

        await query.edit_message_text("❌ Оплата отклонена.")

# /addstars (начислить конкретному пользователю)
async def add_stars(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        return
    try:
        user_id = int(context.args[0])
        stars = int(context.args[1])
        await change_balance(user_id, stars, f"🎁 Админ начислил {stars} ⭐")
        await update.message.reply_text(f"✅ Пользователю {user_id} начислено {stars} ⭐")
        try:
            await context.bot.send_message(user_id, f"🎁 Вам начислено {stars} ⭐ от администратора!")
        except:
            pass
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

# /massaddstars (массовая раздача всем)
async def mass_add_stars(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        return
    try:
        stars = int(context.args[0])

        # Делаем пакетно в транзакции
        users = await all_user_ids()
        if not users:
            await update.message.reply_text("❗️Нет пользователей для раздачи.")
            return

        async with POOL.acquire() as conn:
            async with conn.transaction():
                # Массовое обновление баланс + история
                await conn.executemany(
                    "UPDATE users SET balance = balance + $1 WHERE user_id=$2",
                    [(stars, uid) for uid in users]
                )
                await conn.executemany(
                    "INSERT INTO history (user_id, record) VALUES ($1, $2)",
                    [(uid, f"🎁 Массовое начисление {stars} ⭐") for uid in users]
                )

        # Оповещения пользователям (без падения при заблоканном боте)
        sent = 0
        for uid in users:
            try:
                await context.bot.send_message(uid, f"🎁 Вам начислено {stars} ⭐ (массовая раздача)")
                sent += 1
            except:
                pass

        await update.message.reply_text(f"✅ Начислено по {stars} ⭐ всем ({len(users)}) пользователям. " +
                                        f"Сообщений отправлено: {sent}.")

    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

# /stats
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        return
    users_total = len(await all_user_ids())
    orders_total = await orders_count()
    await update.message.reply_text(
        f"📊 Статистика:\n"
        f"👥 Пользователей: {users_total}\n"
        f"🛒 Заявок: {orders_total}"
    )

# ==================== APP ====================

def build_app() -> Application:
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("addstars", add_stars))
    app.add_handler(CommandHandler("massaddstars", mass_add_stars))

    app.add_handler(CallbackQueryHandler(admin_handler, pattern="^(confirm_|reject_)"))
    app.add_handler(CallbackQueryHandler(menu_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    return app

def main():
    app = build_app()
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    import asyncio
    asyncio.run(init_db())  # создаём таблицы при старте
    main()
