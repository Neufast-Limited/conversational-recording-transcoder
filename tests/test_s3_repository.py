import contextlib
import io
import os
import unittest
from unittest.mock import patch

import boto3
from botocore.stub import Stubber

from conversational_recording_transcoder.config import Settings
from conversational_recording_transcoder.main import main
from conversational_recording_transcoder.repositories.s3_repository import S3Repository


class S3RepositoryTests(unittest.TestCase):
    def test_startup_initializes_without_any_s3_requests(self):
        client = boto3.client("s3", region_name="ap-southeast-1",
                              aws_access_key_id="testing", aws_secret_access_key="testing")
        # No responses are registered: any S3 operation fails this test.
        with Stubber(client), patch(
            "conversational_recording_transcoder.main.boto3.client", return_value=client
        ), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(), 0)

    def test_repository_retains_injected_client(self):
        client = object()
        self.assertIs(S3Repository(client).client, client)

    def test_no_bucket_configuration_is_required(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(Settings.from_env(), Settings(region="ap-southeast-1"))


if __name__ == "__main__":
    unittest.main()
