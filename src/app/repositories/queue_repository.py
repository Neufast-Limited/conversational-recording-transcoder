import json


class ScoringQueue:
    def __init__(self, client: object, queue_url: str):
        self._client = client
        self._queue_url = queue_url

    def request_scoring(self, interview_id: str) -> None:
        self._client.send_message(
            QueueUrl=self._queue_url,
            MessageBody=json.dumps({"interview_id": interview_id}),
            MessageGroupId=f"messageGroup_{interview_id}",
            MessageDeduplicationId=f"messageId_{interview_id}",
        )
