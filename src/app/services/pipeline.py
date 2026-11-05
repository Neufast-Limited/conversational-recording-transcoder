import json
import logging
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from ..config import Settings
from ..errors import InvalidInterviewId, TranscodeError, TranscriptNotReady
from ..repositories.queue_repository import QueueRepository
from ..repositories.storage_repository import StorageRepository
from .manifest import find_sessions
from .transcoder import transcode_sessions

logger = logging.getLogger(__name__)

# Same format the scoring lambda accepts.
INTERVIEW_ID_PATTERN = re.compile(r"^[A-Za-z0-9_\-]{1,128}$")


class TranscodePipeline:
    def __init__(self, settings: Settings, storage: StorageRepository, queue: QueueRepository):
        self.settings = settings
        self.storage = storage
        self.queue = queue

    def process_interview(self, interview_id: str) -> None:
        if not isinstance(interview_id, str) or not INTERVIEW_ID_PATTERN.match(interview_id):
            raise InvalidInterviewId(f"Invalid interview_id: {interview_id!r}")

        settings = self.settings
        marker_key = f"{interview_id}/transcode_done.json"
        mp4_key = f"{interview_id}/{interview_id}.mp4"
        transcript_key = f"{interview_id}/transcript.json"

        if self.storage.head(settings.output_bucket, marker_key) is not None:
            logger.info("interview_id=%s already processed, skipping", interview_id)
            return

        mp4_size = self.storage.head(settings.output_bucket, mp4_key)
        if mp4_size is None:
            mp4_size = self.build_mp4(interview_id, mp4_key)
        else:
            logger.info("interview_id=%s MP4 already exists, skipping transcode", interview_id)

        if self.storage.head(settings.output_bucket, transcript_key) is None:
            raise TranscriptNotReady(f"{transcript_key} is not in {settings.output_bucket} yet")

        self.queue.send_message(
            settings.scoring_queue_url,
            json.dumps({"interview_id": interview_id}),
            group_id=f"messageGroup_{interview_id}",
            dedup_id=f"messageId_{interview_id}",
        )
        logger.info("interview_id=%s scoring message sent", interview_id)

        self.storage.put_json_if_absent(
            settings.output_bucket,
            marker_key,
            {
                "interview_id": interview_id,
                "mp4_key": mp4_key,
                "mp4_size": mp4_size,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    def build_mp4(self, interview_id: str, mp4_key: str) -> int:
        settings = self.settings
        sessions = find_sessions(self.storage, settings.recording_bucket, interview_id)
        logger.info("interview_id=%s found %d recording session(s)", interview_id, len(sessions))

        with tempfile.TemporaryDirectory(dir=settings.scratch_dir) as scratch:
            mp4_path = transcode_sessions(
                self.storage,
                settings.recording_bucket,
                sessions,
                Path(scratch),
                settings.download_concurrency,
                settings.ffmpeg_timeout_seconds,
            )
            local_size = mp4_path.stat().st_size
            self.storage.upload_file(settings.output_bucket, mp4_key, str(mp4_path), "video/mp4")

        remote_size = self.storage.head(settings.output_bucket, mp4_key)
        if remote_size != local_size:
            raise TranscodeError(f"Uploaded MP4 is {remote_size} bytes, expected {local_size}")
        logger.info("interview_id=%s uploaded %s (%d bytes)", interview_id, mp4_key, remote_size)
        return remote_size
