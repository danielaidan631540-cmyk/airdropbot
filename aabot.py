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
# RENDER PORT FIX (Render အတွက် ဒါပါမှ အဆင်ပြေမှာပါ)
# =====================
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is active!")

def run_health_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    server.serve_forever()

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
# DB FUNCTIONS (သင့် Code အတိုင်း)
# =====================
def db_conn(): return sqlite3.connect(DB_PATH)

def init_db():
    con = db_conn()
    cur = con.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY, username TEXT, balance INTEGER NOT NULL DEFAULT 0,
        ref_count INTEGER NOT NULL DEFAULT 0, ref_by INTEGER, pending_ref INTEGER,
        last_daily INTEGER NOT NULL DEFAULT 0, mission_done INTEGER NOT NULL DEFAULT 0, created_at INTEGER NOT NULL)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS withdraw_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, amount INTEGER NOT NULL,
        method TEXT NOT NULL, account TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'PENDING', created_at INTEGER NOT NULL)""")
    con.commit(); con.close()

def upsert_user(user_id: int, username: str | None):
    now = int(time.time()); con = db_conn(); cur = con.cursor()
    cur.execute("SELECT user_id FROM users WHERE user_id=?", (user_id,))
    if cur.fetchone() is None:
        cur.execute("INSERT INTO users(user_id, username, created_at) VALUES(?,?,?)", (user_id, username or "", now))
    else:
        cur.execute("UPDATE users SET username=? WHERE user_id=?", (username or "", user_id))
    con.commit(); con.close()

def get_user(user_id: int):
    con = db_conn(); cur = con.cursor()
    cur.execute("SELECT user_id, username, balance, ref_count, ref_by, pending_ref, last_daily, mission_done FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone(); con.close(); return row

def add_balance(user_id: int, amount: int):
    con = db_conn(); cur = con.cursor()
    cur.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amount, user_id))
    con.commit(); con.close()

def set_mission_done(user_id: int):
    con = db_conn(); cur = con.cursor()
    cur.execute("UPDATE users SET mission_done=1 WHERE user_id=?", (user_id,))
    con.commit(); con.close()

def create_withdraw_request(user_id: int, amount: int, method: str, account: str) -> int:
    now = int(time.time()); con = db_conn(); cur = con.cursor()
    cur.execute("INSERT INTO withdraw_requests(user_id, amount, method, account, created_at) VALUES(?,?,?,?,?)", (user_id, amount, method, account, now))
    req_id = cur.lastrowid; con.commit(); con.close(); return req_id

# =====================
# HANDLERS (သင့် Code ထဲက Logic များ)
# =====================
async def check_join_all(chats: list[str], user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    try:
        for ch in chats:
            m = await context.bot.get_chat_member(ch, user_id)
            if m.status not in ("member", "administrator", "creator"): return False
        return True
    except: return False

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    upsert_user(user.id, user.username)
    if not await check_join_all(GATE_CHANNELS, user.id, context):
        await update.message.reply_text("🚫 Join Gate Channels First ✅", reply_markup=gate_join_kb())
        return
    await update.message.reply_text("🎁 AARON AIRDROP မှကြိုဆိုပါတယ်!", reply_markup=MAIN_KB)

async def on_verify_gate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer(); uid = q.from_user.id
    if await check_join_all(GATE_CHANNELS, uid, context):
        await q.message.reply_text("✅ Verified!", reply_markup=MAIN_KB)
    else:
        await q.message.reply_text("❌ Join မပြီးသေးပါ။", reply_markup=gate_join_kb())

async def on_withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    row = get_user(uid)
    bal = row[2] if row else 0
    if bal < WITHDRAW_MIN_MMK:
        await update.message.reply_text(f"❌ လက်ကျန် {bal} MMK သာရှိပါသည်။ (Min: {WITHDRAW_MIN_MMK})")
        return
    context.user_data["wd_step"] = 1
    await update.message.reply_text(f"📤 ပမာဏ (Amount) ကို နံပါတ်တစ်ခုတည်း ပို့ပေးပါ။ (Max: {bal})")

async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    uid = update.effective_user.id
    if text == BTN_DAILY:
        # သင်၏ Daily Bonus Logic...
        await update.message.reply_text("Daily Bonus Logic here...")
    elif text == BTN_BAL:
        row = get_user(uid)
        await update.message.reply_text(f"💰 လက်ကျန်: {row[2]} MMK")
    elif text == BTN_WD:
        await on_withdraw(update, context)
    
    # --- Withdraw Flow (သင့် Logic အတိုင်း) ---
    step = context.user_data.get("wd_step")
    if step == 1:
        try:
            amt = int(text)
            row = get_user(uid)
            if amt < WITHDRAW_MIN_MMK or amt > row[2]:
                await update.message.reply_text("ပမာဏ မှားနေပါသည်။")
                return
            context.user_data["wd_amount"] = amt
            context.user_data["wd_step"] = 2
            await update.message.reply_text("Payment Method နှင့် ဖုန်းနံပါတ်ပို့ပါ (ဥပမာ- KBZPay: 09xxx)")
        except: await update.message.reply_text("နံပါတ်ပဲ ပို့ပါ။")
    elif step == 2:
        amt = context.user_data["wd_amount"]
        method, account = text.split(":") if ":" in text else ("Payment", text)
        req_id = create_withdraw_request(uid, amt, str(method), str(account))
        add_balance(uid, -amt)
        context.user_data.clear()
        await update.message.reply_text(f"✅ တောင်းဆိုမှုအောင်မြင်သည်။ ID: {req_id}", reply_markup=MAIN_KB)
        # Admin ကို အသိပေးခြင်း
        await context.bot.send_message(ADMIN_ID, f"🔔 Withdraw Request\nID: {req_id}\nUser: {uid}\nAmount: {amt}\nInfo: {text}")

# =====================
# MAIN
# =====================
def main():
    init_db()
    # Health server ကို thread နဲ့ run ပါမယ် (Render error မတက်အောင်)
    threading.Thread(target=run_health_server, daemon=True).start()
    
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(on_verify_gate, pattern="^verify_gate$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.run_polling()

if __name__ == "__main__":
    main()
