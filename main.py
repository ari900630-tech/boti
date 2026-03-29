import os
import json
import asyncio
import yt_dlp
import requests
import re
from concurrent.futures import ThreadPoolExecutor
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

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
        return ReplyKeyboardMarkup(
            [[KeyboardButton("❌ ביטול פעולה")]], 
            resize_keyboard=True, 
            is_persistent=True,
            input_field_placeholder=placeholder
        )
    
    kb = [
        [KeyboardButton("🎤 חיפוש לפי שם זמר"), KeyboardButton("🎵 חיפוש לפי שם שיר")],
        [KeyboardButton("📢 שיתוף הבוט לקבלת הורדות")]
    ]
    if user_id == ADMIN_ID:
        kb.append([KeyboardButton("📣 פרסום הודעה לכולם"), KeyboardButton("📊 סטטיסטיקת בוט")])
    
    return ReplyKeyboardMarkup(
        kb, 
        resize_keyboard=True, 
        is_persistent=True,
        input_field_placeholder=placeholder
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    db = load_db()
    uid = str(user_id)
    
    if uid not in db:
        db[uid] = {"credits": 5, "state": None}
        save_db(db)
    
    await update.message.reply_text(
        "🚀 ברוך הבא לבוט ההורדות!\nהמקלדת זמינה תמיד דרך כפתור ה-4 נקודות בשורת הכתיבה.",
        reply_markup=get_main_keyboard(user_id)
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    uid = str(user_id)
    text = update.message.text
    db = load_db()
    is_admin = (user_id == ADMIN_ID)

    if text == "❌ ביטול פעולה":
        db[uid]["state"] = None
        save_db(db)
        return await update.message.reply_text("הפעולה בוטלה. חזרנו לתפריט הראשי.", reply_markup=get_main_keyboard(user_id))

    if text == "📊 סטטיסטיקת בוט" and is_admin:
        user_count = len(db.keys())
        return await update.message.reply_text(f"📊 **סה\"כ משתמשים רשומים:** {user_count}", reply_markup=get_main_keyboard(user_id))

    if text == "📢 שיתוף הבוט לקבלת הורדות":
        bot_info = await context.bot.get_me()
        share_text = f"מצאתי בוט מטורף להורדת שירים! 🎶🔥\nhttps://t.me/{bot_info.username}?start={user_id}"
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("🚀 שיתוף מהיר", switch_inline_query=share_text)]])
        return await update.message.reply_text("לחץ על הכפתור כדי לשתף:", reply_markup=markup)

    if text == "📣 פרסום הודעה לכולם" and is_admin:
        db[uid]["state"] = "broadcasting"
        save_db(db)
        return await update.message.reply_text("שלח את ההודעה להפצה:", reply_markup=get_main_keyboard(user_id, True))

    if db.get(uid, {}).get("state") == "broadcasting" and is_admin:
        db[uid]["state"] = None
        save_db(db)
        count = 0
        for u in db.keys():
            try:
                await context.bot.send_message(chat_id=int(u), text=text)
                count += 1
            except: pass
        return await update.message.reply_text(f"✅ נשלח ל-{count} משתמשים.", reply_markup=get_main_keyboard(user_id))

    if text in ["🎤 חיפוש לפי שם זמר", "🎵 חיפוש לפי שם שיר"]:
        db[uid]["state"] = "searching"
        save_db(db)
        return await update.message.reply_text(f"הקלד את שם החיפוש (עד 100 תוצאות):", reply_markup=get_main_keyboard(user_id, True))

    if db.get(uid, {}).get("state") == "searching":
        db[uid]["state"] = None
        save_db(db)
        status = await update.message.reply_text("🔍 מחפש ביוטיוב...")
        
        try:
            def fetch_yt():
                url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&q={text}&maxResults=100&type=video&key={YOUTUBE_API_KEY}"
                response = requests.get(url, timeout=10)
                return response.json()

            res = await asyncio.get_event_loop().run_in_executor(None, fetch_yt)
            items = res.get('items', [])
            
            if not items:
                error_msg = res.get("error", {}).get("message", "לא נמצאו תוצאות.")
                return await status.edit_text(f"❌ שגיאה: {error_msg}", reply_markup=get_main_keyboard(user_id))
            
            buttons = []
            for i in items:
                v_id = i.get('id', {}).get('videoId')
                if v_id:
                    title = i['snippet']['title'][:55]
                    buttons.append([InlineKeyboardButton(title, callback_data=f"dl_{v_id}")] )
            
            await status.delete()
            # שליחת התוצאות עם המקלדת הראשית כדי לוודא שאינה נעלמת
            return await update.message.reply_text(f"תוצאות עבור '{text}':", reply_markup=InlineKeyboardMarkup(buttons))
        except Exception as e:
            return await status.edit_text(f"❌ תקלה: {str(e)}", reply_markup=get_main_keyboard(user_id))

    if "youtube.com" in text or "youtu.be" in text:
        asyncio.create_task(download_logic(update, context, text))

async def callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer("מוריד... 🚀")
    v_id = update.callback_query.data.split('_')[1]
    asyncio.create_task(download_logic(update, context, f"https://www.youtube.com/watch?v={v_id}", update.callback_query))

async def download_logic(update, context, url, query=None):
    target = query.message if query else update.message
    status_msg = await target.reply_text("⏳ מוריד...")
    
    def run_download():
        try:
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': 'tmp_%(id)s.%(ext)s',
                'quiet': True,
                'no_warnings': True
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                title = clean_filename(info.get('title', 'song'))
                path = f"{title}.mp3"
                os.rename(ydl.prepare_filename(info), path)
                return title, path
        except Exception as e:
            print(f"Download Error: {e}")
            return None, None

    title, filename = await asyncio.get_running_loop().run_in_executor(executor, run_download)
    if title and filename:
        with open(filename, 'rb') as f:
            await context.bot.send_audio(chat_id=update.effective_chat.id, audio=f, title=title)
        os.remove(filename)
        await status_msg.delete()
    else:
        await status_msg.edit_text("❌ הורדה נכשלה. נסה שוב מאוחר יותר.")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(callback_query))
    app.run_polling()

if __name__ == '__main__': main()
