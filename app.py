import os
import logging
import sqlite3
import asyncio
from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters

# ===== Logging =====
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ===== Config =====
BOT_TOKEN = os.environ.get("BOT_TOKEN")  # Render এ Env var হিসেবে দিবেন
if not BOT_TOKEN:
    raise RuntimeError("❌ BOT_TOKEN env variable is missing!")

CHANNEL_ID = -1002742606192  # আপনার চ্যানেল আইডি
GROUP_ID = -1002892874648    # আপনার গ্রুপ আইডি

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
            title = text.splitlines()[0].strip().lower()
            try:
                post_link = msg.link
            except Exception:
                post_link = f"https://t.me/c/{str(CHANNEL_ID).replace('-100','')}/{msg.message_id}"
            upsert_anime(title, post_link)
    except Exception as e:
        logger.exception("Error caching channel messages: %s", e)
    logger.info("Caching done.")

# ===== Main =====
async def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, group_message_handler))

    # চ্যানেলের পোস্ট ক্যাশ
    await cache_channel_messages(app)

    # Polling মোডে চালানো
    logger.info("Bot is running in polling mode...")
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
