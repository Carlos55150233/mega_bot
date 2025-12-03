import re
import requests
import asyncio
import logging
from .base import BaseService

logger = logging.getLogger(__name__)

class MediafireService(BaseService):
    def can_handle(self, url: str) -> bool:
        return "mediafire.com" in url

    async def get_file_info(self, url: str):
        try:
            loop = asyncio.get_running_loop()
            
            # Mediafire requires a session to get the direct link
            session = requests.Session()
            session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            })

            response = await loop.run_in_executor(
                None,
                lambda: session.get(url, timeout=30)
            )
            
            if response.status_code != 200:
                return None

            # Scrape direct link
            # Look for aria-label="Download file" or similar
            content = response.text
            
            # Regex for download button
            match = re.search(r'href="((https?://download[^"]+))"', content)
            if not match:
                # Try alternative pattern
                match = re.search(r'aria-label="Download file"\s+href="([^"]+)"', content)
            
            if not match:
                return None
                
            direct_url = match.group(1)
            
            # Get file size and name from headers of direct link (HEAD request)
            head_response = await loop.run_in_executor(
                None,
                lambda: session.head(direct_url, allow_redirects=True, timeout=30)
            )
            
            size = int(head_response.headers.get('Content-Length', 0))
            
            # Try to get name from Content-Disposition
            name = "mediafire_file"
            cd = head_response.headers.get('Content-Disposition')
            if cd:
                fname_match = re.search(r'filename="?([^"]+)"?', cd)
                if fname_match:
                    name = fname_match.group(1)
            else:
                # Fallback to URL name
                name = direct_url.split('/')[-1]

            return {
                'service': 'mediafire',
                'download_url': direct_url,
                'size': size,
                'name': name
            }

        except Exception as e:
            logger.error(f"Error getting Mediafire info: {e}")
            return None

    async def download_to_file(self, file_info, destination_path, progress_callback=None):
        try:
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(
                None,
                lambda: requests.get(file_info['download_url'], stream=True, timeout=60)
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
            logger.error(f"Error downloading Mediafire file: {e}")
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
            
            return response.content
        except Exception as e:
            logger.error(f"Error downloading Mediafire chunk: {e}")
            return None
