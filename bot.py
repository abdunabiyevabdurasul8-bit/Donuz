import logging
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, ConversationHandler, filters
)

# --- SOZLAMALAR ---
BOT_TOKEN = ""
ADMIN_ID = 5692925792  # Admin Telegram ID

# Database Sozlash
conn = sqlite3.connect('bot_database.db', check_same_thread=False)
cursor = conn.cursor()

cursor.execute('''
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    balance REAL DEFAULT 0
)''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS orders (
    order_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    item_name TEXT,
    price REAL,
    status TEXT DEFAULT 'Kutilmoqda'
)''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS promocodes (
    code TEXT PRIMARY KEY,
    amount REAL,
    limit_count INTEGER,
    used_count INTEGER DEFAULT 0
)''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS promo_uses (
    user_id INTEGER,
    code TEXT,
    PRIMARY KEY (user_id, code)
)''')
conn.commit()

# --- STEP CONSTANTS ---
(
    PROMO_CODE, PROMO_AMOUNT, PROMO_LIMIT, 
    USE_PROMO, CHECK_ORDER, 
    TRANSFER_USER, TRANSFER_AMOUNT, 
    ADMIN_APPROVE_PAYMENT,
    MANUAL_ADD_USER, MANUAL_ADD_AMOUNT,
    MANUAL_SUB_USER, MANUAL_SUB_AMOUNT
) = range(12)

# --- ASOSIY MENYU ---
def main_keyboard():
    return ReplyKeyboardMarkup([
        ["🛍️ Buyurtma berish", "💳 Balans to'ldirish"],
        ["💸 Pul o'tkazish", "🔍 Buyurtmani tekshirish"],
        ["🎁 Promokod", "👤 Balans va Profil"],
        ["📊 Statistika"]
    ], resize_keyboard=True)

# --- START COMMAND ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    conn.commit()
    await update.message.reply_text("Xush kelibsiz! Kerakli bo'limni tanlang:", reply_markup=main_keyboard())

# --- BALANS TO'LDIRISH ---
async def fill_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = (
        "💳 Balansni to'ldirish uchun:\n\n"
        "1. Karta raqamiga to'lov qiling:\n"
        "<code>9860 6067 6078 9275</code> (A.Abdurasul)\n\n"
        "2. To'lov qilgach, to'lov cheki (skrinshot) rasmini shu botning o'ziga yuboring!\n\n"
        f"🆔 Sizning ID: <code>{user_id}</code>"
    )
    await update.message.reply_text(text, parse_mode="HTML")

# --- CHEK RASMINI TUTIB OLISH ---
async def handle_receipt_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    photo_id = update.message.photo[-1].file_id

    await update.message.reply_text("✅ Chek qabul qilindi! Admin ko'rib chiqqach, balansingiz to'ldiriladi.")

    admin_keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Balans qo'shish", callback_data=f"pay_approve_{user_id}")]
    ])

    username = update.effective_user.username
    user_mention = f"@{username}" if username else "Yo'q"
    caption_text = f"📥 Yangi to'lov cheki!\n\n👤 Foydalanuvchi ID: {user_id}\n👤 Username: {user_mention}"

    await context.bot.send_photo(
        chat_id=ADMIN_ID,
        photo=photo_id,
        caption=caption_text,
        reply_markup=admin_keyboard
    )

# --- ADMIN CHEK ORQALI BALANS QO'SHISH ---
async def approve_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    target_user_id = query.data.split("_")[2]
    context.user_data['pay_target_user'] = target_user_id
    
    await query.message.reply_text(f"💳 ID: {target_user_id} foydalanuvchisining balansiga qancha pul qo'shmoqchisiz (so'mda)?")
    return ADMIN_APPROVE_PAYMENT

async def save_payment_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(update.message.text)
        target_user = context.user_data['pay_target_user']

        cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, target_user))
        conn.commit()

        await update.message.reply_text(f"✅ User ID {target_user} balansiga {amount:,.0f} so'm qo'shildi!")
        await context.bot.send_message(target_user, f"🎉 Hisobingiz {amount:,.0f} so'mga to'ldirildi!")
    except ValueError:
        await update.message.reply_text("❌ Noto'g'ri summa kiritildi.")
    
    return ConversationHandler.END

# --- ADMIN QO'LDA BALANS QO'SHISH (/addbalance) ---
async def manual_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    await update.message.reply_text("➕ Balansiga pul qo'shmoqchi bo'lgan foydalanuvchining ID raqamini kiriting:")
    return MANUAL_ADD_USER

async def manual_add_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = int(update.message.text)
        cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
        if not cursor.fetchone():
            await update.message.reply_text("❌ Bunday foydalanuvchi topilmadi.")
            return ConversationHandler.END
        
        context.user_data['manual_add_user_id'] = user_id
        await update.message.reply_text(f"💰 ID: {user_id} balansiga qancha so'm QO'SHMOQCHISIZ?")
        return MANUAL_ADD_AMOUNT
    except ValueError:
        await update.message.reply_text("❌ ID faqat raqamlardan iborat bo'lishi kerak.")
        return ConversationHandler.END

async def manual_add_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(update.message.text)
        user_id = context.user_data['manual_add_user_id']
        
        cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
        conn.commit()
        
        await update.message.reply_text(f"✅ ID: {user_id} balansiga {amount:,.0f} so'm qo'shildi!")
        await context.bot.send_message(user_id, f"🎉 Hisobingizga admin tomonidan {amount:,.0f} so'm qo'shildi!")
    except ValueError:
        await update.message.reply_text("❌ Noto'g'ri summa kiritildi.")
    return ConversationHandler.END

# --- ADMIN QO'LDA BALANS AYRISH (/subbalance) ---
async def manual_sub_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    await update.message.reply_text("➖ Balansidan pul AYRIMOQCHI bo'lgan foydalanuvchining ID raqamini kiriting:")
    return MANUAL_SUB_USER

async def manual_sub_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = int(update.message.text)
        cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
        if not cursor.fetchone():
            await update.message.reply_text("❌ Bunday foydalanuvchi topilmadi.")
            return ConversationHandler.END
        
        context.user_data['manual_sub_user_id'] = user_id
        await update.message.reply_text(f"📉 ID: {user_id} balansidan qancha so'm AYRIMOQCHISIZ?")
        return MANUAL_SUB_AMOUNT
    except ValueError:
        await update.message.reply_text("❌ ID faqat raqamlardan iborat bo'lishi kerak.")
        return ConversationHandler.END

async def manual_sub_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(update.message.text)
        user_id = context.user_data['manual_sub_user_id']
        
        cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, user_id))
        conn.commit()
        
        await update.message.reply_text(f"✅ ID: {user_id} balansidan {amount:,.0f} so'm ayrib tashlandi!")
        await context.bot.send_message(user_id, f"⚠️ Balansingizdan admin tomonidan {amount:,.0f} so'm olib tashlandi.")
    except ValueError:
        await update.message.reply_text("❌ Noto'g'ri summa kiritildi.")
    return ConversationHandler.END

# --- PUL O'TKAZISH TIZIMI ---
async def transfer_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("💸 Pul o'tkazmoqchi bo'lgan foydalanuvchining Telegram ID raqamini kiriting:")
    return TRANSFER_USER

async def transfer_get_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        target_id = int(update.message.text)
        if target_id == update.effective_user.id:
            await update.message.reply_text("❌ O'zingizga pul o'tkaza olmaysiz!")
            return ConversationHandler.END

        cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (target_id,))
        if not cursor.fetchone():
            await update.message.reply_text("❌ Bunday foydalanuvchi botda topilmadi.")
            return ConversationHandler.END

        context.user_data['transfer_target'] = target_id
        await update.message.reply_text("Qancha summa o'tkazmoqchisiz (masalan: 10000)?")
        return TRANSFER_AMOUNT
    except ValueError:
        await update.message.reply_text("❌ Noto'g'ri ID kiritildi.")
        return ConversationHandler.END

async def transfer_get_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(update.message.text)
        sender_id = update.effective_user.id
        target_id = context.user_data['transfer_target']

        if amount <= 0:
            await update.message.reply_text("❌ Noto'g'ri summa kiritildi.")
            return ConversationHandler.END

        cursor.execute("SELECT balance FROM users WHERE user_id = ?", (sender_id,))
        res = cursor.fetchone()
        sender_balance = res[0] if res else 0

        if sender_balance < amount:
            await update.message.reply_text("❌ Balansda yetarli mablag' mavjud emas!")
            return ConversationHandler.END

        cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, sender_id))
        cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, target_id))
        conn.commit()

        await update.message.reply_text(f"✅ {target_id} ID egasiga {amount:,.0f} so'm muvaffaqiyatli o'tkazildi!")
        await context.bot.send_message(target_id, f"🎉 Hisobingizga {sender_id} ID egasi tomonidan {amount:,.0f} so'm o'tkazildi!")

    except ValueError:
        await update.message.reply_text("❌ Noto'g'ri summa kiritildi.")

    return ConversationHandler.END

# --- BUYURTMANI TEKSHIRISH ---
async def check_order_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 Tekshirmoqchi bo'lgan Buyurtma ID raqamini kiriting:")
    return CHECK_ORDER

async def check_order_process(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        order_id = int(update.message.text)
        user_id = update.effective_user.id

        cursor.execute("SELECT item_name, price, status FROM orders WHERE order_id = ? AND user_id = ?", (order_id, user_id))
        order = cursor.fetchone()

        if order:
            item_name, price, status = order
            status_icon = "⏳" if status == "Kutilmoqda" else ("✅" if status == "Bajarildi" else "❌")
            msg = (
                f"📦 Buyurtma #{order_id} ma'lumotlari:\n\n"
                f"🔹 Mahsulot: {item_name}\n"
                f"💵 Narxi: {price:,.0f} so'm\n"
                f"📌 Holati: {status_icon} {status}"
            )
            await update.message.reply_text(msg)
        else:
            await update.message.reply_text("❌ Sizga tegishli bunday buyurtma ID topilmadi.")

    except ValueError:
        await update.message.reply_text("❌ Buyurtma ID faqat raqamlardan iborat bo'ladi.")

    return ConversationHandler.END

# --- PROMOKOD ISHLATISH ---
async def use_promo_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎁 Promokodizni kiriting:")
    return USE_PROMO

async def use_promo_process(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.strip()
    user_id = update.effective_user.id

    cursor.execute("SELECT amount, limit_count, used_count FROM promocodes WHERE code = ?", (code,))
    promo = cursor.fetchone()

    if not promo:
        await update.message.reply_text("❌ Bunday promokod mavjud emas!")
        return ConversationHandler.END

    amount, limit_count, used_count = promo

    if used_count >= limit_count:
        await update.message.reply_text("❌ Ushbu promokod ishlatilish limiti tugagan!")
        return ConversationHandler.END

    cursor.execute("SELECT 1 FROM promo_uses WHERE user_id = ? AND code = ?", (user_id, code))
    if cursor.fetchone():
        await update.message.reply_text("❌ Siz ushbu promokodni avval ishlatgansiz!")
        return ConversationHandler.END

    cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
    cursor.execute("UPDATE promocodes SET used_count = used_count + 1 WHERE code = ?", (code,))
    cursor.execute("INSERT INTO promo_uses (user_id, code) VALUES (?, ?)", (user_id, code))
    conn.commit()

    await update.message.reply_text(f"🎉 Tabriklaymiz! Promokod muvaffaqiyatli faollashtirildi.\n💰 Balansingizga {amount:,.0f} so'm qo'shildi!")
    return ConversationHandler.END

# --- ADMIN PROMOKOD YARATISH (/addpromo) ---
async def add_promo_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Bu buyruq faqat Admin uchun!")
        return ConversationHandler.END

    await update.message.reply_text("🔑 Yangi promokod nomini kiriting (Masalan: BONUS5000):")
    return PROMO_CODE

async def add_promo_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['new_promo_code'] = update.message.text.strip()
    await update.message.reply_text("💰 Promokod summasini kiriting (so'mda):")
    return PROMO_AMOUNT

async def add_promo_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data['new_promo_amount'] = float(update.message.text)
        await update.message.reply_text("👥 Nechta foydalanuvchi ishlata olishini (limit sonini) kiriting:")
        return PROMO_LIMIT
    except ValueError:
        await update.message.reply_text("❌ Summani raqamda kiriting.")
        return ConversationHandler.END

async def add_promo_limit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        limit = int(update.message.text)
        code = context.user_data['new_promo_code']
        amount = context.user_data['new_promo_amount']

        cursor.execute("INSERT OR REPLACE INTO promocodes (code, amount, limit_count) VALUES (?, ?, ?)", (code, amount, limit))
        conn.commit()

        await update.message.reply_text(f"✅ Promokod muvaffaqiyatli yaratildi!\n\n🔑 Kodu: {code}\n💰 Summasi: {amount:,.0f} so'm\n👥 Limiti: {limit} ta")
    except ValueError:
        await update.message.reply_text("❌ Limit sonini raqamda kiriting.")

    return ConversationHandler.END

# --- STATISTIKA ---
async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cursor.execute("SELECT COUNT(*) FROM users")
    users_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM orders")
    orders_count = cursor.fetchone()[0]
    await update.message.reply_text(
        f"📊 Bot Statistikasi:\n\n👥 Foydalanuvchilar: {users_count} ta\n📦 Buyurtmalar: {orders_count} ta"
    )

# --- PROFIL ---
async def show_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    res = cursor.fetchone()
    balance = res[0] if res else 0
    await update.message.reply_text(
        f"👤 Sizning Profilingiz:\n\n🆔 ID: {user_id}\n💰 Balans: {balance:,.0f} so'm"
    )

# --- KATEGORIYALAR TIZIMI ---
async def order_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📱 Telegram xizmatlari", callback_data="cat_telegram")],
        [InlineKeyboardButton("🎮 PUBG Mobile UC", callback_data="cat_pubg")],
        [InlineKeyboardButton("🔥 Free Fire Diamond", callback_data="cat_ff")]
    ])
    await update.message.reply_text("🛒 Kerakli bo'limni tanlang:", reply_markup=keyboard)

async def category_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "cat_telegram":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("TG Premium 3 Oy — 178,000 so'm", callback_data="buy_TG Premium 3 Oy_178000")],
            [InlineKeyboardButton("TG Premium 6 Oy — 246,000 so'm", callback_data="buy_TG Premium 6 Oy_246000")],
            [InlineKeyboardButton("TG Premium 12 Oy — 440,000 so'm", callback_data="buy_TG Premium 12 Oy_440000")],
            [InlineKeyboardButton("TG Akkaunt — 8,000 so'm", callback_data="buy_TG Akkaunt_8000")],
            [InlineKeyboardButton("🔙 Orqaga", callback_data="cat_back")]
        ])
        await query.edit_message_text("📱 Telegram xizmatlari:", reply_markup=keyboard)

    elif query.data == "cat_pubg":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("60 UC — 13,000 so'm", callback_data="buy_PUBG 60 UC_13000")],
            [InlineKeyboardButton("120 UC — 24,000 so'm", callback_data="buy_PUBG 120 UC_24000")],
            [InlineKeyboardButton("180 UC — 36,000 so'm", callback_data="buy_PUBG 180 UC_36000")],
            [InlineKeyboardButton("325 UC — 59,000 so'm", callback_data="buy_PUBG 325 UC_59000")],
            [InlineKeyboardButton("385 UC — 70,000 so'm", callback_data="buy_PUBG 385 UC_70000")],
            [InlineKeyboardButton("660 UC — 115,000 so'm", callback_data="buy_PUBG 660 UC_115000")],
            [InlineKeyboardButton("985 UC — 170,000 so'm", callback_data="buy_PUBG 985 UC_170000")],
            [InlineKeyboardButton("1320 UC — 230,000 so'm", callback_data="buy_PUBG 1320 UC_230000")],
            [InlineKeyboardButton("1800 UC — 280,000 so'm", callback_data="buy_PUBG 1800 UC_280000")],
            [InlineKeyboardButton("2460 UC — 400,000 so'm", callback_data="buy_PUBG 2460 UC_400000")],
            [InlineKeyboardButton("3850 UC — 550,000 so'm", callback_data="buy_PUBG 3850 UC_550000")],
            [InlineKeyboardButton("5650 UC — 830,000 so'm", callback_data="buy_PUBG 5650 UC_830000")],
            [InlineKeyboardButton("8100 UC — 1,100,000 so'm", callback_data="buy_PUBG 8100 UC_1100000")],
            [InlineKeyboardButton("🔙 Orqaga", callback_data="cat_back")]
        ])
        await query.edit_message_text("🎮 PUBG Mobile UC paketlari:", reply_markup=keyboard)

    elif query.data == "cat_ff":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("110 Diamond — 12,000 so'm", callback_data="buy_FF 110 Diamond_12000")],
            [InlineKeyboardButton("341 Diamond — 34,000 so'm", callback_data="buy_FF 341 Diamond_34000")],
            [InlineKeyboardButton("572 Diamond — 56,000 so'm", callback_data="buy_FF 572 Diamond_56000")],
            [InlineKeyboardButton("1166 Diamond — 110,000 so'm", callback_data="buy_FF 1166 Diamond_110000")],
            [InlineKeyboardButton("2398 Diamond — 230,000 so'm", callback_data="buy_FF 2398 Diamond_230000")],
            [InlineKeyboardButton("6160 Diamond — 550,000 so'm", callback_data="buy_FF 6160 Diamond_550000")],
            [InlineKeyboardButton("Evo Acces 3D — 8,000 so'm", callback_data="buy_FF Evo Accsess_8000")],
            [InlineKeyboardButton("Evo Acces 7D — 12,000 so'm", callback_data="buy_FF Evo Accsess 7D_12000")],
            [InlineKeyboardButton("Evo Acces 30D — 40,000 so'm", callback_data="buy_FF Evo Accsess 30D_40000")],
            [InlineKeyboardButton("Prime kichik 7 kunlik — 8,000 so'm", callback_data="buy_FF Prime kichkina 7 kunlik_8000")],
            [InlineKeyboardButton("Prime 7 kunlik — 25,000 so'm", callback_data="buy_FF Prime 7 kunlik_25000")],
            [InlineKeyboardButton("Prime oylik — 86,000 so'm", callback_data="buy_FF Prime oylik_86000")],
            [InlineKeyboardButton("6 Level Up Package — 6,000 so'm", callback_data="buy_FF 6 Level Up Package_6000")],
            [InlineKeyboardButton("10 Level Up Package — 11,000 so'm", callback_data="buy_FF 10 Level Up Package_11000")],
            [InlineKeyboardButton("15 Level Up Package — 16,000 so'm", callback_data="buy_FF 15 Level Up Package_16000")],
            [InlineKeyboardButton("20 Level Up Package — 20,000 so'm", callback_data="buy_FF 20 Level Up Package_20000")],
            [InlineKeyboardButton("25 Level Up Package — 24,000 so'm", callback_data="buy_FF 25 Level Up Package_24000")],
            [InlineKeyboardButton("30 Level Up Package — 28,000 so'm", callback_data="buy_FF 30 Level Up Package_28000")],
            [InlineKeyboardButton("🔙 Orqaga", callback_data="cat_back")]
        ])
        await query.edit_message_text("🔥 Free Fire Diamond paketlari:", reply_markup=keyboard)

    elif query.data == "cat_back":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📱 Telegram xizmatlari", callback_data="cat_telegram")],
            [InlineKeyboardButton("🎮 PUBG Mobile UC", callback_data="cat_pubg")],
            [InlineKeyboardButton("🔥 Free Fire Diamond", callback_data="cat_ff")]
        ])
        await query.edit_message_text("🛒 Kerakli bo'limni tanlang:", reply_markup=keyboard)

# --- BUYURTMA XARIDI ---
async def process_buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    _, item_name, price = query.data.split("_")
    price = float(price)

    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    res = cursor.fetchone()
    balance = res[0] if res else 0

    if balance < price:
        await query.answer("❌ Hisobingizda yetarli pul yo'q!", show_alert=True)
        return

    cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (price, user_id))
    cursor.execute("INSERT INTO orders (user_id, item_name, price) VALUES (?, ?, ?)", (user_id, item_name, price))
    order_id = cursor.lastrowid
    conn.commit()

    await query.edit_message_text(f"✅ Buyurtmangiz qabul qilindi!\n🆔 Buyurtma ID: {order_id}\n📦 Mahsulot: {item_name}")

    admin_keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Qabul qilish", callback_data=f"adm_accept_{order_id}"),
            InlineKeyboardButton("❌ Rad etish", callback_data=f"adm_reject_{order_id}")
        ]
    ])
    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=f"🆕 Yangi Buyurtma!\n\n🆔 ID: {order_id}\n👤 User ID: {user_id}\n📦 Mahsulot: {item_name}\n💵 Narxi: {price:,.0f} so'm",
        reply_markup=admin_keyboard
    )

# --- ADMIN BUYURTMANI TASDIQLASHI ---
async def admin_order_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, action, order_id = query.data.split("_")
    order_id = int(order_id)

    cursor.execute("SELECT user_id, item_name, price, status FROM orders WHERE order_id = ?", (order_id,))
    order = cursor.fetchone()
    
    if not order or order[3] != 'Kutilmoqda':
        await query.edit_message_text("Ushbu buyurtma ko'rib chiqilgan.")
        return

    user_id, item_name, price, status = order

    if action == "accept":
        cursor.execute("UPDATE orders SET status = 'Bajarildi' WHERE order_id = ?", (order_id,))
        conn.commit()
        await query.edit_message_text(f"✅ Buyurtma #{order_id} qabul qilindi.")
        await context.bot.send_message(user_id, f"🎉 Sizning #{order_id} raqamli buyurtmangiz muvaffaqiyatli bajarildi!")

    elif action == "reject":
        cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (price, user_id))
        cursor.execute("UPDATE orders SET status = 'Bekor qilindi' WHERE order_id = ?", (order_id,))
        conn.commit()
        await query.edit_message_text(f"❌ Buyurtma #{order_id} bekor qilindi.")
        await context.bot.send_message(user_id, f"⚠️ Sizning #{order_id} raqamli buyurtmangiz bekor qilindi. Pul balansingizga qaytarildi.")

# --- CANCEL ---
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Jarayon bekor qilindi.", reply_markup=main_keyboard())
    return ConversationHandler.END

# --- BOTNI ISHGA TUSHIRISH ---
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Regex("^💳 Balans to'ldirish$"), fill_balance))
    app.add_handler(MessageHandler(filters.Regex("^📊 Statistika$"), show_stats))
    app.add_handler(MessageHandler(filters.Regex("^👤 Balans va Profil$"), show_profile))
    app.add_handler(MessageHandler(filters.Regex("^🛍️ Buyurtma berish$"), order_start))
    
    app.add_handler(MessageHandler(filters.PHOTO, handle_receipt_photo))

    app.add_handler(CallbackQueryHandler(category_callback, pattern="^cat_"))
    app.add_handler(CallbackQueryHandler(process_buy, pattern="^buy_"))
    app.add_handler(CallbackQueryHandler(admin_order_action, pattern="^adm_"))

    pay_approve_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(approve_payment_callback, pattern="^pay_approve_")],
        states={
            ADMIN_APPROVE_PAYMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_payment_amount)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    transfer_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^💸 Pul o'tkazish$"), transfer_start)],
        states={
            TRANSFER_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, transfer_get_user)],
            TRANSFER_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, transfer_get_amount)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    check_order_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🔍 Buyurtmani tekshirish$"), check_order_start)],
        states={
            CHECK_ORDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, check_order_process)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    use_promo_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🎁 Promokod$"), use_promo_start)],
        states={
            USE_PROMO: [MessageHandler(filters.TEXT & ~filters.COMMAND, use_promo_process)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    add_promo_conv = ConversationHandler(
        entry_points=[CommandHandler("addpromo", add_promo_start)],
        states={
            PROMO_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_promo_code)],
            PROMO_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_promo_amount)],
            PROMO_LIMIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_promo_limit)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    manual_add_conv = ConversationHandler(
        entry_points=[CommandHandler("addbalance", manual_add_start)],
        states={
            MANUAL_ADD_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, manual_add_user)],
            MANUAL_ADD_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, manual_add_amount)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    manual_sub_conv = ConversationHandler(
        entry_points=[CommandHandler("subbalance", manual_sub_start)],
        states={
            MANUAL_SUB_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, manual_sub_user)],
            MANUAL_SUB_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, manual_sub_amount)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    app.add_handler(pay_approve_conv)
    app.add_handler(transfer_conv)
    app.add_handler(check_order_conv)
    app.add_handler(use_promo_conv)
    app.add_handler(add_promo_conv)
    app.add_handler(manual_add_conv)
    app.add_handler(manual_sub_conv)

    print("Bot muvaffaqiyatli ishga tushdi...")
    app.run_polling()

if __name__ == "__main__":
    main()
