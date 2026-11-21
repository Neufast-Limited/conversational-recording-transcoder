import unittest
from unittest.mock import Mock

from app.config import Settings
from app.errors import TranscriptNotReady
from app.services.pipeline import TranscodePipeline


class PerformanceGuardTests(unittest.TestCase):
    def test_missing_transcript_allows_encoding_but_prevents_scoring(self):
        storage, queue = Mock(), Mock()
        storage.head.return_value = None
        pipeline = TranscodePipeline(Settings(region="ap-southeast-1", output_bucket="test"), storage, queue)
        pipeline.build_mp4 = Mock(return_value=100)
        with self.assertRaises(TranscriptNotReady):
            pipeline.process_interview("perf_tc_guard_001")
        pipeline.build_mp4.assert_called_once_with("perf_tc_guard_001", "perf_tc_guard_001/perf_tc_guard_001.mp4")
        queue.send_message.assert_not_called()
        storage.put_json_if_absent.assert_not_called()


if __name__ == "__main__":
    unittest.main()
