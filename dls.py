import os
import logging
import glob
import yt_dlp
import time  # Import this at the top of the script
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

DOWNLOADS_DIR = "downloads"
os.makedirs(DOWNLOADS_DIR, exist_ok=True)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")  # Use environment variable for security

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Welcome! Send me YouTube links or a playlist URL to download videos or MP3s.")

def get_downloaded_file():
    """Finds the most recently downloaded file in the downloads directory."""
    files = glob.glob(os.path.join(DOWNLOADS_DIR, "*"))
    if not files:
        return None
    return max(files, key=os.path.getctime)  # Get the latest downloaded file

async def download_video(url: str, audio_only=False):
    try:
        ydl_opts = {
            'format': 'bestaudio/best' if audio_only else 'bestvideo+bestaudio/best',
            'outtmpl': os.path.join(DOWNLOADS_DIR, '%(title)s.%(ext)s'),
            'noplaylist': False,  # Allow playlists
            'restrictfilenames': True,
            'nooverwrites': True,
        }

        if audio_only:
            ydl_opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }]

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.extract_info(url, download=True)
        
        time.sleep(2)  # Give some time for the file system to update
        return get_downloaded_file()  # Return the latest file

    except Exception as e:
        return f"Error downloading {url}: {str(e)}"

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_input = update.message.text
    urls = user_input.split(',')
    audio_only = "mp3" in user_input.lower()
    num_videos = len(urls)

    await update.message.reply_text(f"Your video(s) is being downloaded, wait a while boss. ({num_videos} video(s))")

    success = False
    failure = False

    for url in urls:
        url = url.strip()
        filename = await download_video(url, audio_only)

        if filename and os.path.exists(filename):
            if os.path.getsize(filename) > 50 * 1024 * 1024:
                await update.message.reply_text("File too large for Telegram. Try downloading a smaller file.")
            else:
                await update.message.reply_document(document=open(filename, 'rb'))
            success = True
        else:
            await update.message.reply_text(f"Failed to download: {url}")
            failure = True

    if success:
        await update.message.reply_text("Download complete! Enjoy your files.")
    if failure:
        await update.message.reply_text("Some downloads failed. Please try again with a different link.")

if __name__ == '__main__':
    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    application.run_polling()
