import json

from botocore.exceptions import ClientError

from .storage_repository import StorageRepository

MISSING_CODES = {"404", "NoSuchKey", "NotFound"}
EXISTS_CODES = {"PreconditionFailed", "ConditionalRequestConflict"}


class S3Repository(StorageRepository):
    def __init__(self, client: object):
        self._client = client

    @property
    def client(self) -> object:
        return self._client

    def list_objects(self, bucket: str, prefix: str) -> dict[str, int]:
        paginator = self._client.get_paginator("list_objects_v2")
        objects: dict[str, int] = {}
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for item in page.get("Contents", []):
                objects[item["Key"]] = item["Size"]
        return objects

    def head(self, bucket: str, key: str) -> int | None:
        try:
            response = self._client.head_object(Bucket=bucket, Key=key)
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") in MISSING_CODES:
                return None
            raise
        return response["ContentLength"]

    def read_json(self, bucket: str, key: str) -> dict:
        response = self._client.get_object(Bucket=bucket, Key=key)
        return json.loads(response["Body"].read())

    def download_file(self, bucket: str, key: str, path: str) -> None:
        self._client.download_file(bucket, key, path)

    def upload_file(self, bucket: str, key: str, path: str, content_type: str) -> None:
        self._client.upload_file(path, bucket, key, ExtraArgs={"ContentType": content_type})

    def put_json_if_absent(self, bucket: str, key: str, payload: dict) -> bool:
        try:
            self._client.put_object(
                Bucket=bucket,
                Key=key,
                Body=json.dumps(payload).encode("utf-8"),
                ContentType="application/json",
                IfNoneMatch="*",
            )
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") in EXISTS_CODES:
                return False
            raise
        return True
