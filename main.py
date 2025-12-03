import os
import logging
import asyncio
import time
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait
from dotenv import load_dotenv
from services.manager import ServiceManager

async def safe_edit_message(message: Message, text: str):
    """Edit message safely handling FloodWait."""
    try:
        await message.edit_text(text)
    except FloodWait as e:
        logger.warning(f"FloodWait: Waiting {e.value} seconds")
        await asyncio.sleep(e.value)
        try:
            await message.edit_text(text)
        except Exception:
            pass
    except Exception as e:
        logger.error(f"Error editing message: {e}")

# Load environment variables
load_dotenv()

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Environment variables
# Environment variables
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")

# Validate and fallback
if not API_ID or not str(API_ID).strip():
    print("⚠️ API_ID no encontrado en .env")
    API_ID = input("Introduce tu API_ID: ")

if not API_HASH or not API_HASH.strip():
    print("⚠️ API_HASH no encontrado en .env")
    API_HASH = input("Introduce tu API_HASH: ")

if not BOT_TOKEN or not BOT_TOKEN.strip():
    print("⚠️ TELEGRAM_TOKEN no encontrado en .env")
    BOT_TOKEN = input("Introduce tu TELEGRAM_TOKEN: ")

try:
    API_ID = int(API_ID)
except ValueError:
    print("❌ Error: API_ID debe ser un número (ej: 123456).")
    exit(1)

# Initialize Service Manager
service_manager = ServiceManager()

# Initialize Pyrogram Client
app = Client(
    "mega_bot_session",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

async def progress(current, total, message: Message, start_time, status_text, last_update_time):
    """Progress callback for uploads."""
    now = time.time()
    
    # Update only every 7 seconds to avoid FloodWait blocking the upload
    if now - last_update_time[0] < 7: 
        return
        
    last_update_time[0] = now
        
    percentage = current * 100 / total
    speed = current / (now - start_time)
    eta = (total - current) / speed if speed > 0 else 0
    
    try:
        await message.edit_text(
            f"{status_text}\n"
            f"📊 **Progreso:** `{percentage:.1f}%`\n"
            f"💾 **Procesado:** `{current/1024/1024:.1f} MB` / `{total/1024/1024:.1f} MB`\n"
            f"🚀 **Velocidad:** `{speed/1024/1024:.1f} MB/s`\n"
            f"⏳ **ETA:** `{int(eta)}s`"
        )
    except FloodWait as e:
        # If we hit flood wait during progress, just skip this update
        # We don't want to sleep here because it would block the upload
        pass 
    except Exception:
        pass # Ignore errors to keep uploading

@app.on_message(filters.command("start"))
async def start(client, message):
    await message.reply_text(
        "🤖 **Mega Bot RDP (Pyrogram Edition)**\n\n"
        "🚀 **Soporte 2GB+ Activado**\n"
        "Envíame enlaces de:\n"
        "📦 **Mega.nz**\n"
        "🔥 **Mediafire**\n\n"
        "Los descargaré en el servidor y te los enviaré completos."
    )

@app.on_message(filters.text & ~filters.command("start"))
async def handle_url(client, message):
    url = message.text.strip()
    
    if not url.startswith(('http://', 'https://')):
        return

    status_msg = await message.reply_text("🔄 **Analizando enlace...**")
    
    try:
        # Detect service
        service = service_manager.get_service(url)
        if not service:
            await safe_edit_message(status_msg, "❌ Enlace no soportado.")
            return

        # Get file info
        file_info = await service.get_file_info(url)
        if not file_info:
            await safe_edit_message(status_msg, "❌ No se pudo obtener información del archivo.")
            return

        file_name = file_info['name']
        file_size = file_info['size']
        
        await safe_edit_message(status_msg, 
            f"📦 **Archivo:** `{file_name}`\n"
            f"📊 **Tamaño:** `{file_size/1024/1024:.2f} MB`\n\n"
            f"⬇️ **Iniciando descarga al servidor...**"
        )
        
        # Download to local file
        destination = f"downloads/{file_name}"
        os.makedirs("downloads", exist_ok=True)
        
        start_time = time.time()
        last_update_time = [0] # Mutable list to pass by reference

        async def download_progress(current, total):
            await progress(current, total, status_msg, start_time, "⬇️ **Descargando...**", last_update_time)

        success = await service.download_to_file(file_info, destination, download_progress)
        
        if not success:
            await safe_edit_message(status_msg, "❌ Error en la descarga.")
            if os.path.exists(destination):
                os.remove(destination)
            return

        await safe_edit_message(status_msg, "✅ **Descarga completada.**\n📤 **Subiendo a Telegram...**")
        
        # Upload to Telegram
        start_time = time.time()
        last_update_time = [0] # Reset for upload
        
        async def upload_progress(current, total):
             await progress(current, total, status_msg, start_time, "📤 **Subiendo...**", last_update_time)

        await client.send_document(
            chat_id=message.chat.id,
            document=destination,
            caption=f"📦 `{file_name}`",
            progress=upload_progress
        )
        
        await safe_edit_message(status_msg, "✅ **¡Proceso Finalizado!**")
        
        # Cleanup
        if os.path.exists(destination):
            os.remove(destination)

    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        await safe_edit_message(status_msg, f"❌ Error: {str(e)}")
        # Cleanup on error
        if 'destination' in locals() and os.path.exists(destination):
            os.remove(destination)

if __name__ == "__main__":
    print("🤖 Bot iniciado (Pyrogram)...")
    app.run()
