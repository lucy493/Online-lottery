import json
import logging
import os
import random
import time
from pathlib import Path
from threading import Thread
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# =========================================================
# 🌐 FLASK KEEP-ALIVE SERVER
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
REQUIRED_CHANNEL = "@semeraonlinerewards"  # Public Channel Username

DATA_FILE = Path("scratch_data.json")

# ነባሪ ማስታወቂያ ምስል (ደስ የሚል የአኒሜሽን/ሽልማት ምስል URL)
DEFAULT_AD_IMAGE = "https://img.freepik.com/free-vector/happy-people-winning-money-cash-prize_74855-14115.jpg"

DEFAULT_SETTINGS = {
    "ticket_price": 10,
    "payment_info": (
        "🏦 Bank: የኢትዮጵያ ንግድ ባንክ (CBE)\n"
        "🔢 Account: 1000421183458\n"
        "👤 Name: Nuru Adem\n\n"
        "📱 Telebirr: 0981751543"
    ),
    "game_open": True,
    "prizes": [0, 10, 50, 100, 200],
    "channel_ad_image": DEFAULT_AD_IMAGE,
    "channel_ad_text": (
        "🎉 **ደስታቸውን ከአሸናፊዎቻችን ጋር ይካፈሉ!** 🤑✨\n\n"
        "በቀላሉ የዕድል መንኮራኩሩን በማሽከርከር የቴሌብር እና የባንክ ገንዘብ ሽልማቶችን ያሸንፉ! 🎰\n\n"
        "👇 **አሁኑኑ ይጀምሩና ዕድልዎን ይሞክሩ፦**\n"
        "🤖 ቦት፦ @semera_rewards_bot"
    ),
    "ad_interval_seconds": 3600  # በየ 1 ሰዓቱ ይለጥፋል
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
main_wallets = {}        
winning_wallets = {}     
used_tx_ids = set()      
users = set()
settings = DEFAULT_SETTINGS.copy()
user_states = {}         

def save_data():
    data = {
        "pending_deposits": pending_deposits,
        "pending_withdrawals": pending_withdrawals,
        "main_wallets": main_wallets,
        "winning_wallets": winning_wallets,
        "used_tx_ids": list(used_tx_ids),
        "users": list(users),
        "settings": settings,
    }
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=4)
    except Exception as e:
        logger.error(f"Save error: {e}")

def load_data():
    global pending_deposits, pending_withdrawals, main_wallets, winning_wallets, used_tx_ids, users, settings
    if not DATA_FILE.exists():
        return
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)
            pending_deposits = data.get("pending_deposits", {})
            pending_withdrawals = data.get("pending_withdrawals", {})
            main_wallets = data.get("main_wallets", {})
            winning_wallets = data.get("winning_wallets", {})
            used_tx_ids = set(data.get("used_tx_ids", []))
            users = set(data.get("users", []))
            settings = DEFAULT_SETTINGS.copy()
            settings.update(data.get("settings", {}))
            if "prizes" not in settings:
                settings["prizes"] = [0, 10, 50, 100, 200]
            if "channel_ad_image" not in settings:
                settings["channel_ad_image"] = DEFAULT_AD_IMAGE
    except Exception as e:
        logger.error(f"Load error: {e}")

def is_admin(user_id):
    return user_id == ADMIN_ID

# =========================================================
# 📢 AUTOMATED PHOTO & AD BROADCAST JOB
# =========================================================
async def send_channel_broadcast(context: ContextTypes.DEFAULT_TYPE):
    """ለቻናል ማስታወቂያ በምስልና በማራኪ ፅሁፍ አውቶማቲክ የሚያስተላልፍ ተግባር"""
    ad_text = settings.get("channel_ad_text")
    ad_image = settings.get("channel_ad_image")
    
    # ቻናሉ ላይ የሚቀመጥ አዝራር (Play Button)
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎰 አሁኑኑ ተጫወቱ (Play Now)", url="https://t.me/semera_rewards_bot")]
    ])

    if ad_text and ad_image:
        try:
            await context.bot.send_photo(
                chat_id=REQUIRED_CHANNEL,
                photo=ad_image,
                caption=ad_text,
                parse_mode="Markdown",
                reply_markup=keyboard
            )
            logger.info("Successfully posted photo ad to channel.")
        except Exception as e:
            logger.error(f"Failed to post photo ad to channel: {e}")

# =========================================================
# 🔍 CHANNEL MEMBERSHIP CHECK
# =========================================================
async def check_joined_channel(bot, user_id):
    if is_admin(user_id):
        return True
    try:
        member = await bot.get_chat_member(chat_id=REQUIRED_CHANNEL, user_id=user_id)
        if member.status in ["creator", "administrator", "member"]:
            return True
        return False
    except Exception as e:
        logger.error(f"Channel Check Error: {e}")
        return True

def join_channel_keyboard():
    keyboard = [
        [InlineKeyboardButton("📢 ቻናሉን የተቀላቀሉ (Join Channel)", url=f"https://t.me/{REQUIRED_CHANNEL.replace('@', '')}")],
        [InlineKeyboardButton("✅ አረጋግጥ (Check Membership)", callback_data="check_join")]
    ]
    return InlineKeyboardMarkup(keyboard)

# =========================================================
# 🎛️ MENUS & KEYBOARDS
# =========================================================
def bottom_persistent_keyboard():
    return ReplyKeyboardMarkup(
        [[KeyboardButton("📱 Main Menu")]],
        resize_keyboard=True,
        is_persistent=True
    )

def main_inline_menu(user_id):
    m_bal = main_wallets.get(str(user_id), 0)
    w_bal = winning_wallets.get(str(user_id), 0)
    
    keyboard = [
        [InlineKeyboardButton(f"🎡 እድልህን ሞክር / Spin ({settings['ticket_price']} ETB)", callback_data="spin_wheel")],
        [InlineKeyboardButton("💵 ዲፖዚት አድርግ (Deposit)", callback_data="deposit")],
        [InlineKeyboardButton(f"👛 Wallet (Main: {m_bal} | Win: {w_bal})", callback_data="my_wallet")],
        [InlineKeyboardButton("🏆 ሽልማት ተቀበል (Withdraw)", callback_data="withdraw")],
        [InlineKeyboardButton("💳 የክፍያ መረጃ", callback_data="payment_info")],
    ]
    if user_id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("⚙️ Admin Panel", callback_data="admin_panel")])
    return InlineKeyboardMarkup(keyboard)

def admin_menu():
    keyboard = [
        [InlineKeyboardButton("🟢/🔴 ጨዋታ ON/OFF", callback_data="toggle_game")],
        [InlineKeyboardButton("🎁 ሽልማቶችን ማስተካከያ", callback_data="manage_prizes")],
        [InlineKeyboardButton("🖼️ የቻናል ማስታወቂያ ምስል ቀይር", callback_data="set_channel_ad_image")],
        [InlineKeyboardButton("✍️ የቻናል ማስታወቂያ ጽሁፍ ቀይር", callback_data="set_channel_ad_text")],
        [InlineKeyboardButton("📨 ለተጠቃሚዎች Broadcast ላክ", callback_data="broadcast_msg")],
        [InlineKeyboardButton("👥 የተጠቃሚዎች ብዛት", callback_data="admin_users")],
        [InlineKeyboardButton("🔙 User Menu", callback_data="menu")],
    ]
    return InlineKeyboardMarkup(keyboard)

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

    joined = await check_joined_channel(context.bot, user.id)
    if not joined:
        await update.message.reply_text(
            f"⚠️ **ቦቱን ለመጠቀም መጀመሪያ የቴሌግራም ቻናላችንን መቀላቀል አለብዎት!**\n\n"
            f"እባክዎን ከታች ያለውን ሊንክ ተጭነው {REQUIRED_CHANNEL} ይቀላቀሉ፦",
            reply_markup=join_channel_keyboard(),
            parse_mode="Markdown"
        )
        return

    await update.message.reply_text(
        f"👋 ሰላም {user.first_name}!\n\n🎰 **ወደ Spinning Wheel ሎተሪ እንኳን በደህና መጡ!**\n\n"
        f"🎟️ የትኬት ዋጋ: **{settings['ticket_price']} ETB**\n"
        f"💵 Main Wallet: **{main_wallets[uid_str]} ETB**\n"
        f"🏆 Winning Wallet: **{winning_wallets[uid_str]} ETB**\n\n"
        "👇 ከታች ያለውን ሜኑ ይጠቀሙ፦",
        reply_markup=bottom_persistent_keyboard(),
    )
    await update.message.reply_text(
        "🏠 **ዋና ሜኑ፦**",
        reply_markup=main_inline_menu(user.id),
        parse_mode="Markdown"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid_str = str(user.id)
    text = update.message.text.strip() if update.message.text else ""

    if text == "📱 Main Menu":
        joined = await check_joined_channel(context.bot, user.id)
        if not joined:
            await update.message.reply_text(
                f"⚠️ **እባክዎን መጀመሪያ የቴሌግራም ቻናላችንን ይቀላቀሉ!**\n\n{REQUIRED_CHANNEL}",
                reply_markup=join_channel_keyboard(),
                parse_mode="Markdown"
            )
            return

        user_states.pop(uid_str, None)
        await update.message.reply_text("🏠 **MAIN MENU**", reply_markup=main_inline_menu(user.id), parse_mode="Markdown")
        return

    state = user_states.get(uid_str, "")

    # Admin: Set Channel Ad Photo/Image (Photo OR URL)
    if state == "WAITING_CHANNEL_AD_IMAGE" and is_admin(user.id):
        if update.message.photo:
            photo_id = update.message.photo[-1].file_id
            settings["channel_ad_image"] = photo_id
            save_data()
            user_states.pop(uid_str, None)
            await update.message.reply_text("✅ **የማስታወቂያ ምስሉ በተሳካ ሁኔታ ተቀይሯል!**", reply_markup=main_inline_menu(user.id))
        elif text.startswith("http"):
            settings["channel_ad_image"] = text
            save_data()
            user_states.pop(uid_str, None)
            await update.message.reply_text("✅ **የማስታወቂያ ምስል Link በተሳካ ሁኔታ ተቀይሯል!**", reply_markup=main_inline_menu(user.id))
        else:
            await update.message.reply_text("❌ እባክዎን Photo ቀጥታ ይላኩ ወይም የኢሜጅ URL ያስገቡ፦")
        return

    # Admin: Set Channel Auto-Ad Text
    if state == "WAITING_CHANNEL_AD_TEXT" and text and is_admin(user.id):
        settings["channel_ad_text"] = text
        save_data()
        user_states.pop(uid_str, None)
        await update.message.reply_text(
            f"✅ **የቻናል ማስታወቂያ ጽሁፍ ተቀይሯል!**\n\n`{text}`",
            parse_mode="Markdown",
            reply_markup=main_inline_menu(user.id)
        )
        return

    # Admin: Broadcast Message to Bot Users
    if state == "WAITING_BROADCAST_TEXT" and text and is_admin(user.id):
        user_states.pop(uid_str, None)
        success_count = 0
        for uid in list(users):
            try:
                await context.bot.send_message(chat_id=uid, text=f"📢 **ማስታወቂያ፦**\n\n{text}", parse_mode="Markdown")
                success_count += 1
            except Exception:
                pass
        await update.message.reply_text(f"✅ ማስታወቂያው ለ **{success_count}** ተጠቃሚዎች ተልኳል!", reply_markup=main_inline_menu(user.id))
        return

    # Admin: Manage Prizes Input
    if state == "WAITING_NEW_PRIZES" and text and is_admin(user.id):
        try:
            p_list = [int(x.strip()) for x in text.split(",")]
            settings["prizes"] = p_list
            save_data()
            user_states.pop(uid_str, None)
            await update.message.reply_text(f"✅ የሽልማት ዝርዝሩ ተስተካክሏል፦\n`{p_list}`", parse_mode="Markdown", reply_markup=main_inline_menu(user.id))
        except ValueError:
            await update.message.reply_text("❌ እባክዎን ቁጥሮችን በኮማ (,) ለይተው ያስገቡ፦")
        return

    # Deposit Amount Input
    if state == "WAITING_DEPOSIT_AMOUNT" and text:
        try:
            amount = int(text)
            if amount < 10:
                await update.message.reply_text("❌ አነስተኛው የዲፖዚት መጠን 10 ETB ነው።")
                return
            
            user_states[uid_str] = f"WAITING_DEPOSIT_TXID:{amount}"
            await update.message.reply_text(
                f"💳 **የ {amount} ETB ዲፖዚት ጥያቄ**\n\n"
                f"{settings['payment_info']}\n\n"
                f"🔢 እባክዎን የላኩበትን **Transaction ID** ያስገቡ፦",
                parse_mode="Markdown"
            )
        except ValueError:
            await update.message.reply_text("❌ እባክዎን ትክክለኛ ቁጥር ብቻ ያስገቡ፦")
        return

    # Deposit Transaction ID Input
    if state.startswith("WAITING_DEPOSIT_TXID:") and text:
        amount = int(state.split(":")[1])
        tx_id = text.strip()

        if tx_id in used_tx_ids:
            await update.message.reply_text("❌ **ይህ የትራንዛክሽን ቁጥር ከዚህ ቀደም ስራ ላይ ውሏል!**")
            return

        user_states[uid_str] = f"WAITING_DEPOSIT_RECEIPT:{amount}:{tx_id}"
        await update.message.reply_text(
            f"✅ የትራንዛክሽን ቁጥር: `{tx_id}` ተመዝግቧል።\n\n📸 አሁን የ **{amount} ETB** ክፍያ ደረሰኝ Screenshot ይላኩ።",
            parse_mode="Markdown"
        )
        return

    # Deposit Receipt Photo Upload
    if update.message.photo and state.startswith("WAITING_DEPOSIT_RECEIPT:"):
        _, amount_str, tx_id = state.split(":")
        amount = int(amount_str)
        photo_id = update.message.photo[-1].file_id

        pending_deposits[uid_str] = {
            "user_id": user.id,
            "name": user.first_name,
            "username": user.username or "የለውም",
            "amount": amount,
            "tx_id": tx_id,
            "photo_id": photo_id,
        }
        user_states.pop(uid_str, None)
        save_data()

        keyboard = [[InlineKeyboardButton("✅ APPROVE DEPOSIT", callback_data=f"dep_approve:{user.id}"), InlineKeyboardButton("❌ REJECT", callback_data=f"dep_reject:{user.id}")]]
        caption = f"📥 **NEW WALLET DEPOSIT REQUEST**\n\n👤 Name: {user.first_name}\n🆔 User ID: `{user.id}`\n💰 Amount: **{amount} ETB**\n🔢 TX ID: `{tx_id}`"
        
        await context.bot.send_photo(chat_id=ADMIN_ID, photo=photo_id, caption=caption, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
        await update.message.reply_text(f"✅ **የ {amount} ETB ዲፖዚት ጥያቄዎ ደርሶናል!** Admin ሲያጸድቀው ገቢ ይሆናል።", parse_mode="Markdown", reply_markup=main_inline_menu(user.id))
        return

    # Withdrawal Amount Input
    if state == "WAITING_WITHDRAW_AMOUNT" and text:
        try:
            req_amount = int(text)
            w_bal = winning_wallets.get(uid_str, 0)
            if req_amount <= 0 or req_amount > w_bal:
                await update.message.reply_text(f"❌ አልተቻለም! ማውጣት የሚችሉት ከ **1 - {w_bal} ETB** ብቻ ነው።")
                return

            user_states[uid_str] = f"WAITING_WITHDRAW_PHONE:{req_amount}"
            await update.message.reply_text(f"📱 **የ {req_amount} ETB ሽልማት ማውጫ**\n\nእባክዎን **የስልክ ቁጥር** ያስገቡ፦", parse_mode="Markdown")
        except ValueError:
            await update.message.reply_text("❌ እባክዎን ትክክለኛ ቁጥር ብቻ ያስገቡ፦")
        return

    # Withdrawal Phone Input
    if state.startswith("WAITING_WITHDRAW_PHONE:") and text:
        req_amount = int(state.split(":")[1])
        phone_no = text.strip()

        winning_wallets[uid_str] -= req_amount
        user_states.pop(uid_str, None)
        save_data()

        username = f"@{user.username}" if user.username else "የለውም"
        admin_alert = f"🏆 **NEW PRIZE CLAIM REQUEST**\n\n👤 ደንበኛ: {user.first_name}\n🔗 Telegram: {username}\n🆔 User ID: `{user.id}`\n💰 የሚወጣው መጠን: **{req_amount} ETB**\n📱 የስልክ ቁጥር: `{phone_no}`"
        await context.bot.send_message(chat_id=ADMIN_ID, text=admin_alert, parse_mode="Markdown")

        await update.message.reply_text(f"✅ **የሽልማት ጥያቄዎ ለአድሚን ተልኳል!**", parse_mode="Markdown", reply_markup=main_inline_menu(user.id))

# =========================================================
# 🔄 CALLBACK ROUTER
# =========================================================
async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id
    uid_str = str(user_id)

    joined = await check_joined_channel(context.bot, user_id)
    if not joined and data != "check_join":
        await query.edit_message_text(
            f"⚠️ **ቦቱን ለመጠቀም መጀመሪያ የቴሌግራም ቻናላችንን ይቀላቀሉ!**\n\n{REQUIRED_CHANNEL}",
            reply_markup=join_channel_keyboard(),
            parse_mode="Markdown"
        )
        return

    if data == "check_join":
        if joined:
            await query.edit_message_text("✅ **አመስግናለሁ! ቻናሉን ስለተቀላቀሉ አሁን ቦቱን መጠቀም ይችላሉ።**", parse_mode="Markdown", reply_markup=main_inline_menu(user_id))
        else:
            await query.answer("❌ ገና አልተቀላቀሉም! እባክዎን መጀመሪያ ቻናሉን Join ያድርጉ።", show_alert=True)

    elif data == "menu":
        user_states.pop(uid_str, None)
        await query.edit_message_text("🏠 **MAIN MENU**", parse_mode="Markdown", reply_markup=main_inline_menu(user_id))
    
    elif data == "my_wallet":
        m_bal = main_wallets.get(uid_str, 0)
        w_bal = winning_wallets.get(uid_str, 0)
        text = f"👛 **የእኔ WALLET**\n\n💵 **Main Wallet:** {m_bal} ETB\n🏆 **Winning Wallet:** {w_bal} ETB"
        keyboard = [
            [InlineKeyboardButton("💵 ዲፖዚት አድርግ", callback_data="deposit")],
            [InlineKeyboardButton("🎡 እድልህን ሞክር", callback_data="spin_wheel")],
            [InlineKeyboardButton("🏆 ሽልማት ተቀበል", callback_data="withdraw")],
            [InlineKeyboardButton("🔙 Menu", callback_data="menu")]
        ]
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "deposit":
        user_states[uid_str] = "WAITING_DEPOSIT_AMOUNT"
        await query.edit_message_text("💵 **ወደ Main Wallet ገንዘብ ለማስገባት**\n\nየሚልኩትን የብር መጠን በቁጥር ያስገቡ፦", parse_mode="Markdown")

    elif data == "spin_wheel":
        if not settings["game_open"]:
            await query.edit_message_text("🔴 **ጨዋታው ለጊዜው ተዘጋቷል።**", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", callback_data="menu")]]))
            return

        m_bal = main_wallets.get(uid_str, 0)
        price = settings["ticket_price"]

        if m_bal < price:
            await query.edit_message_text(f"❌ **Main Wallet ላይ በቂ ሂሳብ የለዎትም!**\n\n🎟️ የትኬት ዋጋ: **{price} ETB**\n💵 የእርስዎ Main Wallet: **{m_bal} ETB**", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💵 ዲፖዚት አድርግ", callback_data="deposit")], [InlineKeyboardButton("🔙 Menu", callback_data="menu")]]))
            return

        main_wallets[uid_str] = m_bal - price
        win_amt = random.choice(settings["prizes"])

        frames = ["🎡 [  |  ]", "🎡 [  /  ]", "🎡 [  -  ]", "🎡 [  \\  ]", "🎡 [  |  ]"]
        for frame in frames:
            try:
                await query.edit_message_text(f"🔄 **ዕድል ማውጫው እየተሽከረከረ ነው...**\n\n{frame}", parse_mode="Markdown")
                time.sleep(0.3)
            except Exception:
                pass

        if win_amt == 0:
            result_msg = "🎰 **SPIN RESULT** 🎰\n\n❌ **ለጥቂት ነው! በዚህ ጊዜ አልወጣም።**"
        else:
            winning_wallets[uid_str] = winning_wallets.get(uid_str, 0) + win_amt
            result_msg = f"🎉🎉 **እንኳን ደስ አለዎት!** 🎉🎉\n\n🏆 **የ {win_amt} ETB ሽልማት አሸንፈዋል!**"

        save_data()
        await query.edit_message_text(result_msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 እንደገና ሞክር", callback_data="spin_wheel")], [InlineKeyboardButton("🏠 ወደ ዋና ሜኑ", callback_data="menu")]]))

    elif data == "withdraw":
        w_bal = winning_wallets.get(uid_str, 0)
        if w_bal <= 0:
            await query.edit_message_text("❌ **Winning Wallet ላይ የተቀመጠ አሸናፊ ሂሳብ የለዎትም።**", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", callback_data="menu")]]))
            return

        user_states[uid_str] = "WAITING_WITHDRAW_AMOUNT"
        await query.edit_message_text(f"🏆 **የሽልማት ማውጫ**\n\n💰 የሚገኝ አጠቃላይ ሽልማት: **{w_bal} ETB**\n\nየብር መጠን ያስገቡ፦", parse_mode="Markdown")

    elif data == "payment_info":
        await query.edit_message_text(f"💳 **የክፍያ መረጃ**\n\n{settings['payment_info']}", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", callback_data="menu")]]))

    # Admin Panel Actions
    elif data == "admin_panel":
        if not is_admin(user_id): return
        await query.edit_message_text("⚙️ **ADMIN PANEL**", parse_mode="Markdown", reply_markup=admin_menu())

    elif data == "set_channel_ad_image":
        if not is_admin(user_id): return
        user_states[uid_str] = "WAITING_CHANNEL_AD_IMAGE"
        await query.edit_message_text(
            "🖼️ **የቻናል ማስታወቂያ ምስል ቀይር**\n\n"
            "እባክዎን አዲሱን የማስታወቂያ Photo ቀጥታ ወደ ቦቱ ይላኩ (ወይም የኢሜጅ Direct Link ያስገቡ)፦",
            parse_mode="Markdown"
        )

    elif data == "set_channel_ad_text":
        if not is_admin(user_id): return
        user_states[uid_str] = "WAITING_CHANNEL_AD_TEXT"
        cur_ad = settings.get("channel_ad_text", "የለም")
        await query.edit_message_text(
            f"📢 **የቻናል ማስታወቂያ ማስተካከያ**\n\n"
            f"**አሁን ያለው ማስታወቂያ፦**\n{cur_ad}\n\n"
            f"እባክዎን በየሰዓቱ ከምስሉ ጋር አብሮ እንዲለቀቅ የሚፈልጉትን አዲስ ማስታወቂያ ይፃፉ፦",
            parse_mode="Markdown"
        )

    elif data == "toggle_game":
        if not is_admin(user_id): return
        settings["game_open"] = not settings["game_open"]
        save_data()
        await query.edit_message_text(f"Status: **{'🟢 OPEN' if settings['game_open'] else '🔴 CLOSED'}**", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel")]]))

    elif data == "manage_prizes":
        if not is_admin(user_id): return
        user_states[uid_str] = "WAITING_NEW_PRIZES"
        cur_prizes = ", ".join(map(str, settings["prizes"]))
        await query.edit_message_text(f"🎁 **የሽልማት ማስተካከያ**\n\nአሁን ያሉ ሽልማቶች፦ `{cur_prizes}`\n\nአዲሱን የሽልማት መጠን በኮማ (,) ለይተው ያስገቡ፦", parse_mode="Markdown")

    elif data == "broadcast_msg":
        if not is_admin(user_id): return
        user_states[uid_str] = "WAITING_BROADCAST_TEXT"
        await query.edit_message_text("📢 **ለሁሉም የቦት ተጠቃሚዎች የሚላክ ማስታወቂያ**\n\nጽሁፉን ይፃፉ፦", parse_mode="Markdown")

    elif data == "admin_users":
        if not is_admin(user_id): return
        await query.edit_message_text(f"👥 አጠቃላይ ተጠቃሚዎች፦ **{len(users)}**", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel")]]))

    # Approve/Reject Deposit
    elif data.startswith("dep_approve:") or data.startswith("dep_reject:"):
        if not is_admin(user_id): return
        action, target_uid_str = data.split(":")
        dep_data = pending_deposits.pop(target_uid_str, None)
        if not dep_data:
            await query.edit_message_caption("⚠️ Request not found.")
            return

        target_uid = int(target_uid_str)
        if action == "dep_approve":
            amt, tx_id = dep_data["amount"], dep_data["tx_id"]
            main_wallets[target_uid_str] = main_wallets.get(target_uid_str, 0) + amt
            used_tx_ids.add(tx_id)
            save_data()

            await context.bot.send_message(chat_id=target_uid, text=f"✅ **የ {amt} ETB ዲፖዚትዎ ጸድቋል!**", parse_mode="Markdown", reply_markup=main_inline_menu(target_uid))
            await query.edit_message_caption(f"✅ **DEPOSIT APPROVED ({amt} ETB)**\n👤 {dep_data['name']}")
        else:
            save_data()
            await context.bot.send_message(chat_id=target_uid, text="❌ የዲፖዚት ደረሰኝዎ አልተቀበለም።", reply_markup=main_inline_menu(target_uid))
            await query.edit_message_caption(f"❌ **DEPOSIT REJECTED**\n👤 {dep_data['name']}")

# =========================================================
# 🎬 MAIN FUNCTION
# =========================================================
def main():
    load_data()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Schedule Channel Broadcast Job (every 1 hour = 3600 seconds)
    if app.job_queue:
        app.job_queue.run_repeating(
            send_channel_broadcast,
            interval=settings.get("ad_interval_seconds", 3600),
            first=10  # ቦቱ እንደተነሳ ከ 10 ሰከንድ በኋላ የመጀመሪያውን ይልካል
        )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO | filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(callback_router))

    print("🚀 Bot running with Photo-Ad capability...")
    app.run_polling()

if __name__ == "__main__":
    while True:
        try:
            main()
        except Exception as e:
            logger.error(f"Bot disconnected: {e}. Restarting in 5 seconds...")
            time.sleep(5)
