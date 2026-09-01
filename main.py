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
    "ticket_price": 10,
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
card_stock = {"10": [], "50": [], "100": []}
pending_payments = {}
pending_withdrawals = {}
wallets = {} # uid_str -> balance (int)
users = set()
settings = DEFAULT_SETTINGS.copy()
user_scratch_cards = {} # uid_str -> card_info
user_states = {} # uid_str -> state_name

def save_data():
    data = {
        "card_stock": card_stock,
        "pending_payments": pending_payments,
        "pending_withdrawals": pending_withdrawals,
        "wallets": wallets,
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
    global card_stock, pending_payments, pending_withdrawals, wallets, users, settings, user_scratch_cards
    if not DATA_FILE.exists():
        return
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)
            card_stock = data.get("card_stock", {"10": [], "50": [], "100": []})
            pending_payments = data.get("pending_payments", {})
            pending_withdrawals = data.get("pending_withdrawals", {})
            wallets = data.get("wallets", {})
            users = set(data.get("users", []))
            settings = DEFAULT_SETTINGS.copy()
            settings.update(data.get("settings", {}))
            user_scratch_cards = data.get("user_scratch_cards", {})
    except Exception as e:
        logger.error(f"Load error: {e}")

def is_admin(user_id):
    return user_id == ADMIN_ID

# =========================================================
# 🎛️ MENUS
# =========================================================
def main_menu(user_id):
    bal = wallets.get(str(user_id), 0)
    keyboard = [
        [InlineKeyboardButton("🎟️ ትኬት ግዛ (10 ETB)", callback_data="buy_bank")],
        [InlineKeyboardButton(f"🔄 በWallet ትኬት ግዛ ({bal} ETB አለዎት)", callback_data="buy_wallet")],
        [InlineKeyboardButton("👛 የእኔ Wallet", callback_data="my_wallet"), InlineKeyboardButton("📲 ካርድ/ሽልማት ተቀበል", callback_data="withdraw")],
        [InlineKeyboardButton("💳 የክፍያ መረጃ", callback_data="payment_info")],
    ]
    if user_id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("⚙️ Admin Panel", callback_data="admin_panel")])
    return InlineKeyboardMarkup(keyboard)

def admin_menu():
    keyboard = [
        [InlineKeyboardButton("📦 የካርድ ስቶክ (Stock)", callback_data="admin_stock")],
        [InlineKeyboardButton("🟢/🔴 ጨዋታ ON/OFF", callback_data="toggle_game")],
        [InlineKeyboardButton("👥 የተጠቃሚዎች ብዛት", callback_data="admin_users")],
        [InlineKeyboardButton("🔙 User Menu", callback_data="menu")],
    ]
    return InlineKeyboardMarkup(keyboard)

# =========================================================
# 🎲 SCRATCH LOGIC (25% WIN RATE)
# =========================================================
def generate_prize():
    rand = random.random()
    if rand > 0.25:
        return "LOSE", 0
    
    prize_rand = random.random()
    if prize_rand <= 0.80:
        return "WIN", 10
    elif prize_rand <= 0.96:
        return "WIN", 50
    else:
        return "WIN", 100

# =========================================================
# 🚀 CORE HANDLERS
# =========================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    users.add(user.id)
    if str(user.id) not in wallets:
        wallets[str(user.id)] = 0
    save_data()
    
    await update.message.reply_text(
        f"👋 ሰላም {user.first_name}!\n\n🎰 **ወደ Scratch & Win (ፋቅ ፋቅ) ሎተሪ እንኳን በደህና መጡ!**\n\n🎟️ የትኬት ዋጋ: **{settings['ticket_price']} ETB**\n🏆 ከፍተኛ ሽልማት: **100 ETB Card**\n\n👇 ከታች ያለውን ሜኑ ይጠቀሙ፦",
        reply_markup=main_menu(user.id),
        parse_mode="Markdown"
    )

async def add_card_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
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

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid_str = str(user.id)
    state = user_states.get(uid_str)

    # Text message for Withdrawal Phone Number
    if state == "WAITING_PHONE" and update.message.text:
        phone = update.message.text.strip()
        bal = wallets.get(uid_str, 0)
        
        if bal <= 0:
            await update.message.reply_text("❌ Wallet ላይ በቂ ሂሳብ የለዎትም።", reply_markup=main_menu(user.id))
            user_states.pop(uid_str, None)
            return

        pending_withdrawals[uid_str] = {"phone": phone, "amount": bal, "name": user.first_name}
        user_states.pop(uid_str, None)
        save_data()

        # Alert Admin
        keyboard = [
            [
                InlineKeyboardButton("✅ APPROVED & SENT", callback_data=f"wd_approve:{user.id}"),
                InlineKeyboardButton("❌ REJECT", callback_data=f"wd_reject:{user.id}"),
            ]
        ]
        admin_text = (
            "📲 **NEW CARD WITHDRAWAL REQUEST**\n\n"
            f"👤 Name: {user.first_name}\n"
            f"🆔 User ID: `{user.id}`\n"
            f"📱 Phone: `{phone}`\n"
            f"💰 Amount: **{bal} ETB**"
        )
        await context.bot.send_message(chat_id=ADMIN_ID, text=admin_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
        
        await update.message.reply_text(
            f"✅ **የካርድ መጠየቂያ ጥያቄዎ ተልኳል!**\n\n📱 ስልክ: `{phone}`\n💰 መጠን: **{bal} ETB**\n\n⏳ Admin በቅርቡ ካርዱን ይልክልዎታል።",
            parse_mode="Markdown",
            reply_markup=main_menu(user.id)
        )
        return

    # Photo Message for Deposit Receipts
    if update.message.photo:
        if not settings["game_open"]:
            await update.message.reply_text("🔴 ጨዋታው ለጊዜው ተዘጋቷል።")
            return
        if uid_str in pending_payments:
            await update.message.reply_text("⏳ ደረሰኝዎ አስቀድሞ ለAdmin ተልኳል፤ እባክዎን ትንሽ ይጠብቁ።")
            return

        photo_id = update.message.photo[-1].file_id
        pending_payments[uid_str] = {
            "user_id": user.id,
            "name": user.first_name,
            "photo_id": photo_id,
        }
        save_data()

        keyboard = [
            [
                InlineKeyboardButton("✅ APPROVE", callback_data=f"approve:{user.id}"),
                InlineKeyboardButton("❌ REJECT", callback_data=f"reject:{user.id}"),
            ]
        ]
        caption = (
            "📥 **NEW TICKET PAYMENT**\n\n"
            f"👤 Name: {user.first_name}\n"
            f"🆔 User ID: `{user.id}`\n"
            f"💰 Amount: {settings['ticket_price']} ETB"
        )
        await context.bot.send_photo(
            chat_id=ADMIN_ID,
            photo=photo_id,
            caption=caption,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        await update.message.reply_text(
            "✅ **ደረሰኝዎ ደርሶናል!**\n\n⏳ Admin ክፍያውን እያረጋገጠው ነው። ከጸደቀ በኋላ የሎተሪ ካርድዎ ይላክልዎታል።",
            parse_mode="Markdown",
        )

# =========================================================
# 🔄 CALLBACK ROUTER
# =========================================================
async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id
    uid_str = str(user_id)

    if data == "menu":
        user_states.pop(uid_str, None)
        await query.edit_message_text("🏠 **MAIN MENU**", parse_mode="Markdown", reply_markup=main_menu(user_id))
    
    elif data == "my_wallet":
        bal = wallets.get(uid_str, 0)
        text = (
            f"👛 **የእኔ WALLET**\n\n"
            f"💰 ያለው ሂሳብ: **{bal} ETB**\n\n"
            "💡 ያሸነፉትን ገንዘብ መልሰው ለትኬት መግዣነት መጠቀም ወይም ወደ ስልክዎ በካርድ መውሰድ ይችላሉ።"
        )
        keyboard = [
            [InlineKeyboardButton("🔄 በWallet ትኬት ግዛ", callback_data="buy_wallet")],
            [InlineKeyboardButton("📲 ካርድ/ሽልማት ተቀበል", callback_data="withdraw")],
            [InlineKeyboardButton("🔙 Menu", callback_data="menu")]
        ]
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "buy_bank":
        if not settings["game_open"]:
            await query.edit_message_text("🔴 **ጨዋታው ለጊዜው ተዘጋቷል።**", parse_mode="Markdown")
            return
        keyboard = [
            [InlineKeyboardButton("💳 የክፍያ መረጃ", callback_data="payment_info")],
            [InlineKeyboardButton("🔙 Menu", callback_data="menu")],
        ]
        await query.edit_message_text(
            f"🎟️ **ትኬት ለመግዛት**\n\n💰 ዋጋ: **{settings['ticket_price']} ETB**\n\n1️⃣ የክፍያ መረጃን ይመልከቱ\n2️⃣ 10 ብር ክፍያ ይፈጽሙ\n3️⃣ የክፍያ ደረሰኝ Screenshot ይላኩ",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    elif data == "buy_wallet":
        if not settings["game_open"]:
            await query.edit_message_text("🔴 **ጨዋታው ለጊዜው ተዘጋቷል።**", parse_mode="Markdown")
            return
        bal = wallets.get(uid_str, 0)
        price = settings["ticket_price"]
        if bal < price:
            await query.edit_message_text(
                f"❌ **Wallet ላይ በቂ ሂሳብ የለዎትም!**\n\n💰 የትኬት ዋጋ: **{price} ETB**\n👛 የእርስዎ Wallet: **{bal} ETB**\n\nእባክዎን በባንክ/ቴሌብር ክፍያ ፈጽመው ትኬት ይግዙ።",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🎟️ በባንክ/ቴሌብር ግዛ", callback_data="buy_bank")], [InlineKeyboardButton("🔙 Menu", callback_data="menu")]])
            )
            return

        # Deduct wallet & give scratch card
        wallets[uid_str] = bal - price
        res_type, amt = generate_prize()
        user_scratch_cards[uid_str] = {"result_type": res_type, "amount": amt}
        save_data()

        keyboard = [[InlineKeyboardButton("🪙 ካርዱን ፍቅ አድርግ", callback_data="scratch")]]
        scratch_msg = (
            "🎉 **ትኬት በWallet አግኝተዋል!**\n\n"
            "🎟️ **የእርስዎ የሎተሪ ካርድ ተዘጋጅቷል፦**\n\n"
            "▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒\n"
            "▒▒▒▒ SCRATCH ▒▒▒▒\n"
            "▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒\n\n"
            "👇 *ውጤቱን ለማየት ከታች ያለውን ቁልፍ ይጫኑ!*"
        )
        await query.edit_message_text(scratch_msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "withdraw":
        bal = wallets.get(uid_str, 0)
        if bal <= 0:
            await query.edit_message_text("❌ **Wallet ላይ የተቀመጠ አሸናፊ ሂሳብ የለዎትም።**", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", callback_data="menu")]]))
            return
        user_states[uid_str] = "WAITING_PHONE"
        await query.edit_message_text(
            f"📲 **ካርድ/ሽልማት ለመቀበል**\n\n💰 በWallet የሚወጣ ሂሳብ: **{bal} ETB**\n\n👇 **እባክዎን ካርዱ እንዲላክበት የሚፈልጉትን የስልክ ቁጥር በፅሁፍ ይላኩ፦**",
            parse_mode="Markdown"
        )

    elif data == "payment_info":
        keyboard = [[InlineKeyboardButton("🔙 Menu", callback_data="menu")]]
        await query.edit_message_text(
            f"💳 **የክፍያ መረጃ**\n\n💰 ዋጋ: **{settings['ticket_price']} ETB**\n\n{settings['payment_info']}\n\n📸 ክፍያ ካደረጉ በኋላ ደረሰኙን Screenshot አድርገው እዚህ ይላኩ።",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    elif data == "scratch":
        card_info = user_scratch_cards.pop(uid_str, None)
        if not card_info:
            await query.edit_message_text("⚠️ ለመፈቀቅ የተዘጋጀ ካርድ አልተገኘም ወይም አስቀድመው ፈቅደውታለህ።", reply_markup=main_menu(user_id))
            return

        result_type, amount = card_info["result_type"], card_info["amount"]

        if result_type == "LOSE":
            text = (
                "🎰 **SCRATCH RESULT** 🎰\n\n"
                "░▒▓█ **[ ❌ እንደገና ይሞክሩ ]** █▓▒░\n\n"
                "ለጥቂት ነው! በዚህ ጊዜ አልወጣም።\nመልካም እድል ለቀጣይ! 🍀"
            )
        else:
            # Add to user wallet
            cur_bal = wallets.get(uid_str, 0)
            wallets[uid_str] = cur_bal + amount
            text = (
                f"🎉🎉 **እንኳን ደስ አለዎት!** 🎉🎉\n\n"
                f"🏆 **የ {amount} ETB ሽልማት አሸንፈዋል!**\n\n"
                f"👛 **{amount} ETB** አውቶማቲክ ወደ Walletዎ ተጨምሯል!\n"
                f"💰 በአሁኑ ወቅት በWalletዎ: **{wallets[uid_str]} ETB** አለዎት።"
            )
        save_data()
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 ወደ ዋና ሜኑ", callback_data="menu")]]))

    # Admin Panel Actions
    elif data == "admin_panel":
        if not is_admin(user_id): return
        await query.edit_message_text("⚙️ **ADMIN PANEL**", parse_mode="Markdown", reply_markup=admin_menu())

    elif data == "admin_stock":
        if not is_admin(user_id): return
        msg = "📦 **CURRENT CARD STOCK**\n\n"
        msg += f"🔹 10 ETB: {len(card_stock.get('10', []))} ካርድ\n"
        msg += f"🔹 50 ETB: {len(card_stock.get('50', []))} ካርድ\n"
        msg += f"🔹 100 ETB: {len(card_stock.get('100', []))} ካርድ\n\n"
        msg += "💡 ካርድ ለመጨመር ኮማንድ ይጠቀሙ፦\n`/addcard 10 1234567890`"
        await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel")]]))

    elif data == "toggle_game":
        if not is_admin(user_id): return
        settings["game_open"] = not settings["game_open"]
        save_data()
        await query.edit_message_text(f"Status: **{'🟢 OPEN' if settings['game_open'] else '🔴 CLOSED'}**", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel")]]))

    elif data == "admin_users":
        if not is_admin(user_id): return
        await query.edit_message_text(f"👥 አጠቃላይ ተጠቃሚዎች፦ **{len(users)}**", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel")]]))

    # Approve/Reject Payment
    elif data.startswith("approve:") or data.startswith("reject:"):
        if not is_admin(user_id): return
        action, target_uid_str = data.split(":")
        target_uid = int(target_uid_str)
        u_data = pending_payments.pop(target_uid_str, None)
        if not u_data:
            await query.edit_message_caption("⚠️ Request not found.")
            return

        if action == "approve":
            res_type, amt = generate_prize()
            user_scratch_cards[target_uid_str] = {"result_type": res_type, "amount": amt}
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
            await context.bot.send_message(chat_id=target_uid, text=scratch_msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
            await query.edit_message_caption(f"✅ **APPROVED**\n👤 {u_data['name']}")
        else:
            save_data()
            await context.bot.send_message(chat_id=target_uid, text="❌ **የክፍያ ደረሰኝዎ አልተቀበለም።**", parse_mode="Markdown")
            await query.edit_message_caption(f"❌ **REJECTED**\n👤 {u_data['name']}")

    # Approve/Reject Withdrawal Request
    elif data.startswith("wd_approve:") or data.startswith("wd_reject:"):
        if not is_admin(user_id): return
        action, target_uid_str = data.split(":")
        wd_data = pending_withdrawals.pop(target_uid_str, None)
        if not wd_data:
            await query.edit_message_text("⚠️ Request not found.")
            return

        target_uid = int(target_uid_str)
        if action == "wd_approve":
            wallets[target_uid_str] = 0 # reset wallet balance
            save_data()
            await context.bot.send_message(
                chat_id=target_uid,
                text=f"🎁 **የ {wd_data['amount']} ETB የሞባይል ካርድ/ጥቅል ወደ `{wd_data['phone']}` ተልኮልዎታል!**\n\nእናመሰግናለን! 🍀",
                parse_mode="Markdown",
                reply_markup=main_menu(target_uid)
            )
            await query.edit_message_text(f"✅ **WITHDRAWAL SENT**\n📱 Phone: `{wd_data['phone']}`\n💰 Amount: {wd_data['amount']} ETB", parse_mode="Markdown")
        else:
            save_data()
            await context.bot.send_message(chat_id=target_uid, text="❌ የካርድ መጠየቂያ ጥያቄዎ አልተቀበለም።", reply_markup=main_menu(target_uid))
            await query.edit_message_text(f"❌ **WITHDRAWAL REJECTED**\n👤 {wd_data['name']}")

# =========================================================
# 🎬 MAIN FUNCTION
# =========================================================
def main():
    load_data()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("addcard", add_card_cmd))
    app.add_handler(MessageHandler(filters.PHOTO | filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(callback_router))

    print("🚀 Scratch & Win Lottery Bot (with Wallet) is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
