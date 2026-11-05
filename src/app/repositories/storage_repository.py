from abc import ABC, abstractmethod


class StorageRepository(ABC):
    @property
    @abstractmethod
    def client(self) -> object:
        """Configured storage client, ready for repository operations."""

    @abstractmethod
    def list_objects(self, bucket: str, prefix: str) -> dict[str, int]:
        """Return every object key under the prefix mapped to its size in bytes."""

    @abstractmethod
    def head(self, bucket: str, key: str) -> int | None:
        """Return the object size in bytes, or None when the object does not exist."""

    @abstractmethod
    def read_json(self, bucket: str, key: str) -> dict:
        """Download and parse a JSON object."""

    @abstractmethod
    def download_file(self, bucket: str, key: str, path: str) -> None:
        """Download an object to a local file path."""

    @abstractmethod
    def upload_file(self, bucket: str, key: str, path: str, content_type: str) -> None:
        """Upload a local file, using multipart upload for large files."""

    @abstractmethod
    def put_json_if_absent(self, bucket: str, key: str, payload: dict) -> bool:
        """Write a JSON object only if the key is absent. Return False when it already exists."""
