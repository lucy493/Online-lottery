import json
import logging
import os
import random
import time
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
    return "Bot is alive and running 24/7!"

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
pending_deposits = {}
pending_withdrawals = {}
main_wallets = {}    # uid_str -> balance (int)
winning_wallets = {} # uid_str -> balance (int)
users = set()
settings = DEFAULT_SETTINGS.copy()
user_scratch_cards = {} # uid_str -> card_info
user_states = {}        # uid_str -> state_name

def save_data():
    data = {
        "pending_deposits": pending_deposits,
        "pending_withdrawals": pending_withdrawals,
        "main_wallets": main_wallets,
        "winning_wallets": winning_wallets,
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
    global pending_deposits, pending_withdrawals, main_wallets, winning_wallets, users, settings, user_scratch_cards
    if not DATA_FILE.exists():
        return
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)
            pending_deposits = data.get("pending_deposits", {})
            pending_withdrawals = data.get("pending_withdrawals", {})
            main_wallets = data.get("main_wallets", {})
            winning_wallets = data.get("winning_wallets", {})
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
    m_bal = main_wallets.get(str(user_id), 0)
    w_bal = winning_wallets.get(str(user_id), 0)
    
    keyboard = [
        [InlineKeyboardButton(f"🎟️ ትኬት ግዛ ({settings['ticket_price']} ETB)", callback_data="buy_ticket")],
        [InlineKeyboardButton("💵 ዲፖዚት አድርግ (Deposit)", callback_data="deposit")],
        [InlineKeyboardButton(f"👛 Wallet (Main: {m_bal} | Win: {w_bal})", callback_data="my_wallet")],
        [InlineKeyboardButton("🏆 ሽልማት ተቀበል", callback_data="withdraw")],
        [InlineKeyboardButton("💳 የክፍያ መረጃ", callback_data="payment_info")],
    ]
    if user_id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("⚙️ Admin Panel", callback_data="admin_panel")])
    return InlineKeyboardMarkup(keyboard)

def admin_menu():
    keyboard = [
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
    uid_str = str(user.id)
    users.add(user.id)
    
    if uid_str not in main_wallets: main_wallets[uid_str] = 0
    if uid_str not in winning_wallets: winning_wallets[uid_str] = 0
    save_data()
    
    await update.message.reply_text(
        f"👋 ሰላም {user.first_name}!\n\n🎰 **ወደ Scratch & Win (ፋቅ ፋቅ) ሎተሪ እንኳን በደህና መጡ!**\n\n"
        f"🎟️ የትኬት ዋጋ: **{settings['ticket_price']} ETB**\n"
        f"💵 Main Wallet: **{main_wallets[uid_str]} ETB**\n"
        f"🏆 Winning Wallet: **{winning_wallets[uid_str]} ETB**\n\n"
        "👇 ከታች ያለውን ሜኑ ይጠቀሙ፦",
        reply_markup=main_menu(user.id),
        parse_mode="Markdown"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid_str = str(user.id)
    state = user_states.get(uid_str)

    # Deposit Amount Input
    if state == "WAITING_DEPOSIT_AMOUNT" and update.message.text:
        try:
            amount = int(update.message.text.strip())
            if amount < 10:
                await update.message.reply_text("❌ አነስተኛው የዲፖዚት መጠን 10 ETB ነው። እባክዎን በድጋሚ ያስገቡ፦")
                return
            
            user_states[uid_str] = f"WAITING_DEPOSIT_RECEIPT:{amount}"
            await update.message.reply_text(
                f"💳 **የ {amount} ETB ዲፖዚት ጥያቄ**\n\n"
                f"{settings['payment_info']}\n\n"
                f"📸 እባክዎን የ **{amount} ETB** ክፍያ ፈፅመው የደረሰኙን Screenshot አሁን ይላኩ።",
                parse_mode="Markdown"
            )
        except ValueError:
            await update.message.reply_text("❌ እባክዎን ትክክለኛ ቁጥር ብቻ ያስገቡ (ለምሳሌ፦ 50 ወይም 100)፦")
        return

    # Deposit Receipt Photo
    if update.message.photo and state and state.startswith("WAITING_DEPOSIT_RECEIPT:"):
        amount = int(state.split(":")[1])
        photo_id = update.message.photo[-1].file_id
        
        pending_deposits[uid_str] = {
            "user_id": user.id,
            "name": user.first_name,
            "username": user.username or "",
            "amount": amount,
            "photo_id": photo_id,
        }
        user_states.pop(uid_str, None)
        save_data()

        keyboard = [
            [
                InlineKeyboardButton("✅ APPROVE DEPOSIT", callback_data=f"dep_approve:{user.id}"),
                InlineKeyboardButton("❌ REJECT", callback_data=f"dep_reject:{user.id}"),
            ]
        ]
        caption = (
            "📥 **NEW WALLET DEPOSIT REQUEST**\n\n"
            f"👤 Name: {user.first_name}\n"
            f"🆔 User ID: `{user.id}`\n"
            f"💰 Requested Amount: **{amount} ETB**"
        )
        await context.bot.send_photo(
            chat_id=ADMIN_ID,
            photo=photo_id,
            caption=caption,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        await update.message.reply_text(
            f"✅ **የ {amount} ETB ዲፖዚት ደረሰኝዎ ደርሶናል!**\n\n⏳ Admin ክፍያውን እያረጋገጠው ነው። ሲጸድቅ ወደ Main Walletዎ ገቢ ይሆናል።",
            parse_mode="Markdown",
            reply_markup=main_menu(user.id)
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
        m_bal = main_wallets.get(uid_str, 0)
        w_bal = winning_wallets.get(uid_str, 0)
        text = (
            f"👛 **የእኔ WALLET**\n\n"
            f"💵 **Main Wallet (የጥሬ ብር):** {m_bal} ETB\n"
            f"🏆 **Winning Wallet (የሽልማት):** {w_bal} ETB\n\n"
            "💡 *ከMain Wallet ላይ ትኬት መግዛት ይችላሉ። ያሸነፉትን ሽልማት ደግሞ መቀበል ይችላሉ።*"
        )
        keyboard = [
            [InlineKeyboardButton("💵 ዲፖዚት አድርግ", callback_data="deposit")],
            [InlineKeyboardButton("🎟️ ትኬት ግዛ", callback_data="buy_ticket")],
            [InlineKeyboardButton("🏆 ሽልማት ተቀበል", callback_data="withdraw")],
            [InlineKeyboardButton("🔙 Menu", callback_data="menu")]
        ]
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "deposit":
        user_states[uid_str] = "WAITING_DEPOSIT_AMOUNT"
        await query.edit_message_text(
            "💵 **ወደ Main Wallet ገንዘብ ለማስገባት**\n\nየሚልኩትን የብር መጠን በቁጥር ያስገቡ (ለምሳሌ፦ 50, 100, 200)፦",
            parse_mode="Markdown"
        )

    elif data == "buy_ticket":
        if not settings["game_open"]:
            await query.edit_message_text("🔴 **ጨዋታው ለጊዜው ተዘጋቷል።**", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", callback_data="menu")]]))
            return
        
        m_bal = main_wallets.get(uid_str, 0)
        price = settings["ticket_price"]

        if m_bal < price:
            await query.edit_message_text(
                f"❌ **Main Wallet ላይ በቂ ሂሳብ የለዎትም!**\n\n"
                f"🎟️ የትኬት ዋጋ: **{price} ETB**\n"
                f"💵 የእርስዎ Main Wallet: **{m_bal} ETB**\n\n"
                "እባክዎን በመጀመሪያ ዲፖዚት ያድርጉ።",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("💵 ዲፖዚት አድርግ", callback_data="deposit")],
                    [InlineKeyboardButton("🔙 Menu", callback_data="menu")]
                ])
            )
            return

        # Deduct 10 ETB from Main Wallet
        main_wallets[uid_str] = m_bal - price
        res_type, amt = generate_prize()
        user_scratch_cards[uid_str] = {"result_type": res_type, "amount": amt}
        save_data()

        keyboard = [[InlineKeyboardButton("🪙 ካርዱን ፍቅ አድርግ", callback_data="scratch")]]
        scratch_msg = (
            "🎉 **ትኬት ተቆርጧል!**\n\n"
            "🎟️ **የእርስዎ የሎተሪ ካርድ ተዘጋጅቷል፦**\n\n"
            "▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒\n"
            "▒▒▒▒ SCRATCH ▒▒▒▒\n"
            "▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒\n\n"
            "👇 *ውጤቱን ለማየት ከታች ያለውን ቁልፍ ይጫኑ!*"
        )
        await query.edit_message_text(scratch_msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "withdraw":
        w_bal = winning_wallets.get(uid_str, 0)
        if w_bal <= 0:
            await query.edit_message_text("❌ **Winning Wallet ላይ የተቀመጠ አሸናፊ ሂሳብ/ሽልማት የለዎትም።**", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", callback_data="menu")]]))
            return

        # Notify Admin Inbox
        username = f"@{query.from_user.username}" if query.from_user.username else "የለውም"
        admin_alert = (
            "🏆 **NEW PRIZE CLAIM REQUEST**\n\n"
            f"👤 ደንበኛ: {query.from_user.first_name}\n"
            f"🔗 Telegram Username: {username}\n"
            f"🆔 User ID: `{user_id}`\n"
            f"🎁 ያሸነፈው ሽልማት/ካርድ: **{w_bal} ETB**\n\n"
            "👉 *እባክዎን ደንበኛውን በግል አናግረው የስልክ ቁጥሩን በመቀበል አስተናግዱት!*"
        )
        await context.bot.send_message(chat_id=ADMIN_ID, text=admin_alert, parse_mode="Markdown")

        await query.edit_message_text(
            f"✅ **የሽልማት ጥያቄዎ ለAdmin ተልኳል!**\n\n"
            f"🏆 ያሸነፉት መጠን: **{w_bal} ETB**\n\n"
            "👨‍💻 Admin በቅርቡ በግል የቴሌግራም መልእክት አናግሮዎት በስልክ ቁጥርዎ ያስተናግድዎታል።",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 ወደ ዋና ሜኑ", callback_data="menu")]])
        )

    elif data == "payment_info":
        keyboard = [[InlineKeyboardButton("🔙 Menu", callback_data="menu")]]
        await query.edit_message_text(
            f"💳 **የክፍያ መረጃ**\n\n{settings['payment_info']}\n\n💡 ዲፖዚት ለማድረግ ከዋናው ሜኑ **'💵 ዲፖዚት አድርግ'** የሚለውን ይጫኑ።",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    elif data == "scratch":
        card_info = user_scratch_cards.pop(uid_str, None)
        if not card_info:
            await query.edit_message_text("⚠️ ለመፈቀቅ የተዘጋጀ ካርድ አልተገኘም ወይም አስቀድመው ፈቅደውታል።", reply_markup=main_menu(user_id))
            return

        result_type, amount = card_info["result_type"], card_info["amount"]

        if result_type == "LOSE":
            text = (
                "🎰 **SCRATCH RESULT** 🎰\n\n"
                "░▒▓█ **[ ❌ እንደገና ይሞክሩ ]** █▓▒░\n\n"
                "ለጥቂት ነው! በዚህ ጊዜ አልወጣም።\nመልካም እድል ለቀጣይ! 🍀"
            )
        else:
            # Add to Winning Wallet
            cur_w = winning_wallets.get(uid_str, 0)
            winning_wallets[uid_str] = cur_w + amount
            text = (
                f"🎉🎉 **እንኳን ደስ አለዎት!** 🎉🎉\n\n"
                f"🏆 **የ {amount} ETB ሽልማት አሸንፈዋል!**\n\n"
                f"🏆 **{amount} ETB** ወደ **Winning Wallet** ተጨምሯል!\n"
                f"💰 አጠቃላይ የሽልማት ቦርሳዎ: **{winning_wallets[uid_str]} ETB**"
            )
        save_data()
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 ወደ ዋና ሜኑ", callback_data="menu")]]))

    # Admin Panel Actions
    elif data == "admin_panel":
        if not is_admin(user_id): return
        await query.edit_message_text("⚙️ **ADMIN PANEL**", parse_mode="Markdown", reply_markup=admin_menu())

    elif data == "toggle_game":
        if not is_admin(user_id): return
        settings["game_open"] = not settings["game_open"]
        save_data()
        await query.edit_message_text(f"Status: **{'🟢 OPEN' if settings['game_open'] else '🔴 CLOSED'}**", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel")]]))

    elif data == "admin_users":
        if not is_admin(user_id): return
        await query.edit_message_text(f"👥 አጠቃላይ ተጠቃሚዎች፦ **{len(users)}**", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel")]]))

    # Approve Deposit
    elif data.startswith("dep_approve:") or data.startswith("dep_reject:"):
        if not is_admin(user_id): return
        action, target_uid_str = data.split(":")
        dep_data = pending_deposits.pop(target_uid_str, None)
        if not dep_data:
            await query.edit_message_caption("⚠️ Request not found.")
            return

        target_uid = int(target_uid_str)
        if action == "dep_approve":
            amt = dep_data["amount"]
            main_wallets[target_uid_str] = main_wallets.get(target_uid_str, 0) + amt
            save_data()
            await context.bot.send_message(
                chat_id=target_uid,
                text=f"✅ **የ {amt} ETB ዲፖዚትዎ ጸድቋል!**\n\n💵 Main Wallet: **{main_wallets[target_uid_str]} ETB**\n\nአሁን የፋቅ ፋቅ ትኬት መግዛት ይችላሉ!",
                parse_mode="Markdown",
                reply_markup=main_menu(target_uid)
            )
            await query.edit_message_caption(f"✅ **DEPOSIT APPROVED ({amt} ETB)**\n👤 {dep_data['name']}")
        else:
            save_data()
            await context.bot.send_message(chat_id=target_uid, text="❌ የዲፖዚት ደረሰኝዎ አልተቀበለም።", reply_markup=main_menu(target_uid))
            await query.edit_message_caption(f"❌ **DEPOSIT REJECTED**\n👤 {dep_data['name']}")

# =========================================================
# 🎬 MAIN FUNCTION (WITH AUTO-RESTART LOOP)
# =========================================================
def main():
    load_data()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO | filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(callback_router))

    print("🚀 Dual-Wallet Scratch & Win Lottery Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    while True:
        try:
            main()
        except Exception as e:
            logger.error(f"Bot disconnected: {e}. Restarting in 5 seconds...")
            time.sleep(5)
