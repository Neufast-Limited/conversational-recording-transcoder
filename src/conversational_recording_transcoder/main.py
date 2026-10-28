import json
import sys

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from .config import Settings
from .repositories.s3_repository import S3Repository
from .repositories.storage_repository import StorageRepository


def main() -> int:
    try:
        settings = Settings.from_env()
        client = boto3.client(
            "s3",
            region_name=settings.region,
            config=Config(
                connect_timeout=5,
                read_timeout=10,
                retries={"mode": "standard", "total_max_attempts": 2},
            ),
        )
        storage: StorageRepository = S3Repository(client)
    except (ValueError, BotoCoreError, ClientError) as error:
        print(json.dumps({"status": "error", "message": str(error)}), file=sys.stderr)
        return 1
    print(json.dumps({"status": "initialized", "service": "s3",
                      "region": settings.region}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
