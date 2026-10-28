# Conversational recording transcoder baseline

Minimal Python starter: FFmpeg is installed in Docker and an AWS S3 client is initialized through the repository layer. Startup performs no S3 operations and exits after initialization.

## Structure

```text
src/conversational_recording_transcoder/
  config.py                      # Environment configuration
  main.py                        # Entrypoint; wires dependencies
  repositories/
    storage_repository.py        # Storage interface
    s3_repository.py             # S3 implementation, injected AWS client
```

AWS SDK calls live in the repository layer. Application code depends on the storage interface. Credentials use boto3's default credential chain: local profiles, environment variables, or an IAM role.

## Run

```bash
cp .env.example .env
docker compose build --builder default
docker compose run --rm conversational-recording-transcoder
```

Compose mounts the host's `~/.aws` directory read-only and uses UID/GID 1000 so local profiles remain readable. Set `LOCAL_UID` and `LOCAL_GID` for a different host user. For SSO profiles, run `aws sso login --profile <profile>` on the host first and set `AWS_PROFILE` in `.env`.

Alternatively, supply `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and optional `AWS_SESSION_TOKEN` in `.env`. Credentials are never copied into the image. For deployment on AWS, use the task's IAM role and omit the local credentials mount.

Startup creates the configured S3 client, injects it into `S3Repository`, and prints `status: initialized`. AWS credentials follow the SDK's standard credential chain. No bucket is required and no bucket access check, listing, upload, download, or transcoding runs. Client initialization does not verify AWS permissions; those will be checked when future operations are implemented.

## Verify FFmpeg

```bash
docker compose run --rm --entrypoint ffmpeg conversational-recording-transcoder -version
```

## Tests

```bash
docker compose run --rm --entrypoint python \
  -v "$PWD/tests:/app/tests:ro" conversational-recording-transcoder -m unittest discover -s tests -v
```

Tests verify startup makes no S3 requests and requires no bucket configuration.
