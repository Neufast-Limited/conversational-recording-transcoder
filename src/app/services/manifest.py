import re
from dataclasses import dataclass
from datetime import datetime, timezone

from ..errors import InvalidRecording, RecordingNotReady
from ..repositories.storage_repository import StorageRepository

MANIFEST_NAME = "manifest.json"
MANIFEST_VERSION = 1
CHUNK_PATTERN = re.compile(r"chunk_(\d{8})\.webm$")
USABLE_STATUSES = {"complete", "interrupted"}
UNFINISHED_STATUSES = {"recording", "incomplete"}


@dataclass(frozen=True)
class ChunkInfo:
    seq: int
    key: str
    size: int


@dataclass(frozen=True)
class RecordingSession:
    session_id: str
    started_at: float
    chunks: tuple[ChunkInfo, ...]


def started_at_seconds(value: object) -> float:
    """Epoch seconds from an ISO string or an epoch value in seconds or milliseconds."""
    if isinstance(value, (int, float)):
        return value / 1000 if value > 1e11 else float(value)
    if isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return 0.0
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()
    return 0.0


def find_sessions(storage: StorageRepository, bucket: str, interview_id: str) -> list[RecordingSession]:
    """Return the validated recording sessions of an interview, oldest first."""
    root = f"{interview_id}/recording_chunks/"
    objects = storage.list_objects(bucket, root)

    session_ids = []
    for key in objects:
        parts = key[len(root):].split("/")
        if len(parts) == 2 and parts[1] == MANIFEST_NAME:
            session_ids.append(parts[0])
    if not session_ids:
        raise RecordingNotReady(f"No recording manifest found under {root}")

    sessions = []
    for session_id in sorted(session_ids):
        prefix = f"{root}{session_id}/"
        manifest = storage.read_json(bucket, f"{prefix}{MANIFEST_NAME}")
        session = validate_session(session_id, prefix, manifest, objects)
        if session is not None:
            sessions.append(session)
    if not sessions:
        raise InvalidRecording(f"All recording sessions under {root} are empty")
    sessions.sort(key=lambda item: item.started_at)
    return sessions


def validate_session(
    session_id: str, prefix: str, manifest: dict, objects: dict[str, int]
) -> RecordingSession | None:
    """Validate one session's manifest against the uploaded chunks. None means no chunks were recorded."""
    if manifest.get("version") != MANIFEST_VERSION:
        raise InvalidRecording(f"Session {session_id}: unsupported manifest version {manifest.get('version')!r}")

    status = manifest.get("status")
    if status in UNFINISHED_STATUSES:
        raise RecordingNotReady(f"Session {session_id}: manifest status is {status}")
    if status not in USABLE_STATUSES:
        raise InvalidRecording(f"Session {session_id}: unknown manifest status {status!r}")
    if manifest.get("missingSequences"):
        raise RecordingNotReady(f"Session {session_id}: missing chunks {manifest['missingSequences']}")

    entries = manifest.get("chunks") or []
    if not entries:
        return None

    manifest_sizes: dict[int, int] = {}
    for entry in entries:
        seq = int(entry["seq"])
        if seq in manifest_sizes:
            raise InvalidRecording(f"Session {session_id}: duplicate chunk seq {seq}")
        manifest_sizes[seq] = int(entry["size"])
    if sorted(manifest_sizes) != list(range(len(manifest_sizes))):
        raise RecordingNotReady(f"Session {session_id}: chunk sequence is not contiguous from 0")

    uploaded_sizes: dict[int, int] = {}
    for key, size in objects.items():
        if key.startswith(prefix):
            match = CHUNK_PATTERN.search(key[len(prefix):])
            if match:
                uploaded_sizes[int(match.group(1))] = size
    stale = sorted(set(uploaded_sizes) - set(manifest_sizes))
    if stale:
        raise RecordingNotReady(f"Session {session_id}: chunks {stale} are uploaded but not in the manifest")

    chunks = []
    for seq in sorted(manifest_sizes):
        size = uploaded_sizes.get(seq)
        if size is None:
            raise RecordingNotReady(f"Session {session_id}: chunk {seq} is not uploaded")
        if size != manifest_sizes[seq]:
            raise RecordingNotReady(
                f"Session {session_id}: chunk {seq} is {size} bytes, manifest says {manifest_sizes[seq]}"
            )
        chunks.append(ChunkInfo(seq=seq, key=f"{prefix}chunk_{seq:08d}.webm", size=size))

    total_bytes = manifest.get("totalBytes")
    if total_bytes is not None and int(total_bytes) != sum(chunk.size for chunk in chunks):
        raise RecordingNotReady(f"Session {session_id}: totalBytes does not match the chunk sizes")

    return RecordingSession(
        session_id=session_id,
        started_at=started_at_seconds(manifest.get("startedAt")),
        chunks=tuple(chunks),
    )
