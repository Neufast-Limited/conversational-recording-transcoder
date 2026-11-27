import contextlib
import io
import os
import unittest
from unittest.mock import patch

import boto3
from botocore.exceptions import ClientError
from botocore.stub import Stubber

from app.config import Settings
from app.main import main
from app.repositories.s3_repository import S3Repository


class S3RepositoryTests(unittest.TestCase):
    def test_startup_initializes_without_any_s3_requests(self):
        client = boto3.client("s3", region_name="ap-southeast-1",
                              aws_access_key_id="testing", aws_secret_access_key="testing")
        # No responses are registered: any S3 operation fails this test.
        with Stubber(client), patch(
            "app.main.boto3.client", return_value=client
        ), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(), 0)

    def test_repository_retains_injected_client(self):
        client = object()
        self.assertIs(S3Repository(client).client, client)

    def test_no_bucket_configuration_is_required(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(Settings.from_env(), Settings(region="ap-southeast-1"))

    def test_conditional_marker_conflict_can_be_retried(self):
        client = boto3.client(
            "s3", region_name="ap-southeast-1", aws_access_key_id="testing", aws_secret_access_key="testing"
        )
        storage = S3Repository(client)
        params = {
            "Bucket": "output", "Key": "interview/transcode_done.json", "Body": b"{}",
            "ContentType": "application/json", "IfNoneMatch": "*",
        }
        with Stubber(client) as stub:
            stub.add_client_error("put_object", "ConditionalRequestConflict", http_status_code=409, expected_params=params)
            stub.add_client_error("put_object", "PreconditionFailed", http_status_code=412, expected_params=params)
            with self.assertRaises(ClientError):
                storage.put_json_if_absent("output", "interview/transcode_done.json", {})
            self.assertFalse(storage.put_json_if_absent("output", "interview/transcode_done.json", {}))


if __name__ == "__main__":
    unittest.main()
