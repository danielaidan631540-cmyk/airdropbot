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
# CONFIG
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
# RENDER PORT FIX (FAKE SERVER)
# =====================
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running alive!")

def run_health_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    server.serve_forever()

# =====================
# UI & KEYBOARDS
# =====================
BTN_DAILY = "နေ့စဉ်ဘောနပ်🎁"
BTN_BAL = "လက်ကျန်ငွေ💰"
BTN_REF = "ဖိတ်ခေါ်ရန်👥"
BTN_WD = "ငွေထုတ်ရန်📤"
BTN_TOP = "ထိပ်ဆုံး🎖️"
BTN_MISSION = "Mission 🎯"

MAIN_KB = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(BTN_DAILY), KeyboardButton(BTN_BAL)],
        [KeyboardButton(BTN_REF), KeyboardButton(BTN_WD)],
        [KeyboardButton(BTN_MISSION), KeyboardButton(BTN_TOP)],
    ],
    resize_keyboard=True,
)

def gate_join_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Join Gate Channel 1", url=GATE_LINKS[0])],
        [InlineKeyboardButton("✅ Join Gate Channel 2", url=GATE_LINKS[1])],
        [InlineKeyboardButton("🔍 Verify Joined", callback_data="verify_gate")],
    ])

def mission_join_kb():
    rows = [[InlineKeyboardButton(f"✅ Join Mission {i+1}", url=MISSION_LINKS[i])] for i in range(len(MISSION_LINKS))]
    rows.append([InlineKeyboardButton("🔍 Verify Mission", callback_data="verify_mission")])
    return InlineKeyboardMarkup(rows)

# =====================
# DATABASE FUNCTIONS
# =====================
def db_conn():
    return sqlite3.connect(DB_PATH)

def init_db():
    con = db_conn()
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            balance INTEGER NOT NULL DEFAULT 0,
            ref_count INTEGER NOT NULL DEFAULT 0,
            ref_by INTEGER,
            pending_ref INTEGER,
            last_daily INTEGER NOT NULL DEFAULT 0,
            mission_done INTEGER NOT NULL DEFAULT 0,
            created_at INTEGER NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS withdraw_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount INTEGER NOT NULL,
            method TEXT NOT NULL,
            account TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'PENDING',
            created_at INTEGER NOT NULL
        )
    """)
    con.commit()
    con.close()

def upsert_user(user_id, username):
    con = db_conn(); cur = con.cursor()
    cur.execute("SELECT user_id FROM users WHERE user_id=?", (user_id,))
    if not cur.fetchone():
        cur.execute("INSERT INTO users(user_id, username, created_at) VALUES(?,?,?)", (user_id, username or "", int(time.time())))
    else:
        cur.execute("UPDATE users SET username=? WHERE user_id=?", (username or "", user_id))
    con.commit(); con.close()

def get_user(user_id):
    con = db_conn(); cur = con.cursor()
    cur.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone(); con.close()
    return row

def add_balance(user_id, amount):
    con = db_conn(); cur = con.cursor()
    cur.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amount, user_id))
    con.commit(); con.close()

def create_withdraw_request(user_id, amount, method, account):
    con = db_conn(); cur = con.cursor()
    cur.execute("INSERT INTO withdraw_requests(user_id, amount, method, account, created_at) VALUES(?,?,?,?,?)", 
                (user_id, amount, method, account, int(time.time())))
    req_id = cur.lastrowid
    con.commit(); con.close()
    return req_id

# =====================
# HELPERS
# =====================
async def check_join_all(chats, user_id, context):
    for ch in chats:
        try:
            m = await context.bot.get_chat_member(ch, user_id)
            if m.status not in ["member", "administrator", "creator"]: return False
        except: return False
    return True

async def apply_pending_ref(user_id, context):
    row = get_user(user_id)
    if row and row[5]: # pending_ref
        inviter_id = row[5]
        if row[4] is None and inviter_id != user_id:
            con = db_conn(); cur = con.cursor()
            cur.execute("UPDATE users SET ref_by=?, ref_count=ref_count+1 WHERE user_id=?", (inviter_id, user_id))
            cur.execute("UPDATE users SET balance=balance+?, ref_count=ref_count+1 WHERE user_id=?", (REF_BONUS_MMK, inviter_id))
            cur.execute("UPDATE users SET pending_ref=NULL WHERE user_id=?", (user_id,))
            con.commit(); con.close()

# =====================
# HANDLERS
# =====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    upsert_user(uid, update.effective_user.username)
    
    if context.args and context.args[0].startswith("ref_"):
        inviter = int(context.args[0].replace("ref_", ""))
        con = db_conn(); cur = con.cursor()
        cur.execute("UPDATE users SET pending_ref=? WHERE user_id=? AND ref_by IS NULL", (inviter, uid))
        con.commit(); con.close()

    if not await check_join_all(GATE_CHANNELS, uid, context):
        await update.message.reply_text("🚫 Gate Channel ၂ ခုလုံးကို Join ပေးပါ။", reply_markup=gate_join_kb())
        return

    await apply_pending_ref(uid, context)
    await update.message.reply_text("🎁 AARON AIRDROP မှ ကြိုဆိုပါတယ်!", reply_markup=MAIN_KB)

async def on_verify_gate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    uid = q.from_user.id
    if await check_join_all(GATE_CHANNELS, uid, context):
        await apply_pending_ref(uid, context)
        await q.message.reply_text("✅ Verified! မီနူးအသုံးပြုနိုင်ပါပြီ။", reply_markup=MAIN_KB)
    else:
        await q.message.reply_text("❌ Join ရန်ကျန်သေးသည်!", reply_markup=gate_join_kb())

async def on_verify_mission(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    uid = q.from_user.id
    if await check_join_all(MISSION_CHANNELS, uid, context):
        row = get_user(uid)
        if row[7] == 0:
            add_balance(uid, MISSION_REWARD_MMK)
            con = db_conn(); cur = con.cursor()
            cur.execute("UPDATE users SET mission_done=1 WHERE user_id=?", (uid,))
            con.commit(); con.close()
            await q.message.reply_text(f"✅ Mission အောင်မြင်ပါသည်။ {MISSION_REWARD_MMK} MMK ရရှိပါသည်။", reply_markup=MAIN_KB)
        else:
            await q.message.reply_text("✅ Mission ပြီးသားဖြစ်ပါသည်။")
    else:
        await q.message.reply_text("❌ Mission များ မပြီးသေးပါ။", reply_markup=mission_join_kb())

async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    uid = update.effective_user.id
    user = get_user(uid)

    if text == BTN_BAL:
        await update.message.reply_text(f"💰 လက်ကျန်ငွေ: {user[2]} MMK\n👥 ဖိတ်ခေါ်သူ: {user[3]} ယောက်")
    elif text == BTN_DAILY:
        now = int(time.time())
        if now - user[6] >= DAILY_COOLDOWN_SEC:
            add_balance(uid, DAILY_BONUS_MMK)
            con = db_conn(); cur = con.cursor()
            cur.execute("UPDATE users SET last_daily=? WHERE user_id=?", (now, uid))
            con.commit(); con.close()
            await update.message.reply_text(f"✅ {DAILY_BONUS_MMK} MMK ရရှိပါပြီ!")
        else:
            await update.message.reply_text("⏳ ၂၄ နာရီမပြည့်သေးပါ။")
    elif text == BTN_REF:
        await update.message.reply_text(f"👥 ဖိတ်ခေါ်လင့်ခ်:\nhttps://t.me/{BOT_USERNAME}?start=ref_{uid}")
    elif text == BTN_MISSION:
        if user[7] == 1: await update.message.reply_text("✅ Mission ပြီးသားပါ။")
        else: await update.message.reply_text("🎯 Mission ပြီးအောင်လုပ်ပါ-", reply_markup=mission_join_kb())
    elif text == BTN_WD:
        if user[2] < WITHDRAW_MIN_MMK:
            await update.message.reply_text(f"❌ အနည်းဆုံး {WITHDRAW_MIN_MMK} MMK ရှိမှ ထုတ်ယူနိုင်ပါသည်။")
        else:
            context.user_data['wd'] = True
            await update.message.reply_text("📤 ထုတ်မည့်ပမာဏ နှင့် Payment (ဥပမာ: 500 KBZPay 09xxx) ပို့ပေးပါ။")
    elif context.user_data.get('wd'):
        req_id = create_withdraw_request(uid, 0, "Request", text) # Simplified for quick use
        await context.bot.send_message(ADMIN_ID, f"📤 Withdraw Request\nUser: {uid}\nInfo: {text}")
        context.user_data['wd'] = False
        await update.message.reply_text("✅ Request တင်ပြီးပါပြီ။ Admin က စစ်ဆေးပေးပါလိမ့်မည်။")

# =====================
# MAIN RUN
# =====================
def main():
    init_db()
    # Health Server For Render Port Error Fix
    threading.Thread(target=run_health_server, daemon=True).start()

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(on_verify_gate, pattern="^verify_gate$"))
    app.add_handler(CallbackQueryHandler(on_verify_mission, pattern="^verify_mission$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
