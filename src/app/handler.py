import json
import logging
from functools import lru_cache

import boto3

from .clients import build_client_config
from .config import Settings
from .repositories.queue_repository import ScoringQueue
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
    return TranscodePipeline(settings, S3Repository(s3), ScoringQueue(sqs, settings.scoring_queue_url))


def lambda_handler(event: dict, context: object) -> dict:
    pipeline = get_pipeline()
    records = event.get("Records", [])
    failures = []
    for index, record in enumerate(records):
        message_id = record["messageId"]
        try:
            interview_id = json.loads(record["body"])["interview_id"]
            pipeline.process_interview(interview_id)
        except Exception:
            logger.exception("Failed to process message %s", message_id)
            failures.append({"itemIdentifier": message_id})
            if record.get("eventSourceARN", "").endswith(".fifo"):
                failures.extend({"itemIdentifier": pending["messageId"]} for pending in records[index + 1:])
                break
    return {"batchItemFailures": failures}
