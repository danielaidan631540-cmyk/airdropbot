import os
import sqlite3
import time
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
# RENDER HEALTH CHECK SERVER
# =====================
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is alive and running!")

def run_health_server():
    # Render က ပေးတဲ့ PORT (မရှိရင် 8080) မှာ HTTP Server ဖွင့်ထားပေးပါမယ်
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    print(f"Health server started on port {port}")
    server.serve_forever()

# =====================
# DATABASE MANAGEMENT
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
        cur.execute("SELECT user_id, username, balance, ref_count, ref_by, pending_ref, last_daily, mission_done FROM users WHERE user_id=?", (user_id,))
        return cur.fetchone()

def upsert_user(user_id, username):
    now = int(time.time())
    with sqlite3.connect(DB_PATH) as con:
        cur = con.cursor()
        cur.execute("INSERT OR IGNORE INTO users (user_id, username, created_at) VALUES (?,?,?)", (user_id, username or "", now))
        cur.execute("UPDATE users SET username=? WHERE user_id=?", (username or "", user_id))
        con.commit()

# =====================
# KEYBOARDS
# =====================
MAIN_KB = ReplyKeyboardMarkup([
    [KeyboardButton("နေ့စဉ်ဘောနပ်🎁"), KeyboardButton("လက်ကျန်ငွေ💰")],
    [KeyboardButton("ဖိတ်ခေါ်ရန်👥"), KeyboardButton("ငွေထုတ်ရန်📤")],
    [KeyboardButton("Mission 🎯"), KeyboardButton("ထိပ်ဆုံး🎖️")]
], resize_keyboard=True)

def gate_join_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Join Gate 1", url=GATE_LINKS[0])],
        [InlineKeyboardButton("✅ Join Gate 2", url=GATE_LINKS[1])],
        [InlineKeyboardButton("🔍 Verify Joined", callback_data="verify_gate")]
    ])

def mission_join_kb():
    rows = [[InlineKeyboardButton(f"✅ Join Mission {i+1}", url=MISSION_LINKS[i])] for i in range(len(MISSION_LINKS))]
    rows.append([InlineKeyboardButton("🔍 Verify Mission", callback_data="verify_mission")])
    return InlineKeyboardMarkup(rows)

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
    upsert_user(uid, update.effective_user.username)
    
    # Referral Checking
    if context.args and context.args[0].startswith("ref_"):
        try:
            inviter = int(context.args[0].replace("ref_", ""))
            user = get_user(uid)
            if inviter != uid and user and user[4] is None:
                with sqlite3.connect(DB_PATH) as con:
                    con.execute("UPDATE users SET pending_ref=? WHERE user_id=?", (inviter, uid))
        except: pass

    if not await check_join_all(GATE_CHANNELS, uid, context):
        await update.message.reply_text("🚫 Channel အားလုံးကို Join ပေးမှ အသုံးပြုနိုင်ပါမည်။", reply_markup=gate_join_kb())
        return
    await update.message.reply_text("🎁 AARON AIRDROP မှ ကြိုဆိုပါတယ်!", reply_markup=MAIN_KB)

async def on_verify_gate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    uid = q.from_user.id
    if await check_join_all(GATE_CHANNELS, uid, context):
        user = get_user(uid)
        if user and user[5]: # Apply pending ref
            inviter_id = user[5]
            with sqlite3.connect(DB_PATH) as con:
                con.execute("UPDATE users SET ref_by=?, ref_count=ref_count+1, pending_ref=NULL WHERE user_id=?", (inviter_id, uid))
                con.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (REF_BONUS_MMK, inviter_id))
            try: await context.bot.send_message(inviter_id, f"👥 သင့်လင့်ခ်မှ လူသစ်တစ်ယောက် join သဖြင့် {REF_BONUS_MMK} MMK ရရှိပါသည်!")
            except: pass
        await q.message.reply_text("✅ Verified! မီနူးအသုံးပြုနိုင်ပါပြီ။", reply_markup=MAIN_KB)
    else:
        await q.message.reply_text("❌ Join ရန်ကျန်သေးသည်!", reply_markup=gate_join_kb())

async def on_verify_mission(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    uid = q.from_user.id
    if await check_join_all(MISSION_CHANNELS, uid, context):
        user = get_user(uid)
        if user[7] == 0:
            with sqlite3.connect(DB_PATH) as con:
                con.execute("UPDATE users SET balance=balance+?, mission_done=1 WHERE user_id=?", (MISSION_REWARD_MMK, uid))
            await q.message.reply_text(f"✅ Mission အောင်မြင်ပါသည်။ {MISSION_REWARD_MMK} MMK ရရှိပါသည်။", reply_markup=MAIN_KB)
        else:
            await q.message.reply_text("✅ Mission ပြီးသားဖြစ်ပါသည်။")
    else:
        await q.message.reply_text("❌ Mission များ မပြီးသေးပါ။", reply_markup=mission_join_kb())

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
            await update.message.reply_text(f"✅ ယနေ့အတွက် {DAILY_BONUS_MMK} MMK ရရှိပါပြီ!")
        else:
            await update.message.reply_text("⏳ ၂၄ နာရီမပြည့်သေးပါ။ မနက်ဖြန်မှ ပြန်လာခဲ့ပါ။")
    elif text == "ဖိတ်ခေါ်ရန်👥":
        await update.message.reply_text(f"👥 သင့်ဖိတ်ခေါ်လင့်ခ်:\nhttps://t.me/{BOT_USERNAME}?start=ref_{uid}")
    elif text == "Mission 🎯":
        if user[7] == 1: await update.message.reply_text("✅ Mission ပြီးသားပါ။")
        else: await update.message.reply_text("🎯 Mission Channel များ Join ပြီး Verify နှိပ်ပါ-", reply_markup=mission_join_kb())
    elif text == "ထိပ်ဆုံး🎖️":
        with sqlite3.connect(DB_PATH) as con:
            cur = con.cursor()
            cur.execute("SELECT username, ref_count FROM users ORDER BY ref_count DESC LIMIT 10")
            rows = cur.fetchall()
            msg = "🎖️ **Top 10 Referrers**\n\n"
            for i, r in enumerate(rows, 1):
                msg += f"{i}. @{r[0] if r[0] else 'User'} - {r[1]} refs\n"
            await update.message.reply_text(msg)
    elif text == "ငွေထုတ်ရန်📤":
        if user[2] < WITHDRAW_MIN_MMK:
            await update.message.reply_text(f"❌ အနည်းဆုံး {WITHDRAW_MIN_MMK} MMK လိုအပ်သည်။")
        else:
            context.user_data['wd'] = True
            await update.message.reply_text("📤 ပမာဏနှင့် Payment အချက်အလက်ပို့ပါ (ဥပမာ- 500 KPay 09xxx)")
    elif context.user_data.get('wd'):
        await context.bot.send_message(ADMIN_ID, f"📤 **Withdraw Request**\nUser: {uid}\nInfo: {text}")
        context.user_data['wd'] = False
        await update.message.reply_text("✅ တောင်းဆိုမှု ပို့ပြီးပါပြီ။")

# =====================
# MAIN RUNNER
# =====================
def main():
    init_db()
    # Health Server For Render Port Fix
    threading.Thread(target=run_health_server, daemon=True).start()

    application = Application.builder().token(BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(on_verify_gate, pattern="^verify_gate$"))
    application.add_handler(CallbackQueryHandler(on_verify_mission, pattern="^verify_mission$"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    print("Bot is starting...")
    # Polling mode
    application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
