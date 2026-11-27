# Conversational recording transcoder

An SQS-triggered Lambda that converts browser-recorded WebM chunks to MP4 and requests scoring from `conversational-ai-lambda-processing`.

## Processing

The input message body is `{"interview_id":"<id>"}`. For each interview, the Lambda:

1. Checks for `{id}/transcode_done.json` in the output bucket and skips completed interviews.
2. When a nonempty `{id}/{id}.mp4` is unavailable, validates the session manifests and chunk sizes under `{id}/recording_chunks/` in the recording bucket. FFmpeg encodes H.264 video and AAC audio. It processes multiple sessions in start-time order and joins them at 1280×720. The Lambda checks the output with ffprobe and verifies its size after upload.
3. Waits for `{id}/transcript.json` in the output bucket. If it is missing, SQS can retry the record and reuse the uploaded MP4.
4. Sends `{"interview_id":"<id>"}` to the scoring FIFO queue with group ID `messageGroup_{id}` and deduplication ID `messageId_{id}`. It then writes the completion marker with a conditional S3 put.

Enable `ReportBatchItemFailures` on the Lambda event source mapping and configure a dead-letter queue. Standard batches continue after an item fails. FIFO batches stop at the first failure and return the remaining items for retry. [AWS SQS batch error handling](https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-errorhandling.html)

## Configuration

| Environment variable | Purpose |
| --- | --- |
| `CVI_RECORDING_BUCKET_NAME` | S3 bucket containing the manifests and WebM chunks |
| `AWS_BUCKET_NAME` | S3 bucket containing the transcript, MP4, and completion marker |
| `SCORING_QUEUE_URL` | Scoring FIFO queue URL |
| `AWS_REGION` | AWS region. Falls back to `AWS_DEFAULT_REGION`, then `ap-southeast-1` |
| `SCRATCH_DIR` | Writable working directory, defaults to `/tmp` |
| `FFMPEG_TIMEOUT_SECONDS` | Timeout per FFmpeg or ffprobe command, defaults to 780 seconds |
| `DOWNLOAD_CONCURRENCY` | Chunk download workers per session, defaults to 8 |

The Lambda role needs `s3:ListBucket` and `s3:GetObject` on the recording bucket, `s3:ListBucket`, `s3:GetObject`, and `s3:PutObject` on the output bucket, and `sqs:SendMessage` on the scoring queue. Size Lambda memory, timeout, and ephemeral storage for the largest recordings.

## Local startup and regression tests

```bash
test -f .env || cp .env.example .env
docker compose build --builder default
docker compose run --rm conversational-recording-transcoder
docker compose run --rm --entrypoint python \
  -v "$PWD/tests:/app/tests:ro" conversational-recording-transcoder -m unittest discover -s tests -v
python3 -m unittest discover -s performance-tests -v
```

Compose runs the S3 client startup check using the standard AWS credential chain. For an SSO profile, run `aws sso login --profile <profile>` on the host and set `AWS_PROFILE` in `.env`. Compose mounts the host AWS config read-only. Set `LOCAL_UID` and `LOCAL_GID` if the host credentials are owned by a user other than UID/GID 1000.

The regression suite uses local WebM fixtures, real FFmpeg and ffprobe, and mocked AWS calls. It covers single- and multi-session output, transcript retries, completion markers, and SQS batch handling.

## Image publishing and load testing

`./scripts/push_to_ecr.sh [tag]` builds and publishes a single-platform image to ECR and verifies its manifest. The Lambda image runs `app.handler.lambda_handler`. Use `./scripts/push_to_ecr.sh --help` for configuration.

The [k6 runbook](performance-tests/K6.md) covers offline checks and load tests for an existing Lambda. The [isolated-stack runbook](performance-tests/README.md) covers load tests with a dedicated scoring sink.
