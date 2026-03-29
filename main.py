import os
import json
import asyncio
import yt_dlp
import requests
import re
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# --- הגדרות שרת ---
TOKEN = os.getenv("BOT_TOKEN", "8670146396:AAFM4nhtzxS9NEfD3Dn-RkAGkftYelMXqug")
YOUTUBE_API_KEY = os.getenv("YT_API_KEY", "AIzaSyAKK4VTbQJ_8tsHfxb2tcDZ9SSR9gWXH-0")
ADMIN_ID = int(os.getenv("ADMIN_ID", 8708085965))
DB_FILE = "users_data.json"

executor = ThreadPoolExecutor(max_workers=20)

# --- ניהול בסיס נתונים ---
def load_db():
    if not os.path.exists(DB_FILE): return {}
    try:
        with open(DB_FILE, "r", encoding='utf-8') as f: return json.load(f)
    except: return {}

def save_db(db):
    with open(DB_FILE, "w", encoding='utf-8') as f: json.dump(db, f, indent=4, ensure_ascii=False)

def update_activity(uid, db):
    hour = str(datetime.now().hour)
    user_data = db.get(uid, {})
    activity = user_data.get("activity_log", {})
    activity[hour] = activity.get(hour, 0) + 1
    user_data["activity_log"] = activity
    db[uid] = user_data
    save_db(db)

def get_peak_hour(uid, db):
    activity = db.get(uid, {}).get("activity_log", {})
    if not activity: return 20 # ברירת מחדל שמונה בערב
    return int(max(activity, key=activity.get))

# --- עיצובים (Themes) ---
THEMES = {
    "קלאסי 🎹": {"search_s": "🎤", "search_m": "🎵", "profile": "👤", "help": "❓", "share": "📢", "settings": "⚙️", "stats": "📊", "back": "🔙"},
    "ניאון ⚡": {"search_s": "🎙️", "search_m": "🎧", "profile": "💎", "help": "💡", "share": "🔥", "settings": "🛠️", "stats": "📈", "back": "⬅️"},
    "טבע 🌿": {"search_s": "🦜", "search_m": "🍀", "profile": "🌳", "help": "🍄", "share": "🌊", "settings": "⚙️", "stats": "🌻", "back": "🪵"}
}

def get_icon(uid, db, key):
    theme_name = db.get(uid, {}).get("theme", "קלאסי 🎹")
    return THEMES.get(theme_name, THEMES["קלאסי 🎹"]).get(key, "✨")

# --- מקלדות ---
def get_main_keyboard(user_id, db):
    uid = str(user_id)
    kb = [
        [KeyboardButton(f"{get_icon(uid, db, 'search_s')} חיפוש לפי שם זמר"), KeyboardButton(f"{get_icon(uid, db, 'search_m')} חיפוש לפי שם שיר")],
        [KeyboardButton(f"{get_icon(uid, db, 'profile')} הפרופיל שלי"), KeyboardButton(f"{get_icon(uid, db, 'settings')} הגדרות")],
        [KeyboardButton(f"{get_icon(uid, db, 'help')} עזרה"), KeyboardButton(f"{get_icon(uid, db, 'share')} שיתוף הבוט")]
    ]
    if user_id == ADMIN_ID:
        kb.append([KeyboardButton(f"{get_icon(uid, db, 'stats')} סטטיסטיקת בוט")])
    return ReplyKeyboardMarkup(kb, resize_keyboard=True, is_persistent=True)

def get_settings_keyboard(uid, db):
    notif_status = "✅ פעיל" if db.get(uid, {}).get("notifications", True) else "❌ כבוי"
    kb = [
        [KeyboardButton("🎨 שינוי עיצוב כפתורים")],
        [KeyboardButton("💾 הגדרת פורמט קבוע"), KeyboardButton("🔊 הגדרת איכות קבועה")],
        [KeyboardButton(f"🔔 תזכורת יומית: {notif_status}")],
        [KeyboardButton(f"{get_icon(uid, db, 'back')} חזור")]
    ]
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)

# --- פונקציות עזר ---
def get_greeting():
    hour = datetime.now().hour
    current_time = datetime.now().strftime("%H:%M")
    if 5 <= hour < 12: greet = "בוקר טוב ☀️"
    elif 12 <= hour < 18: greet = "צהריים טובים 🌤️"
    elif 18 <= hour < 22: greet = "ערב טוב 🌙"
    else: greet = "לילה טוב ✨"
    return f"שלום! השעה עכשיו {current_time}. {greet}"

def clean_filename(title):
    return " ".join(re.sub(r'[\\/*?:"<>|]', "", title).split())

# --- לוגיקה ראשית ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    db = load_db()
    uid = str(user_id)
    
    if uid not in db:
        db[uid] = {
            "credits": 5, "state": None, "theme": "קלאסי 🎹",
            "default_format": None, "default_quality": None,
            "notifications": True, "activity_log": {}, "last_notified": ""
        }
        save_db(db)
    
    await update.message.reply_text(get_greeting(), reply_markup=get_main_keyboard(user_id, db))

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    uid = str(user_id)
    text = update.message.text
    db = load_db()
    update_activity(uid, db)
    is_admin = (user_id == ADMIN_ID)

    # --- ניווט וחזור ---
    if "חזור" in text:
        db[uid]["state"] = None
        save_db(db)
        return await update.message.reply_text("חזרנו לתפריט הראשי.", reply_markup=get_main_keyboard(user_id, db))

    # --- הגדרות ---
    if "הגדרות" in text:
        db[uid]["state"] = "in_settings"
        save_db(db)
        return await update.message.reply_text("⚙️ **מרכז הגדרות:**\nכאן תוכל להתאים את הבוט לצרכים שלך.", reply_markup=get_settings_keyboard(uid, db), parse_mode="Markdown")

    if text == "🎨 שינוי עיצוב כפתורים":
        kb = [[KeyboardButton(t)] for t in THEMES.keys()]
        kb.append([KeyboardButton(f"{get_icon(uid, db, 'back')} חזור")])
        return await update.message.reply_text("בחר ערכת נושא חדשה:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))

    if text in THEMES.keys():
        db[uid]["theme"] = text
        save_db(db)
        return await update.message.reply_text(f"העיצוב שונה ל-{text}!", reply_markup=get_settings_keyboard(uid, db))

    if text == "💾 הגדרת פורמט קבוע":
        kb = [[KeyboardButton(f"קבע: {f}")] for f in ["mp3", "wav", "m4a"]]
        kb.append([KeyboardButton("❌ ביטול הגדרה קבועה"), KeyboardButton(f"{get_icon(uid, db, 'back')} חזור")])
        return await update.message.reply_text("בחר פורמט שייבחר תמיד אוטומטית:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))

    if text.startswith("קבע: "):
        val = text.split(": ")[1]
        if val in ["mp3", "wav", "m4a"]:
            db[uid]["default_format"] = val
        else:
            db[uid]["default_quality"] = val
        save_db(db)
        return await update.message.reply_text(f"הגדרה נשמרה: {val}", reply_markup=get_settings_keyboard(uid, db))

    if text == "❌ ביטול הגדרה קבועה":
        db[uid]["default_format"] = None
        db[uid]["default_quality"] = None
        save_db(db)
        return await update.message.reply_text("הגדרות ברירת המחדל בוטלו.", reply_markup=get_settings_keyboard(uid, db))

    if text.startswith("🔔 תזכורת יומית"):
        db[uid]["notifications"] = not db.get(uid, {}).get("notifications", True)
        save_db(db)
        return await update.message.reply_text("הגדרת התזכורת עודכנה.", reply_markup=get_settings_keyboard(uid, db))

    # --- לוגיקת הורדה וחיפוש (המקורית שלך) ---
    if "חיפוש" in text:
        db[uid]["state"] = "searching"
        save_db(db)
        return await update.message.reply_text("מה לחפש?")

    if db.get(uid, {}).get("state") == "searching":
        db[uid]["state"] = None
        save_db(db)
        status = await update.message.reply_text("🔍 מחפש...")
        url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&q={text}&maxResults=10&type=video&key={YOUTUBE_API_KEY}"
        res = requests.get(url).json()
        buttons = [[InlineKeyboardButton(i['snippet']['title'][:50], callback_data=f"setup_{i['id']['videoId']}")] for i in res.get('items', [])]
        await status.delete()
        return await update.message.reply_text("תוצאות:", reply_markup=InlineKeyboardMarkup(buttons))

    if "youtube.com" in text or "youtu.be" in text:
        await prepare_download(update, context, text, uid, db)

async def prepare_download(update, context, url, uid, db):
    # בדיקה אם יש הגדרות קבועות
    def_format = db[uid].get("default_format")
    def_quality = db[uid].get("default_quality", "192")
    
    if def_format:
        await download_logic(update, context, url, def_format, def_quality)
    else:
        db[uid]["pending_url"] = url
        db[uid]["state"] = "choosing_format"
        save_db(db)
        kb = [[KeyboardButton(f)] for f in ["mp3", "wav", "m4a"]]
        await update.message.reply_text("בחר פורמט:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))

async def callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = update.callback_query.data
    uid = str(update.effective_user.id)
    db = load_db()
    if data.startswith("setup_"):
        v_url = f"https://www.youtube.com/watch?v={data.split('_')[1]}"
        await update.callback_query.answer()
        await prepare_download(update, context, v_url, uid, db)

async def download_logic(update, context, url, fmt, quality):
    user_id = update.effective_user.id
    db = load_db()
    if user_id != ADMIN_ID and db.get(str(user_id), {}).get("credits", 0) <= 0:
        return await context.bot.send_message(chat_id=update.effective_chat.id, text="⚠️ אין הורדות!")

    status = await context.bot.send_message(chat_id=update.effective_chat.id, text=f"⏳ מוריד בפורמט {fmt}...")
    
    def run():
        try:
            ydl_opts = {
                'format': 'bestaudio/best', 'outtmpl': 'tmp_%(id)s.%(ext)s', 'quiet': True,
                'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': fmt, 'preferredquality': quality}]
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                title = clean_filename(info.get('title', 'song'))
                tmp = ydl.prepare_filename(info).rsplit('.', 1)[0] + f".{fmt}"
                final = f"{title}.{fmt}"
                if os.path.exists(tmp):
                    os.rename(tmp, final)
                    return title, final
        except: return None, None

    title, file = await asyncio.get_running_loop().run_in_executor(executor, run)
    if file:
        with open(file, 'rb') as f:
            await context.bot.send_audio(chat_id=update.effective_chat.id, audio=f, title=title)
        os.remove(file)
        await status.delete()
        if user_id != ADMIN_ID:
            db[str(user_id)]["credits"] -= 1; save_db(db)
    else: await status.edit_text("❌ נכשל.")

# --- מנגנון תזכורת חכם (רץ ברקע) ---
async def daily_reminder(app):
    while True:
        now = datetime.now()
        db = load_db()
        for uid, data in db.items():
            if data.get("notifications", True):
                peak = get_peak_hour(uid, db)
                last_notified = data.get("last_notified", "")
                today = now.strftime("%Y-%m-%d")
                
                if now.hour == peak and last_notified != today:
                    try:
                        await app.bot.send_message(chat_id=int(uid), text="🎶 זמן מעולה להוריד שיר חדש! מה בא לך לשמוע היום?")
                        db[uid]["last_notified"] = today
                        save_db(db)
                    except: pass
        await asyncio.sleep(3600) # בדיקה פעם בשעה

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(callback_query))
    
    loop = asyncio.get_event_loop()
    loop.create_task(daily_reminder(app))
    
    print("Bot is alive...")
    app.run_polling()

if __name__ == '__main__': main()
