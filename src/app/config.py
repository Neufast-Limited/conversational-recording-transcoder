import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    region: str

    @classmethod
    def from_env(cls) -> "Settings":
        region = (os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "ap-southeast-1").strip()
        return cls(region=region)
