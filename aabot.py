import os
import sqlite3
import time
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
# CONFIG (CHANGE THESE)
# =====================
BOT_TOKEN = os.getenv("8256239679:AAG2j3mNNNkme0UPeC_buVzS1m6p2peEvJE").strip()
BOT_USERNAME = "arronairdrop5_bot"   # e.g. aaronairdrops_bot
ADMIN_ID = 8190754710               # your telegram numeric id

DAILY_BONUS_MMK = 20
REF_BONUS_MMK = 20
MISSION_REWARD_MMK = 50

DAILY_COOLDOWN_SEC = 24 * 60 * 60
WITHDRAW_MIN_MMK = 500

DB_PATH = "airdrop.db"

# ---------------------
# CHANNELS (CHANGE)
# Gate: start မလုပ်ခင် join လုပ်ရမယ့် channel 2 ခု
# Mission: mission reward ရဖို့ join လုပ်ရမယ့် channel 5 ခု
# ---------------------
GATE_CHANNELS = [
    "@aaronairdrop2",
    "@aaronproofs1",
]

GATE_LINKS = [
    "https://t.me/aaronairdrop2",
    "https://t.me/aaronproofs1",
]

MISSION_CHANNELS = [
    "@aaronmission1",
    "@aaronmission2",
    "@aaronmission3",
    "@aaronmission4",
    "@aaronmission5",
]

MISSION_LINKS = [
    "https://t.me/aaronmission1",
    "https://t.me/aaronmission2",
    "https://t.me/aaronmission3",
    "https://t.me/aaronmission4",
    "https://t.me/aaronmission5",
]

# =====================
# UI
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
    rows = [[InlineKeyboardButton(f"✅ Join Mission {i+1}", url=MISSION_LINKS[i])]
            for i in range(len(MISSION_LINKS))]
    rows.append([InlineKeyboardButton("🔍 Verify Mission", callback_data="verify_mission")])
    return InlineKeyboardMarkup(rows)

# =====================
# DB
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

def upsert_user(user_id: int, username: str | None):
    now = int(time.time())
    con = db_conn()
    cur = con.cursor()
    cur.execute("SELECT user_id FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    if row is None:
        cur.execute(
            "INSERT INTO users(user_id, username, created_at) VALUES(?,?,?)",
            (user_id, username or "", now),
        )
    else:
        cur.execute("UPDATE users SET username=? WHERE user_id=?", (username or "", user_id))
    con.commit()
    con.close()

def get_user(user_id: int):
    con = db_conn()
    cur = con.cursor()
    cur.execute("""
        SELECT user_id, username, balance, ref_count, ref_by, pending_ref, last_daily, mission_done
        FROM users WHERE user_id=?
    """, (user_id,))
    row = cur.fetchone()
    con.close()
    return row

def add_balance(user_id: int, amount: int):
    con = db_conn()
    cur = con.cursor()
    cur.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amount, user_id))
    con.commit()
    con.close()

def inc_ref(inviter_id: int):
    con = db_conn()
    cur = con.cursor()
    cur.execute("UPDATE users SET ref_count = ref_count + 1 WHERE user_id=?", (inviter_id,))
    con.commit()
    con.close()

def update_last_daily(user_id: int, ts: int):
    con = db_conn()
    cur = con.cursor()
    cur.execute("UPDATE users SET last_daily=? WHERE user_id=?", (ts, user_id))
    con.commit()
    con.close()

def set_mission_done(user_id: int):
    con = db_conn()
    cur = con.cursor()
    cur.execute("UPDATE users SET mission_done=1 WHERE user_id=?", (user_id,))
    con.commit()
    con.close()

def top_referrers(limit: int = 10):
    con = db_conn()
    cur = con.cursor()
    cur.execute("""
        SELECT username, user_id, ref_count
        FROM users
        ORDER BY ref_count DESC, balance DESC
        LIMIT ?
    """, (limit,))
    rows = cur.fetchall()
    con.close()
    return rows

def create_withdraw_request(user_id: int, amount: int, method: str, account: str) -> int:
    now = int(time.time())
    con = db_conn()
    cur = con.cursor()
    cur.execute("""
        INSERT INTO withdraw_requests(user_id, amount, method, account, created_at)
        VALUES(?,?,?,?,?)
    """, (user_id, amount, method, account, now))
    req_id = cur.lastrowid
    con.commit()
    con.close()
    return req_id

def set_pending_ref(user_id: int, inviter_id: int):
    con = db_conn()
    cur = con.cursor()
    cur.execute("UPDATE users SET pending_ref=? WHERE user_id=?", (inviter_id, user_id))
    con.commit()
    con.close()

def clear_pending_ref(user_id: int):
    con = db_conn()
    cur = con.cursor()
    cur.execute("UPDATE users SET pending_ref=NULL WHERE user_id=?", (user_id,))
    con.commit()
    con.close()

def set_ref_by_once(user_id: int, inviter_id: int) -> bool:
    """Set ref_by only if empty. Return True if set."""
    con = db_conn()
    cur = con.cursor()
    cur.execute("SELECT ref_by FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    if not row:
        con.close()
        return False
    if row[0] is not None:
        con.close()
        return False
    cur.execute("UPDATE users SET ref_by=? WHERE user_id=?", (inviter_id, user_id))
    con.commit()
    con.close()
    return True

# =====================
# HELPERS
# =====================
def invite_link(user_id: int) -> str:
    return f"https://t.me/{BOT_USERNAME}?start=ref_{user_id}"

def fmt_time_left(seconds_left: int) -> str:
    h = seconds_left // 3600
    m = (seconds_left % 3600) // 60
    if h > 0:
        return f"{h}h {m}m"
    return f"{m}m"

async def is_member_of(chat: str, user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    m = await context.bot.get_chat_member(chat, user_id)
    return m.status in ("member", "administrator", "creator")

async def check_join_all(chats: list[str], user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    try:
        for ch in chats:
            if not await is_member_of(ch, user_id, context):
                return False
        return True
    except Exception:
        return False

async def show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🎁 AARON AIRDROP မှကြိုဆိုပါတယ်!\n\n"
        f"✅ Daily Bonus: 24 နာရီတစ်ကြိမ် {DAILY_BONUS_MMK} MMK\n"
        f"👥 Referral: တစ်ခါဖိတ်ခေါ်လျှင် {REF_BONUS_MMK} MMK\n"
        f"🎯 Mission complete reward: {MISSION_REWARD_MMK} MMK\n\n"
        "👇 မီနူးမှရွေးပါ"
    )
    if update.message:
        await update.message.reply_text(text, reply_markup=MAIN_KB)
    else:
        await update.callback_query.message.reply_text(text, reply_markup=MAIN_KB)

async def apply_pending_ref_if_any(user_id: int, context: ContextTypes.DEFAULT_TYPE):
    row = get_user(user_id)
    if not row:
        return
    pending = row[5]
    if pending is None:
        return
    inviter_id = int(pending)

    if inviter_id == user_id:
        clear_pending_ref(user_id)
        return

    upsert_user(inviter_id, "")
    if set_ref_by_once(user_id, inviter_id):
        inc_ref(inviter_id)
        add_balance(inviter_id, REF_BONUS_MMK)
    clear_pending_ref(user_id)

# =====================
# HANDLERS
# =====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = user.id
    uname = user.username or ""
    upsert_user(uid, uname)

    if context.args:
        arg = context.args[0].strip()
        if arg.startswith("ref_"):
            try:
                inviter = int(arg.replace("ref_", ""))
                if inviter != uid:
                    set_pending_ref(uid, inviter)
            except:
                pass

    joined_gate = await check_join_all(GATE_CHANNELS, uid, context)
    if not joined_gate:
        await update.message.reply_text(
            "🚫 Start မလုပ်ခင် Gate Channel ၂ ခုကို Join လုပ်ပေးပါ ✅\n\n"
            "ပြီးရင် 🔍 Verify Joined ကိုနှိပ်ပါ။",
            reply_markup=gate_join_kb()
        )
        return

    await apply_pending_ref_if_any(uid, context)
    await show_menu(update, context)

async def on_verify_gate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    upsert_user(uid, q.from_user.username or "")

    joined_gate = await check_join_all(GATE_CHANNELS, uid, context)
    if not joined_gate:
        await q.message.reply_text("❌ Gate Channel ၂ ခုလုံး Join မပြီးသေးပါ။", reply_markup=gate_join_kb())
        return

    await apply_pending_ref_if_any(uid, context)
    await q.message.reply_text("✅ Verified! အခု မီနူးဝင်နိုင်ပါပြီ။", reply_markup=MAIN_KB)

async def on_verify_mission(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    upsert_user(uid, q.from_user.username or "")

    if not await check_join_all(GATE_CHANNELS, uid, context):
        await q.message.reply_text("🚫 Gate Channel ၂ ခု join မပြီးသေးပါ။", reply_markup=gate_join_kb())
        return

    ok = await check_join_all(MISSION_CHANNELS, uid, context)
    if not ok:
        await q.message.reply_text("❌ Mission Channel ၅ ခုလုံး Join မပြီးသေးပါ။", reply_markup=mission_join_kb())
        return

    row = get_user(uid)
    if row and int(row[7]) == 1:
        await q.message.reply_text("✅ Mission ပြီးသားပါ။", reply_markup=MAIN_KB)
        return

    add_balance(uid, MISSION_REWARD_MMK)
    set_mission_done(uid)
    bal = get_user(uid)[2]
    await q.message.reply_text(
        f"✅ Mission ပြီးပါပြီ 🎯\n🎁 {MISSION_REWARD_MMK} MMK ပေါင်းပြီးပါပြီ\n💰 လက်ကျန်: {bal} MMK",
        reply_markup=MAIN_KB
    )

async def on_daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not await check_join_all(GATE_CHANNELS, uid, context):
        await update.message.reply_text("🚫 Gate Channel ၂ ခု join လုပ်ပေးပါ။", reply_markup=gate_join_kb())
        return

    row = get_user(uid)
    if not row:
        upsert_user(uid, update.effective_user.username or "")
        row = get_user(uid)

    last_daily = int(row[6])
    now = int(time.time())
    elapsed = now - last_daily

    if elapsed >= DAILY_COOLDOWN_SEC:
        add_balance(uid, DAILY_BONUS_MMK)
        update_last_daily(uid, now)
        bal = get_user(uid)[2]
        await update.message.reply_text(
            f"✅ ဘောနပ် {DAILY_BONUS_MMK} MMK ရရှိပြီးပါပြီ 🎁\n💰 လက်ကျန်: {bal} MMK",
            reply_markup=MAIN_KB
        )
    else:
        left = DAILY_COOLDOWN_SEC - elapsed
        await update.message.reply_text(
            f"⏳ ဒီနေ့ဘောနပ်ယူပြီးသားပါ။\nနောက်တစ်ခါယူလို့ရမယ့်အချိန်: {fmt_time_left(left)}",
            reply_markup=MAIN_KB
        )

async def on_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not await check_join_all(GATE_CHANNELS, uid, context):
        await update.message.reply_text("🚫 Gate Channel ၂ ခု join လုပ်ပေးပါ။", reply_markup=gate_join_kb())
        return

    row = get_user(uid)
    if not row:
        upsert_user(uid, update.effective_user.username or "")
        row = get_user(uid)

    bal = row[2]
    refc = row[3]
    await update.message.reply_text(
        f"💰 သင့်လက်ကျန်ငွေ: {bal} MMK\n👥 ဖိတ်ခေါ်ထားသူ: {refc} ယောက်",
        reply_markup=MAIN_KB
    )

async def on_ref(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not await check_join_all(GATE_CHANNELS, uid, context):
        await update.message.reply_text("🚫 Gate Channel ၂ ခု join လုပ်ပေးပါ။", reply_markup=gate_join_kb())
        return

    row = get_user(uid)
    refc = row[3] if row else 0
    link = invite_link(uid)

    msg = (
        "သူငယ်ချင်းများကိုဖိတ်ခေါ်ပြီး👥\n"
        "ဘောနပ်🎁 ရယူပါ\n\n"
        "သင့်ဖိတ်ခေါ်ကုဒ်👇\n"
        f"{link}\n\n"
        f"ဖိတ်ခေါ်ထားသောလူဦးရေ: {refc}\n"
        f"တစ်ခါဖိတ်ခေါ်လျှင် {REF_BONUS_MMK} ကျပ်ရရှိမာ ဖြစ်ပါတယ်ဗျ"
    )
    await update.message.reply_text(msg, reply_markup=MAIN_KB)

async def on_top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not await check_join_all(GATE_CHANNELS, uid, context):
        await update.message.reply_text("🚫 Gate Channel ၂ ခု join လုပ်ပေးပါ။", reply_markup=gate_join_kb())
        return

    rows = top_referrers(limit=10)
    if not rows:
        await update.message.reply_text("🎖️ ထိပ်ဆုံးစာရင်း မရှိသေးပါ။", reply_markup=MAIN_KB)
        return

    lines = ["🎖️ ဖိတ်ခေါ်အများဆုံး (Top 10)\n"]
    for i, (username, user_id, refc) in enumerate(rows, start=1):
        name = f"@{username}" if username else f"User{user_id}"
        lines.append(f"{i}) {name} — {refc} invites")

    await update.message.reply_text("\n".join(lines), reply_markup=MAIN_KB)

async def on_mission(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not await check_join_all(GATE_CHANNELS, uid, context):
        await update.message.reply_text("🚫 Gate Channel ၂ ခု join လုပ်ပေးပါ။", reply_markup=gate_join_kb())
        return

    row = get_user(uid)
    if row and int(row[7]) == 1:
        await update.message.reply_text("✅ Mission ပြီးသားပါ။", reply_markup=MAIN_KB)
        return

    await update.message.reply_text(
        "🎯 Mission\n\nMission Channel ၅ ခုလုံး Join လုပ်ပြီး 🔍 Verify Mission ကိုနှိပ်ပါ။",
        reply_markup=mission_join_kb()
    )

async def on_withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not await check_join_all(GATE_CHANNELS, uid, context):
        await update.message.reply_text("🚫 Gate Channel ၂ ခု join လုပ်ပေးပါ။", reply_markup=gate_join_kb())
        return

    row = get_user(uid)
    bal = row[2] if row else 0
    if bal < WITHDRAW_MIN_MMK:
        await update.message.reply_text(
            f"📤 ငွေထုတ်ရန်\nMinimum: {WITHDRAW_MIN_MMK} MMK\nသင့်လက်ကျန်: {bal} MMK\n\nလက်ကျန် မပြည့်သေးပါ။",
            reply_markup=MAIN_KB
        )
        return

    context.user_data["wd_step"] = 1
    await update.message.reply_text(
        f"📤 ငွေထုတ်ရန်\nAmount (MMK) ပို့ပါ။ (Min: {WITHDRAW_MIN_MMK} / Max: {bal})\n\nမလုပ်တော့ဘူးဆို /start",
        reply_markup=None
    )

async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()

    if text == BTN_DAILY:
        return await on_daily(update, context)
    if text == BTN_BAL:
        return await on_balance(update, context)
    if text == BTN_REF:
        return await on_ref(update, context)
    if text == BTN_TOP:
        return await on_top(update, context)
    if text == BTN_MISSION:
        return await on_mission(update, context)
    if text == BTN_WD:
        return await on_withdraw(update, context)

    step = context.user_data.get("wd_step")
    if not step:
        await update.message.reply_text("မီနူးကနေရွေးပါ 👇", reply_markup=MAIN_KB)
        return

    uid = update.effective_user.id
    row = get_user(uid)
    bal = row[2] if row else 0

    if step == 1:
        try:
            amt = int(text)
        except:
            await update.message.reply_text("Amount ကို နံပါတ်နဲ့ပဲ ပို့ပါ။")
            return
        if amt < WITHDRAW_MIN_MMK:
            await update.message.reply_text(f"Minimum {WITHDRAW_MIN_MMK} MMK ထက်နည်းနေပါတယ်။")
            return
        if amt > bal:
            await update.message.reply_text(f"Balance မလုံလောက်ပါ။ Max {bal} MMK ပါ။")
            return
        context.user_data["wd_amount"] = amt
        context.user_data["wd_step"] = 2
        await update.message.reply_text("KBZPay: 09123456789 (သို့) WavePay: 09xxxxxxxxx ပုံစံနဲ့ပို့ပါ။")
        return

    if step == 2:
        amt = int(context.user_data.get("wd_amount", 0))
        if ":" not in text:
            await update.message.reply_text("ဒီပုံစံနဲ့ပို့ပါ: KBZPay: 09123456789")
            return
        method, account = [x.strip() for x in text.split(":", 1)]
        req_id = create_withdraw_request(uid, amt, method, account)
        add_balance(uid, -amt)

        try:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"📤 Withdraw Request\nID:{req_id}\nUser:{uid}\nAmount:{amt}\n{method}:{account}\nStatus:PENDING"
            )
        except:
            pass

        context.user_data.pop("wd_step", None)
        context.user_data.pop("wd_amount", None)
        new_bal = get_user(uid)[2]
        await update.message.reply_text(
            f"✅ Request တင်ပြီးပါပြီ! ID: {req_id}\n💰 လက်ကျန်: {new_bal} MMK",
            reply_markup=MAIN_KB
        )

# =====================
# RUN
# =====================

    
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(on_verify_gate, pattern="^verify_gate$"))
    app.add_handler(CallbackQueryHandler(on_verify_mission, pattern="^verify_mission$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.run_polling()

if __name__ == "__main__":
    main()
