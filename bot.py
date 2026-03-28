import logging
import os
import json
import random
import aiohttp
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("BOT_TOKEN", "8700788744:AAEOnYVlBLBmYa5cq42FzvKl_ejt3QVmgmM")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "highsecurityprison20110403")
DATA_FILE = "group_data.json"
MAX_STRIKES = 3
TENOR_KEY = "AIzaSyC0GqEFQBM1EBuQi4iQ2JRQH_V2AY2HPKU"

# ── PREMIUM EMOJI ─────────────────────────────────────────────────────────────
E = {
    "star":     "5289838457995162746",
    "fire":     "5282950541633159914",
    "crown":    "5282771355597573467",
    "diamond":  "5282951851598187151",
    "bolt":     "5307573700810278628",
    "heart":    "5330281399062662593",
    "skull":    "5231119159772877401",
    "shield":   "5233307505739729799",
    "sword":    "5296611823284426406",
    "coin":     "5296547334350477502",
    "trophy":   "5296706776421408363",
    "pin":      "5296526834471573876",
    "warning":  "5294239399314233968",
    "ban":      "5296753127708464916",
    "rank1":    "5301148086138082742",
    "rank2":    "5255711399480410850",
    "rank3":    "5255949344963576350",
    "rank4":    "5283143750736975265",
    "rank5":    "5256242240258330190",
    "rank6":    "5256092753921593216",
    "rank7":    "5255749281091971709",
    "rank8":    "5282977827560397021",
    "casino":   "5289880024688651953",
    "work":     "5292214004406574147",
    "pet":      "5289887115679658691",
}

def pe(key, fallback="⭐"):
    return f'<tg-emoji emoji-id="{E[key]}">{fallback}</tg-emoji>'

CHANNEL_RULES_HTML = (
    f'{pe("pin","📌")} <b>bot by fucckeddream</b>\n'
    f'{pe("warning","⚠️")} Запрещены любые оскорбления\n'
    f'{pe("ban","🚫")} Запрещены DDOS/SWAT/DOX'
)

# ── RANKS ─────────────────────────────────────────────────────────────────────
RANKS = [
    (0,     "rank1", "🥚", "Новичок"),
    (100,   "rank2", "🐣", "Птенец"),
    (500,   "rank3", "🐥", "Пользователь"),
    (1500,  "rank4", "⚔️", "Воин"),
    (3000,  "rank5", "🛡️", "Ветеран"),
    (6000,  "rank6", "💎", "Элита"),
    (12000, "rank7", "👑", "Легенда"),
    (25000, "rank8", "🌟", "Бессмертный"),
]

def get_rank(xp, html=False):
    row = RANKS[0]
    for r in RANKS:
        if xp >= r[0]: row = r
    _, ekey, fallback, name = row
    if html:
        return f'{pe(ekey, fallback)} {name}'
    return f"{fallback} {name}"

def next_rank_info(xp):
    for r in RANKS:
        if xp < r[0]:
            return r[0], f"{r[2]} {r[3]}"
    return None, None

# ── DATA ──────────────────────────────────────────────────────────────────────
def load():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"admins": [], "users": {}, "settings": {"fun_enabled": True}}

def save(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_user(data, user_id, username="", full_name=""):
    uid = str(user_id)
    if uid not in data["users"]:
        data["users"][uid] = {
            "username": username, "full_name": full_name,
            "coins": 100, "xp": 0, "nickname": "",
            "pet_size": 10, "pet_last": "", "work_last": "", "daily_last": "",
            "married_to": "", "proposals": [], "msg_count": 0,
            "strikes": 0, "muted_until": "", "banned": False,
        }
    u = data["users"][uid]
    for k, v in [("strikes",0),("muted_until",""),("banned",False)]:
        if k not in u: u[k] = v
    return u

def dn(u):
    return u.get("nickname") or u.get("full_name") or u.get("username") or "Неизвестный"

def is_admin(uid):
    return uid in load()["admins"]

def is_fun():
    return load().get("settings", {}).get("fun_enabled", True)

# ── GUARDS ────────────────────────────────────────────────────────────────────
async def req_admin(update):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Только для администраторов бота.")
        return False
    return True

async def req_fun(update):
    if not is_fun():
        await update.message.reply_text("🔒 Развлечения сейчас отключены.")
        return False
    return True

def get_target(update):
    if update.message.reply_to_message:
        return update.message.reply_to_message.from_user
    return None

def parse_duration(s):
    s = s.strip().lower()
    try:
        if s.endswith("m"): return int(s[:-1])
        if s.endswith("h"): return int(s[:-1]) * 60
        if s.endswith("d"): return int(s[:-1]) * 1440
        return int(s)
    except ValueError:
        return None

def fmt_dur(m):
    if m < 60: return f"{m} мин"
    if m < 1440: return f"{m//60} ч"
    return f"{m//1440} д"

# ════════════════════════════════════════════════════════════════════════════════
#  AUTH
# ════════════════════════════════════════════════════════════════════════════════
async def admin_cmd(update, ctx):
    user = update.effective_user
    if not ctx.args:
        await update.message.reply_text("🔑 /admin <пароль>"); return
    if " ".join(ctx.args) == ADMIN_PASSWORD:
        data = load()
        if user.id not in data["admins"]:
            data["admins"].append(user.id)
            save(data)
        await update.message.reply_text("✅ Ты теперь администратор бота!")
    else:
        await update.message.reply_text("❌ Неверный пароль.")

async def revoke_cmd(update, ctx):
    data = load()
    if update.effective_user.id in data["admins"]:
        data["admins"].remove(update.effective_user.id)
        save(data)
    await update.message.reply_text("✅ Права сняты.")

# ════════════════════════════════════════════════════════════════════════════════
#  MODERATION
# ════════════════════════════════════════════════════════════════════════════════
async def ban_cmd(update, ctx):
    if not await req_admin(update): return
    t = get_target(update)
    if not t: await update.message.reply_text("↩️ Ответь на сообщение нарушителя."); return
    reason = " ".join(ctx.args) if ctx.args else "Нарушение правил"
    data = load(); u = get_user(data, t.id, t.username or "", t.full_name)
    u["banned"] = True; save(data)
    try:
        await ctx.bot.ban_chat_member(update.effective_chat.id, t.id)
        await update.message.reply_text(
            f'{pe("ban","🔨")} <b>{dn(u)}</b> забанен.\n📋 {reason}', parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def unban_cmd(update, ctx):
    if not await req_admin(update): return
    t = get_target(update)
    if not t: await update.message.reply_text("↩️ Ответь на сообщение."); return
    data = load(); u = get_user(data, t.id, t.username or "", t.full_name)
    u["banned"] = False; u["strikes"] = 0; save(data)
    try:
        await ctx.bot.unban_chat_member(update.effective_chat.id, t.id, only_if_banned=True)
        await update.message.reply_text(f'✅ <b>{dn(u)}</b> разбанен.', parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def kick_cmd(update, ctx):
    if not await req_admin(update): return
    t = get_target(update)
    if not t: await update.message.reply_text("↩️ Ответь на сообщение нарушителя."); return
    reason = " ".join(ctx.args) if ctx.args else "Нарушение правил"
    cid = update.effective_chat.id
    data = load(); u = get_user(data, t.id, t.username or "", t.full_name); save(data)
    try:
        await ctx.bot.ban_chat_member(cid, t.id)
        await ctx.bot.unban_chat_member(cid, t.id)
        await update.message.reply_text(
            f'{pe("ban","👟")} <b>{dn(u)}</b> кикнут.\n📋 {reason}', parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def mute_cmd(update, ctx):
    if not await req_admin(update): return
    t = get_target(update)
    if not t: await update.message.reply_text("↩️ Ответь на сообщение."); return
    dur_str = ctx.args[0] if ctx.args else "10m"
    mins = parse_duration(dur_str)
    if mins is None: await update.message.reply_text("❌ Формат: 10m / 2h / 1d"); return
    reason = " ".join(ctx.args[1:]) if len(ctx.args) > 1 else "Нарушение правил"
    until = datetime.utcnow() + timedelta(minutes=mins)
    data = load(); u = get_user(data, t.id, t.username or "", t.full_name)
    u["muted_until"] = until.isoformat(); save(data)
    try:
        await ctx.bot.restrict_chat_member(
            update.effective_chat.id, t.id,
            permissions=ChatPermissions(can_send_messages=False), until_date=until)
        await update.message.reply_text(
            f'🔇 <b>{dn(u)}</b> замьючен на <b>{fmt_dur(mins)}</b>.\n📋 {reason}', parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def unmute_cmd(update, ctx):
    if not await req_admin(update): return
    t = get_target(update)
    if not t: await update.message.reply_text("↩️ Ответь на сообщение."); return
    data = load(); u = get_user(data, t.id, t.username or "", t.full_name)
    u["muted_until"] = ""; save(data)
    try:
        await ctx.bot.restrict_chat_member(
            update.effective_chat.id, t.id,
            permissions=ChatPermissions(
                can_send_messages=True, can_send_media_messages=True,
                can_send_polls=True, can_send_other_messages=True,
                can_add_web_page_previews=True))
        await update.message.reply_text(f'🔊 <b>{dn(u)}</b> размьючен.', parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def ro_cmd(update, ctx):
    if not await req_admin(update): return
    t = get_target(update)
    if not t: await update.message.reply_text("↩️ Ответь на сообщение."); return
    dur_str = ctx.args[0] if ctx.args else "30m"
    mins = parse_duration(dur_str)
    if mins is None: await update.message.reply_text("❌ Формат: 30m / 2h / 1d"); return
    until = datetime.utcnow() + timedelta(minutes=mins)
    data = load(); u = get_user(data, t.id, t.username or "", t.full_name); save(data)
    try:
        await ctx.bot.restrict_chat_member(
            update.effective_chat.id, t.id,
            permissions=ChatPermissions(can_send_messages=False), until_date=until)
        await update.message.reply_text(
            f'📖 <b>{dn(u)}</b> в режиме чтения на <b>{fmt_dur(mins)}</b>.', parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def strike_cmd(update, ctx):
    if not await req_admin(update): return
    t = get_target(update)
    if not t: await update.message.reply_text("↩️ Ответь на сообщение нарушителя."); return
    reason = " ".join(ctx.args) if ctx.args else "Нарушение правил"
    data = load(); u = get_user(data, t.id, t.username or "", t.full_name)
    u["strikes"] = u.get("strikes", 0) + 1
    strikes = u["strikes"]; save(data)
    if strikes >= MAX_STRIKES:
        u["banned"] = True; save(data)
        try: await ctx.bot.ban_chat_member(update.effective_chat.id, t.id)
        except Exception: pass
        await update.message.reply_text(
            f'{pe("ban","🚫")} <b>{dn(u)}</b> — страйк {strikes}/{MAX_STRIKES} → <b>автобан!</b>\n📋 {reason}',
            parse_mode="HTML")
    else:
        await update.message.reply_text(
            f'{pe("warning","⚠️")} <b>{dn(u)}</b> — страйк <b>{strikes}/{MAX_STRIKES}</b>\n'
            f'📋 {reason}\n❗ Ещё {MAX_STRIKES-strikes} страйк(ов) → бан.',
            parse_mode="HTML")

async def unstrike_cmd(update, ctx):
    if not await req_admin(update): return
    t = get_target(update)
    if not t: await update.message.reply_text("↩️ Ответь на сообщение."); return
    data = load(); u = get_user(data, t.id, t.username or "", t.full_name)
    if u["strikes"] > 0: u["strikes"] -= 1
    save(data)
    await update.message.reply_text(
        f'✅ Страйк снят. У <b>{dn(u)}</b> — <b>{u["strikes"]}/{MAX_STRIKES}</b>.', parse_mode="HTML")

async def warn_cmd(update, ctx):
    if not await req_admin(update): return
    t = get_target(update)
    if not t: await update.message.reply_text("↩️ Ответь на сообщение нарушителя."); return
    reason = " ".join(ctx.args) if ctx.args else "Нарушение правил"
    data = load(); u = get_user(data, t.id, t.username or "", t.full_name); save(data)
    await update.message.reply_text(
        f'{pe("warning","⚠️")} <b>{dn(u)}</b>, предупреждение!\n'
        f'📋 {reason}\n<i>Следующие нарушения — мут или бан.</i>', parse_mode="HTML")

async def purge_cmd(update, ctx):
    if not await req_admin(update): return
    try: count = min(int(ctx.args[0]) if ctx.args else 5, 50)
    except ValueError: await update.message.reply_text("❌ /purge 10"); return
    import asyncio
    cid = update.effective_chat.id
    mid = update.message.message_id
    deleted = 0
    for i in range(mid, mid - count - 1, -1):
        try: await ctx.bot.delete_message(cid, i); deleted += 1
        except Exception: pass
    note = await ctx.bot.send_message(cid, f"🗑️ Удалено <b>{deleted}</b> сообщений.", parse_mode="HTML")
    await asyncio.sleep(5)
    try: await note.delete()
    except Exception: pass

async def userinfo_cmd(update, ctx):
    if not await req_admin(update): return
    t = get_target(update)
    if not t: await update.message.reply_text("↩️ Ответь на сообщение пользователя."); return
    data = load(); u = get_user(data, t.id, t.username or "", t.full_name)
    muted_str = ""
    if u.get("muted_until"):
        try:
            until = datetime.fromisoformat(u["muted_until"])
            if until > datetime.utcnow():
                muted_str = f'\n🔇 Мут до: {until.strftime("%d.%m %H:%M")} UTC'
        except Exception: pass
    await update.message.reply_text(
        f'🔍 <b>Инфо</b>\n\n'
        f'👤 {dn(u)}\n🆔 <code>{t.id}</code>\n'
        f'📛 @{t.username or "—"}\n'
        f'⚠️ Страйков: {u.get("strikes",0)}/{MAX_STRIKES}\n'
        f'🚫 Забанен: {"да" if u.get("banned") else "нет"}'
        f'{muted_str}\n'
        f'💬 Сообщений: {u.get("msg_count",0)}\n'
        f'💰 Монет: {u.get("coins",0)}\n'
        f'⭐ XP: {u.get("xp",0)} ({get_rank(u.get("xp",0))})',
        parse_mode="HTML")

async def funoff_cmd(update, ctx):
    if not await req_admin(update): return
    data = load()
    data.setdefault("settings", {})["fun_enabled"] = False; save(data)
    await update.message.reply_text(
        "🔒 <b>Режим строгой модерации.</b>\nРазвлечения отключены.", parse_mode="HTML")

async def funon_cmd(update, ctx):
    if not await req_admin(update): return
    data = load()
    data.setdefault("settings", {})["fun_enabled"] = True; save(data)
    await update.message.reply_text("🎉 <b>Развлечения включены!</b>", parse_mode="HTML")

async def add_coins(update, ctx):
    if not await req_admin(update): return
    if not update.message.reply_to_message or not ctx.args:
        await update.message.reply_text("/addcoins <сумма> (reply)"); return
    try: amount = int(ctx.args[0])
    except ValueError: await update.message.reply_text("❌ Некорректная сумма."); return
    t = update.message.reply_to_message.from_user
    data = load(); u = get_user(data, t.id, t.username or "", t.full_name)
    u["coins"] += amount; save(data)
    await update.message.reply_text(
        f'✅ <b>{dn(u)}</b> +<b>{amount} монет</b>', parse_mode="HTML")

# ════════════════════════════════════════════════════════════════════════════════
#  ECONOMY / FUN
# ════════════════════════════════════════════════════════════════════════════════
async def profile(update, ctx):
    if not await req_fun(update): return
    user = update.effective_user
    data = load(); u = get_user(data, user.id, user.username or "", user.full_name); save(data)
    rank_html = get_rank(u["xp"], html=True)
    nxt, nxt_name = next_rank_info(u["xp"])
    progress = ""
    if nxt:
        pct = int((u["xp"]/nxt)*20)
        bar = "█"*pct + "░"*(20-pct)
        progress = f'\n<code>[{bar}]</code> до {nxt_name}'
    married = ""
    if u.get("married_to"):
        p = data["users"].get(u["married_to"], {})
        married = f'\n{pe("heart","💍")} В браке с: <b>{dn(p)}</b>'
    await update.message.reply_text(
        f'{pe("star","⭐")} <b>{dn(u)}</b>\n'
        f'🏅 {rank_html}\n'
        f'{pe("star","⭐")} {u["xp"]} XP{progress}\n'
        f'{pe("coin","💰")} {u["coins"]} монет\n'
        f'{pe("pet","🐾")} Питомец: {u["pet_size"]} см\n'
        f'{pe("warning","⚠️")} Страйков: {u.get("strikes",0)}/{MAX_STRIKES}\n'
        f'💬 {u["msg_count"]} сообщ.'
        f'{married}',
        parse_mode="HTML")

async def set_nick(update, ctx):
    if not await req_fun(update): return
    if not ctx.args: await update.message.reply_text("✏️ /nick <никнейм>"); return
    nick = " ".join(ctx.args)[:32]
    data = load()
    u = get_user(data, update.effective_user.id, update.effective_user.username or "", update.effective_user.full_name)
    u["nickname"] = nick; save(data)
    await update.message.reply_text(f"✅ Ник: <b>{nick}</b>", parse_mode="HTML")

async def balance(update, ctx):
    if not await req_fun(update): return
    data = load(); u = get_user(data, update.effective_user.id); save(data)
    await update.message.reply_text(
        f'{pe("coin","💰")} <b>{u["coins"]} монет</b>', parse_mode="HTML")

async def give_coins(update, ctx):
    if not await req_fun(update): return
    user = update.effective_user
    if not update.message.reply_to_message or not ctx.args:
        await update.message.reply_text("↩️ /give <сумма> (reply)"); return
    try:
        amount = int(ctx.args[0])
        if amount <= 0: raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Некорректная сумма."); return
    t = update.message.reply_to_message.from_user
    data = load()
    s = get_user(data, user.id, user.username or "", user.full_name)
    r = get_user(data, t.id, t.username or "", t.full_name)
    if s["coins"] < amount: await update.message.reply_text("❌ Недостаточно монет."); return
    s["coins"] -= amount; r["coins"] += amount; save(data)
    await update.message.reply_text(
        f'{pe("coin","💰")} <b>{dn(s)}</b> → <b>{dn(r)}</b>: <b>{amount} монет</b>', parse_mode="HTML")

async def daily(update, ctx):
    if not await req_fun(update): return
    user = update.effective_user
    data = load(); u = get_user(data, user.id, user.username or "", user.full_name)
    now = datetime.utcnow()
    if u.get("daily_last"):
        diff = now - datetime.fromisoformat(u["daily_last"])
        if diff < timedelta(hours=22):
            rem = timedelta(hours=22) - diff
            h = int(rem.total_seconds())//3600; m = (int(rem.total_seconds())%3600)//60
            await update.message.reply_text(f"⏳ Следующий бонус через <b>{h}ч {m}м</b>.", parse_mode="HTML"); return
    reward = random.randint(50, 200)
    u["coins"] += reward; u["xp"] += 10; u["daily_last"] = now.isoformat(); save(data)
    await update.message.reply_text(
        f'🎁 Ежедневный бонус: <b>+{reward} монет</b> и <b>+10 XP</b>!\n'
        f'{pe("coin","💰")} Баланс: {u["coins"]}', parse_mode="HTML")

JOBS = [
    ("🧑‍💻 поработал программистом", 80, 300),
    ("🚕 развозил пассажиров", 50, 150),
    ("🍕 доставлял пиццу", 40, 120),
    ("🏗️ строил здания", 60, 200),
    ("🎨 нарисовал картину", 70, 250),
    ("📦 фасовал товары", 45, 130),
    ("🎮 стримил игры", 30, 400),
    ("📝 написал статью", 55, 180),
    ("🔧 чинил технику", 65, 220),
    ("🌾 работал на ферме", 35, 110),
]

async def work(update, ctx):
    if not await req_fun(update): return
    user = update.effective_user
    data = load(); u = get_user(data, user.id, user.username or "", user.full_name)
    now = datetime.utcnow()
    if u.get("work_last") and now - datetime.fromisoformat(u["work_last"]) < timedelta(hours=1):
        m = int((timedelta(hours=1)-(now-datetime.fromisoformat(u["work_last"]))).total_seconds()/60)
        await update.message.reply_text(f"😴 Работа через <b>{m} мин</b>.", parse_mode="HTML"); return
    job, mn, mx = random.choice(JOBS); earned = random.randint(mn, mx)
    u["coins"] += earned; u["xp"] += 5; u["work_last"] = now.isoformat(); save(data)
    await update.message.reply_text(
        f'{pe("work","💼")} {job} — <b>+{earned} монет</b>!\n'
        f'{pe("coin","💰")} {u["coins"]} | ⭐ {u["xp"]} XP', parse_mode="HTML")

async def pet_cmd(update, ctx):
    if not await req_fun(update): return
    user = update.effective_user
    data = load(); u = get_user(data, user.id, user.username or "", user.full_name)
    now = datetime.utcnow()
    if u.get("pet_last") and now - datetime.fromisoformat(u["pet_last"]) < timedelta(hours=6):
        rem = timedelta(hours=6)-(now-datetime.fromisoformat(u["pet_last"]))
        h = int(rem.total_seconds())//3600; m = (int(rem.total_seconds())%3600)//60
        await update.message.reply_text(
            f'{pe("pet","🐾")} Кормление через <b>{h}ч {m}м</b>. Сейчас: <b>{u["pet_size"]} см</b>',
            parse_mode="HTML"); return
    growth = random.randint(-3, 10); u["pet_size"] = max(1, u["pet_size"]+growth)
    u["pet_last"] = now.isoformat(); save(data)
    emoji = "📈" if growth > 0 else ("📉" if growth < 0 else "➡️")
    msg = "подрос" if growth > 0 else ("усох" if growth < 0 else "не изменился")
    await update.message.reply_text(
        f'{pe("pet","🐾")} Питомец {msg}! {emoji}\n📏 <b>{u["pet_size"]} см</b>', parse_mode="HTML")

async def pet_top(update, ctx):
    if not await req_fun(update): return
    data = load()
    top = sorted(data["users"].items(), key=lambda x: x[1].get("pet_size",0), reverse=True)[:10]
    text = f'{pe("trophy","🏆")} <b>Топ питомцев:</b>\n\n'
    for i,(uid,u) in enumerate(top,1):
        medal = {1:"🥇",2:"🥈",3:"🥉"}.get(i,f"{i}.")
        text += f'{medal} {dn(u)} — <b>{u.get("pet_size",0)} см</b>\n'
    await update.message.reply_text(text, parse_mode="HTML")

async def top_xp(update, ctx):
    if not await req_fun(update): return
    data = load()
    top = sorted(data["users"].items(), key=lambda x: x[1].get("xp",0), reverse=True)[:10]
    text = f'{pe("trophy","🏆")} <b>Топ по XP:</b>\n\n'
    for i,(uid,u) in enumerate(top,1):
        medal = {1:"🥇",2:"🥈",3:"🥉"}.get(i,f"{i}.")
        text += f'{medal} {dn(u)} — {get_rank(u.get("xp",0))} | <b>{u.get("xp",0)} XP</b>\n'
    await update.message.reply_text(text, parse_mode="HTML")

async def top_coins(update, ctx):
    if not await req_fun(update): return
    data = load()
    top = sorted(data["users"].items(), key=lambda x: x[1].get("coins",0), reverse=True)[:10]
    text = f'{pe("coin","💰")} <b>Топ богачей:</b>\n\n'
    for i,(uid,u) in enumerate(top,1):
        medal = {1:"🥇",2:"🥈",3:"🥉"}.get(i,f"{i}.")
        text += f'{medal} {dn(u)} — <b>{u.get("coins",0)} монет</b>\n'
    await update.message.reply_text(text, parse_mode="HTML")

# ── CASINO ────────────────────────────────────────────────────────────────────
SLOTS = ["🍒","🍋","🍊","🍇","⭐","💎","7️⃣"]

async def casino(update, ctx):
    if not await req_fun(update): return
    user = update.effective_user
    if not ctx.args: await update.message.reply_text("🎰 /casino <ставка>"); return
    data = load(); u = get_user(data, user.id, user.username or "", user.full_name)
    try:
        bet = int(ctx.args[0])
        if bet <= 0 or bet > u["coins"]: raise ValueError
    except ValueError:
        await update.message.reply_text(f"❌ Некорректная ставка. У тебя {u['coins']} монет."); return
    s1,s2,s3 = [random.choice(SLOTS) for _ in range(3)]
    line = f"{s1} | {s2} | {s3}"
    if s1==s2==s3=="7️⃣": mult,result = 10,f'{pe("trophy","🎉")} ДЖЕКПОТ!'
    elif s1==s2==s3: mult,result = 5,f'{pe("star","🎊")} Три в ряд!'
    elif s1==s2 or s2==s3 or s1==s3: mult,result = 2,"✨ Два совпадения!"
    else: mult,result = 0,"😔 Не повезло..."
    if mult:
        won=bet*mult; u["coins"]+=won-bet; u["xp"]+=3
        msg=f"{result}\n{line}\n\n<b>+{won} монет</b> (x{mult})!\n{pe('coin','💰')} {u['coins']}"
    else:
        u["coins"]-=bet
        msg=f"{result}\n{line}\n\n<b>-{bet} монет</b>\n{pe('coin','💰')} {u['coins']}"
    save(data)
    await update.message.reply_text(f"🎰 <b>Слоты</b>\n\n{msg}", parse_mode="HTML")

async def flip(update, ctx):
    if not await req_fun(update): return
    user = update.effective_user
    if len(ctx.args) < 2: await update.message.reply_text("🪙 /flip <орёл/решка> <ставка>"); return
    choice = ctx.args[0].lower().replace("орел","орёл")
    if choice not in ("орёл","решка"): await update.message.reply_text("❌ орёл или решка"); return
    data = load(); u = get_user(data, user.id, user.username or "", user.full_name)
    try:
        bet = int(ctx.args[1])
        if bet <= 0 or bet > u["coins"]: raise ValueError
    except ValueError:
        await update.message.reply_text(f"❌ Некорректная ставка. У тебя {u['coins']}."); return
    result = random.choice(["орёл","решка"])
    if choice == result: u["coins"]+=bet; u["xp"]+=2; msg=f"🪙 Выпал <b>{result}</b> — угадал! <b>+{bet} монет</b>"
    else: u["coins"]-=bet; msg=f"🪙 Выпал <b>{result}</b> — не угадал. <b>-{bet} монет</b>"
    save(data)
    await update.message.reply_text(f"{msg}\n{pe('coin','💰')} {u['coins']}", parse_mode="HTML")

async def dice_game(update, ctx):
    if not await req_fun(update): return
    user = update.effective_user
    if not ctx.args: await update.message.reply_text("🎲 /dice <ставка>"); return
    data = load(); u = get_user(data, user.id, user.username or "", user.full_name)
    try:
        bet = int(ctx.args[0])
        if bet <= 0 or bet > u["coins"]: raise ValueError
    except ValueError:
        await update.message.reply_text(f"❌ Некорректная ставка. У тебя {u['coins']}."); return
    p,b = random.randint(1,6), random.randint(1,6)
    if p>b: u["coins"]+=bet; u["xp"]+=2; r=f"🎲 {p} vs {b} — Победа! <b>+{bet}</b>"
    elif p<b: u["coins"]-=bet; r=f"🎲 {p} vs {b} — Поражение. <b>-{bet}</b>"
    else: r=f"🎲 {p} vs {b} — Ничья!"
    save(data)
    await update.message.reply_text(f"{r}\n{pe('coin','💰')} {u['coins']}", parse_mode="HTML")

async def roulette(update, ctx):
    if not await req_fun(update): return
    user = update.effective_user
    if len(ctx.args) < 2: await update.message.reply_text("🎡 /roulette <красное/чёрное/0-36> <ставка>"); return
    data = load(); u = get_user(data, user.id, user.username or "", user.full_name)
    try:
        bet = int(ctx.args[-1])
        if bet <= 0 or bet > u["coins"]: raise ValueError
    except ValueError:
        await update.message.reply_text(f"❌ Некорректная ставка. У тебя {u['coins']}."); return
    choice = ctx.args[0].lower(); spin = random.randint(0,36)
    reds = {1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36}
    color = "🔴" if spin in reds else ("⚫" if spin else "🟢")
    if choice in ("красное","красный"): won=spin in reds; mult=2
    elif choice in ("чёрное","чёрный"): won=spin not in reds and spin!=0; mult=2
    else:
        try: num=int(choice); won=spin==num; mult=36
        except ValueError: await update.message.reply_text("❌ красное / чёрное / число 0-36"); return
    if won:
        gain=bet*mult-bet; u["coins"]+=gain; u["xp"]+=3; result=f"✅ <b>+{gain} монет</b>"
    else:
        u["coins"]-=bet; result=f"❌ <b>-{bet} монет</b>"
    save(data)
    await update.message.reply_text(
        f"🎡 Выпало: <b>{spin}</b> {color}\n{result}\n{pe('coin','💰')} {u['coins']}", parse_mode="HTML")

# ── MARRIAGE ──────────────────────────────────────────────────────────────────
async def propose(update, ctx):
    if not await req_fun(update): return
    user = update.effective_user
    if not update.message.reply_to_message: await update.message.reply_text("💍 Ответь на сообщение."); return
    t = update.message.reply_to_message.from_user
    if t.id == user.id: await update.message.reply_text("😅 Нельзя жениться на себе."); return
    data = load()
    u = get_user(data, user.id, user.username or "", user.full_name)
    tv = get_user(data, t.id, t.username or "", t.full_name)
    if u.get("married_to"): await update.message.reply_text("💔 Ты уже в браке. /divorce"); return
    if tv.get("married_to"): await update.message.reply_text(f"💔 {dn(tv)} уже в браке."); return
    if str(user.id) in tv.get("proposals",[]): await update.message.reply_text("⏳ Уже отправлял предложение."); return
    if "proposals" not in tv: tv["proposals"] = []
    tv["proposals"].append(str(user.id)); save(data)
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("💍 Принять", callback_data=f"marry_accept_{user.id}"),
        InlineKeyboardButton("❌ Отклонить", callback_data=f"marry_decline_{user.id}"),
    ]])
    await update.message.reply_text(
        f'💍 <b>{dn(u)}</b> делает предложение <b>{dn(tv)}</b>!\n{dn(tv)}, согласен(на)?',
        parse_mode="HTML", reply_markup=kb)

async def marry_callback(update, ctx):
    query = update.callback_query; await query.answer()
    user = query.from_user; parts = query.data.split("_")
    action, proposer_id = parts[1], int(parts[2])
    data = load()
    u = get_user(data, user.id, user.username or "", user.full_name)
    p = get_user(data, proposer_id)
    if str(proposer_id) not in u.get("proposals",[]):
        await query.edit_message_text("❌ Предложение недействительно."); return
    u["proposals"].remove(str(proposer_id))
    if action == "accept":
        u["married_to"]=str(proposer_id); p["married_to"]=str(user.id); save(data)
        await query.edit_message_text(
            f'🎊 <b>{dn(p)}</b> и <b>{dn(u)}</b> теперь в браке! 💍', parse_mode="HTML")
    else:
        save(data)
        await query.edit_message_text(
            f'💔 <b>{dn(u)}</b> отклонил(а) предложение.', parse_mode="HTML")

async def divorce(update, ctx):
    if not await req_fun(update): return
    user = update.effective_user
    data = load(); u = get_user(data, user.id, user.username or "", user.full_name)
    if not u.get("married_to"): await update.message.reply_text("💭 Ты не в браке."); return
    partner = data["users"].get(u["married_to"], {})
    u["married_to"] = ""
    if partner: partner["married_to"] = ""
    save(data)
    await update.message.reply_text(
        f'💔 <b>{dn(u)}</b> и <b>{dn(partner)}</b> развелись.', parse_mode="HTML")

# ════════════════════════════════════════════════════════════════════════════════
#  SOCIAL ACTIONS (GIF)
# ════════════════════════════════════════════════════════════════════════════════
SOCIAL_GIFS = {
    "kiss":     ("anime kiss",       "💋 <b>{a}</b> целует <b>{b}</b>!"),
    "hug":      ("anime hug",        "🤗 <b>{a}</b> обнимает <b>{b}</b>!"),
    "pat":      ("anime head pat",   "🥰 <b>{a}</b> гладит <b>{b}</b> по голове!"),
    "slap":     ("anime slap",       "👋 <b>{a}</b> даёт пощёчину <b>{b}</b>!"),
    "poke":     ("anime poke",       "👉 <b>{a}</b> тычет в <b>{b}</b>!"),
    "bite":     ("anime bite",       "😈 <b>{a}</b> кусает <b>{b}</b>!"),
    "lick":     ("anime lick",       "👅 <b>{a}</b> лижет <b>{b}</b>!"),
    "cuddle":   ("anime cuddle",     "💞 <b>{a}</b> прижимается к <b>{b}</b>!"),
    "punch":    ("anime punch",      "👊 <b>{a}</b> бьёт <b>{b}</b>!"),
    "kill":     ("anime kill",       "⚔️ <b>{a}</b> убивает <b>{b}</b>!"),
    "feed":     ("anime feeding",    "🍡 <b>{a}</b> кормит <b>{b}</b>!"),
    "highfive": ("anime high five",  "🙌 <b>{a}</b> дай пять с <b>{b}</b>!"),
    "wave":     ("anime wave",       "👋 <b>{a}</b> машет <b>{b}</b>!"),
    "blush":    ("anime blush",      "😳 <b>{a}</b> краснеет рядом с <b>{b}</b>!"),
    "cry":      ("anime cry",        "😢 <b>{a}</b> плачет из-за <b>{b}</b>..."),
    "dance":    ("anime dance",      "💃 <b>{a}</b> танцует с <b>{b}</b>!"),
    "throw":    ("anime throw",      "🎯 <b>{a}</b> кидает предмет в <b>{b}</b>!"),
    "shoot":    ("anime gun point",  "🔫 <b>{a}</b> целится в <b>{b}</b>!"),
    "stare":    ("anime stare",      "👀 <b>{a}</b> пристально смотрит на <b>{b}</b>..."),
    "wed":      ("anime wedding",    "💍 <b>{a}</b> ведёт <b>{b}</b> под венец!"),
}

async def fetch_gif(query: str):
    try:
        url = (
            f"https://tenor.googleapis.com/v2/search"
            f"?q={query}&key={TENOR_KEY}&limit=20&media_filter=gif&contentfilter=medium"
        )
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as r:
                data = await r.json()
                results = data.get("results", [])
                if not results: return None
                item = random.choice(results)
                return item["media_formats"]["gif"]["url"]
    except Exception as e:
        logger.warning("Tenor error: %s", e)
        return None

async def social_action(update, ctx, action: str):
    if not await req_fun(update): return
    user = update.effective_user
    if not update.message.reply_to_message:
        await update.message.reply_text(f"↩️ Ответь на сообщение, чтобы использовать /{action}"); return
    target = update.message.reply_to_message.from_user
    data = load()
    u = get_user(data, user.id, user.username or "", user.full_name)
    t = get_user(data, target.id, target.username or "", target.full_name)
    save(data)
    query, template = SOCIAL_GIFS[action]
    caption = template.format(a=dn(u), b=dn(t))
    gif_url = await fetch_gif(query)
    if gif_url:
        await update.message.reply_animation(animation=gif_url, caption=caption, parse_mode="HTML")
    else:
        await update.message.reply_text(caption, parse_mode="HTML")

async def cmd_kiss(u,c):     await social_action(u,c,"kiss")
async def cmd_hug(u,c):      await social_action(u,c,"hug")
async def cmd_pat(u,c):      await social_action(u,c,"pat")
async def cmd_slap(u,c):     await social_action(u,c,"slap")
async def cmd_poke(u,c):     await social_action(u,c,"poke")
async def cmd_bite(u,c):     await social_action(u,c,"bite")
async def cmd_lick(u,c):     await social_action(u,c,"lick")
async def cmd_cuddle(u,c):   await social_action(u,c,"cuddle")
async def cmd_punch(u,c):    await social_action(u,c,"punch")
async def cmd_kill(u,c):     await social_action(u,c,"kill")
async def cmd_feed(u,c):     await social_action(u,c,"feed")
async def cmd_highfive(u,c): await social_action(u,c,"highfive")
async def cmd_wave(u,c):     await social_action(u,c,"wave")
async def cmd_blush(u,c):    await social_action(u,c,"blush")
async def cmd_cry(u,c):      await social_action(u,c,"cry")
async def cmd_dance(u,c):    await social_action(u,c,"dance")
async def cmd_throw(u,c):    await social_action(u,c,"throw")
async def cmd_shoot(u,c):    await social_action(u,c,"shoot")
async def cmd_stare(u,c):    await social_action(u,c,"stare")
async def cmd_wed(u,c):      await social_action(u,c,"wed")

# ════════════════════════════════════════════════════════════════════════════════
#  CHANNEL / GROUP HANDLERS
# ════════════════════════════════════════════════════════════════════════════════
async def channel_post(update, ctx):
    pass  # нужен чтобы хэндлер CHANNEL_POSTS был зарегистрирован

async def discussion_reply_handler(update, ctx):
    msg = update.message
    if not msg: return
    if not getattr(msg, "is_automatic_forward", False): return
    try:
        await msg.reply_text(CHANNEL_RULES_HTML, parse_mode="HTML")
    except Exception as e:
        logger.warning("discussion_reply error: %s", e)

async def on_message(update, ctx):
    user = update.effective_user
    if not user or user.is_bot: return
    data = load(); u = get_user(data, user.id, user.username or "", user.full_name)
    u["msg_count"] = u.get("msg_count",0) + 1
    if u["msg_count"] % 5 == 0: u["xp"] += 2
    save(data)

# ── /help ─────────────────────────────────────────────────────────────────────
async def help_cmd(update, ctx):
    fun = is_fun()
    fun_block = (
        "\n\n🎮 <b>Развлечения</b>\n"
        "/profile — профиль\n/nick &lt;ник&gt; — никнейм\n"
        "/top — топ XP\n/top_coins — топ монет\n"
        "/balance — баланс\n/daily — бонус\n/work — работа\n"
        "/give &lt;сумма&gt; (reply) — передать монеты\n"
        "/casino &lt;ставка&gt;\n/flip &lt;орёл/решка&gt; &lt;ставка&gt;\n"
        "/dice &lt;ставка&gt;\n/roulette &lt;цвет/число&gt; &lt;ставка&gt;\n"
        "/pet — питомец\n/pet_top\n"
        "/propose (reply) — предложение руки\n/divorce — развод\n\n"
        "💋 <b>Социальные</b> (все через reply)\n"
        "/kiss /hug /pat /slap /poke /bite\n"
        "/lick /cuddle /punch /kill /feed\n"
        "/highfive /wave /blush /cry /dance\n"
        "/throw /shoot /stare /wed"
    ) if fun else "\n\n🔒 <b>Развлечения отключены</b> (/funon чтобы включить)"
    await update.message.reply_text(
        "📖 <b>Команды бота</b>\n\n"
        "⚙️ <b>Модерация</b> (только бот-админы)\n"
        "/ban [причина] — бан (reply)\n"
        "/unban — разбан (reply)\n"
        "/kick [причина] — кик (reply)\n"
        "/mute 10m/2h/1d [причина] — мут (reply)\n"
        "/unmute — снять мут (reply)\n"
        "/ro &lt;время&gt; — режим чтения (reply)\n"
        "/strike [причина] — страйк (reply)\n"
        "/unstrike — снять страйк (reply)\n"
        "/warn [причина] — предупреждение (reply)\n"
        "/purge &lt;N&gt; — удалить N сообщений\n"
        "/userinfo — инфо о юзере (reply)\n"
        "/addcoins &lt;сумма&gt; — выдать монеты (reply)\n"
        "/funoff — выключить развлечения\n"
        "/funon — включить развлечения\n\n"
        "🔑 <b>Авторизация</b>\n"
        "/admin &lt;пароль&gt; — стать бот-админом\n"
        "/revoke — снять права"
        f"{fun_block}",
        parse_mode="HTML")

# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    COMMANDS = [
        ("start", help_cmd), ("help", help_cmd),
        ("admin", admin_cmd), ("revoke", revoke_cmd),
        # moderation
        ("ban", ban_cmd), ("unban", unban_cmd), ("kick", kick_cmd),
        ("mute", mute_cmd), ("unmute", unmute_cmd), ("ro", ro_cmd),
        ("strike", strike_cmd), ("unstrike", unstrike_cmd), ("warn", warn_cmd),
        ("purge", purge_cmd), ("userinfo", userinfo_cmd),
        ("funoff", funoff_cmd), ("funon", funon_cmd), ("addcoins", add_coins),
        # economy
        ("profile", profile), ("nick", set_nick), ("balance", balance),
        ("give", give_coins), ("daily", daily), ("work", work),
        ("pet", pet_cmd), ("pet_top", pet_top),
        ("top", top_xp), ("top_coins", top_coins),
        ("casino", casino), ("flip", flip), ("dice", dice_game), ("roulette", roulette),
        ("propose", propose), ("divorce", divorce),
        # social
        ("kiss", cmd_kiss), ("hug", cmd_hug), ("pat", cmd_pat),
        ("slap", cmd_slap), ("poke", cmd_poke), ("bite", cmd_bite),
        ("lick", cmd_lick), ("cuddle", cmd_cuddle), ("punch", cmd_punch),
        ("kill", cmd_kill), ("feed", cmd_feed), ("highfive", cmd_highfive),
        ("wave", cmd_wave), ("blush", cmd_blush), ("cry", cmd_cry),
        ("dance", cmd_dance), ("throw", cmd_throw), ("shoot", cmd_shoot),
        ("stare", cmd_stare), ("wed", cmd_wed),
    ]
    for cmd, fn in COMMANDS:
        app.add_handler(CommandHandler(cmd, fn))

    app.add_handler(CallbackQueryHandler(marry_callback, pattern="^marry_"))
    app.add_handler(MessageHandler(filters.UpdateType.CHANNEL_POSTS, channel_post))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, discussion_reply_handler), group=1)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))

    logger.info("Bot started")
    app.run_polling()

if __name__ == "__main__":
    main()
