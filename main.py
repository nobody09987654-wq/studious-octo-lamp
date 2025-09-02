# main.py
# ITeach Academy Registration Bot (no DB) — direct admin notifications
# Local-friendly: BOT_TOKEN and ADMIN_ID are embedded but can be overridden by environment variables.

import os
import re
import logging
import html
from datetime import datetime
from typing import Optional, Dict, Any, List

try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Contact,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from telegram.constants import ParseMode

# ----------------------- Config -----------------------
# You can keep these hardcoded for local testing, or set BOT_TOKEN / ADMIN_ID env variables.
BOT_TOKEN = os.getenv("BOT_TOKEN", "7832412035:AAFVc6186iqlNE_HS60u11tdCzC8pvCQ02c")
ADMIN_ID = int(os.getenv("ADMIN_ID", "6427405038"))

# ----------------------- Logging & Timezone -----------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger("iteach_bot")

try:
    TASHKENT_TZ = ZoneInfo("Asia/Tashkent") if ZoneInfo else None
except Exception:
    TASHKENT_TZ = None

# ----------------------- Constants & Labels -----------------------
COURSES = {
    "english": "🇬🇧 Ingliz tili",
    "german": "🇩🇪 Nemis tili",
    "math": "🧮 Matematika",
    "uzbek": "🇺🇿 Ona tili",
    "history": "📜 Tarix",
    "biology": "🧬 Biologiya",
    "chemistry": "⚗️ Kimyo",
}
COURSES_WITH_LEVEL = {"english", "german"}

LEVELS = {
    "A1": "A1 • Beginner",
    "A2": "A2 • Elementary",
    "B1": "B1 • Intermediate",
    "B2": "B2 • Upper-Intermediate",
    "C1": "C1 • Advanced",
    "C2": "C2 • Proficient",
}

SECTIONS_ENGLISH = {
    "kids": "👶 Kids",
    "general": "📘 General",
    "cefr": "🧭 CEFR",
    "ielts": "🎓 IELTS",
}
SECTIONS_GERMAN = {
    "kids": "👶 Kids",
    "general": "📘 General",
    "certificate": "🏅 Certificate",
}
SECTIONS_OTHERS = {
    "kids": "👶 Kids",
    "general": "📘 General",
    "certificate": "🏅 Certificate",
}

# ----------------------- Helpers: Keyboards -----------------------
def kb_register() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("🚀 Ro'yxatdan o'tish", callback_data="reg:start")]])

def kb_courses() -> InlineKeyboardMarkup:
    rows: List[List[InlineKeyboardButton]] = []
    items = list(COURSES.items())
    for i in range(0, len(items), 2):
        row = []
        for key, label in items[i : i + 2]:
            row.append(InlineKeyboardButton(label, callback_data=f"reg:course:{key}"))
        rows.append(row)
    rows.append([InlineKeyboardButton("❌ Bekor qilish", callback_data="reg:cancel")])
    return InlineKeyboardMarkup(rows)

def kb_levels() -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(LEVELS["A1"], callback_data="reg:level:A1"),
            InlineKeyboardButton(LEVELS["A2"], callback_data="reg:level:A2"),
        ],
        [
            InlineKeyboardButton(LEVELS["B1"], callback_data="reg:level:B1"),
            InlineKeyboardButton(LEVELS["B2"], callback_data="reg:level:B2"),
        ],
        [
            InlineKeyboardButton(LEVELS["C1"], callback_data="reg:level:C1"),
            InlineKeyboardButton(LEVELS["C2"], callback_data="reg:level:C2"),
        ],
        [InlineKeyboardButton("⬅️ Ortga (Kurslar)", callback_data="reg:back:courses")],
    ]
    return InlineKeyboardMarkup(rows)

def kb_sections(course_key: str) -> InlineKeyboardMarkup:
    if course_key == "english":
        sections = SECTIONS_ENGLISH
        back = "reg:back:levels"
    elif course_key == "german":
        sections = SECTIONS_GERMAN
        back = "reg:back:levels"
    else:
        sections = SECTIONS_OTHERS
        back = "reg:back:courses"

    rows: List[List[InlineKeyboardButton]] = []
    items = list(sections.items())
    for i in range(0, len(items), 2):
        row = []
        for key, label in items[i : i + 2]:
            row.append(InlineKeyboardButton(label, callback_data=f"reg:section:{key}"))
        rows.append(row)
    rows.append([InlineKeyboardButton("⬅️ Ortga", callback_data=back)])
    rows.append([InlineKeyboardButton("❌ Bekor qilish", callback_data="reg:cancel")])
    return InlineKeyboardMarkup(rows)

def kb_review() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Tasdiqlash", callback_data="reg:confirm"),
                InlineKeyboardButton("✏️ O‘zgartirish", callback_data="reg:edit"),
            ],
            [InlineKeyboardButton("❌ Bekor qilish", callback_data="reg:cancel")],
        ]
    )

def kb_edit_menu(course_key: str) -> InlineKeyboardMarkup:
    row1 = [
        InlineKeyboardButton("📚 Kurs", callback_data="reg:edit:course"),
        InlineKeyboardButton("🗂 Bo‘lim", callback_data="reg:edit:section"),
    ]
    row2 = [
        InlineKeyboardButton("👤 Ism familiya", callback_data="reg:edit:name"),
        InlineKeyboardButton("🎂 Yosh", callback_data="reg:edit:age"),
    ]
    row3 = [InlineKeyboardButton("📱 Telefon", callback_data="reg:edit:phone")]
    rows = [row1, row2, row3]
    if course_key in COURSES_WITH_LEVEL:
        rows.insert(1, [InlineKeyboardButton("📊 Daraja", callback_data="reg:edit:level")])
    rows.append([InlineKeyboardButton("⬅️ Ortga (Ko‘rib chiqish)", callback_data="reg:back:review")])
    return InlineKeyboardMarkup(rows)

# ----------------------- Validation -----------------------
def valid_full_name(s: str) -> bool:
    s = s.strip()
    parts = s.split()
    if not (2 <= len(parts) <= 5):
        return False
    for p in parts:
        letters = [ch for ch in p if ch.isalpha()]
        if len(letters) < 2:
            return False
    return True

def valid_age(s: str) -> bool:
    if not s.isdigit():
        return False
    n = int(s)
    return 3 <= n <= 100

PHONE_REGEX = re.compile(r"^\+998\d{9}$")

def normalize_phone(text: str) -> Optional[str]:
    t = text.strip()
    if t.startswith("+"):
        t = "+" + re.sub(r"[^\d]", "", t[1:])
    else:
        t = re.sub(r"[^\d]", "", t)
    if t.startswith("998") and len(t) == 12:
        t = "+" + t
    if PHONE_REGEX.match(t):
        return t
    return None

# ----------------------- Content builders (HTML escaped) -----------------------
def esc(s: Any) -> str:
    return html.escape("" if s is None else str(s))

def build_review_text(d: Dict[str, Any]) -> str:
    course_label = esc(COURSES.get(d.get("course_key", ""), d.get("course_label", "")))
    level_label = esc(d.get("level_label", "") or "")
    section_label = esc(d.get("section_label", ""))
    full_name = esc(d.get("full_name", ""))
    age = esc(d.get("age", ""))
    phone = esc(d.get("phone", ""))

    lines = [
        "🧾 <b>Ma’lumotlarni ko‘rib chiqing:</b>",
        f"• 📚 <b>Kurs:</b> {course_label}",
    ]
    if d.get("course_key") in COURSES_WITH_LEVEL and level_label:
        lines.append(f"• 📊 <b>Daraja:</b> {level_label}")
    lines += [
        f"• 🗂 <b>Bo‘lim:</b> {section_label}",
        f"• 👤 <b>Ism familiya:</b> {full_name}",
        f"• 🎂 <b>Yosh:</b> {age}",
        f"• 📱 <b>Telefon:</b> {phone}",
    ]
    return "\n".join(lines)

def build_admin_text(d: Dict[str, Any], u) -> str:
    course_label = esc(COURSES.get(d.get("course_key", ""), d.get("course_label", "")))
    level_label = esc(d.get("level_label", "") or "")
    section_label = esc(d.get("section_label", ""))
    full_name = esc(d.get("full_name", ""))
    age = esc(d.get("age", ""))
    phone = esc(d.get("phone", ""))

    username = esc(f"@{u.username}") if getattr(u, "username", None) else esc("@None")
    tnow = (
        datetime.now(TASHKENT_TZ).strftime("%Y-%m-%d %H:%M:%S")
        if TASHKENT_TZ
        else datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    )

    lines = [
        "🔔 <b>Yangi o‘quvchi ro‘yxatdan o‘tdi</b>",
        f"👤 <b>Ism:</b> {full_name}",
        f"🎂 <b>Yosh:</b> {age}",
        f"📱 <b>Telefon:</b> {phone}",
        f"📚 <b>Kurs:</b> {course_label}",
        f"🗂 <b>Bo‘lim:</b> {section_label}",
    ]
    if d.get("course_key") in COURSES_WITH_LEVEL and level_label:
        lines.append(f"📊 <b>Daraja:</b> {level_label}")

    lines += [
        f"🆔 <b>Telegram ID:</b> {esc(getattr(u, 'id', ''))}",
        f"👤 <b>Username:</b> {username}",
        f"📅 <b>Sana:</b> {tnow} (Asia/Tashkent)",
    ]
    return "\n".join(lines)

# ----------------------- Flow Helpers -----------------------
async def goto_courses(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📚 Qaysi <b>kurs</b>da o‘qimoqchisiz?\n"
        "<i>Iltimos, quyidagilardan birini tanlang.</i>"
    )
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text, reply_markup=kb_courses(), parse_mode=ParseMode.HTML
        )
    else:
        await update.message.reply_text(text, reply_markup=kb_courses(), parse_mode=ParseMode.HTML)
    context.user_data["step"] = "choose_course"

async def goto_levels(query, context: ContextTypes.DEFAULT_TYPE):
    # query is a CallbackQuery object
    await query.edit_message_text(
        "📊 Iltimos, <b>darajangizni</b> tanlang:",
        reply_markup=kb_levels(),
        parse_mode=ParseMode.HTML,
    )
    context.user_data["step"] = "choose_level"

async def goto_sections(query, context: ContextTypes.DEFAULT_TYPE):
    course_key = context.user_data.get("course_key")
    await query.edit_message_text(
        "🗂 Iltimos, <b>bo‘lim</b>ni tanlang:",
        reply_markup=kb_sections(course_key),
        parse_mode=ParseMode.HTML,
    )
    context.user_data["step"] = "choose_section"

async def ask_full_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "✍️ <b>Iltimos, to‘liq ism-familiyangizni kiriting.</b>\n"
        "<i>Masalan: Ziyodulla Egamberdiyev</i>"
    )
    await update.effective_chat.send_message(msg, parse_mode=ParseMode.HTML, reply_markup=ReplyKeyboardRemove())
    context.user_data["step"] = "ask_name"

async def ask_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_chat.send_message("🎂 <b>Yoshingizni kiriting:</b>", parse_mode=ParseMode.HTML)
    context.user_data["step"] = "ask_age"

async def ask_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = ReplyKeyboardMarkup(
        [[KeyboardButton("📱 Raqamni ulashish", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await update.effective_chat.send_message(
        "📞 <b>Telefon raqamingizni kiriting</b> (format: <code>+998XXXXXXXXX</code>) yoki pastdagi tugma orqali yuboring.",
        parse_mode=ParseMode.HTML,
        reply_markup=kb,
    )
    context.user_data["step"] = "ask_phone"

async def show_review(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = build_review_text(context.user_data)
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=kb_review(), parse_mode=ParseMode.HTML)
    else:
        await update.effective_chat.send_message(text, reply_markup=kb_review(), parse_mode=ParseMode.HTML)
    context.user_data["step"] = "review"

# ----------------------- Handlers -----------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome = (
        "Assalomu alaykum!\n"
        "<b>Welcome to ITeach Academy</b> 🎓\n\n"
        "Bizning o‘quv jamoamizga qo‘shilish va ro‘yxatdan o‘tish uchun pastdagi tugmani bosing."
    )
    await update.message.reply_text(welcome, reply_markup=kb_register(), parse_mode=ParseMode.HTML)
    context.user_data.clear()

async def cb_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data or ""
    await query.answer()
    logger.info("Callback data: %s", data)

    if data == "reg:cancel":
        context.user_data.clear()
        await query.edit_message_text("❌ Ro‘yxatdan o‘tish bekor qilindi.")
        return

    if data == "reg:start":
        await goto_courses(update, context)
        return

    if data == "reg:back:courses":
        context.user_data.pop("level_key", None)
        context.user_data.pop("level_label", None)
        context.user_data.pop("section_key", None)
        context.user_data.pop("section_label", None)
        await goto_courses(update, context)
        return

    if data == "reg:back:levels":
        context.user_data.pop("section_key", None)
        context.user_data.pop("section_label", None)
        await goto_levels(query, context)
        return

    if data == "reg:back:review":
        await show_review(update, context)
        return

    if data.startswith("reg:course:"):
        course_key = data.split(":")[2]
        if course_key not in COURSES:
            await query.edit_message_text("Noto‘g‘ri kurs tanlandi. Qaytadan urinib ko‘ring.")
            return
        context.user_data["course_key"] = course_key
        context.user_data["course_label"] = COURSES[course_key]
        context.user_data.pop("level_key", None)
        context.user_data.pop("level_label", None)
        context.user_data.pop("section_key", None)
        context.user_data.pop("section_label", None)

        if course_key in COURSES_WITH_LEVEL:
            await goto_levels(query, context)
        else:
            await goto_sections(query, context)
        return

    if data.startswith("reg:level:"):
        level_key = data.split(":")[2]
        if level_key not in LEVELS:
            await query.edit_message_text("Noto‘g‘ri daraja tanlandi. Qaytadan urinib ko‘ring.")
            return
        context.user_data["level_key"] = level_key
        context.user_data["level_label"] = LEVELS[level_key]
        await goto_sections(query, context)
        return

    if data.startswith("reg:section:"):
        section_key = data.split(":")[2]
        course_key = context.user_data.get("course_key")
        valid_keys = (
            SECTIONS_ENGLISH
            if course_key == "english"
            else SECTIONS_GERMAN
            if course_key == "german"
            else SECTIONS_OTHERS
        )
        if section_key not in valid_keys:
            await query.edit_message_text("Noto‘g‘ri bo‘lim tanlandi. Qaytadan urinib ko‘ring.")
            return
        context.user_data["section_key"] = section_key
        context.user_data["section_label"] = valid_keys[section_key]
        await ask_full_name(update, context)
        return

    if data == "reg:confirm":
        required = ["course_key", "course_label", "section_label", "full_name", "age", "phone"]
        if context.user_data.get("course_key") in COURSES_WITH_LEVEL:
            required.append("level_label")
        missing = [k for k in required if not context.user_data.get(k)]
        if missing:
            await query.edit_message_text(
                "Ma’lumotlar yetarli emas. Iltimos, /start buyrug‘i bilan qaytadan boshlang."
            )
            context.user_data.clear()
            return

        # Notify user
        await query.edit_message_text(
            "🎉 <b>Tabriklaymiz!</b> Siz ro‘yxatdan o‘tdingiz.\nTez orada siz bilan telefon raqamingiz orqali bog‘lanamiz.",
            parse_mode=ParseMode.HTML,
        )

        # Notify admin (no DB)
        try:
            user = update.effective_user
            admin_text = build_admin_text(context.user_data, user)
            await context.bot.send_message(chat_id=ADMIN_ID, text=admin_text, parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.warning("Failed to notify admin: %s", e)

        context.user_data.clear()
        return

    if data == "reg:edit":
        course_key = context.user_data.get("course_key", "")
        await query.edit_message_text(
            "Qaysi <b>bo‘limni</b> o‘zgartiramiz?",
            reply_markup=kb_edit_menu(course_key),
            parse_mode=ParseMode.HTML,
        )
        context.user_data["step"] = "edit_menu"
        return

    if data.startswith("reg:edit:"):
        field = data.split(":")[2]
        context.user_data["edit_field"] = field

        if field == "course":
            await goto_courses(update, context)
            return
        if field == "level":
            await goto_levels(query, context)
            return
        if field == "section":
            await goto_sections(query, context)
            return
        if field == "name":
            await query.edit_message_text("✍️ Yangi <b>ism-familiya</b>ni kiriting:", parse_mode=ParseMode.HTML)
            context.user_data["step"] = "ask_name"
            return
        if field == "age":
            await query.edit_message_text("🎂 Yangi <b>yosh</b>ni kiriting:", parse_mode=ParseMode.HTML)
            context.user_data["step"] = "ask_age"
            return
        if field == "phone":
            kb = ReplyKeyboardMarkup(
                [[KeyboardButton("📱 Raqamni ulashish", request_contact=True)]],
                resize_keyboard=True,
                one_time_keyboard=True,
            )
            await query.edit_message_text(
                "📞 Yangi <b>telefon</b>ni kiriting (format: <code>+998XXXXXXXXX</code>) yoki pastdagi tugma orqali yuboring.",
                parse_mode=ParseMode.HTML,
            )
            await update.effective_chat.send_message("Telefonni yuboring:", reply_markup=kb)
            context.user_data["step"] = "ask_phone"
            return

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    step = context.user_data.get("step")
    text = (update.message.text or "").strip()

    if step == "ask_name":
        if not valid_full_name(text):
            await update.message.reply_text(
                "❌ To‘liq ism-familiya kiriting.\nMasalan: <i>Ziyodulla Egamberdiyev</i>",
                parse_mode=ParseMode.HTML,
            )
            return
        context.user_data["full_name"] = text
        await ask_age(update, context)
        return

    if step == "ask_age":
        if not valid_age(text):
            await update.message.reply_text("❌ Yosh faqat 3–100 oralig‘ida bo‘lishi kerak. Qayta kiriting:")
            return
        context.user_data["age"] = int(text)
        await ask_phone(update, context)
        return

    if step == "ask_phone":
        normalized = normalize_phone(text)
        if not normalized:
            await update.message.reply_text(
                "❌ Noto‘g‘ri format. Iltimos, <code>+998XXXXXXXXX</code> shaklida kiriting yoki pastdagi tugmadan foydalaning.",
                parse_mode=ParseMode.HTML,
            )
            return
        context.user_data["phone"] = normalized
        await show_review(update, context)
        return

    await update.message.reply_text(
        "Iltimos, /start buyrug‘i bilan boshlang yoki jarayon tugmalaridan foydalaning."
    )

async def contact_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    step = context.user_data.get("step")
    contact: Contact = update.message.contact
    phone = contact.phone_number if contact else None
    if step != "ask_phone" or not phone:
        return
    normalized = normalize_phone(phone)
    if not normalized:
        await update.message.reply_text(
            "❌ Telefon raqamingiz <code>+998XXXXXXXXX</code> formatida bo‘lishi kerak. Qayta yuboring.",
            parse_mode=ParseMode.HTML,
        )
        return
    context.user_data["phone"] = normalized
    await update.message.reply_text("✔️ Qabul qilindi.", reply_markup=ReplyKeyboardRemove())
    await show_review(update, context)

async def cancel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "❌ Jarayon bekor qilindi. Qayta boshlash uchun /start bosing.", reply_markup=ReplyKeyboardRemove()
    )

# ----------------------- App bootstrap ------------
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cancel", cancel_cmd))

    # Callbacks
    app.add_handler(CallbackQueryHandler(cb_handler))

    # Messages
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.add_handler(MessageHandler(filters.CONTACT, contact_handler))

    logger.info("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
