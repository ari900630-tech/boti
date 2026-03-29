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

# הגדרת לוגים למעקב ב-Railway
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
    
    # בדיקת הצטרפות דרך קישור שיתוף (מערכת קרדיטים)
    if context.args and uid not in db:
        referrer_id = context.args[0]
        if referrer_id in db and referrer_id != uid:
            db[referrer_id]["credits"] = db[referrer_id].get("credits", 0) + 2
            save_db(db)
            try:
                await context.bot.send_message(chat_id=int(referrer_id), text="🎁 חבר הצטרף! קיבלת 2 הורדות נוספות.")
            except: pass

    if uid not in db:
        db[uid] = {"credits": 5, "state": None}
        save_db(db)
    
    await update.message.reply_text(
        "🚀 ברוך הבא לבוט ההורדות המקצועי!\n\n"
        f"שלום {update.effective_user.first_name}, המקלדת זמינה תמיד דרך כפתור ה-4 נקודות למטה.\n"
        f"יש לך כרגע: {db[uid].get('credits', 0)} הורדות.",
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
        return await update.message.reply_text("לחץ על הכפתור כדי לשתף ולקבל עוד הורדות:", reply_markup=markup)

    if text == "📣 פרסום הודעה לכולם" and is_admin:
        db[uid]["state"] = "broadcasting"
        save_db(db)
        return await update.message.reply_text("שלח את ההודעה (טקסט) שברצונך להפיץ לכל המשתמשים:", reply_markup=get_main_keyboard(user_id, True))

    if db.get(uid, {}).get("state") == "broadcasting" and is_admin:
        db[uid]["state"] = None
        save_db(db)
        count = 0
        for u in db.keys():
            try:
                await context.bot.send_message(chat_id=int(u), text=text)
                count += 1
            except: pass
        return await update.message.reply_text(f"✅ ההודעה נשלחה בהצלחה ל-{count} משתמשים.", reply_markup=get_main_keyboard(user_id))

    if text in ["🎤 חיפוש לפי שם זמר", "🎵 חיפוש לפי שם שיר"]:
        db[uid]["state"] = "searching"
        save_db(db)
        return await update.message.reply_text(f"הקלד כעת את שם החיפוש (אני אמצא עד 100 תוצאות עבורך):", reply_markup=get_main_keyboard(user_id, True))

    if db.get(uid, {}).get("state") == "searching":
        db[uid]["state"] = None
        save_db(db)
        status = await update.message.reply_text("🔍 מחפש ביוטיוב, אנא המתן...")
        
        try:
            def fetch_yt():
                url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&q={text}&maxResults=100&type=video&key={YOUTUBE_API_KEY}"
                response = requests.get(url, timeout=15)
                return response.json()

            res = await asyncio.get_event_loop().run_in_executor(None, fetch_yt)
            items = res.get('items', [])
            
            if not items:
                return await status.edit_text("❌ לא נמצאו תוצאות לחיפוש זה. נסה שם אחר.", reply_markup=get_main_keyboard(user_id))
            
            buttons = []
            for i in items:
                v_id = i.get('id', {}).get('videoId')
                if v_id:
                    title = i['snippet']['title'][:55]
                    buttons.append([InlineKeyboardButton(title, callback_data=f"dl_{v_id}")])
            
            await status.delete()
            return await update.message.reply_text(f"תוצאות עבור '{text}':", reply_markup=InlineKeyboardMarkup(buttons))
        except Exception as e:
            logger.error(f"Search Error: {e}")
            return await status.edit_text("❌ תקלה בחיפוש. נסה שוב בעוד כמה דקות.", reply_markup=get_main_keyboard(user_id))

    # טיפול בקישורים ישירים
    if "youtube.com" in text or "youtu.be" in text:
        asyncio.create_task(download_logic(update, context, text))

async def callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("ההורדה מתחילה... 🚀")
    v_id = query.data.split('_')[1]
    url = f"https://www.youtube.com/watch?v={v_id}"
    asyncio.create_task(download_logic(update, context, url, query))

async def download_logic(update, context, url, query=None):
    user_id = update.effective_user.id
    uid = str(user_id)
    db = load_db()
    
    # בדיקת קרדיטים (אלא אם זה האדמין)
    if user_id != ADMIN_ID and db.get(uid, {}).get("credits", 0) <= 0:
        target = query.message if query else update.message
        return await target.reply_text("❌ נגמרו לך ההורדות! שתף את הבוט כדי לקבל עוד.")

    target = query.message if query else update.message
    status_msg = await target.reply_text("⏳ מוריד ומעבד את השיר, אנא המתן...")
    
    def run_download():
        try:
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': 'tmp_%(id)s.%(ext)s',
                'quiet': True,
                'no_warnings': True,
                'nocheckcertificate': True,
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                title = clean_filename(info.get('title', 'song'))
                # yt-dlp מוסיף .mp3 אחרי העיבוד
                temp_filename = f"tmp_{info['id']}.mp3"
                final_filename = f"{title}.mp3"
                if os.path.exists(temp_filename):
                    os.rename(temp_filename, final_filename)
                    return title, final_filename
                return None, None
        except Exception as e:
            logger.error(f"Download Error: {e}")
            return None, None

    title, filename = await asyncio.get_running_loop().run_in_executor(executor, run_download)
    
    if title and filename:
        try:
            with open(filename, 'rb') as f:
                await context.bot.send_audio(
                    chat_id=update.effective_chat.id, 
                    audio=f, 
                    title=title,
                    write_timeout=300
                )
            # הורדת קרדיט
            if user_id != ADMIN_ID:
                db[uid]["credits"] -= 1
                save_db(db)
            
            os.remove(filename)
            await status_msg.delete()
        except Exception as e:
            logger.error(f"Send Error: {e}")
            if os.path.exists(filename): os.remove(filename)
            await status_msg.edit_text("❌ שגיאה בשליחת הקובץ לטלגרם. נסה שוב.")
    else:
        await status_msg.edit_text("❌ ההורדה נכשלה. יתכן שהסרטון ארוך מדי או חסום.")

def main():
    # הגדרות רשת מורחבות למניעת ניתוקים ב-Railway
    app = Application.builder().token(TOKEN).write_timeout(300).read_timeout(300).connect_timeout(300).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(callback_query))
    
    # הפעלה יציבה
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
