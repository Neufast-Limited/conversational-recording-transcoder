import json
import logging
from functools import lru_cache

import boto3

from .clients import build_client_config
from .config import Settings
from .repositories.queue_repository import SqsRepository
from .repositories.s3_repository import S3Repository
from .services.pipeline import TranscodePipeline

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


@lru_cache(maxsize=1)
def get_pipeline() -> TranscodePipeline:
    settings = Settings.from_env()
    settings.validate_runtime()
    config = build_client_config(settings)
    s3 = boto3.client("s3", region_name=settings.region, config=config)
    sqs = boto3.client("sqs", region_name=settings.region, config=config)
    return TranscodePipeline(settings, S3Repository(s3), SqsRepository(sqs))


def lambda_handler(event: dict, context: object) -> dict:
    """SQS handler. Failed records are reported individually so SQS retries them and
    moves them to the dead-letter queue after the redrive limit."""
    pipeline = get_pipeline()
    failures = []
    for record in event.get("Records", []):
        message_id = record.get("messageId")
        try:
            interview_id = json.loads(record["body"])["interview_id"]
            pipeline.process_interview(interview_id)
        except Exception:
            logger.exception("Failed to process message %s", message_id)
            failures.append({"itemIdentifier": message_id})
    return {"batchItemFailures": failures}
