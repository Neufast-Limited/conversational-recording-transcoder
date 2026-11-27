import unittest

from transcoder_perf import attribute_test_invocations, invocation_intervals, validate_probe


class EvidenceTests(unittest.TestCase):
    def test_warm_worker_delayed_traceback_does_not_mix_interviews(self):
        first = "11111111-1111-1111-1111-111111111111"
        second = "22222222-2222-2222-2222-222222222222"
        messages = [f"START RequestId: {first}",
                    f"[ERROR]\ttime\t{first}\tFailed to process message msg-one",
                    f"END RequestId: {first}", f"START RequestId: {second}",
                    "Delayed traceback: interview_one/transcript.json",
                    f"[ERROR]\ttime\t{second}\tFailed to process message msg-two",
                    f"END RequestId: {second}"]
        events = [{"timestamp": i, "logStreamName": "warm", "message": message} for i, message in enumerate(messages)]
        _, peak, mapping, _ = attribute_test_invocations(events, ["interview_one", "interview_two"], "run",
                                                       {"msg-one": "interview_one", "msg-two": "interview_two"})
        self.assertEqual(mapping, {"interview_one": {first}, "interview_two": {second}})
        self.assertEqual(peak, 1)

    def test_real_sqs_message_id_maps_to_test_interview(self):
        events = [{"timestamp": 1, "logStreamName": "test", "message": "START RequestId: actual"},
                  {"timestamp": 2, "logStreamName": "test", "message": "Failed to process message 1234-abcd"},
                  {"timestamp": 3, "logStreamName": "test", "message": "END RequestId: actual"}]
        intervals, peak, mapping, _ = attribute_test_invocations(events, ["interview_test"], "run",
                                                                {"1234-abcd": "interview_test"})
        self.assertEqual(mapping["interview_test"], {"actual"})
        self.assertEqual(peak, 1)

    def test_fragmented_error_log_maps_message_id_to_100th_interview(self):
        ids = [f"interview_perftc_test_{i:03d}" for i in range(1, 101)]
        events = [{"timestamp": 1, "logStreamName": "test", "message": "START RequestId: actual"},
                  {"timestamp": 2, "logStreamName": "other", "message": "START RequestId: unrelated"},
                  {"timestamp": 3, "logStreamName": "test", "message": "Failed to process message run100-100"},
                  {"timestamp": 4, "logStreamName": "test", "message": "END RequestId: actual"},
                  {"timestamp": 5, "logStreamName": "other", "message": "END RequestId: unrelated"}]
        intervals, peak, mapping, _ = attribute_test_invocations(events, ids, "run100")
        self.assertEqual([item["request_id"] for item in intervals], ["actual"])
        self.assertEqual(mapping[ids[99]], {"actual"})
        self.assertEqual(peak, 1)

    def test_twenty_serial_invocations_do_not_prove_concurrency(self):
        events = []
        for i in range(20):
            events += [{"timestamp": i * 10, "message": f"START RequestId: job-{i}"},
                       {"timestamp": i * 10 + 5, "message": f"END RequestId: job-{i}"}]
        intervals, peak = invocation_intervals(events)
        self.assertEqual(len(intervals), 20)
        self.assertEqual(peak, 1)

    def test_twenty_overlapping_invocations_prove_concurrency(self):
        events = [{"timestamp": i, "message": f"START RequestId: job-{i}"} for i in range(20)]
        events += [{"timestamp": 100 + i, "message": f"END RequestId: job-{i}"} for i in range(20)]
        _, peak = invocation_intervals(events)
        self.assertEqual(peak, 20)

    def test_duplicate_log_delivery_does_not_inflate_concurrency(self):
        event = {"timestamp": 1, "message": "START RequestId: job-1"}
        intervals, peak = invocation_intervals([event, event])
        self.assertEqual(peak, 1)
        self.assertIsNone(intervals[0]["end_ms"])

    def test_touching_intervals_are_not_overlapping(self):
        events = [{"timestamp": 1, "message": "START RequestId: a"},
                  {"timestamp": 2, "message": "END RequestId: a"},
                  {"timestamp": 2, "message": "START RequestId: b"}]
        self.assertEqual(invocation_intervals(events)[1], 1)

    def test_report_is_retained_for_resource_measurement(self):
        events = [{"timestamp": 1, "message": "START RequestId: a"},
                  {"timestamp": 2, "message": "REPORT RequestId: a Duration: 10 ms Max Memory Used: 200 MB"}]
        self.assertIn("200 MB", invocation_intervals(events)[0][0]["report"])

    def test_short_output_is_rejected_even_with_both_streams(self):
        with self.assertRaises(ValueError):
            validate_probe({"format": {"duration": "201"}, "streams": [
                {"codec_type": "video"}, {"codec_type": "audio"}]}, 3600)

    def test_missing_audio_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_probe({"format": {"duration": "3600"}, "streams": [{"codec_type": "video"}]}, 3600)

    def test_normal_container_rounding_is_accepted(self):
        self.assertEqual(validate_probe({"format": {"duration": "3600.02"}, "streams": [
            {"codec_type": "video"}, {"codec_type": "audio"}]}, 3600), 3600.02)


if __name__ == "__main__":
    unittest.main()
