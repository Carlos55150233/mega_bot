from .mega import MegaService
from .mediafire import MediafireService
from .terabox import TeraboxService

class ServiceManager:
    def __init__(self):
        self.services = [
            MegaService(),
            MediafireService(),
            TeraboxService()
        ]

    def get_service(self, url: str):
        for service in self.services:
            if service.can_handle(url):
                return service
        return None
