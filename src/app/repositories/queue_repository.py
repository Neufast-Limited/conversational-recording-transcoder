from abc import ABC, abstractmethod


class QueueRepository(ABC):
    @abstractmethod
    def send_message(self, queue_url: str, body: str, group_id: str, dedup_id: str) -> None:
        """Send a message to a FIFO queue."""


class SqsRepository(QueueRepository):
    def __init__(self, client: object):
        self.sqs = client

    def send_message(self, queue_url: str, body: str, group_id: str, dedup_id: str) -> None:
        self.sqs.send_message(
            QueueUrl=queue_url,
            MessageBody=body,
            MessageGroupId=group_id,
            MessageDeduplicationId=dedup_id,
        )
