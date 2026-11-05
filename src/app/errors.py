class TranscoderError(Exception):
    """Base class for transcoder failures."""


class InvalidInterviewId(TranscoderError):
    """The interview_id does not match the format the scoring lambda accepts."""


class RecordingNotReady(TranscoderError):
    """Recording uploads look unfinished or inconsistent; a retry may succeed."""


class InvalidRecording(TranscoderError):
    """The recording data is unusable and retrying will not fix it."""


class TranscriptNotReady(TranscoderError):
    """transcript.json is not in the output bucket yet; a retry may succeed."""


class TranscodeError(TranscoderError):
    """ffmpeg or ffprobe failed or produced an unusable file."""
