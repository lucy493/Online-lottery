import json
import logging
import os
import random
from pathlib import Path
from threading import Thread
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# =========================================================
# 🌐 FLASK KEEP-ALIVE SERVER (FOR RENDER FREE WEB SERVICE)
# =========================================================
app = Flask('')

@app.route('/')
def home():
    return "Bot is alive and running!"

def run():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))

def keep_alive():
    t = Thread(target=run)
    t.daemon = True
    t.start()

keep_alive()

# =========================================================
# ⚙️ CONFIGURATION
# =========================================================
BOT_TOKEN = "8956746553:AAH3rFAWSYPMveVRGCOoDIC8-0gRpIAnk_w"
ADMIN_ID = 1465416690

DATA_FILE = Path("scratch_data.json")

DEFAULT_SETTINGS = {
    "ticket_price": "10 ETB",
    "payment_info": (
        "🏦 Bank: የኢትዮጵያ ንግድ ባንክ (CBE)\n"
        "🔢 Account: 1000421183458\n"
        "👤 Name: Nuru Adem\n\n"
        "📱 Telebirr: 0981751543"
    ),
    "game_open": True,
}

# =========================================================
# 📝 LOGGING
# =========================================================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# =========================================================
# 💾 DATA STORAGE & PERSISTENCE
# =========================================================
# Stock format: {"10": ["code1", "code2"], "50": ["code3"], "100": ["code4"]}
card_stock = {"10": [], "50": [], "100": []}
pending_payments = {}
users = set()
settings = DEFAULT_SETTINGS.copy()
user_scratch_cards = {} # uid -> card_info

def save_data():
    data = {
        "card_stock": card_stock,
        "pending_payments": pending_payments,
        "users": list(users),
        "settings": settings,
        "user_scratch_cards": user_scratch_cards,
    }
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=4)
    except Exception as e:
        logger.error(f"Save error: {e}")

def load_data():
    global card_stock, pending_payments, users, settings, user_scratch_cards
    if not DATA_FILE.exists():
        return
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)
            card_stock = data.get("card_stock", {"10": [], "50": [], "100": []})
            pending_payments = data.get("pending_payments", {})
            users = set(data.get("users", []))
            settings = DEFAULT_SETTINGS.copy()
            settings.update(data.get("settings", {}))
            user_scratch_cards = data.get("user_scratch_cards", {})
    except Exception as e:
        logger.error(f"Load error: {e}")

def is_admin(update: Update):
    user = update.effective_user
    return user is not None and user.id == ADMIN_ID

# =========================================================
# 🎛️ MENUS
# =========================================================
def main_menu():
    keyboard = [
        [InlineKeyboardButton("🎟️ የ10 ብር ትኬት ግዛ", callback_data="buy")],
        [InlineKeyboardButton("💳 የክፍያ መረጃ", callback_data="payment_info")],
    ]
    return InlineKeyboardMarkup(keyboard)

def admin_menu():
    keyboard = [
        [InlineKeyboardButton("📦 የካርድ ስቶክ (Stock)", callback_data="admin_stock")],
        [InlineKeyboardButton("🟢/🔴 ጨዋታ ON/OFF", callback_data="toggle_game")],
        [InlineKeyboardButton("👥 የተጠቃሚዎች ብዛት", callback_data="admin_users")],
    ]
    return InlineKeyboardMarkup(keyboard)

# =========================================================
# 🚀 CORE HANDLERS
# =========================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    users.add(user.id)
    save_data()
    
    if user.id == ADMIN_ID:
        keyboard = [
            [InlineKeyboardButton("⚙️ Admin Panel", callback_data="admin_panel")],
            [InlineKeyboardButton("🎟️ User Menu", callback_data="menu")],
        ]
        await update.message.reply_text(
            "👋 **Admin እንኳን ደህና መጡ!**",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
    else:
        await update.message.reply_text(
            f"👋 ሰላም {user.first_name}!\n\n🎰 **ወደ Scratch & Win (ፋቅ ፋቅ) ሎተሪ እንኳን በደህና መጡ!**\n\n🎟️ የትኬት ዋጋ: **{settings['ticket_price']}**\n🏆 ከፍተኛ ሽልማት: **100 ETB Card**",
            reply_markup=main_menu(),
        )

# ካርድ ስቶክ ማስገቢያ ኮማንድ ለምሳሌ፦ /addcard 10 123456789
async def add_card_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("⚠️ አጠቃቀም፦ `/addcard <10/50/100> <የካርድ_ቁጥር>`", parse_mode="Markdown")
        return
    amount, code = args[0], args[1]
    if amount in card_stock:
        card_stock[amount].append(code)
        save_data()
        await update.message.reply_text(f"✅ የ {amount} ብር ካርድ ተጨምሯል!\nየአሁኑ ስቶክ፦ {len(card_stock[amount])} ካርድ")
    else:
        await update.message.reply_text("❌ እባክዎን የካርድ መጠን 10, 50 ወይም 100 ይምረጡ።")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    users.add(user_id)

    if not settings["game_open"]:
        await update.message.reply_text("🔴 ጨዋታው ለጊዜው ተዘጋቷል።")
        return
    if str(user_id) in pending_payments:
        await update.message.reply_text("⏳ ደረሰኝዎ አስቀድሞ ለAdmin ተልኳል፤ እባክዎን ትንሽ ይጠብቁ።")
        return

    photo_id = update.message.photo[-1].file_id
    pending_payments[str(user_id)] = {
        "user_id": user_id,
        "name": user.first_name,
        "username": user.username or "",
        "photo_id": photo_id,
    }
    save_data()

    username = f"@{user.username}" if user.username else "None"
    keyboard = [
        [
            InlineKeyboardButton("✅ APPROVE", callback_data=f"approve:{user_id}"),
            InlineKeyboardButton("❌ REJECT", callback_data=f"reject:{user_id}"),
        ]
    ]
    caption = (
        "📥 **NEW TICKET PAYMENT**\n\n"
        f"👤 Name: {user.first_name}\n"
        f"🔗 Username: {username}\n"
        f"🆔 User ID: `{user_id}`\n\n"
        f"💰 Amount: {settings['ticket_price']}"
    )
    await context.bot.send_photo(
        chat_id=ADMIN_ID,
        photo=photo_id,
        caption=caption,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    await update.message.reply_text(
        "✅ **ደረሰኝዎ ደርሶናል!**\n\n⏳ Admin ክፍያውን እያረጋገጠው ነው።\nከጸደቀ በኋላ የሎተሪ ካርድዎ ይላክልዎታል።",
        parse_mode="Markdown",
    )

# =========================================================
# 🎲 SCRATCH LOGIC (25% WIN RATE)
# =========================================================
def generate_prize():
    # 25% win, 75% lose
    # From wins: 80% -> 10 ETB, 16% -> 50 ETB, 4% -> 100 ETB
    rand = random.random()
    if rand > 0.25:
        return "LOSE", 0
    
    # User won
    prize_rand = random.random()
    if prize_rand <= 0.80:
        return "WIN", "10"
    elif prize_rand <= 0.96:
        return "WIN", "50"
    else:
        return "WIN", "100"

# =========================================================
# 🔄 CALLBACK ROUTER
# =========================================================
async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    if data == "menu":
        await query.edit_message_text("🏠 **MAIN MENU**", parse_mode="Markdown", reply_markup=main_menu())
    elif data == "buy":
        if not settings["game_open"]:
            await query.edit_message_text("🔴 **ጨዋታው ለጊዜው ተዘጋቷል።**", parse_mode="Markdown")
            return
        keyboard = [
            [InlineKeyboardButton("💳 የክፍያ መረጃ", callback_data="payment_info")],
            [InlineKeyboardButton("🔙 Menu", callback_data="menu")],
        ]
        await query.edit_message_text(
            f"🎟️ **ትኬት ለመግዛት**\n\n💰 ዋጋ: **{settings['ticket_price']}**\n\n1️⃣ የክፍያ መረጃን ይመልከቱ\n2️⃣ 10 ብር ክፍያ ይፈጽሙ\n3️⃣ የክፍያ ደረሰኝ Screenshot ይላኩ",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
    elif data == "payment_info":
        keyboard = [[InlineKeyboardButton("🔙 Menu", callback_data="menu")]]
        await query.edit_message_text(
            f"💳 **የክፍያ መረጃ**\n\n💰 ዋጋ: **{settings['ticket_price']}**\n\n{settings['payment_info']}\n\n📸 ክፍያ ካደረጉ በኋላ ደረሰኙን Screenshot አድርገው እዚህ ይላኩ።",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    # Scratch Action
    elif data == "scratch":
        card_info = user_scratch_cards.pop(str(user_id), None)
        if not card_info:
            await query.edit_message_text("⚠️ ለመፈቀቅ የተዘጋጀ ካርድ አልተገኘም ወይም አስቀድመው ፈቅደውታል።")
            return

        result_type, amount = card_info["result_type"], card_info["amount"]

        if result_type == "LOSE":
            text = (
                "🎰 **SCRATCH RESULT** 🎰\n\n"
                "░▒▓█ **[ ❌ እንደገና ይሞክሩ ]** █▓▒░\n\n"
                "ለጥቂት ነው! በዚህ ጊዜ አልወጣም።\nመልካም እድል ለቀጣይ! 🍀"
            )
        else:
            # Try to get code from stock
            if card_stock.get(amount) and len(card_stock[amount]) > 0:
                code = card_stock[amount].pop(0)
                text = (
                    f"🎉🎉 **እንኳን ደስ አለዎት!** 🎉🎉\n\n"
                    f"🏆 **የ {amount} ETB የሞባይል ካርድ አሸንፈዋል!**\n\n"
                    f"🔢 **የካርድ ቁጥር፦** `{code}`"
                )
            else:
                text = (
                    f"🎉🎉 **እንኳን ደስ አለዎት!** 🎉🎉\n\n"
                    f"🏆 **የ {amount} ETB የሞባይል ካርድ አሸንፈዋል!**\n\n"
                    f"⚠️ የካርድ ቁጥሩ በስቶክ ስለለቀቀ አድሚኑ በቅርቡ ይልክልዎታል።\n🆔 User ID: `{user_id}`"
                )
        save_data()
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🎟️ እንደገና ግዛ", callback_data="buy")]]))

    # Admin Panel
    elif data == "admin_panel":
        if user_id != ADMIN_ID: return
        await query.edit_message_text("⚙️ **ADMIN PANEL**", parse_mode="Markdown", reply_markup=admin_menu())
    elif data == "admin_stock":
        if user_id != ADMIN_ID: return
        msg = "📦 **CURRENT CARD STOCK**\n\n"
        msg += f"🔹 10 ETB: {len(card_stock.get('10', []))} ካርድ\n"
        msg += f"🔹 50 ETB: {len(card_stock.get('50', []))} ካርድ\n"
        msg += f"🔹 100 ETB: {len(card_stock.get('100', []))} ካርድ\n\n"
        msg += "💡 ካርድ ለመጨመር ኮማንድ ይጠቀሙ፦\n`/addcard 10 1234567890`"
        await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel")]]))
    elif data == "toggle_game":
        if user_id != ADMIN_ID: return
        settings["game_open"] = not settings["game_open"]
        save_data()
        await query.edit_message_text(f"Status: **{'🟢 OPEN' if settings['game_open'] else '🔴 CLOSED'}**", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel")]]))
    elif data == "admin_users":
        if user_id != ADMIN_ID: return
        await query.edit_message_text(f"👥 አጠቃላይ ተጠቃሚዎች፦ **{len(users)}**", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel")]]))

    # Approve / Reject
    elif data.startswith("approve:") or data.startswith("reject:"):
        if user_id != ADMIN_ID: return
        action, uid_str = data.split(":")
        uid = int(uid_str)
        u_data = pending_payments.pop(str(uid), None)
        if not u_data:
            await query.edit_message_caption("⚠️ Request not found.")
            return

        if action == "approve":
            res_type, amt = generate_prize()
            user_scratch_cards[str(uid)] = {"result_type": res_type, "amount": amt}
            save_data()

            keyboard = [[InlineKeyboardButton("🪙 ካርዱን ፍቅ አድርግ", callback_data="scratch")]]
            scratch_msg = (
                "🎉 **ክፍያዎ ጸድቋል!**\n\n"
                "🎟️ **የእርስዎ የሎተሪ ካርድ ተዘጋጅቷል፦**\n\n"
                "▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒\n"
                "▒▒▒▒ SCRATCH ▒▒▒▒\n"
                "▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒\n\n"
                "👇 *ውጤቱን ለማየት ከታች ያለውን ቁልፍ ይጫኑ!*"
            )
            await context.bot.send_message(chat_id=uid, text=scratch_msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
            await query.edit_message_caption(f"✅ **APPROVED & CARD SENT**\n👤 {u_data['name']}")
        else:
            save_data()
            await context.bot.send_message(chat_id=uid, text="❌ **የክፍያ ደረሰኝዎ አልተቀበለም።**", parse_mode="Markdown")
            await query.edit_message_caption(f"❌ **REJECTED**\n👤 {u_data['name']}")

# =========================================================
# 🎬 MAIN FUNCTION
# =========================================================
def main():
    load_data()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("addcard", add_card_cmd))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CallbackQueryHandler(callback_router))

    print("🚀 Scratch & Win Lottery Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()

    
