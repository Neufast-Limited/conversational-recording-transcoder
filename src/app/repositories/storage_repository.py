from abc import ABC, abstractmethod


class StorageRepository(ABC):
    @property
    @abstractmethod
    def client(self) -> object:
        """Configured storage client, ready for future repository operations."""
