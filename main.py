import os
import json
import asyncio
import yt_dlp
import requests
import re
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# --- הגדרות ---
TOKEN = "8670146396:AAFM4nhtzxS9NEfD3Dn-RkAGkftYelMXqug"
YOUTUBE_API_KEY = "AIzaSyAKK4VTbQJ_8tsHfxb2tcDZ9SSR9gWXH-0"
ADMIN_ID = 8708085965 
DB_FILE = "users_data.json"

executor = ThreadPoolExecutor(max_workers=20)

def load_db():
    if not os.path.exists(DB_FILE): return {}
    with open(DB_FILE, "r") as f: return json.load(f)

def save_db(db):
    with open(DB_FILE, "w") as f: json.dump(db, f)

def clean_filename(title):
    clean = re.sub(r'[\\/*?:"<>|]', "", title)
    return " ".join(clean.split())

def get_main_keyboard(user_id, searching=False):
    if searching:
        return ReplyKeyboardMarkup([[KeyboardButton("❌ ביטול פעולה")]], resize_keyboard=True, is_persistent=True)
    
    kb = [
        [KeyboardButton("🎤 חיפוש לפי שם זמר"), KeyboardButton("🎵 חיפוש לפי שם שיר")],
        [KeyboardButton("📢 שיתוף הבוט לקבלת הורדות")]
    ]
    if user_id == ADMIN_ID:
        kb.append([KeyboardButton("📣 פרסום הודעה לכולם")])
    return ReplyKeyboardMarkup(kb, resize_keyboard=True, is_persistent=True)

async def open_telegram(app):
    try:
        bot_info = await app.bot.get_me()
        url = f"https://t.me/{bot_info.username}"
        webbrowser.open(url)
    except: pass

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    db = load_db()
    uid = str(user_id)
    
    args = context.args
    if args and args[0].isdigit():
        referrer_id = args[0]
        if uid not in db and referrer_id != uid:
            if referrer_id in db:
                db[referrer_id]["credits"] = db[referrer_id].get("credits", 0) + 5
                try: await context.bot.send_message(chat_id=int(referrer_id), text="🎁 חבר נרשם דרכך! קיבלת 5 הורדות בונוס.")
                except: pass

    if uid not in db:
        db[uid] = {"credits": 5, "state": None}
        save_db(db)
    
    is_admin = (user_id == ADMIN_ID)
    msg = "👑 שלום אדוני המנהל!" if is_admin else f"🚀 ברוך הבא!\nנותרו לך {db[uid]['credits']} הורדות."
    await update.message.reply_text(msg, reply_markup=get_main_keyboard(user_id))

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    uid = str(user_id)
    text = update.message.text
    db = load_db()
    is_admin = (user_id == ADMIN_ID)

    if text == "❌ ביטול פעולה":
        db[uid]["state"] = None
        save_db(db)
        return await update.message.reply_text("הפעולה בוטלה.", reply_markup=get_main_keyboard(user_id))

    if text == "📢 שיתוף הבוט לקבלת הורדות":
        bot_info = await context.bot.get_me()
        share_text = f"מצאתי בוט מטורף להורדת שירים מיוטיוב בחינם! 🎶🔥\nכנסו דרך הקישור שלי לקבלת הורדות בחינם: https://t.me/{bot_info.username}?start={user_id}"
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("🚀 בחר חבר לשיתוף הקישור", switch_inline_query=share_text)]])
        return await update.message.reply_text("לחץ על הכפתור למטה כדי לבחור למי לשלוח:", reply_markup=markup)

    if text == "📣 פרסום הודעה לכולם" and is_admin:
        db[uid]["state"] = "broadcasting"
        save_db(db)
        return await update.message.reply_text("כתוב את ההודעה להפצה לכל המשתמשים:", reply_markup=get_main_keyboard(user_id, True))

    if db.get(uid, {}).get("state") == "broadcasting" and is_admin:
        db[uid]["state"] = None
        save_db(db)
        count = 0
        status = await update.message.reply_text("📣 מפיץ הודעה...")
        for user in db.keys():
            try:
                await context.bot.send_message(chat_id=int(user), text=f"📢 **הודעה חשובה:**\n\n{text}", parse_mode="Markdown")
                count += 1
            except: pass
        return await status.edit_text(f"✅ נשלח ל-{count} משתמשים.", reply_markup=get_main_keyboard(user_id))

    if text in ["🎤 חיפוש לפי שם זמר", "🎵 חיפוש לפי שם שיר"]:
        db[uid]["state"] = "searching"
        save_db(db)
        return await update.message.reply_text(f"הקלד את שם ה{'זמר' if 'זמר' in text else 'שיר'}:", reply_markup=get_main_keyboard(user_id, True))

    if db.get(uid, {}).get("state") == "searching":
        db[uid]["state"] = None
        save_db(db)
        status = await update.message.reply_text("🔍 מחפש ביוטיוב (100 תוצאות)...")
        try:
            url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&q={text}&maxResults=100&type=video&key={YOUTUBE_API_KEY}"
            res = await asyncio.get_event_loop().run_in_executor(None, lambda: requests.get(url, timeout=15).json())
            buttons = [[InlineKeyboardButton(i['snippet']['title'][:55], callback_data=f"dl_{i['id']['videoId']}")] for i in res.get('items', []) if i.get('id', {}).get('videoId')]
            if not buttons: return await status.edit_text("לא נמצאו תוצאות.", reply_markup=get_main_keyboard(user_id))
            await status.delete()
            return await update.message.reply_text(f"תוצאות עבור '{text}':", reply_markup=InlineKeyboardMarkup(buttons))
        except: return await status.edit_text("❌ שגיאה בחיפוש.", reply_markup=get_main_keyboard(user_id))

    if "youtube.com" in text or "youtu.be" in text:
        if not is_admin and db.get(uid, {}).get("credits", 0) <= 0:
            return await update.message.reply_text("⚠️ אין לך הורדות! שתף את הבוט.")
        asyncio.create_task(download_logic(update, context, text))

async def callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    db = load_db()
    if user_id != ADMIN_ID and db.get(str(user_id), {}).get("credits", 0) <= 0:
        return await update.callback_query.answer("אין הורדות!", show_alert=True)
    await update.callback_query.answer("מתחיל הורדה... 🚀")
    v_id = update.callback_query.data.split('_')[1]
    asyncio.create_task(download_logic(update, context, f"https://www.youtube.com/watch?v={v_id}", update.callback_query))

async def download_logic(update, context, url, query=None):
    user_id = update.effective_user.id
    target = query.message if query else update.message
    status_msg = await target.reply_text("⏳ מוריד...")
    
    def run_download():
        try:
            ydl_opts = {'format': 'bestaudio/best', 'outtmpl': 'tmp_%(id)s.%(ext)s', 'quiet': True}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                title = clean_filename(info.get('title', 'song'))
                path = f"{title}.mp3"
                os.rename(ydl.prepare_filename(info), path)
                return title, path
        except: return None, None

    title, filename = await asyncio.get_running_loop().run_in_executor(executor, run_download)
    if title and filename:
        with open(filename, 'rb') as f:
            await context.bot.send_audio(chat_id=update.effective_chat.id, audio=f, title=title)
        os.remove(filename)
        await status_msg.delete()
        if user_id != ADMIN_ID:
            db = load_db(); db[str(user_id)]["credits"] -= 1; save_db(db)
    else: await status_msg.edit_text("❌ נכשל.", reply_markup=get_main_keyboard(user_id))

def main():
    app = Application.builder().token(TOKEN).build()
    asyncio.get_event_loop().create_task(open_telegram(app))
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(callback_query))
    app.run_polling()

if __name__ == '__main__': main()
