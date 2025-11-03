import os
import logging
import tempfile
import shutil
from pathlib import Path
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import yt_dlp

# 🔐 Get token from environment
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN environment variable is required!")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Create global downloads base (optional, but we'll use temp dirs per request)
BASE_DOWNLOADS_DIR = Path("downloads")
BASE_DOWNLOADS_DIR.mkdir(exist_ok=True)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎵 Send me a YouTube video or playlist link!\n"
        "Add the word **mp3** in your message to get audio only."
    )


def download_with_ytdlp(url: str, audio_only: bool, download_dir: Path) -> list[Path]:
    """Download video(s) and return list of file paths."""
    ydl_opts = {
        "format": "bestaudio/best" if audio_only else "bestvideo+bestaudio/best",
        "outtmpl": str(download_dir / "%(title).200s.%(ext)s"),
        "noplaylist": False,  # Allow playlists
        "quiet": True,
        "no_warnings": True,
        "restrictfilenames": True,
    }

    if audio_only:
        ydl_opts["postprocessors"] = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ]

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        # Handle playlist vs single video
        if "entries" in info:
            # Playlist
            files = []
            for entry in info["entries"]:
                if entry and entry.get("requested_downloads"):
                    for d in entry["requested_downloads"]:
                        files.append(Path(d["filepath"]))
            return files
        else:
            # Single video
            if info.get("requested_downloads"):
                return [Path(d["filepath"]) for d in info["requested_downloads"]]
    return []


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text.strip()
    if not user_input:
        await update.message.reply_text("Please send a YouTube link.")
        return

    urls = [u.strip() for u in user_input.split(",") if u.strip()]
    audio_only = "mp3" in user_input.lower()

    await update.message.reply_text(
        f"📥 Downloading {'audio' if audio_only else 'video'}(s)... "
        f"({len(urls)} link(s))\nThis may take a minute!"
    )

    # ✅ Create a unique temp directory per request
    with tempfile.TemporaryDirectory(dir=BASE_DOWNLOADS_DIR) as tmp_dir:
        download_dir = Path(tmp_dir)
        all_files = []

        for url in urls:
            try:
                files = download_with_ytdlp(url, audio_only, download_dir)
                all_files.extend(files)
            except Exception as e:
                logger.error(f"Download failed for {url}: {e}")
                await update.message.reply_text(f"❌ Failed to download: {url}")

        if not all_files:
            await update.message.reply_text("❌ No files were downloaded.")
            return

        success_count = 0
        for file_path in all_files:
            try:
                if file_path.stat().st_size > 50 * 1024 * 1024:
                    await update.message.reply_text(
                        f"⚠️ Skipped (too large): {file_path.name[:30]}... (>50MB)"
                    )
                    continue

                with open(file_path, "rb") as f:
                    if audio_only:
                        await update.message.reply_audio(audio=f)
                    else:
                        await update.message.reply_video(video=f)
                success_count += 1

            except Exception as e:
                logger.error(f"Send file failed: {e}")
                await update.message.reply_text(f"⚠️ Could not send: {file_path.name[:30]}...")

        await update.message.reply_text(
            f"✅ Done! Sent {success_count}/{len(all_files)} file(s)."
        )
        # Temp dir auto-deleted after `with` block → ✅ no cleanup needed!


def main():
    if not TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set!")

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("YouTube bot started.")
    app.run_polling()


if __name__ == "__main__":
    main()
