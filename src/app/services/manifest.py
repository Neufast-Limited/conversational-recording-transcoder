import re
from dataclasses import dataclass
from datetime import datetime, timezone

from ..errors import InvalidRecording, RecordingNotReady
from ..repositories.storage_repository import StorageRepository

MANIFEST_NAME = "manifest.json"
MANIFEST_VERSION = 1
CHUNK_PATTERN = re.compile(r"chunk_([0-9]{8})\.webm")
USABLE_STATUSES = {"complete", "interrupted"}
UNFINISHED_STATUSES = {"recording", "incomplete"}


@dataclass(frozen=True)
class RecordingSession:
    session_id: str
    started_at: float
    chunk_keys: tuple[str, ...]


def _started_at_seconds(value: object) -> float:
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
    session_ids = []
    uploads: dict[str, dict[int, int]] = {}
    for key, size in storage.list_objects(bucket, root).items():
        session_id, _, name = key[len(root):].partition("/")
        if name == MANIFEST_NAME:
            session_ids.append(session_id)
        elif match := CHUNK_PATTERN.fullmatch(name):
            uploads.setdefault(session_id, {})[int(match[1])] = size
    if not session_ids:
        raise RecordingNotReady(f"No recording manifest found under {root}")

    sessions = []
    for session_id in sorted(session_ids):
        prefix = f"{root}{session_id}/"
        manifest = storage.read_json(bucket, f"{prefix}{MANIFEST_NAME}")
        session = _validate_session(session_id, prefix, manifest, uploads.get(session_id, {}))
        if session is not None:
            sessions.append(session)
    if not sessions:
        raise InvalidRecording(f"All recording sessions under {root} are empty")
    sessions.sort(key=lambda item: item.started_at)
    return sessions


def _validate_session(
    session_id: str, prefix: str, manifest: dict, uploaded_sizes: dict[int, int]
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

    manifest_sizes: dict[int, int] = {}
    for entry in manifest.get("chunks") or []:
        seq = int(entry["seq"])
        if seq in manifest_sizes:
            raise InvalidRecording(f"Session {session_id}: duplicate chunk seq {seq}")
        manifest_sizes[seq] = int(entry["size"])
    if not manifest_sizes:
        return None

    sequences = range(len(manifest_sizes))
    if sorted(manifest_sizes) != list(sequences):
        raise RecordingNotReady(f"Session {session_id}: chunk sequence is not contiguous from 0")

    stale = sorted(uploaded_sizes.keys() - manifest_sizes.keys())
    if stale:
        raise RecordingNotReady(f"Session {session_id}: chunks {stale} are uploaded but not in the manifest")

    for seq in sequences:
        size = uploaded_sizes.get(seq)
        if size is None:
            raise RecordingNotReady(f"Session {session_id}: chunk {seq} is not uploaded")
        if size != manifest_sizes[seq]:
            raise RecordingNotReady(
                f"Session {session_id}: chunk {seq} is {size} bytes, manifest says {manifest_sizes[seq]}"
            )

    total_bytes = manifest.get("totalBytes")
    if total_bytes is not None and int(total_bytes) != sum(manifest_sizes.values()):
        raise RecordingNotReady(f"Session {session_id}: totalBytes does not match the chunk sizes")

    return RecordingSession(
        session_id=session_id,
        started_at=_started_at_seconds(manifest.get("startedAt")),
        chunk_keys=tuple(f"{prefix}chunk_{seq:08d}.webm" for seq in sequences),
    )
