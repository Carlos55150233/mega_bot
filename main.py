import os
import logging
import re
import base64
import struct
import requests
from io import BytesIO
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from Cryptodome.Cipher import AES
from Cryptodome.Util import Counter
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
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL")

# Chunk size for downloads (400MB to fit in PythonAnywhere)
CHUNK_SIZE = 400 * 1024 * 1024  # 400 MB
TELEGRAM_MAX_SIZE = 49 * 1024 * 1024  # 49 MB for Telegram uploads

def base64_to_a32(s):
    """Convert base64 string to array of 32-bit integers."""
    # Add padding if needed
    s += '=' * (4 - len(s) % 4) if len(s) % 4 else ''
    # Replace URL-safe characters
    s = s.replace('-', '+').replace('_', '/')
    s = s.replace(',', '')
    
    b = base64.b64decode(s)
    result = []
    for i in range(0, len(b), 4):
        result.append(struct.unpack('>I', b[i:i+4])[0] if i+4 <= len(b) else 0)
    return result

def a32_to_bytes(a):
    """Convert array of 32-bit integers to bytes."""
    return b''.join(struct.pack('>I', x) for x in a)

def decrypt_key(key, master_key):
    """Decrypt file key using master key."""
    cipher = AES.new(a32_to_bytes(master_key), AES.MODE_ECB)
    decrypted = cipher.decrypt(a32_to_bytes(key))
    return list(struct.unpack('>4I', decrypted[:16]))

def parse_mega_url(url):
    """Extract file ID and key from Mega URL."""
    # Pattern: mega.nz/file/FILE_ID#KEY or mega.nz/#!FILE_ID!KEY
    match = re.search(r'mega\.nz/(?:file/|#!)([a-zA-Z0-9_-]+)[#!]([a-zA-Z0-9_-]+)', url)
    if not match:
        return None, None
    return match.group(1), match.group(2)

async def get_mega_file_info(file_id, file_key_str):
    """Get file info from Mega API."""
    try:
        # Parse the file key
        file_key = base64_to_a32(file_key_str)
        
        # Decrypt the file key (first 8 elements are the key)
        k = (file_key[0] ^ file_key[4], file_key[1] ^ file_key[5],
             file_key[2] ^ file_key[6], file_key[3] ^ file_key[7])
        
        # Get file info from Mega API
        api_url = "https://g.api.mega.co.nz/cs"
        data = [{"a": "g", "g": 1, "p": file_id}]
        
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(
            None, 
            lambda: requests.post(api_url, json=data, timeout=30)
        )
        
        if response.status_code != 200:
            return None
        
        result = response.json()
        if not result or isinstance(result, dict) and 'e' in result:
            return None
            
        file_data = result[0]
        
        return {
            'download_url': file_data['g'],
            'size': file_data['s'],
            'key': k,
            'iv': (file_key[4], file_key[5], 0, 0),
            'name': file_data.get('at', 'file')
        }
    except Exception as e:
        logger.error(f"Error getting file info: {e}")
        return None

async def download_and_decrypt_chunk(url, start, end, key, iv_base, chunk_num):
    """Download and decrypt a specific chunk of the file."""
    try:
        headers = {'Range': f'bytes={start}-{end}'}
        
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(
            None,
            lambda: requests.get(url, headers=headers, stream=True, timeout=60)
        )
        
        if response.status_code not in [200, 206]:
            return None
        
        # Calculate IV for this chunk (CTR mode needs adjusted IV)
        block_offset = start // 16
        iv = list(iv_base)
        iv[2] = (block_offset >> 32) & 0xFFFFFFFF
        iv[3] = block_offset & 0xFFFFFFFF
        
        # Create AES cipher in CTR mode
        iv_bytes = a32_to_bytes(iv)
        ctr = Counter.new(128, initial_value=int.from_bytes(iv_bytes, 'big'))
        cipher = AES.new(a32_to_bytes(key), AES.MODE_CTR, counter=ctr)
        
        # Decrypt the chunk
        encrypted_data = response.content
        decrypted_data = cipher.decrypt(encrypted_data)
        
        return decrypted_data
    except Exception as e:
        logger.error(f"Error downloading chunk {chunk_num}: {e}")
        return None

async def process_mega_link_chunked(url: str, chat_id: int, message_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Download Mega file in chunks and upload to Telegram."""
    try:
        # Parse URL
        file_id, file_key_str = parse_mega_url(url)
        if not file_id or not file_key_str:
            await context.bot.edit_message_text(
                chat_id=chat_id, 
                message_id=message_id, 
                text="❌ URL de Mega inválida."
            )
            return
        
        # Get file info
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text="Obteniendo información del archivo... 🔍"
        )
        
        file_info = await get_mega_file_info(file_id, file_key_str)
        if not file_info:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text="❌ No se pudo obtener información del archivo."
            )
            return
        
        file_size = file_info['size']
        file_name = file_info['name']
        
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=f"📦 Archivo: {file_name}\n📊 Tamaño: {file_size/1024/1024:.2f} MB\n\nDescargando en chunks para ahorrar espacio... ⏳"
        )
        
        # Process file in chunks
        num_chunks = (file_size + CHUNK_SIZE - 1) // CHUNK_SIZE
        
        for chunk_num in range(num_chunks):
            start = chunk_num * CHUNK_SIZE
            end = min(start + CHUNK_SIZE - 1, file_size - 1)
            
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=f"📥 Descargando chunk {chunk_num + 1}/{num_chunks} ({(end-start+1)/1024/1024:.1f} MB)..."
            )
            
            # Download and decrypt chunk
            decrypted_chunk = await download_and_decrypt_chunk(
                file_info['download_url'],
                start,
                end,
                file_info['key'],
                file_info['iv'],
                chunk_num
            )
            
            if not decrypted_chunk:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"❌ Error descargando chunk {chunk_num + 1}"
                )
                continue
            
            # Split chunk into Telegram-sized parts if needed
            chunk_parts = []
            for i in range(0, len(decrypted_chunk), TELEGRAM_MAX_SIZE):
                chunk_parts.append(decrypted_chunk[i:i+TELEGRAM_MAX_SIZE])
            
            # Upload each part
            for part_idx, part_data in enumerate(chunk_parts):
                part_name = f"{file_name}.part{chunk_num * 100 + part_idx + 1:04d}"
                
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=f"📤 Subiendo parte {chunk_num * 100 + part_idx + 1}... ({len(part_data)/1024/1024:.1f} MB)"
                )
                
                # Upload to Telegram
                await context.bot.send_document(
                    chat_id=chat_id,
                    document=BytesIO(part_data),
                    filename=part_name
                )
            
            # Chunk processed, memory freed automatically
        
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=f"✅ ¡Completado! {num_chunks} chunks procesados.\n\nPara unir los archivos:\n1. Descarga todas las partes\n2. Usa `copy /b *.part* {file_name}` (Windows) o `cat *.part* > {file_name}` (Linux/Mac)"
        )
        
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"❌ Error: {str(e)}"
        )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    await update.message.reply_text(
        "🤖 Bot de Mega Chunked\n\n"
        "Envíame un enlace de Mega.nz y lo descargaré en chunks pequeños para ahorrar espacio en disco.\n\n"
        "⚠️ Los archivos se enviarán en partes que deberás unir después."
    )

async def handle_mega_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the message and spawn a background task."""
    url = update.message.text.strip()
    
    if "mega.nz" not in url:
        await update.message.reply_text("Por favor envíame un enlace válido de Mega.nz.")
        return

    # Reply immediately
    status_msg = await update.message.reply_text("🚀 Procesando enlace...")

    # Spawn background task
    context.application.create_task(
        process_mega_link_chunked(url, update.effective_chat.id, status_msg.message_id, context)
    )

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
        print("No RENDER_EXTERNAL_URL found, using polling...")
        application.run_polling()

if __name__ == "__main__":
    main()
