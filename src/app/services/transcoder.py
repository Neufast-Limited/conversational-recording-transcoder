import json
import logging
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ..errors import TranscodeError
from ..repositories.storage_repository import StorageRepository
from .manifest import RecordingSession

logger = logging.getLogger(__name__)

# libx264 needs even dimensions; keep the recorded size for a single session.
EVEN_SIZE_FILTER = "scale=trunc(iw/2)*2:trunc(ih/2)*2"
# Sessions can differ in size (camera swap), so joined sessions share one frame size.
JOINED_SIZE_FILTER = (
    "scale=1280:720:force_original_aspect_ratio=decrease,"
    "pad=1280:720:(ow-iw)/2:(oh-ih)/2,setsar=1"
)


def run_command(command: list[str], timeout: int) -> str:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as error:
        raise TranscodeError(f"{command[0]} timed out after {timeout}s") from error
    if result.returncode != 0:
        raise TranscodeError(f"{command[0]} exited with {result.returncode}: {result.stderr[-2000:]}")
    return result.stdout


def merge_chunks(
    storage: StorageRepository,
    bucket: str,
    session: RecordingSession,
    work_dir: Path,
    index: int,
    concurrency: int,
) -> Path:
    """Download a session's chunks and append them in sequence order into one webm.

    A byte-level concatenation is valid within one session: the first chunk carries
    the WebM header and the rest continue the same MediaRecorder stream.
    """
    chunk_dir = work_dir / f"chunks{index}"
    chunk_dir.mkdir()
    paths = [chunk_dir / f"{chunk.seq:08d}.webm" for chunk in session.chunks]

    def fetch(pair: tuple[str, Path]) -> None:
        storage.download_file(bucket, pair[0], str(pair[1]))

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        list(pool.map(fetch, [(chunk.key, path) for chunk, path in zip(session.chunks, paths)]))

    merged = work_dir / f"session{index}.webm"
    with merged.open("wb") as output:
        for path in paths:
            with path.open("rb") as source:
                shutil.copyfileobj(source, output)
            path.unlink()
    chunk_dir.rmdir()
    return merged


def convert_to_mp4(source: Path, target: Path, size_filter: str, timeout: int) -> None:
    # Browser webm has no duration and a variable frame rate: regenerate timestamps
    # and force a constant frame rate so the MP4 is seekable and clips cut cleanly.
    run_command(
        [
            "ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error", "-y",
            "-fflags", "+genpts",
            "-i", str(source),
            "-vf", size_filter,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
            "-fps_mode", "cfr", "-r", "30",
            "-c:a", "aac", "-ar", "48000", "-ac", "2",
            "-movflags", "+faststart",
            str(target),
        ],
        timeout,
    )


def join_mp4s(sources: list[Path], target: Path, work_dir: Path, timeout: int) -> None:
    list_file = work_dir / "sessions.txt"
    list_file.write_text("".join(f"file '{source}'\n" for source in sources))
    run_command(
        [
            "ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error", "-y",
            "-f", "concat", "-safe", "0", "-i", str(list_file),
            "-c", "copy", "-movflags", "+faststart",
            str(target),
        ],
        timeout,
    )


def verify_output(path: Path, timeout: int) -> float:
    """Return the duration in seconds after checking for a video and an audio stream."""
    output = run_command(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration:stream=codec_type",
            "-of", "json", str(path),
        ],
        timeout,
    )
    info = json.loads(output)
    stream_types = {stream.get("codec_type") for stream in info.get("streams", [])}
    if not {"video", "audio"} <= stream_types:
        raise TranscodeError(f"Output has streams {sorted(stream_types)}, expected video and audio")
    duration = float(info.get("format", {}).get("duration") or 0)
    if duration <= 0:
        raise TranscodeError("Output has no duration")
    return duration


def transcode_sessions(
    storage: StorageRepository,
    bucket: str,
    sessions: list[RecordingSession],
    work_dir: Path,
    concurrency: int,
    timeout: int,
) -> Path:
    """Turn the recording sessions into one MP4 in work_dir and return its path."""
    joined = len(sessions) > 1
    size_filter = JOINED_SIZE_FILTER if joined else EVEN_SIZE_FILTER

    session_mp4s = []
    for index, session in enumerate(sessions):
        merged = merge_chunks(storage, bucket, session, work_dir, index, concurrency)
        mp4 = work_dir / f"session{index}.mp4"
        logger.info("Converting session %s (%d chunks) to MP4", session.session_id, len(session.chunks))
        convert_to_mp4(merged, mp4, size_filter, timeout)
        merged.unlink()
        session_mp4s.append(mp4)

    if joined:
        final = work_dir / "interview.mp4"
        join_mp4s(session_mp4s, final, work_dir, timeout)
    else:
        final = session_mp4s[0]

    duration = verify_output(final, timeout)
    logger.info("Transcoded %d session(s) into %.1fs of MP4", len(sessions), duration)
    return final
