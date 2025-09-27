import os
import logging
import sqlite3
import asyncio
from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters
from flask import Flask
from threading import Thread

# ===== Logging =====
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ===== Config =====
BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("❌ BOT_TOKEN env variable is missing!")

CHANNEL_ID = -1002742606192
GROUP_ID = -1002892874648

# ===== SQLite DB =====
DB_PATH = "anime_cache.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS anime (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT UNIQUE,
            post_link TEXT
        )
    """)
    conn.commit()
    conn.close()

def upsert_anime(title: str, post_link: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO anime(title, post_link)
        VALUES(?,?)
        ON CONFLICT(title) DO UPDATE SET post_link=excluded.post_link
    """, (title, post_link))
    conn.commit()
    conn.close()

def search_anime(query: str, limit: int = 5):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    pattern = f"%{query}%"
    cur.execute("SELECT title, post_link FROM anime WHERE title LIKE ? LIMIT ?", (pattern, limit))
    rows = cur.fetchall()
    conn.close()
    return rows

# ===== Handlers =====
async def group_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    if update.effective_chat.id != GROUP_ID:
        return

    text = (update.message.text or "").strip().lower()
    if not text:
        return

    results = search_anime(text, limit=3)
    if results:
        reply_texts = [f"👉 {title}\n🔗 {link}" for title, link in results]
        await update.message.reply_text("\n\n".join(reply_texts))
    else:
        await update.message.reply_text("❌ এই নামে কোন এনিমে পাওয়া যায়নি!")

async def cache_channel_messages(application: Application, limit: int = 1000):
    logger.info("Caching channel messages...")
    try:
        async for msg in application.bot.get_chat_history(CHANNEL_ID, limit=limit):
            text = msg.text or msg.caption or ""
            if not text:
                continue
            title = text.splitlines()[0].strip().lower()  # First line as title
            try:
                post_link = msg.link
            except Exception:
                post_link = f"https://t.me/c/{str(CHANNEL_ID).replace('-100','')}/{msg.message_id}"
            upsert_anime(title, post_link)
    except Exception as e:
        logger.exception("Error caching channel messages: %s", e)
    logger.info("Caching done.")

# ===== Flask Web Server =====
app = Flask(__name__)

def run_bot(application):
    # স্টার্ট-আপ মেসেজ গ্রুপে পাঠাও
    try:
        logger.info("Sending startup message to group...")
        application.bot.send_message(GROUP_ID, "🎉 Bot has started successfully! I am now online and ready to help. 😊")
    except Exception as e:
        logger.error(f"Failed to send startup message: {e}")

    logger.info("Bot is running in polling mode...")
    try:
        application.run_polling(allowed_updates=Update.ALL_TYPES)
    except Exception as e:
        logger.error(f"Polling error: {e}")

def keep_alive():
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)))

@app.route('/')
def health_check():
    return "Bot is running", 200

# ===== Main =====
async def start_bot():
    init_db()
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, group_message_handler))

    # Cache channel messages in a separate thread
    cache_thread = Thread(target=lambda: asyncio.run(cache_channel_messages(application)))
    cache_thread.start()

    # Start bot polling in a separate thread
    bot_thread = Thread(target=lambda: run_bot(application))
    bot_thread.start()

    # Start Flask server
    keep_alive()

if __name__ == "__main__":
    asyncio.run(start_bot())
