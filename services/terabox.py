import logging
import os
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
            # The library might have different methods, adapting to common usage
            loop = asyncio.get_running_loop()
            file_info = await loop.run_in_executor(None, lambda: td.get_file_info(url))
            
            if not file_info:
                return None

            return {
                'service': 'terabox',
                'download_url': file_info.get('dlink'), # Library should provide direct link
                'size': int(file_info.get('size', 0)),
                'name': file_info.get('server_filename', 'terabox_file'),
                'headers': {'User-Agent': 'Mozilla/5.0', 'Cookie': f'ndus={cookie}'}
            }

        except Exception as e:
            logger.error(f"Error getting Terabox info: {e}")
            return None

    async def download_to_file(self, file_info, destination_path, progress_callback=None):
        # ... (keep existing download logic but ensure headers are passed)
        return await super().download_to_file(file_info, destination_path, progress_callback) # Use base or re-implement if needed


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
