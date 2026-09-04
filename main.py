import os
import asyncio
import random
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# Logging setup
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Environment Variables
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
# የቻናል ID ወይም Username (ጽሁፍ ሆኖ እንዲያዝ str)
CHANNEL_ID = str(os.environ.get("CHANNEL_USERNAME", ""))

# Data Stores
user_tickets = {} # user_id: count
registered_users = set() # የቦቱ ተጠቃሚዎች ID መያዣ

# የማስታወቂያ ምስል እና ጽሁፍ
channel_post_image = "https://picsum.photos/800/400"  # አስተማማኝ የምስል ሊንክ
channel_post_text = "🎰 **የዕድል ማውጫ ጨዋታ!**\n\nበየቀኑና በየሰዓቱ ብዙ ሽልማቶችን ያሸንፉ! አሁኑኑ ታች ያለውን አዝራር ተጭነው ይጫወቱ!"
wheel_animation_url = "https://media.giphy.com/media/l3V0C199aA4z1Ufmg/giphy.gif"

# Rewards & Probabilities (ፍትሃዊ እና አትራፊ የማሸነፍ እድል)
PRIZES = [0, 10, 20, 50, 100, 500]
WEIGHTS = [80, 10, 5, 4, 0.9, 0.1] # 80% ባዶ፣ 0.1% ብቻ 500 ብር

def spin_wheel():
    return random.choices(PRIZES, weights=WEIGHTS, k=1)[0]

# --- COMMAND HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    registered_users.add(user_id) # ተጠቃሚውን መመዝገብ
    
    if user_id not in user_tickets:
        user_tickets[user_id] = 3 # ለአዲሶች 3 ነፃ ትኬት

    keyboard = [
        [InlineKeyboardButton("🎰 ዕድልህን ሞክር (Spin)", callback_data="spin")],
        [InlineKeyboardButton("🎟️ የእኔ ትኬቶች", callback_data="my_tickets"), InlineKeyboardButton("👥 ጓደኛ ጋብዝ", callback_data="invite")],
    ]
    
    # የቻናል ሊንክ ካለ መጨመር
    clean_channel = CHANNEL_ID.replace('@', '')
    if not clean_channel.startswith("-100") and clean_channel:
        keyboard.append([InlineKeyboardButton("📢 ቻናላችንን ይቀላቀሉ", url=f"https://t.me/{clean_channel}")])
        
    if user_id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("⚙️ Admin Panel", callback_data="admin_panel")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"ሰላም {update.effective_user.first_name}! እንኳን ወደ እድል ማውጫ ቦት በደህና መጡ።\n\nያሉዎት ትኬቶች፦ {user_tickets[user_id]}",
        reply_markup=reply_markup
    )

# --- CALLBACK HANDLERS ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "spin":
        tickets = user_tickets.get(user_id, 0)
        if tickets <= 0:
            await query.message.reply_text("❌ ይቅርታ! በቂ ትኬት የለዎትም። እባክዎን ጓደኞችን በመጋበዝ ትኬት ያግኙ!")
            return

        user_tickets[user_id] -= 1
        
        # 1. አኒሜሽን GIF መላክ
        anim_msg = None
        try:
            anim_msg = await query.message.reply_animation(
                animation=wheel_animation_url,
                caption="🎡 ዊሉ እየተሽከረከረ ነው... እባክዎን ይጠብቁ! 🤞"
            )
            await asyncio.sleep(2.5)
        except Exception as e:
            logger.error(f"Animation error: {e}")

        # 2. እድል ማውጣት
        win_amount = spin_wheel()
        
        if win_amount > 0:
            result_text = f"🎉 **እንኳን ደስ አለዎት!**\n\nለእርስዎ **{win_amount} ብር** ወጥቶልዎታል! 🤑\nቀሪ ትኬት፦ {user_tickets[user_id]}"
        else:
            result_text = f"😔 **ለጥቂት አመለጣችሁ!**\n\nበዚህ ዙር ምንም አልወጣዎትም። ድጋሚ ይሞክሩ!\nቀሪ ትኬት፦ {user_tickets[user_id]}"

        if anim_msg:
            try:
                await anim_msg.delete()
            except Exception:
                pass
        await query.message.reply_text(result_text)

    elif query.data == "my_tickets":
        tickets = user_tickets.get(user_id, 0)
        await query.message.reply_text(f"🎟️ በአሁኑ ወቅት **{tickets}** ትኬቶች አሉዎት።")

    elif query.data == "invite":
        bot_username = (await context.bot.get_me()).username
        ref_link = f"https://t.me/{bot_username}?start={user_id}"
        await query.message.reply_text(f"🔗 የእርስዎ የመጋበዣ ሊንክ፦\n\n{ref_link}\n\nበዚህ ሊንክ ሰዎችን ሲጋብዙ ተጨማሪ ትኬት ያገኛሉ!")

    elif query.data == "admin_panel" and user_id == ADMIN_ID:
        admin_keyboard = [
            [InlineKeyboardButton("📢 አሁኑኑ ማስታወቂያ ወደ ቻናል ልክ", callback_data="post_channel")],
            [InlineKeyboardButton("👥 ማስታወቂያ ለሁሉም ተጠቃሚዎች ልክ", callback_data="post_users")],
            [InlineKeyboardButton("🔙 ወደ ዋና ሜኑ", callback_data="main_menu")]
        ]
        await query.message.reply_text("⚙️ **Welcome to Admin Panel**", reply_markup=InlineKeyboardMarkup(admin_keyboard))

    elif query.data == "post_channel" and user_id == ADMIN_ID:
        success = await send_channel_broadcast(context)
        if success:
            await query.message.reply_text("✅ ማስታወቂያው ወደ ቻናሉ በትክክል ተልኳል!")
        else:
            await query.message.reply_text("❌ ማስታወቂያውን ወደ ቻናል መላክ አልተቻለም። እባክዎን የቻናል ID እና የቦቱን Adminነት ያረጋግጡ።")

    elif query.data == "post_users" and user_id == ADMIN_ID:
        count = await send_users_broadcast(context)
        await query.message.reply_text(f"✅ ማስታወቂያው ለ {count} ተጠቃሚዎች ተልኳል!")

# --- BROADCAST FUNCTIONS ---
async def send_channel_broadcast(context: ContextTypes.DEFAULT_TYPE) -> bool:
    """ወደ ቻናል ብቻ ማስታወቂያ መላኪያ"""
    if not CHANNEL_ID:
        logger.error("CHANNEL_ID is empty!")
        return False
        
    try:
        bot_username = (await context.bot.get_me()).username
        keyboard = [[InlineKeyboardButton("🎰 አሁኑኑ ተጫወቱ", url=f"https://t.me/{bot_username}")]]
        
        # የቻናል ID ከሆነ ወደ integer መቀየር
        target_chat = int(CHANNEL_ID) if CHANNEL_ID.startswith("-100") or CHANNEL_ID.lstrip('-').isdigit() else CHANNEL_ID
        
        await context.bot.send_photo(
            chat_id=target_chat,
            photo=channel_post_image,
            caption=channel_post_text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return True
    except Exception as e:
        logger.error(f"Error posting to channel ({CHANNEL_ID}): {e}")
        return False

async def send_users_broadcast(context: ContextTypes.DEFAULT_TYPE) -> int:
    """ለቦቱ ተጠቃሚዎች (Direct Message) ማስታወቂያ መላኪያ"""
    count = 0
    bot_username = (await context.bot.get_me()).username
    keyboard = [[InlineKeyboardButton("🎰 አሁኑኑ ተጫወቱ", url=f"https://t.me/{bot_username}")]]
    
    for uid in list(registered_users):
        try:
            await context.bot.send_photo(
                chat_id=uid,
                photo=channel_post_image,
                caption=channel_post_text,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            count += 1
            await asyncio.sleep(0.05) # Rate limit ለመከላከል
        except Exception as e:
            logger.error(f"Failed to send to user {uid}: {e}")
    return count

async def auto_post_job(context: ContextTypes.DEFAULT_TYPE):
    """በየ 1 ሰዓቱ አውቶማቲክ ወደ ቻናል የሚልክ"""
    await send_channel_broadcast(context)

# --- MAIN FUNCTION ---
def main():
    if not BOT_TOKEN:
        print("Error: BOT_TOKEN is missing!")
        return

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))

    # በየ 1 ሰዓቱ (3600 ሰከንድ) አውቶማቲክ ማስታወቂያ እንዲልክ ማድረግ
    job_queue = app.job_queue
    if job_queue:
        job_queue.run_repeating(auto_post_job, interval=3600, first=10)

    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()

         
    
                
