import os
import logging
import asyncio
import time
from pyrogram import Client, filters
from pyrogram.types import Message
from dotenv import load_dotenv
from services.manager import ServiceManager

# Load environment variables
load_dotenv()

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Environment variables
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")

# Initialize Service Manager
service_manager = ServiceManager()

# Initialize Pyrogram Client
app = Client(
    "mega_bot_session",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

async def progress(current, total, message: Message, start_time, status_text):
    """Progress callback for uploads."""
    now = time.time()
    diff = now - start_time
    if diff < 1: # Update every 1 second
        return
        
    percentage = current * 100 / total
    speed = current / diff
    eta = (total - current) / speed if speed > 0 else 0
    
    try:
        await message.edit_text(
            f"{status_text}\n"
            f"📊 **Progreso:** `{percentage:.1f}%`\n"
            f"💾 **Procesado:** `{current/1024/1024:.1f} MB` / `{total/1024/1024:.1f} MB`\n"
            f"🚀 **Velocidad:** `{speed/1024/1024:.1f} MB/s`\n"
            f"⏳ **ETA:** `{int(eta)}s`"
        )
        # Reset start time to avoid spamming edits (Pyrogram handles this internally but good to be safe)
    except Exception:
        pass

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
            await status_msg.edit_text("❌ Enlace no soportado.")
            return

        # Get file info
        file_info = await service.get_file_info(url)
        if not file_info:
            await status_msg.edit_text("❌ No se pudo obtener información del archivo.")
            return

        file_name = file_info['name']
        file_size = file_info['size']
        
        await status_msg.edit_text(
            f"📦 **Archivo:** `{file_name}`\n"
            f"📊 **Tamaño:** `{file_size/1024/1024:.2f} MB`\n\n"
            f"⬇️ **Iniciando descarga al servidor...**"
        )
        
        # Download to local file
        destination = f"downloads/{file_name}"
        os.makedirs("downloads", exist_ok=True)
        
        start_time = time.time()
        last_update_time = [0] # Mutable to pass to callback

        async def download_progress(current, total):
            now = time.time()
            if now - last_update_time[0] > 2: # Update every 2 seconds
                last_update_time[0] = now
                await progress(current, total, status_msg, start_time, "⬇️ **Descargando...**")

        success = await service.download_to_file(file_info, destination, download_progress)
        
        if not success:
            await status_msg.edit_text("❌ Error en la descarga.")
            if os.path.exists(destination):
                os.remove(destination)
            return

        await status_msg.edit_text("✅ **Descarga completada.**\n📤 **Subiendo a Telegram...**")
        
        # Upload to Telegram
        start_time = time.time()
        async def upload_progress(current, total):
             # Pyrogram passes current, total automatically
             await progress(current, total, status_msg, start_time, "📤 **Subiendo...**")

        await client.send_document(
            chat_id=message.chat.id,
            document=destination,
            caption=f"📦 `{file_name}`",
            progress=upload_progress
        )
        
        await status_msg.edit_text("✅ **¡Proceso Finalizado!**")
        
        # Cleanup
        if os.path.exists(destination):
            os.remove(destination)

    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        await status_msg.edit_text(f"❌ Error: {str(e)}")
        # Cleanup on error
        if 'destination' in locals() and os.path.exists(destination):
            os.remove(destination)

if __name__ == "__main__":
    print("🤖 Bot iniciado (Pyrogram)...")
    app.run()
