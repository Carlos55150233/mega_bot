import re
import base64
import struct
import requests
import asyncio
import logging
from .base import BaseService
from Cryptodome.Cipher import AES
from Cryptodome.Util import Counter

logger = logging.getLogger(__name__)

class MegaService(BaseService):
    def can_handle(self, url: str) -> bool:
        return "mega.nz" in url

    def base64_to_a32(self, s):
        s += '=' * (4 - len(s) % 4) if len(s) % 4 else ''
        s = s.replace('-', '+').replace('_', '/')
        s = s.replace(',', '')
        b = base64.b64decode(s)
        result = []
        for i in range(0, len(b), 4):
            result.append(struct.unpack('>I', b[i:i+4])[0] if i+4 <= len(b) else 0)
        return result

    def a32_to_bytes(self, a):
        return b''.join(struct.pack('>I', x) for x in a)

    def parse_mega_url(self, url):
        match = re.search(r'mega\.nz/(?:file/|#!)([a-zA-Z0-9_-]+)[#!]([a-zA-Z0-9_-]+)', url)
        if not match:
            return None, None
        return match.group(1), match.group(2)

    async def get_file_info(self, url: str):
        try:
            file_id, file_key_str = self.parse_mega_url(url)
            if not file_id or not file_key_str:
                return None

            file_key = self.base64_to_a32(file_key_str)
            k = (file_key[0] ^ file_key[4], file_key[1] ^ file_key[5],
                 file_key[2] ^ file_key[6], file_key[3] ^ file_key[7])
            
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
                'service': 'mega',
                'download_url': file_data['g'],
                'size': file_data['s'],
                'key': k,
                'iv': (file_key[4], file_key[5], 0, 0),
                'name': file_data.get('at', 'file')
            }
        except Exception as e:
            logger.error(f"Error getting Mega info: {e}")
            return None

    async def download_to_file(self, file_info, destination_path, progress_callback=None):
        try:
            file_size = file_info['size']
            chunk_size = 4096 * 1024 # 4MB chunks for decryption
            
            with open(destination_path, 'wb') as f:
                for start in range(0, file_size, chunk_size):
                    end = min(start + chunk_size - 1, file_size - 1)
                    
                    chunk_data = await self.download_chunk(file_info, start, end)
                    if not chunk_data:
                        return False
                        
                    f.write(chunk_data)
                    
                    if progress_callback:
                        await progress_callback(end + 1, file_size)
                        
            return True
        except Exception as e:
            logger.error(f"Error downloading Mega file: {e}")
            return False

    async def download_chunk(self, file_info, start, end):
        try:
            headers = {'Range': f'bytes={start}-{end}'}
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(
                None,
                lambda: requests.get(file_info['download_url'], headers=headers, stream=True, timeout=60)
            )
            
            if response.status_code not in [200, 206]:
                return None
            
            block_offset = start // 16
            iv = list(file_info['iv'])
            iv[2] = (block_offset >> 32) & 0xFFFFFFFF
            iv[3] = block_offset & 0xFFFFFFFF
            
            iv_bytes = self.a32_to_bytes(iv)
            ctr = Counter.new(128, initial_value=int.from_bytes(iv_bytes, 'big'))
            cipher = AES.new(self.a32_to_bytes(file_info['key']), AES.MODE_CTR, counter=ctr)
            
            return cipher.decrypt(response.content)
        except Exception as e:
            logger.error(f"Error downloading Mega chunk: {e}")
            return None
