from botocore.config import Config

from .config import Settings


def build_client_config(settings: Settings) -> Config:
    return Config(
        connect_timeout=5,
        read_timeout=60,
        retries={"mode": "standard", "total_max_attempts": 5},
        max_pool_connections=settings.download_concurrency + 2,
    )
