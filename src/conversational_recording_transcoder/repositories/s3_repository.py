from .storage_repository import StorageRepository


class S3Repository(StorageRepository):
    def __init__(self, client: object):
        self._client = client

    @property
    def client(self) -> object:
        return self._client
