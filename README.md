# Conversational recording transcoder

SQS-triggered Lambda (container image). After the browser has uploaded its 5-second WebM chunks, it turns them into the single MP4 that `conversational-ai-lambda-processing` expects and then triggers scoring.

## Flow

For each `{"interview_id": ...}` message on the transcoder queue:

1. Skip if `{interview_id}/transcode_done.json` exists in `AWS_BUCKET_NAME`.
2. If `{interview_id}/{interview_id}.mp4` does not exist yet:
   - List `{interview_id}/recording_chunks/` in `CVI_RECORDING_BUCKET_NAME` and validate every session's `manifest.json` (status, contiguous `seq`, chunk sizes against S3, no stale chunks).
   - Per session, download the chunks in order and byte-concatenate them into one webm, then convert it to H.264/AAC MP4 with ffmpeg (constant frame rate, `+faststart`).
   - With several sessions (camera swap or restart), each is normalized to 1280x720 and joined with the ffmpeg concat demuxer.
   - Check the result with ffprobe (video and audio stream, duration > 0), upload it to `{interview_id}/{interview_id}.mp4` in `AWS_BUCKET_NAME` and confirm the size.
3. Require `{interview_id}/transcript.json` in `AWS_BUCKET_NAME`. If it is missing the message fails and returns to the queue.
4. Send `{"interview_id": ...}` to the scoring FIFO queue (`SCORING_QUEUE_URL`) with `MessageGroupId=messageGroup_{id}` and `MessageDeduplicationId=messageId_{id}`, the same values the web app uses.
5. Write the `transcode_done.json` marker with a conditional put.

Failures are returned as `batchItemFailures`, so SQS retries them and moves them to the dead-letter queue after the redrive limit. Enable `ReportBatchItemFailures` on the event source mapping. Unfinished or inconsistent uploads (`RecordingNotReady`) and a missing transcript (`TranscriptNotReady`) are retried the same way.

## Configuration

| Variable | Purpose |
|---|---|
| `CVI_RECORDING_BUCKET_NAME` | Bucket with the recording chunks and manifests |
| `AWS_BUCKET_NAME` | Bucket with `transcript.json`; the MP4 and marker are written here |
| `SCORING_QUEUE_URL` | FIFO queue that triggers the scoring lambda |
| `SCRATCH_DIR`, `FFMPEG_TIMEOUT_SECONDS`, `DOWNLOAD_CONCURRENCY` | Optional tuning (`/tmp`, 780, 8) |

Lambda needs: `s3:ListBucket` and `s3:GetObject` on the recording bucket; `s3:GetObject` and `s3:PutObject` on the output bucket (`s3:ListBucket` too, so a missing key reads as 404 rather than 403); `sqs:SendMessage` on the scoring queue. Size it with up to 10 GB ephemeral storage, a 15 minute timeout and several GB of memory. Set the transcoder queue's visibility timeout to at least the function timeout and give it a dead-letter queue.

## Structure

```text
src/app/
  config.py                      # Environment configuration
  clients.py                     # Shared boto3 client config
  errors.py                      # Retriable and permanent failure types
  handler.py                     # Lambda entrypoint (SQS event)
  main.py                        # Local startup check; wires the S3 client
  repositories/
    storage_repository.py        # Storage interface
    s3_repository.py             # S3 implementation, injected AWS client
    queue_repository.py          # Queue interface and SQS implementation
  services/
    manifest.py                  # Find and validate recording sessions
    transcoder.py                # Chunk concat, ffmpeg conversion, ffprobe check
    pipeline.py                  # Idempotent end-to-end flow for one interview
```

AWS SDK calls live in the repository layer. Application code depends on the storage interface. Credentials use boto3's default credential chain: local profiles, environment variables, or an IAM role.

## Run locally

`docker compose run` starts the startup check (`app.main`). The image's own entrypoint is the Lambda runtime client, running `app.handler.lambda_handler`.

```bash
cp .env.example .env
docker compose build --builder default
docker compose run --rm conversational-recording-transcoder
```

Compose mounts the host's `~/.aws` directory read-only and uses UID/GID 1000 so local profiles remain readable. Set `LOCAL_UID` and `LOCAL_GID` for a different host user. For SSO profiles, run `aws sso login --profile <profile>` on the host first and set `AWS_PROFILE` in `.env`.

Alternatively, supply `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and optional `AWS_SESSION_TOKEN` in `.env`. Credentials are never copied into the image. For deployment on AWS, use the task's IAM role and omit the local credentials mount.

The local startup check creates the configured S3 client, injects it into `S3Repository`, and prints `status: initialized`. AWS credentials follow the SDK's standard credential chain. It makes no S3 requests and does not verify permissions.

## Verify FFmpeg

```bash
docker compose run --rm --entrypoint ffmpeg conversational-recording-transcoder -version
```

## Tests

```bash
docker compose run --rm --entrypoint python \
  -v "$PWD/tests:/app/tests:ro" conversational-recording-transcoder -m unittest discover -s tests -v
```

Tests verify the startup check makes no S3 requests and that no bucket configuration is needed to load settings.
