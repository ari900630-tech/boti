import os
import json
import asyncio
import yt_dlp
import requests
import re
import logging
from concurrent.futures import ThreadPoolExecutor
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# הגדרת לוגים
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- הגדרות מערכת ---
TOKEN = os.getenv("BOT_TOKEN", "8670146396:AAFM4nhtzxS9NEfD3Dn-RkAGkftYelMXqug")
YOUTUBE_API_KEY = os.getenv("YT_API_KEY", "AIzaSyAKK4VTbQ_8tsHfxb2tcDZ9SSR9gWXH-0")
ADMIN_ID = int(os.getenv("ADMIN_ID", 8708085965))
DB_FILE = "users_data.json"

executor = ThreadPoolExecutor(max_workers=20)

# --- ניהול מסד נתונים ---
def load_db():
    if not os.path.exists(DB_FILE): return {}
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_db(db):
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(db, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logger.error(f"שגיאת שמירה: {e}")

def clean_filename(title):
    clean = re.sub(r'[\\/*?:"<>|]', "", title)
    return " ".join(clean.split())

# --- ניהול מקלדות ---
def get_main_keyboard(user_id, searching=False):
    if searching:
        return ReplyKeyboardMarkup(
            [[KeyboardButton("❌ ביטול חיפוש")]], 
            resize_keyboard=True, 
            is_persistent=True
        )
    
    kb = [
        [KeyboardButton("🎤 חיפוש לפי זמר"), KeyboardButton("🎵 חיפוש לפי שיר")],
        [KeyboardButton("📢 שיתוף וקבלת הורדות"), KeyboardButton("✖️ סגור תפריט")]
    ]
    
    if user_id == ADMIN_ID:
        kb.append([KeyboardButton("📊 סטטיסטיקה"), KeyboardButton("📣 הפצה לכולם")])
    
    return ReplyKeyboardMarkup(kb, resize_keyboard=True, is_persistent=True)

# --- פונקציות בוט ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    db = load_db()
    uid = str(user_id)
    
    if uid not in db:
        db[uid] = {"credits": 10, "state": None}
        save_db(db)
    
    await update.message.reply_text(
        f"שלום {update.effective_user.first_name}! 👋\nהבוט מוכן להורדות. המקלדת זמינה בתפריט ה-4 נקודות.",
        reply_markup=get_main_keyboard(user_id)
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    uid = str(user_id)
    text = update.message.text
    db = load_db()
    
    # מניעת שגיאות אם המשתמש לא רשום
    if uid not in db:
        db[uid] = {"credits": 10, "state": None}
        save_db(db)

    # לוגיקת כפתורי תפריט
    if text == "✖️ סגור תפריט":
        return await update.message.reply_text(
            "המקלדת הוסתרה. שלח /start כדי להחזיר אותה.", 
            reply_markup=ReplyKeyboardRemove()
        )

    if text == "❌ ביטול חיפוש":
        db[uid]["state"] = None
        save_db(db)
        return await update.message.reply_text("החיפוש בוטל.", reply_markup=get_main_keyboard(user_id))

    if text == "📊 סטטיסטיקה" and user_id == ADMIN_ID:
        return await update.message.reply_text(f"סה\"כ משתמשים: {len(db)}", reply_markup=get_main_keyboard(user_id))

    if text == "📢 שיתוף וקבלת הורדות":
        bot = await context.bot.get_me()
        link = f"https://t.me/{bot.username}?start={user_id}"
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("🚀 שיתוף בוואטסאפ/טלגרם", switch_inline_query=f"בוט הורדות מטורף! {link}")]])
        return await update.message.reply_text("שתף את הקישור וקבל 2 הורדות על כל חבר:", reply_markup=markup)

    if text in ["🎤 חיפוש לפי זמר", "🎵 חיפוש לפי שיר"]:
        db[uid]["state"] = "searching"
        save_db(db)
        return await update.message.reply_text("הקלד שם לחיפוש:", reply_markup=get_main_keyboard(user_id, True))

    # לוגיקת חיפוש אקטיבית
    if db.get(uid, {}).get("state") == "searching":
        db[uid]["state"] = None
        save_db(db)
        status = await update.message.reply_text("🔍 מחפש ביוטיוב...")
        
        try:
            def search_call():
                # הוספת סוג סרטון לחיפוש כדי למנוע תוצאות ריקות
                url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&q={text}&maxResults=25&type=video&key={YOUTUBE_API_KEY}"
                return requests.get(url, timeout=10).json()

            res = await asyncio.get_event_loop().run_in_executor(None, search_call)
            items = res.get('items', [])
            
            if not items:
                return await status.edit_text("לא נמצאו תוצאות. נסה שם אחר.", reply_markup=get_main_keyboard(user_id))
            
            buttons = []
            for i in items:
                v_id = i.get('id', {}).get('videoId')
                if v_id:
                    title = i['snippet']['title'][:50]
                    buttons.append([InlineKeyboardButton(f"🎵 {title}", callback_data=f"dl_{v_id}")])
            
            await status.delete()
            return await update.message.reply_text(f"תוצאות עבור '{text}':", reply_markup=InlineKeyboardMarkup(buttons))
        except Exception as e:
            logger.error(f"Search error: {e}")
            return await status.edit_text("שגיאה בחיבור ליוטיוב. נסה שוב.", reply_markup=get_main_keyboard(user_id))

    # קישור ישיר
    if "youtube.com" in text or "youtu.be" in text:
        asyncio.create_task(download_logic(update, context, text))

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    
    if data.startswith("dl_"):
        await query.answer("מכין להורדה...")
        v_id = data.split("_")[1]
        url = f"https://www.youtube.com/watch?v={v_id}"
        asyncio.create_task(download_logic(update, context, url, query))

async def download_logic(update, context, url, query=None):
    target = query.message if query else update.message
    status = await target.reply_text("⏳ מוריד...")
    
    def run_dl():
        try:
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': 'tmp_%(id)s.%(ext)s',
                'quiet': True,
                'postprocessors': [{'key': 'FFmpegExtractAudio','preferredcodec': 'mp3','preferredquality': '192'}],
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                title = clean_filename(info.get('title', 'song'))
                return title, f"tmp_{info['id']}.mp3"
        except: return None, None

    title, path = await asyncio.get_running_loop().run_in_executor(executor, run_dl)
    
    if title and path and os.path.exists(path):
        try:
            with open(path, 'rb') as f:
                await context.bot.send_audio(chat_id=update.effective_chat.id, audio=f, title=title)
            os.remove(path)
            await status.delete()
        except:
            if os.path.exists(path): os.remove(path)
            await status.edit_text("שגיאה בשליחת הקובץ.")
    else:
        await status.edit_text("ההורדה נכשלה.")

def main():
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
