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

# הגדרת לוגים למעקב ב-Railway
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- הגדרות ---
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
        logger.error(f"Save DB Error: {e}")

def clean_filename(title):
    clean = re.sub(r'[\\/*?:"<>|]', "", title)
    return " ".join(clean.split())

# --- תפריטים ---
def get_main_keyboard(user_id, searching=False):
    placeholder = "🔍 הקלד שם לחיפוש..." if searching else "בחר פעולה מהתפריט"
    if searching:
        return ReplyKeyboardMarkup([[KeyboardButton("❌ ביטול פעולה")]], resize_keyboard=True, is_persistent=True, input_field_placeholder=placeholder)
    
    kb = [
        [KeyboardButton("🎤 חיפוש לפי זמר"), KeyboardButton("🎵 חיפוש לפי שיר")],
        [KeyboardButton("📢 שיתוף וקבלת הורדות"), KeyboardButton("✖️ סגור תפריט")]
    ]
    if user_id == ADMIN_ID:
        kb.append([KeyboardButton("📣 הפצה לכולם"), KeyboardButton("📊 סטטיסטיקה")])
    
    return ReplyKeyboardMarkup(kb, resize_keyboard=True, is_persistent=True, input_field_placeholder=placeholder)

def get_open_keyboard():
    return ReplyKeyboardMarkup([[KeyboardButton("⌨️ פתח תפריט")]], resize_keyboard=True)

# --- פונקציות ליבה ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    uid = str(user_id)
    db = load_db()
    
    # מערכת הפניות (Referrals)
    if context.args and uid not in db:
        ref_id = context.args[0]
        if ref_id in db and ref_id != uid:
            db[ref_id]["credits"] = db[ref_id].get("credits", 0) + 2
            save_db(db)
            try: await context.bot.send_message(chat_id=int(ref_id), text="🎁 חבר הצטרף! קיבלת 2 הורדות בונוס.")
            except: pass

    if uid not in db:
        db[uid] = {"credits": 5, "state": None}
        save_db(db)
    
    await update.message.reply_text(
        f"🚀 ברוך הבא {update.effective_user.first_name}!\n"
        f"יתרת הורדות: {db[uid].get('credits', 0)}\n\n"
        "התפריט זמין תמיד בכפתור 4 הנקודות למטה.",
        reply_markup=get_main_keyboard(user_id)
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    uid = str(user_id)
    text = update.message.text
    db = load_db()
    
    if uid not in db: db[uid] = {"credits": 5, "state": None}; save_db(db)
    is_admin = (user_id == ADMIN_ID)

    # כפתורי שליטה במקלדת
    if text == "✖️ סגור תפריט":
        return await update.message.reply_text("המקלדת הוסתרה.", reply_markup=get_open_keyboard())
    
    if text == "⌨️ פתח תפריט":
        return await update.message.reply_text("המקלדת חזרה!", reply_markup=get_main_keyboard(user_id))

    if text == "❌ ביטול פעולה":
        db[uid]["state"] = None; save_db(db)
        return await update.message.reply_text("בוטל.", reply_markup=get_main_keyboard(user_id))

    # פונקציות אדמין
    if text == "📊 סטטיסטיקה" and is_admin:
        return await update.message.reply_text(f"📊 משתמשים רשומים: {len(db)}", reply_markup=get_main_keyboard(user_id))

    if text == "📣 הפצה לכולם" and is_admin:
        db[uid]["state"] = "broadcasting"; save_db(db)
        return await update.message.reply_text("שלח הודעה להפצה:", reply_markup=get_main_keyboard(user_id, True))

    if db.get(uid, {}).get("state") == "broadcasting" and is_admin:
        db[uid]["state"] = None; save_db(db)
        count = 0
        for u in db.keys():
            try: 
                await context.bot.send_message(chat_id=int(u), text=text)
                count += 1
            except: pass
        return await update.message.reply_text(f"✅ נשלח ל-{count} משתמשים.", reply_markup=get_main_keyboard(user_id))

    # שיתוף
    if text == "📢 שיתוף וקבלת הורדות":
        bot = await context.bot.get_me()
        link = f"https://t.me/{bot.username}?start={user_id}"
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("🚀 שיתוף מהיר", switch_inline_query=f"בוט הורדות שירים בחינם! 🔥\n{link}")]])
        return await update.message.reply_text("שתף את הבוט וקבל 2 הורדות על כל חבר שנכנס:", reply_markup=markup)

    # חיפוש
    if text in ["🎤 חיפוש לפי זמר", "🎵 חיפוש לפי שיר"]:
        db[uid]["state"] = "searching"; save_db(db)
        return await update.message.reply_text("הקלד שם לחיפוש (עד 100 תוצאות):", reply_markup=get_main_keyboard(user_id, True))

    if db.get(uid, {}).get("state") == "searching":
        db[uid]["state"] = None; save_db(db)
        status = await update.message.reply_text("🔍 מחפש...")
        try:
            def yt_search():
                url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&q={text}&maxResults=50&type=video&key={YOUTUBE_API_KEY}"
                return requests.get(url, timeout=10).json()
            
            res = await asyncio.get_event_loop().run_in_executor(None, yt_search)
            items = res.get('items', [])
            if not items: return await status.edit_text("לא נמצאו תוצאות.", reply_markup=get_main_keyboard(user_id))
            
            buttons = []
            for i in items:
                v_id = i.get('id', {}).get('videoId')
                if v_id:
                    buttons.append([InlineKeyboardButton(f"🎵 {i['snippet']['title'][:50]}", callback_data=f"dl_{v_id}")])
            
            await status.delete()
            return await update.message.reply_text(f"תוצאות עבור '{text}':", reply_markup=InlineKeyboardMarkup(buttons))
        except: return await status.edit_text("❌ תקלה בחיפוש.", reply_markup=get_main_keyboard(user_id))

    if "youtube.com" in text or "youtu.be" in text:
        asyncio.create_task(download_logic(update, context, text))

async def callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("הורדה מתחילה...")
    v_id = query.data.split('_')[1]
    asyncio.create_task(download_logic(update, context, f"https://www.youtube.com/watch?v={v_id}", query))

async def download_logic(update, context, url, query=None):
    user_id = update.effective_user.id
    uid = str(user_id)
    db = load_db()
    
    if user_id != ADMIN_ID and db.get(uid, {}).get("credits", 0) <= 0:
        target = query.message if query else update.message
        return await target.reply_text("❌ נגמרו לך ההורדות! שתף את הבוט לקבלת עוד.")

    target = query.message if query else update.message
    status = await target.reply_text("⏳ מעבד שיר...")
    
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
                await context.bot.send_audio(chat_id=update.effective_chat.id, audio=f, title=title, write_timeout=200)
            if user_id != ADMIN_ID:
                db[uid]["credits"] -= 1; save_db(db)
            os.remove(path); await status.delete()
        except:
            if os.path.exists(path): os.remove(path)
            await status.edit_text("❌ שגיאה בשליחה.")
    else:
        await status.edit_text("❌ הורדה נכשלה.")

def main():
    app = Application.builder().token(TOKEN).write_timeout(200).read_timeout(200).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(callback_query))
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__': main()
