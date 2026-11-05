import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    region: str
    recording_bucket: str = ""
    output_bucket: str = ""
    scoring_queue_url: str = ""
    scratch_dir: str = "/tmp"
    ffmpeg_timeout_seconds: int = 780
    download_concurrency: int = 8

    @classmethod
    def from_env(cls) -> "Settings":
        region = (os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "ap-southeast-1").strip()
        return cls(
            region=region,
            recording_bucket=os.getenv("CVI_RECORDING_BUCKET_NAME", "").strip(),
            output_bucket=os.getenv("AWS_BUCKET_NAME", "").strip(),
            scoring_queue_url=os.getenv("SCORING_QUEUE_URL", "").strip(),
            scratch_dir=os.getenv("SCRATCH_DIR", "/tmp").strip() or "/tmp",
            ffmpeg_timeout_seconds=int(os.getenv("FFMPEG_TIMEOUT_SECONDS", "780")),
            download_concurrency=int(os.getenv("DOWNLOAD_CONCURRENCY", "8")),
        )

    def validate_runtime(self) -> None:
        missing = [
            name
            for name, value in (
                ("CVI_RECORDING_BUCKET_NAME", self.recording_bucket),
                ("AWS_BUCKET_NAME", self.output_bucket),
                ("SCORING_QUEUE_URL", self.scoring_queue_url),
            )
            if not value
        ]
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")
