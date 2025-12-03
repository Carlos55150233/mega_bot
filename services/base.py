from abc import ABC, abstractmethod
from typing import Optional, Dict, Any

class BaseService(ABC):
    """Abstract base class for download services."""
    
    @abstractmethod
    def can_handle(self, url: str) -> bool:
        """Return True if this service can handle the given URL."""
        pass

    @abstractmethod
    async def get_file_info(self, url: str) -> Optional[Dict[str, Any]]:
        """
        Get file metadata.
        Returns dict with:
        - name: str
        - size: int (bytes)
        - direct_url: str (optional)
        - ... other service specific data
        """
        pass

    @abstractmethod
    async def download_chunk(self, file_info: Dict[str, Any], start: int, end: int) -> Optional[bytes]:
        """Download a specific chunk of the file."""
        pass
