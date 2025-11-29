import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from mega import Mega
import asyncio
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Environment variables
TOKEN = os.getenv("TELEGRAM_TOKEN")
PORT = int(os.environ.get("PORT", 5000))
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL")  # e.g., https://your-app.onrender.com

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    await update.message.reply_text("Hola! Envíame un enlace de Mega y trataré de descargarlo y enviártelo.")

async def handle_mega_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Downloads file from Mega and sends it to user."""
    url = update.message.text.strip()
    
    if "mega.nz" not in url:
        await update.message.reply_text("Por favor envíame un enlace válido de Mega.nz.")
        return

    status_msg = await update.message.reply_text("Iniciando descarga de Mega... ⏳")

    try:
        mega = Mega()
        m = mega.login() # Login anonymous
        
        # Download file
        await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=status_msg.message_id, text="Descargando archivo... esto puede tomar un momento.")
        
        # Run blocking download in a separate thread
        loop = asyncio.get_running_loop()
        filename = await loop.run_in_executor(None, lambda: m.download_url(url))
        
        if not filename:
             await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=status_msg.message_id, text="Error: No se pudo descargar el archivo.")
             return

        file_size = os.path.getsize(filename)
        await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=status_msg.message_id, text=f"Descarga completada ({file_size/1024/1024:.2f} MB). Comprimiendo... 🗜️")

        # Compress to ZIP
        zip_filename = f"{filename}.zip"
        import zipfile
        def compress_file(f_in, f_out):
            with zipfile.ZipFile(f_out, 'w', zipfile.ZIP_DEFLATED) as zipf:
                zipf.write(f_in)
        
        await loop.run_in_executor(None, lambda: compress_file(filename, zip_filename))
        
        # Remove original file to save space
        os.remove(filename)
        
        zip_size = os.path.getsize(zip_filename)
        await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=status_msg.message_id, text=f"Comprimido ({zip_size/1024/1024:.2f} MB). Subiendo a Telegram... 🚀")

        # Split and Send
        CHUNK_SIZE = 49 * 1024 * 1024 # 49 MB
        
        if zip_size <= CHUNK_SIZE:
            with open(zip_filename, 'rb') as f:
                await update.message.reply_document(document=f, filename=zip_filename)
        else:
            part_num = 1
            with open(zip_filename, 'rb') as f:
                while True:
                    chunk = f.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    
                    part_name = f"{zip_filename}.{part_num:03d}"
                    # Write chunk to temp file to send
                    with open(part_name, 'wb') as chunk_file:
                        chunk_file.write(chunk)
                        
                    with open(part_name, 'rb') as chunk_file:
                        await update.message.reply_document(document=chunk_file, filename=part_name)
                    
                    os.remove(part_name)
                    part_num += 1

        await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=status_msg.message_id, text="¡Archivos enviados! ✅ Usa 7-Zip o WinRAR para unirlos.")

    except Exception as e:
        logger.error(f"Error: {e}")
        await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=status_msg.message_id, text=f"Ocurrió un error: {str(e)}")
    finally:
        # Cleanup
        if 'filename' in locals() and filename and os.path.exists(filename):
            os.remove(filename)
        if 'zip_filename' in locals() and zip_filename and os.path.exists(zip_filename):
            os.remove(zip_filename)

def main() -> None:
    """Start the bot."""
    if not TOKEN:
        logger.error("No TELEGRAM_TOKEN provided!")
        return

    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_mega_link))

    # Webhook configuration
    if RENDER_EXTERNAL_URL:
        application.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=TOKEN,
            webhook_url=f"{RENDER_EXTERNAL_URL}/{TOKEN}"
        )
    else:
        # Fallback to polling for local testing if no URL provided
        print("No RENDER_EXTERNAL_URL found, using polling...")
        application.run_polling()

if __name__ == "__main__":
    main()
