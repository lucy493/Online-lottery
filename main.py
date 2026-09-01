import os
from threading import Thread
from flask import Flask

app = Flask('')

@app.route('/')
def home():
    return "Bot is alive!"

def run():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))

def keep_alive():
    t = Thread(target=run)
    t.daemon = True
    t.start()

keep_alive()

import json
import logging
import secrets
from pathlib import Path
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# =========================================================
# CONFIGURATION
# =========================================================
# 1. የቦት ቶከን በትክክል ተስተካክሏል
BOT_TOKEN = "8956746553:AAH3rFAWSYPMveVRGCOoDIC8-0gRpIAnk_w"  

# 2. የAdmin ID ቁጥር
ADMIN_ID = 1465416690              

DATA_FILE = Path("lottery_data.json")

# =========================================================
# DEFAULT SETTINGS
# =========================================================
DEFAULT_SETTINGS = {
    "ticket_price": "25 ETB",
    "max_tickets": 10,
    # 3. የባንክ እና የቴሌብር መረጃ
    "payment_info": (
        "🏦 Bank: የኢትዮጵያ ንግድ ባንክ (CBE)\n"
        "🔢 Account: 1000421183458\n"
        "👤 Name: Nuru Adem\n\n"
        "📱 Telebirr: 0981751543"
    ),
    "prize": "ዋና ሽልማት",
    "lottery_open": True,
}

# =========================================================
# LOGGING
# =========================================================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# =========================================================
# DATA STORAGE
# =========================================================
tickets = []
pending_payments = {}
users = set()
settings = DEFAULT_SETTINGS.copy()
winner = None

def save_data():
    data = {
        "tickets": tickets,
        "pending_payments": pending_payments,
        "users": list(users),
        "settings": settings,
        "winner": winner,
    }
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=4)
    except Exception as e:
        logger.error(f"Save error: {e}")

def load_data():
    global tickets, pending_payments, users, settings, winner
    if not DATA_FILE.exists():
        return
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)
            tickets = data.get("tickets", [])
            pending_payments = data.get("pending_payments", {})
            users = set(data.get("users", []))
            saved_settings = data.get("settings", {})
            settings = DEFAULT_SETTINGS.copy()
            settings.update(saved_settings)
            winner = data.get("winner")
    except Exception as e:
        logger.error(f"Load error: {e}")

def is_admin(update: Update):
    user = update.effective_user
    return user is not None and user.id == ADMIN_ID

# =========================================================
# MENUS
# =========================================================
def main_menu():
    keyboard = [
        [InlineKeyboardButton("🎟️ ትኬት ግዛ", callback_data="buy")],
        [
            InlineKeyboardButton("🎫 የእኔ ትኬት", callback_data="my_ticket"),
            InlineKeyboardButton("📊 ሁኔታ", callback_data="status"),
        ],
        [InlineKeyboardButton("💳 ክፍያ", callback_data="payment_info")],
    ]
    return InlineKeyboardMarkup(keyboard)

def admin_menu():
    keyboard = [
        [InlineKeyboardButton("📊 Statistics", callback_data="admin_stats")],
        [InlineKeyboardButton("🎟️ Tickets", callback_data="admin_tickets")],
        [InlineKeyboardButton("🟢/🔴 Lottery ON/OFF", callback_data="toggle_lottery")],
        [InlineKeyboardButton("🎲 Draw Winner", callback_data="admin_draw")],
        [InlineKeyboardButton("🔄 New Lottery", callback_data="reset_confirm")],
    ]
    return InlineKeyboardMarkup(keyboard)

# =========================================================
# CORE HANDLERS
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
            "👋 **Admin እንኳን ደህና መጡ!**\n\nየትኛውን ስርዓት መጠቀም እንደሚፈልጉ ይምረጡ።",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
    else:
        await update.message.reply_text(
            f"👋 ሰላም {user.first_name}!\n\n🎟️ ወደ Lottery Bot እንኳን በደህና መጡ!",
            reply_markup=main_menu(),
        )

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    users.add(user_id)

    if not settings["lottery_open"]:
        await update.message.reply_text("🔴 Lottery ተዘግቷል።")
        return
    if len(tickets) >= settings["max_tickets"]:
        await update.message.reply_text("❌ ሁሉም ትኬቶች ተሸጠዋል!")
        return
    for ticket in tickets:
        if ticket["user_id"] == user_id:
            await update.message.reply_text("⚠️ አስቀድመው ትኬት አለዎት!")
            return
    if str(user_id) in pending_payments:
        await update.message.reply_text("⏳ ደረሰኝዎ አስቀድሞ ለAdmin ተልኳል።")
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
        "📥 **NEW PAYMENT**\n\n"
        f"👤 Name: {user.first_name}\n"
        f"🔗 Username: {username}\n"
        f"🆔 User ID: `{user_id}`\n\n"
        f"💰 Amount: {settings['ticket_price']}\n\n"
        "👇 Payment verification:"
    )
    await context.bot.send_photo(
        chat_id=ADMIN_ID,
        photo=photo_id,
        caption=caption,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    await update.message.reply_text(
        "✅ **ደረሰኝዎ ደርሶናል!**\n\n⏳ Admin እያረጋገጠው ነው።\nከጸደቀ በኋላ የትኬት ቁጥር ይደርስዎታል።",
        parse_mode="Markdown",
    )

# =========================================================
# DRAW LOGIC
# =========================================================
async def run_draw(bot, target_chat_id=None, is_callback=False):
    global winner
    if len(tickets) < settings["max_tickets"]:
        msg = (
            "⚠️ **ዕጣ ማውጣት አይቻልም።**\n\n"
            f"🎟️ Sold: {len(tickets)}\n"
            f"🎟️ Required: {settings['max_tickets']}"
        )
        if is_callback and target_chat_id:
            await target_chat_id.edit_message_text(
                msg,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel")]]),
            )
        return

    winner = secrets.choice(tickets)
    save_data()
    
    text = (
        "🎊🎊 **LOTTERY WINNER** 🎊🎊\n\n"
        f"🏆 Ticket: #{winner['number']}\n\n"
        f"👤 Name: {winner['name']}\n\n"
        f"🆔 User ID: {winner['user_id']}\n\n"
        f"🏆 Prize: {settings['prize']}"
    )

    if is_callback and target_chat_id:
        await target_chat_id.edit_message_text(
            text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel")]]),
        )

    try:
        await bot.send_message(
            chat_id=winner["user_id"],
            text=(
                "🏆🎉 **እንኳን ደስ አለዎት!** 🎉🏆\n\n"
                "የLottery አሸናፊ ሆነዋል!\n\n"
                f"🎟️ Ticket: #{winner['number']}\n\n"
                f"🏆 Prize: {settings['prize']}"
            ),
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error(f"Winner notification error: {e}")

# =========================================================
# CALLBACK ROUTER
# =========================================================
async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    # User Callbacks
    if data == "menu":
        await query.edit_message_text("🏠 **MAIN MENU**", parse_mode="Markdown", reply_markup=main_menu())
    elif data == "buy":
        if not settings["lottery_open"]:
            await query.edit_message_text("🔴 **Lottery ተዘግቷል።**", parse_mode="Markdown")
            return
        if len(tickets) >= settings["max_tickets"]:
            await query.edit_message_text("❌ **ሁሉም ትኬቶች ተሸጠዋል!**", parse_mode="Markdown")
            return
        user_id = query.from_user.id
        for ticket in tickets:
            if ticket["user_id"] == user_id:
                await query.edit_message_text(f"⚠️ አስቀድመው ትኬት አለዎት!\n\n🎟️ Ticket: #{ticket['number']}")
                return
        if str(user_id) in pending_payments:
            await query.edit_message_text("⏳ የክፍያ ደረሰኝዎ ተልኳል። እባክዎን Admin ምላሽ ይጠብቁ።")
            return

        keyboard = [
            [InlineKeyboardButton("💳 የክፍያ መረጃ", callback_data="payment_info")],
            [InlineKeyboardButton("🔙 Menu", callback_data="menu")],
        ]
        await query.edit_message_text(
            f"🎟️ **ትኬት ለመግዛት**\n\n💰 ዋጋ: {settings['ticket_price']}\n\n1️⃣ የክፍያ መረጃን ይመልከቱ\n2️⃣ ክፍያ ይፈጽሙ\n3️⃣ Screenshot ይላኩ",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
    elif data == "payment_info":
        keyboard = [
            [InlineKeyboardButton("📸 ደረሰኝ ላክ", callback_data="receipt_help")],
            [InlineKeyboardButton("🔙 Menu", callback_data="menu")],
        ]
        await query.edit_message_text(
            f"💳 **የክፍያ መረጃ**\n\n💰 ዋጋ: {settings['ticket_price']}\n\n{settings['payment_info']}\n\n📸 ክፍያ ካደረጉ በኋላ ደረሰኙን Screenshot አድርገው እዚህ ይላኩ።",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
    elif data == "receipt_help":
        await query.edit_message_text(
            "📸 **ደረሰኝ ለመላክ**\n\nየክፍያ Screenshot እንደ Photo ይላኩ።",
            parse_mode="Markdown",
        )
    elif data == "my_ticket":
        user_id = query.from_user.id
        found = next((t for t in tickets if t["user_id"] == user_id), None)
        text = f"🎫 **YOUR TICKET**\n\n🎟️ #{found['number']}\n👤 {found['name']}" if found else "📭 ትኬት አልተገኘም።"
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", callback_data="menu")]]))
    elif data == "status":
        sold = len(tickets)
        text = f"📊 **LOTTERY STATUS**\n\n🎟️ Sold: {sold}\n🎟️ Remaining: {settings['max_tickets'] - sold}\n📦 Total: {settings['max_tickets']}\n💰 Price: {settings['ticket_price']}"
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", callback_data="menu")]]))

    # Admin Callbacks
    elif data == "admin_panel":
        if query.from_user.id != ADMIN_ID: return
        await query.edit_message_text("⚙️ **ADMIN PANEL**", parse_mode="Markdown", reply_markup=admin_menu())
    elif data == "admin_stats":
        if query.from_user.id != ADMIN_ID: return
        sold = len(tickets)
        text = f"📊 **STATISTICS**\n\n👥 Users: {len(users)}\n🎟️ Sold: {sold}\n🎟️ Remaining: {settings['max_tickets'] - sold}\n📦 Max: {settings['max_tickets']}\n⏳ Pending: {len(pending_payments)}\n🟢 Status: {'OPEN' if settings['lottery_open'] else 'CLOSED'}"
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel")]]))
    elif data == "admin_tickets":
        if query.from_user.id != ADMIN_ID: return
        text = "🎟️ **SOLD TICKETS**\n\n" + "\n".join([f"#{t['number']} — {t['name']} — `{t['user_id']}`" for t in tickets]) if tickets else "📭 ምንም ትኬት አልተሸጠም።"
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel")]]))
    elif data == "toggle_lottery":
        if query.from_user.id != ADMIN_ID: return
        settings["lottery_open"] = not settings["lottery_open"]
        save_data()
        await query.edit_message_text(f"Status: **{'🟢 OPEN' if settings['lottery_open'] else '🔴 CLOSED'}**", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel")]]))
    elif data == "admin_draw":
        if query.from_user.id != ADMIN_ID: return
        await run_draw(context.bot, target_chat_id=query, is_callback=True)
    elif data == "reset_confirm":
        if query.from_user.id != ADMIN_ID: return
        keyboard = [[InlineKeyboardButton("⚠️ YES, RESET", callback_data="reset_yes")], [InlineKeyboardButton("❌ CANCEL", callback_data="admin_panel")]]
        await query.edit_message_text("⚠️ **RESET LOTTERY?**\n\nይህ የአሁኑን ትኬቶች ያጠፋል።", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    elif data == "reset_yes":
        if query.from_user.id != ADMIN_ID: return
        tickets.clear()
        pending_payments.clear()
        settings["lottery_open"] = True
        save_data()
        await query.edit_message_text("✅ **NEW LOTTERY STARTED!**", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⚙️ Admin Panel", callback_data="admin_panel")]]))

    # Approve / Reject
    elif data.startswith("approve:") or data.startswith("reject:"):
        if query.from_user.id != ADMIN_ID: return
        action, uid_str = data.split(":")
        uid = int(uid_str)
        u_data = pending_payments.pop(str(uid), None)
        if not u_data:
            await query.edit_message_caption("⚠️ Request not found.")
            return
        if action == "approve":
            t_num = len(tickets) + 1
            tickets.append({"number": t_num, "user_id": uid, "name": u_data["name"], "username": u_data.get("username", "")})
            save_data()
            await context.bot.send_message(chat_id=uid, text=f"🎉 **ክፍያዎ ጸድቋል!**\n\n🎟️ **Ticket Number:** #{t_num}\n🍀 **መልካም ዕድል!**", parse_mode="Markdown")
            await query.edit_message_caption(f"✅ **APPROVED**\n👤 {u_data['name']}\n🎟️ Ticket #{t_num}")
        else:
            save_data()
            await context.bot.send_message(chat_id=uid, text="❌ **የክፍያ ደረሰኝዎ አልተቀበለም።**", parse_mode="Markdown")
            await query.edit_message_caption(f"❌ **REJECTED**\n👤 {u_data['name']}")

# =========================================================
# MAIN
# =========================================================
def main():
    load_data()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", lambda u, c: u.message.reply_text("⚙️ **ADMIN PANEL**", parse_mode="Markdown", reply_markup=admin_menu()) if is_admin(u) else None))
    app.add_handler(CommandHandler("draw", lambda u, c: run_draw(c.bot, u.effective_chat.id, False) if is_admin(u) else None))
    
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CallbackQueryHandler(callback_router))

    print("🚀 Lottery Bot Version 3 is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
