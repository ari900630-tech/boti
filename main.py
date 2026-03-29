import os
import json
import asyncio
import yt_dlp
import requests
import re
import logging
from concurrent.futures import ThreadPoolExecutor
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# הגדרת לוגים בסיסית כדי לראות שגיאות ב-Railway
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- הגדרות ---
TOKEN = os.getenv("BOT_TOKEN", "8670146396:AAFM4nhtzxS9NEfD3Dn-RkAGkftYelMXqug")
YOUTUBE_API_KEY = os.getenv("YT_API_KEY", "AIzaSyAKK4VTbQ_8tsHfxb2tcDZ9SSR9gWXH-0")
ADMIN_ID = int(os.getenv("ADMIN_ID", 8708085965))
DB_FILE = "users_data.json"

executor = ThreadPoolExecutor(max_workers=20)

def load_db():
    if not os.path.exists(DB_FILE): return {}
    try:
        with open(DB_FILE, "r") as f: return json.load(f)
    except: return {}

def save_db(db):
    with open(DB_FILE, "w") as f: json.dump(db, f)

def clean_filename(title):
    clean = re.sub(r'[\\/*?:"<>|]', "", title)
    return " ".join(clean.split())

def get_main_keyboard(user_id, searching=False):
    placeholder = "🔍 הקלד שם לחיפוש..." if searching else "בחר פעולה מהתפריט (כפתור ה-4 נקודות)"
    if searching:
        return ReplyKeyboardMarkup([[KeyboardButton("❌ ביטול פעולה")]], resize_keyboard=True, is_persistent=True, input_field_placeholder=placeholder)
    kb = [[KeyboardButton("🎤 חיפוש לפי שם זמר"), KeyboardButton("🎵 חיפוש לפי שם שיר")], [KeyboardButton("📢 שיתוף הבוט לקבלת הורדות")]]
    if user_id == ADMIN_ID:
        kb.append([KeyboardButton("📣 פרסום הודעה לכולם"), KeyboardButton("📊 סטטיסטיקת בוט")])
    return ReplyKeyboardMarkup(kb, resize_keyboard=True, is_persistent=True, input_field_placeholder=placeholder)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(msg="Exception while handling an update:", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text("❌ קרתה תקלה פנימית, הבוט ממשיך לעבוד. נסה שוב.")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    db = load_db()
    if str(user_id) not in db:
        db[str(user_id)] = {"credits": 5, "state": None}
        save_db(db)
    await update.message.reply_text("🚀 ברוך הבא לבוט ההורדות!\nהמקלדת זמינה תמיד דרך כפתור ה-4 נקודות.", reply_markup=get_main_keyboard(user_id))

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    uid = str(user_id)
    text = update.message.text
    db = load_db()
    is_admin = (user_id == ADMIN_ID)

    if text == "❌ ביטול פעולה":
        db[uid]["state"] = None; save_db(db)
        return await update.message.reply_text("הפעולה בוטלה.", reply_markup=get_main_keyboard(user_id))

    if text == "📊 סטטיסטיקת בוט" and is_admin:
        return await update.message.reply_text(f"📊 משתמשים: {len(db)}", reply_markup=get_main_keyboard(user_id))

    if text == "📢 שיתוף הבוט לקבלת הורדות":
        bot = await context.bot.get_me()
        share = f"מצאתי בוט מטורף להורדת שירים! 🎶\nhttps://t.me/{bot.username}?start={user_id}"
        return await update.message.reply_text("שתף:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🚀 שיתוף מהיר", switch_inline_query=share)]]))

    if text == "📣 פרסום הודעה לכולם" and is_admin:
        db[uid]["state"] = "broadcasting"; save_db(db)
        return await update.message.reply_text("שלח הודעה:", reply_markup=get_main_keyboard(user_id, True))

    if db.get(uid, {}).get("state") == "broadcasting" and is_admin:
        db[uid]["state"] = None; save_db(db)
        for u in db.keys():
            try: await context.bot.send_message(chat_id=int(u), text=text)
            except: pass
        return await update.message.reply_text("✅ נשלח.", reply_markup=get_main_keyboard(user_id))

    if text in ["🎤 חיפוש לפי שם זמר", "🎵 חיפוש לפי שם שיר"]:
        db[uid]["state"] = "searching"; save_db(db)
        return await update.message.reply_text("הקלד שם (עד 100 תוצאות):", reply_markup=get_main_keyboard(user_id, True))

    if db.get(uid, {}).get("state") == "searching":
        db[uid]["state"] = None; save_db(db)
        status = await update.message.reply_text("🔍 מחפש...")
        try:
            def fetch():
                r = requests.get(f"https://www.googleapis.com/youtube/v3/search?part=snippet&q={text}&maxResults=100&type=video&key={YOUTUBE_API_KEY}", timeout=15)
                return r.json()
            res = await asyncio.get_event_loop().run_in_executor(None, fetch)
            items = res.get('items', [])
            if not items:
                err = res.get("error", {}).get("message", "לא נמצאו תוצאות.")
                return await status.edit_text(f"❌ שגיאה: {err}", reply_markup=get_main_keyboard(user_id))
            buttons = [[InlineKeyboardButton(i['snippet']['title'][:55], callback_data=f"dl_{i['id']['videoId']}")] for i in items if i.get('id', {}).get('videoId')]
            await status.delete()
            return await update.message.reply_text(f"תוצאות עבור '{text}':", reply_markup=InlineKeyboardMarkup(buttons))
        except Exception as e:
            return await status.edit_text(f"❌ תקלה טכנית: {str(e)}", reply_markup=get_main_keyboard(user_id))

    if "youtube.com" in text or "youtu.be" in text:
        asyncio.create_task(download_logic(update, context, text))

async def callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer("מוריד...")
    v_id = update.callback_query.data.split('_')[1]
    asyncio.create_task(download_logic(update, context, f"https://www.youtube.com/watch?v={v_id}", update.callback_query))

async def download_logic(update, context, url, query=None):
    target = query.message if query else update.message
    status = await target.reply_text("⏳ מוריד...")
    def run():
        try:
            ydl_opts = {'format': 'bestaudio/best', 'outtmpl': 'tmp_%(id)s.%(ext)s', 'quiet': True, 'nocheckcertificate': True}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                title = clean_filename(info.get('title', 'song'))
                path = f"{title}.mp3"; os.rename(ydl.prepare_filename(info), path)
                return title, path
        except: return None, None
    title, path = await asyncio.get_running_loop().run_in_executor(executor, run)
    if title and path:
        try:
            with open(path, 'rb') as f: await context.bot.send_audio(chat_id=update.effective_chat.id, audio=f, title=title, write_timeout=300)
            os.remove(path); await status.delete()
        except: await status.edit_text("❌ שגיאה בשליחה.")
    else: await status.edit_text("❌ נכשל.")

def main():
    app = Application.builder().token(TOKEN).write_timeout(300).read_timeout(300).connect_timeout(300).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(callback_query))
    app.add_error_handler(error_handler) # הוספת מטפל השגיאות
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__': main()
