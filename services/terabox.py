import logging
import os
import asyncio
import requests
from .base import BaseService
from terabox_downloader import TeraboxDownloader

logger = logging.getLogger(__name__)

class TeraboxService(BaseService):
    def can_handle(self, url: str) -> bool:
        return "terabox" in url or "teraboxapp" in url or "1024tera" in url

    async def get_file_info(self, url: str):
        try:
            cookie = os.getenv("TERABOX_COOKIE")
            if not cookie:
                logger.error("TERABOX_COOKIE not found")
                return None

            # Initialize downloader with cookie
            td = TeraboxDownloader(cookie)
            
            # Get file info
            loop = asyncio.get_running_loop()
            # Note: The library method might differ, assuming get_file_info or similar
            # If the library is simple, we might need to check its docs or source.
            # Based on pypi search, it might be 'get_data' or similar.
            # Let's try to be generic or wrap it safely.
            
            # If we look at common terabox-downloader usage:
            # from terabox_downloader import TeraboxDownloader
            # td = TeraboxDownloader(cookie)
            # info = td.get_data(url)
            
            file_info = await loop.run_in_executor(None, lambda: td.get_data(url))
            
            if not file_info:
                return None

            # Map library output to our format
            # Assuming structure based on typical API response
            dlink = file_info.get('dlink') or file_info.get('download_link')
            
            if not dlink:
                # Some libraries return a list
                if isinstance(file_info, list) and len(file_info) > 0:
                    file_info = file_info[0]
                    dlink = file_info.get('dlink')

            if not dlink:
                return None

            return {
                'service': 'terabox',
                'download_url': dlink,
                'size': int(file_info.get('size', 0)),
                'name': file_info.get('server_filename', 'terabox_file'),
                'headers': {'User-Agent': 'Mozilla/5.0', 'Cookie': f'ndus={cookie}'}
            }

        except Exception as e:
            logger.error(f"Error getting Terabox info: {e}")
            return None

    async def download_to_file(self, file_info, destination_path, progress_callback=None):
        try:
            headers = file_info.get('headers', {})
            
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
        return None
