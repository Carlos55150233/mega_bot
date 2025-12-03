import re
import requests
import asyncio
import logging
import os
from .base import BaseService

logger = logging.getLogger(__name__)

class TeraboxService(BaseService):
    def can_handle(self, url: str) -> bool:
        return "terabox" in url or "teraboxapp" in url or "1024tera" in url

    async def get_file_info(self, url: str):
        try:
            cookies = {
                'ndus': os.getenv("TERABOX_COOKIE")
            }
            
            if not cookies['ndus']:
                logger.error("TERABOX_COOKIE (ndus) not found in environment")
                return None

            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'application/json, text/plain, */*',
                'Referer': 'https://www.terabox.com/',
                'Cookie': f"ndus={cookies['ndus']}"
            }

            loop = asyncio.get_running_loop()
            
            # 1. Resolve short URL if needed
            if "/s/" in url:
                shorturl = url.split("/s/")[-1]
            else:
                # Follow redirect to get real URL
                resp = await loop.run_in_executor(
                    None,
                    lambda: requests.get(url, headers=headers, allow_redirects=True)
                )
                final_url = resp.url
                if "surl=" in final_url:
                    shorturl = "1" + final_url.split("surl=")[-1]
                else:
                    shorturl = final_url.split("/")[-1]

            # 2. Get File Info from API
            api_url = f"https://www.terabox.com/api/shorturlinfo?shorturl={shorturl}&root=1"
            
            response = await loop.run_in_executor(
                None,
                lambda: requests.get(api_url, headers=headers, cookies=cookies)
            )
            
            data = response.json()
            if data.get('errno') != 0:
                logger.error(f"Terabox API error: {data}")
                return None

            file_list = data.get('list', [])
            if not file_list:
                return None
                
            file_data = file_list[0] # Assume first file for now
            
            # 3. Get Download Link
            # Sometimes dlink is in the info, sometimes we need another call.
            # Usually 'dlink' is present in the list item.
            dlink = file_data.get('dlink')
            
            if not dlink:
                return None

            return {
                'service': 'terabox',
                'download_url': dlink,
                'size': int(file_data.get('size', 0)),
                'name': file_data.get('server_filename', 'terabox_file'),
                'headers': headers # Important for download
            }

        except Exception as e:
            logger.error(f"Error getting Terabox info: {e}")
            return None

    async def download_to_file(self, file_info, destination_path, progress_callback=None):
        try:
            headers = file_info.get('headers', {})
            # Terabox dlinks often redirect and need the User-Agent/Cookie
            
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(
                None,
                lambda: requests.get(file_info['download_url'], headers=headers, stream=True, timeout=60)
            )
            
            if response.status_code != 200:
                return False
                
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            
            with open(destination_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=1024*1024):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if progress_callback:
                            await progress_callback(downloaded, total_size)
            return True
        except Exception as e:
            logger.error(f"Error downloading Terabox file: {e}")
            return False

    async def download_chunk(self, file_info, start, end):
        # Not used in download_to_file mode, but kept for compatibility
        return None
