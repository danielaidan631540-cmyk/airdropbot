import sqlite3
import time
import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
    CallbackQueryHandler,
)

# =====================
# CONFIGURATION
# =====================
BOT_TOKEN = "8256239679:AAG2j3mNNNkme0UPeC_buVzS1m6p2peEvJE"
BOT_USERNAME = "arronairdrop5_bot"
ADMIN_ID = 8190754710

DAILY_BONUS_MMK = 20
REF_BONUS_MMK = 20
MISSION_REWARD_MMK = 50
DAILY_COOLDOWN_SEC = 24 * 60 * 60
WITHDRAW_MIN_MMK = 500
DB_PATH = "airdrop.db"

GATE_CHANNELS = ["@aaronairdrop2", "@aaronproofs1"]
GATE_LINKS = ["https://t.me/aaronairdrop2", "https://t.me/aaronproofs1"]
MISSION_CHANNELS = ["@aaronmission1", "@aaronmission2", "@aaronmission3", "@aaronmission4", "@aaronmission5"]
MISSION_LINKS = ["https://t.me/aaronmission1", "https://t.me/aaronmission2", "https://t.me/aaronmission3", "https://t.me/aaronmission4", "https://t.me/aaronmission5"]

# =====================
# RENDER PORT FIX
# =====================
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is alive!")

def run_health_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), HealthHandler)
    server.serve_forever()

# =====================
# DB FUNCTIONS
# =====================
def init_db():
    with sqlite3.connect(DB_PATH) as con:
        cur = con.cursor()
        cur.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, username TEXT, balance INTEGER DEFAULT 0,
            ref_count INTEGER DEFAULT 0, ref_by INTEGER, pending_ref INTEGER,
            last_daily INTEGER DEFAULT 0, mission_done INTEGER DEFAULT 0, created_at INTEGER)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS withdraw_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount INTEGER,
            method TEXT, account TEXT, status TEXT DEFAULT 'PENDING', created_at INTEGER)""")
        con.commit()

def get_user(user_id):
    with sqlite3.connect(DB_PATH) as con:
        cur = con.cursor()
        cur.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        return cur.fetchone()

# =====================
# UI ELEMENTS
# =====================
MAIN_KB = ReplyKeyboardMarkup([
    [KeyboardButton("နေ့စဉ်ဘောနပ်🎁"), KeyboardButton("လက်ကျန်ငွေ💰")],
    [KeyboardButton("ဖိတ်ခေါ်ရန်👥"), KeyboardButton("ငွေထုတ်ရန်📤")],
    [KeyboardButton("Mission 🎯"), KeyboardButton("ထိပ်ဆုံး🎖️")]
], resize_keyboard=True)

def gate_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Join Gate 1", url=GATE_LINKS[0])],
        [InlineKeyboardButton("✅ Join Gate 2", url=GATE_LINKS[1])],
        [InlineKeyboardButton("🔍 Verify Joined", callback_data="verify_gate")]
    ])

# =====================
# HANDLERS
# =====================
async def check_join(chats, user_id, context):
    for ch in chats:
        try:
            m = await context.bot.get_chat_member(ch, user_id)
            if m.status not in ["member", "administrator", "creator"]: return False
        except: return False
    return True

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    uname = update.effective_user.username
    now = int(time.time())
    
    with sqlite3.connect(DB_PATH) as con:
        con.execute("INSERT OR IGNORE INTO users (user_id, username, created_at) VALUES (?,?,?)", (uid, uname, now))
    
    if not await check_join(GATE_CHANNELS, uid, context):
        await update.message.reply_text("🚫 Gate Channel များ Join ရန် လိုအပ်ပါသည်။", reply_markup=gate_kb())
        return
    await update.message.reply_text("🎁 AARON AIRDROP မှ ကြိုဆိုပါတယ်!", reply_markup=MAIN_KB)

async def on_verify_gate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if await check_join(GATE_CHANNELS, q.from_user.id, context):
        await q.message.reply_text("✅ Verified! မီနူးအသုံးပြုနိုင်ပါပြီ။", reply_markup=MAIN_KB)
    else:
        await q.message.reply_text("❌ Join ရန် ကျန်သေးသည်!", reply_markup=gate_kb())

async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    uid = update.effective_user.id
    user = get_user(uid)
    if not user: return

    if text == "လက်ကျန်ငွေ💰":
        await update.message.reply_text(f"💰 လက်ကျန်ငွေ: {user[2]} MMK\n👥 ဖိတ်ခေါ်သူ: {user[3]} ယောက်")
    
    elif text == "နေ့စဉ်ဘောနပ်🎁":
        now = int(time.time())
        if now - user[6] >= DAILY_COOLDOWN_SEC:
            with sqlite3.connect(DB_PATH) as con:
                con.execute("UPDATE users SET balance=balance+?, last_daily=? WHERE user_id=?", (DAILY_BONUS_MMK, now, uid))
            await update.message.reply_text(f"✅ {DAILY_BONUS_MMK} MMK ရရှိပါပြီ!")
        else:
            await update.message.reply_text("⏳ ၂၄ နာရီ မပြည့်သေးပါ။")

    elif text == "ဖိတ်ခေါ်ရန်👥":
        await update.message.reply_text(f"👥 သင့်ဖိတ်ခေါ်လင့်ခ်:\nhttps://t.me/{BOT_USERNAME}?start=ref_{uid}")

    elif text == "ငွေထုတ်ရန်📤":
        if user[2] < WITHDRAW_MIN_MMK:
            await update.message.reply_text(f"❌ အနည်းဆုံး {WITHDRAW_MIN_MMK} MMK လိုအပ်သည်။")
        else:
            context.user_data['wd'] = True
            await update.message.reply_text("📤 ထုတ်ယူမည့် ပမာဏ နှင့် Payment (KBZPay/Wave) ကို ပို့ပေးပါ။")

    elif context.user_data.get('wd'):
        # Withdraw Request Handling
        try:
            await context.bot.send_message(ADMIN_ID, f"📤 **Withdraw Request**\nUser: {uid}\nInfo: {text}")
            await update.message.reply_text("✅ Admin ထံ တောင်းဆိုမှု ပို့ပြီးပါပြီ။")
        except: pass
        context.user_data['wd'] = False

# =====================
# RUN
# =====================
def main():
    init_db()
    threading.Thread(target=run_health_server, daemon=True).start()
    
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(on_verify_gate, pattern="verify_gate"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    
    print("Bot is starting...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
