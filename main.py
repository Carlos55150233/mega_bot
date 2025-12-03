import os
import logging
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv
from services.manager import ServiceManager
from io import BytesIO

# Load environment variables
load_dotenv()

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Environment variables
TOKEN = os.getenv("TELEGRAM_TOKEN")
PORT = int(os.environ.get("PORT", 8080))
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL")

# Initialize Service Manager
service_manager = ServiceManager()

# Constants
TELEGRAM_MAX_SIZE = 49 * 1024 * 1024  # 49 MB
CHUNK_SIZE = 400 * 1024 * 1024 # 400 MB

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    await update.message.reply_text(
        "🤖 **Multi-Downloader Bot**\n\n"
        "Soporto enlaces de:\n"
        "📦 **Mega.nz**\n"
        "🔥 **Mediafire**\n"
        "☁️ **Terabox**\n\n"
        "Solo envíame el enlace y yo me encargo del resto. 🚀"
    , parse_mode='Markdown')

async def process_url(url: str, chat_id: int, message_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process a URL using the appropriate service."""
    try:
        # Detect service
        service = service_manager.get_service(url)
        if not service:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text="❌ Enlace no soportado. Solo Mega, Mediafire y Terabox."
            )
            return

        # Get file info
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=f"🔍 Analizando enlace de {service.__class__.__name__.replace('Service', '')}..."
        )

        file_info = await service.get_file_info(url)
        if not file_info:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text="❌ No se pudo obtener información del archivo. Verifica que el enlace sea público."
            )
            return

        file_name = file_info['name']
        file_size = file_info['size']
        
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=f"📦 **Archivo:** `{file_name}`\n📊 **Tamaño:** `{file_size/1024/1024:.2f} MB`\n\n⬇️ Iniciando descarga..."
        , parse_mode='Markdown')

        # Smart Download/Upload Logic
        # For now, we use the chunked approach for everyone to be safe with RAM/Disk
        # In the future, we can check if Local Bot API is enabled to send >50MB files directly.
        
        num_chunks = (file_size + CHUNK_SIZE - 1) // CHUNK_SIZE
        
        for chunk_num in range(num_chunks):
            start = chunk_num * CHUNK_SIZE
            end = min(start + CHUNK_SIZE - 1, file_size - 1)
            
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=f"⬇️ Descargando parte {chunk_num + 1}/{num_chunks}..."
            )
            
            chunk_data = await service.download_chunk(file_info, start, end)
            
            if not chunk_data:
                await context.bot.send_message(chat_id=chat_id, text=f"❌ Error descargando parte {chunk_num + 1}")
                continue

            # Upload to Telegram in 49MB parts
            part_idx = 0
            total_parts = (len(chunk_data) + TELEGRAM_MAX_SIZE - 1) // TELEGRAM_MAX_SIZE
            
            for i in range(0, len(chunk_data), TELEGRAM_MAX_SIZE):
                part_data = chunk_data[i:i+TELEGRAM_MAX_SIZE]
                part_name = f"{file_name}.part{chunk_num * 100 + part_idx + 1:04d}"
                
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=f"📤 Subiendo {part_name} ({part_idx + 1}/{total_parts})..."
                )
                
                try:
                    await asyncio.wait_for(
                        context.bot.send_document(
                            chat_id=chat_id,
                            document=BytesIO(part_data),
                            filename=part_name,
                            read_timeout=120,
                            write_timeout=120
                        ),
                        timeout=180
                    )
                except Exception as e:
                     await context.bot.send_message(chat_id=chat_id, text=f"⚠️ Error subiendo {part_name}: {e}")
                
                part_idx += 1
            
            # Free memory
            del chunk_data

        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text="✅ **¡Proceso Completado!**"
        , parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Error processing URL: {e}", exc_info=True)
        await context.bot.send_message(chat_id=chat_id, text=f"❌ Error interno: {str(e)}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming messages."""
    url = update.message.text.strip()
    
    # Basic URL validation
    if not url.startswith(('http://', 'https://')):
        await update.message.reply_text("⚠️ Por favor envía un enlace válido (http/https).")
        return

    # Reply immediately
    status_msg = await update.message.reply_text("🔄 Procesando enlace...")

    # Spawn background task
    context.application.create_task(
        process_url(url, update.effective_chat.id, status_msg.message_id, context)
    )

def main() -> None:
    """Start the bot."""
    if not TOKEN:
        logger.error("No TELEGRAM_TOKEN provided!")
        return

    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Polling is best for RDP/Windows
    print("🤖 Bot iniciado en modo Polling...")
    application.run_polling()

if __name__ == "__main__":
    main()
