import os
import sqlite3
import time
import threading
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters, CallbackQueryHandler

# =====================
# CONFIGURATION
# =====================
BOT_TOKEN = "8256239679:AAG2j3mNNNkme0UPeC_buVzS1m6p2peEvJE"
BOT_USERNAME = "arronairdrop5_bot"
ADMIN_ID = 8190754710

# အောက်က URL မှာ သင့် Bot ရဲ့ Render Link (ဥပမာ- https://arron-bot.onrender.com) ကို အစားထိုးပါ
RENDER_URL = "https://airdropbot-4.onrender.com" 

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
# WEB SERVER & SELF-AWAKENER
# =====================
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is active and awake!")

def run_health_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    server.serve_forever()

def self_ping():
    """Bot ကို မအိပ်အောင် ၅ မိနစ်တစ်ခါ Website ကို လှမ်းနှိုးပေးမယ့်စနစ်"""
    time.sleep(30)
    while True:
        try:
            r = requests.get(RENDER_URL)
            print(f"Self-ping sent. Status: {r.status_code}")
        except:
            print("Self-ping failed. Checking network...")
        time.sleep(300)

# =====================
# DATABASE MANAGEMENT
# =====================
def init_db():
    with sqlite3.connect(DB_PATH) as con:
        cur = con.cursor()
        cur.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, 
            username TEXT, 
            balance INTEGER DEFAULT 0,
            ref_count INTEGER DEFAULT 0, 
            ref_by INTEGER, 
            pending_ref INTEGER,
            last_daily INTEGER DEFAULT 0, 
            mission_done INTEGER DEFAULT 0, 
            created_at INTEGER)""")
        con.commit()

def get_user(user_id):
    with sqlite3.connect(DB_PATH) as con:
        cur = con.cursor()
        cur.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        return cur.fetchone()

# =====================
# HANDLERS
# =====================
async def check_join_all(chats, user_id, context):
    for ch in chats:
        try:
            m = await context.bot.get_chat_member(ch, user_id)
            if m.status not in ["member", "administrator", "creator"]: return False
        except: return False
    return True

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    username = update.effective_user.username
    now = int(time.time())
    
    with sqlite3.connect(DB_PATH) as con:
        con.execute("INSERT OR IGNORE INTO users (user_id, username, created_at) VALUES (?,?,?)", (uid, username, now))
        con.execute("UPDATE users SET username=? WHERE user_id=?", (username, uid))

    if context.args and context.args[0].startswith("ref_"):
        inviter = int(context.args[0].replace("ref_", ""))
        user = get_user(uid)
        if inviter != uid and user and user[4] is None:
            with sqlite3.connect(DB_PATH) as con:
                con.execute("UPDATE users SET pending_ref=? WHERE user_id=?", (inviter, uid))

    if not await check_join_all(GATE_CHANNELS, uid, context):
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Join Gate 1", url=GATE_LINKS[0])],
            [InlineKeyboardButton("✅ Join Gate 2", url=GATE_LINKS[1])],
            [InlineKeyboardButton("🔍 Verify Join", callback_data="verify_gate")]
        ])
        await update.message.reply_text("🚫 ဆက်လက်အသုံးပြုရန် Gate Channel များကို Join ပေးပါ။", reply_markup=kb)
        return

    main_kb = ReplyKeyboardMarkup([
        [KeyboardButton("နေ့စဉ်ဘောနပ်🎁"), KeyboardButton("လက်ကျန်ငွေ💰")],
        [KeyboardButton("ဖိတ်ခေါ်ရန်👥"), KeyboardButton("Mission 🎯")],
        [KeyboardButton("ငွေထုတ်ရန်📤")]
    ], resize_keyboard=True)
    await update.message.reply_text("🎁 AARON AIRDROP မှ ကြိုဆိုပါတယ်!", reply_markup=main_kb)

async def on_verify_gate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    uid = q.from_user.id
    if await check_join_all(GATE_CHANNELS, uid, context):
        user = get_user(uid)
        if user and user[5]: # Apply pending ref
            inviter_id = user[5]
            with sqlite3.connect(DB_PATH) as con:
                con.execute("UPDATE users SET ref_by=?, ref_count=ref_count+1, balance=balance+?, pending_ref=NULL WHERE user_id=?", (inviter_id, REF_BONUS_MMK, uid))
            try: await context.bot.send_message(inviter_id, f"👥 လူသစ်တစ်ယောက် join သဖြင့် {REF_BONUS_MMK} MMK ရပါပြီ!")
            except: pass
        
        main_kb = ReplyKeyboardMarkup([
            [KeyboardButton("နေ့စဉ်ဘောနပ်🎁"), KeyboardButton("လက်ကျန်ငွေ💰")],
            [KeyboardButton("ဖိတ်ခေါ်ရန်👥"), KeyboardButton("Mission 🎯")],
            [KeyboardButton("ငွေထုတ်ရန်📤")]
        ], resize_keyboard=True)
        await q.message.reply_text("✅ Verified! မီနူးအသုံးပြုနိုင်ပါပြီ။", reply_markup=main_kb)
    else:
        await q.message.reply_text("❌ Join ရန်ကျန်ပါသေးသည်။")

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
            await update.message.reply_text("⏳ ၂၄ နာရီမပြည့်သေးပါ။")
    elif text == "ဖိတ်ခေါ်ရန်👥":
        await update.message.reply_text(f"👥 သင့်လင့်ခ်:\nhttps://t.me/{BOT_USERNAME}?start=ref_{uid}")
    elif text == "ငွေထုတ်ရန်📤":
        if user[2] < WITHDRAW_MIN_MMK:
            await update.message.reply_text(f"❌ အနည်းဆုံး {WITHDRAW_MIN_MMK} MMK ရှိမှ ထုတ်ယူနိုင်ပါမည်။")
        else:
            await update.message.reply_text("📤 ပမာဏနှင့် Payment (ဥပမာ- 500 KPay 09xxx) ကို Admin ဆီ ပို့ပေးပါ။")

# =====================
# MAIN RUNNER
# =====================
def main():
    init_db()
    # threading သုံးပြီး server နဲ့ awakener ကို run ပါမယ်
    threading.Thread(target=run_health_server, daemon=True).start()
    threading.Thread(target=self_ping, daemon=True).start()

    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(on_verify_gate, pattern="^verify_gate$"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    print("Bot is starting with all fixes...")
    application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
