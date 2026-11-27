import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, call, patch

from app.config import Settings
from app.errors import RecordingNotReady
from app.handler import lambda_handler
from app.repositories.queue_repository import ScoringQueue
from app.repositories.storage_repository import StorageRepository
from app.services.manifest import find_sessions
from app.services.pipeline import TranscodePipeline


class TranscoderRegressionTests(unittest.TestCase):
    def test_manifest_rejects_missing_mismatched_and_stale_chunks(self):
        prefix = "interview/recording_chunks/session/"
        first = f"{prefix}chunk_00000000.webm"
        second = f"{prefix}chunk_00000001.webm"
        storage = Mock(spec=StorageRepository)
        storage.read_json.return_value = {
            "version": 1, "status": "complete", "chunks": [{"seq": 0, "size": 10}],
        }
        for uploads, message in (
            ({}, "chunk 0 is not uploaded"),
            ({first: 9}, "chunk 0 is 9 bytes"),
            ({first: 10, second: 10}, r"chunks \[1\] are uploaded but not in the manifest"),
        ):
            with self.subTest(uploads=uploads):
                storage.list_objects.return_value = {f"{prefix}manifest.json": 0, **uploads}
                with self.assertRaisesRegex(RecordingNotReady, message):
                    find_sessions(storage, "chunks", "interview")

    def test_standard_batch_continues_and_fifo_batch_preserves_order(self):
        for queue_name, processed in (("input", ["bad", "good"]), ("input.fifo", ["bad"])):
            with self.subTest(queue=queue_name):
                pipeline = Mock()
                pipeline.process_interview.side_effect = [RuntimeError("first record failed"), None]
                records = [
                    {
                        "messageId": interview_id,
                        "body": json.dumps({"interview_id": interview_id}),
                        "eventSourceARN": f"arn:aws:sqs:ap-southeast-1:123456789012:{queue_name}",
                    }
                    for interview_id in ("bad", "good")
                ]
                with patch("app.handler.get_pipeline", return_value=pipeline), self.assertLogs("app.handler"):
                    result = lambda_handler({"Records": records}, None)

                self.assertEqual(pipeline.process_interview.call_args_list, [call(item) for item in processed])
                failed = ["bad", "good"] if queue_name.endswith(".fifo") else ["bad"]
                self.assertEqual(result, {"batchItemFailures": [{"itemIdentifier": item} for item in failed]})

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg and ffprobe are required")
    def test_single_and_joined_recordings_reuse_mp4_and_score_once(self):
        for sizes, expected_size in ((["160x120"], (160, 120)), (["160x120", "320x180"], (1280, 720))):
            with self.subTest(sizes=sizes), tempfile.TemporaryDirectory(prefix="recording's scratch ") as scratch:
                work_dir = Path(scratch)
                chunks, manifests = {}, {}
                root = "interview_123/recording_chunks/"
                for index, size in enumerate(sizes):
                    source = work_dir / f"source{index}.webm"
                    subprocess.run(
                        [
                            "ffmpeg", "-v", "error", "-f", "lavfi", "-i", f"testsrc2=size={size}:rate=15",
                            "-f", "lavfi", "-i", "sine=sample_rate=48000", "-t", "1",
                            "-c:v", "libvpx", "-threads", "2", "-c:a", "libopus", str(source),
                        ],
                        capture_output=True, check=True, timeout=30,
                    )
                    data = source.read_bytes()
                    prefix = f"{root}session{len(sizes) - index}/"
                    parts = (data[:len(data) // 2], data[len(data) // 2:])
                    for seq, part in enumerate(parts):
                        chunks[f"{prefix}chunk_{seq:08d}.webm"] = part
                    manifests[f"{prefix}manifest.json"] = {
                        "version": 1, "status": "complete", "startedAt": 1_700_000_000_000 + index * 1000,
                        "totalBytes": len(data),
                        "chunks": [{"seq": seq, "size": len(parts[seq])} for seq in (1, 0)],
                    }
                    chunks[f"{prefix}archive/chunk_00000002.webm"] = b"archived"

                published = work_dir / "uploaded.mp4"
                output_sizes = {}
                storage = Mock(spec=StorageRepository)
                storage.list_objects.return_value = {key: len(data) for key, data in chunks.items()} | dict.fromkeys(
                    manifests, 0
                )
                storage.read_json.side_effect = lambda bucket, key: manifests[key]
                storage.download_file.side_effect = lambda bucket, key, path: Path(path).write_bytes(chunks[key])

                def upload_mp4(bucket, key, path, content_type):
                    shutil.copyfile(path, published)
                    output_sizes[key] = published.stat().st_size

                storage.upload_file.side_effect = upload_mp4
                storage.head.side_effect = lambda bucket, key: output_sizes.get(key)
                storage.put_json_if_absent.side_effect = lambda bucket, key, payload: output_sizes.setdefault(
                    key, len(json.dumps(payload))
                )
                sessions = find_sessions(storage, "chunks", "interview_123")
                self.assertEqual([session.session_id for session in sessions], [
                    f"session{index}" for index in range(len(sizes), 0, -1)
                ])

                sqs = Mock()
                pipeline = TranscodePipeline(
                    Settings(region="test", recording_bucket="chunks", output_bucket="out", scratch_dir=scratch),
                    storage,
                    ScoringQueue(sqs, "scoring.fifo"),
                )
                event = {"Records": [{"messageId": "message", "body": '{"interview_id":"interview_123"}'}]}
                with patch("app.handler.get_pipeline", return_value=pipeline), self.assertLogs("app.handler"):
                    self.assertEqual(lambda_handler(event, None), {"batchItemFailures": [{"itemIdentifier": "message"}]})
                    sqs.send_message.assert_not_called()
                    storage.put_json_if_absent.assert_not_called()

                    output_sizes["interview_123/transcript.json"] = 42
                    self.assertEqual(lambda_handler(event, None), {"batchItemFailures": []})
                    self.assertEqual(lambda_handler(event, None), {"batchItemFailures": []})

                storage.upload_file.assert_called_once()
                storage.put_json_if_absent.assert_called_once()
                bucket, key, marker = storage.put_json_if_absent.call_args.args
                self.assertEqual((bucket, key), ("out", "interview_123/transcode_done.json"))
                self.assertEqual(marker["mp4_size"], published.stat().st_size)
                sqs.send_message.assert_called_once_with(
                    QueueUrl="scoring.fifo",
                    MessageBody=json.dumps({"interview_id": "interview_123"}),
                    MessageGroupId="messageGroup_interview_123",
                    MessageDeduplicationId="messageId_interview_123",
                )
                output = subprocess.check_output(
                    ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(published)],
                    text=True, timeout=30,
                )
                info = json.loads(output)
                streams = {stream["codec_type"]: stream for stream in info["streams"]}
                self.assertEqual((streams["video"]["codec_name"], streams["audio"]["codec_name"]), ("h264", "aac"))
                self.assertEqual((streams["video"]["width"], streams["video"]["height"]), expected_size)
                self.assertAlmostEqual(float(info["format"]["duration"]), len(sizes), delta=0.15)
