# Twenty concurrent one-hour transcodes

For the **Grafana k6 test against the existing Lambda, with no deployment**, see
[K6.md](K6.md). The isolated SQS stack below is an alternative, not a prerequisite
for that direct encoding-capacity test.

| Video duration | Value |
|---|---|
| Source video per interview | **1 hour and 0.02 seconds (3,600.02 seconds)** |
| Number of test interviews | 20 copies under distinct interview IDs |
| Total source media across the test | 20 hours and 0.4 seconds (72,000.4 seconds) |

The video duration above is separate from the measured time to transcode it.
Include both the source duration and each output MP4's measured duration in final
result Markdown reports, alongside each task's processing time.

This tests the deployed transcoder container through SQS and Lambda, using twenty
distinct interview IDs. Browser sessions and backend database records are not
required. The transcoder reads chunk manifests and media from S3, writes an MP4,
checks for a transcript, and sends an SQS message.

Use the isolated stack below: it runs the deployed image digest with the same
memory, timeout, architecture and temporary storage. It has its own input queue,
dead-letter queue, execution role, log group and **unconsumed scoring queue**.
Its object reads/writes are restricted to `voicebot-testing/perf_tc_*`; it can list
the bucket so missing output HEAD requests return 404. It has no access to the
real scoring queue. No database records or existing interview objects are changed.

## Prepared on 2026-11-21

- Region: `ap-southeast-1`; source function: `conversational-media-transcoder`.
- Deployed digest: `sha256:364f075574b61e1e12043cc32c63f12c8d63591388d5b31e2871648aa9400d88`.
- Source resources: 4,060 MB memory, 10,000 MB scratch, 900 second timeout.
- Existing input trigger: enabled, batch size 1, maximum concurrency 20.
- Regional unreserved concurrency allocation: 587 of a 1,000 total limit at audit time.
  This is an allocation, not a guarantee that 587 slots are currently idle.
- Existing queue was empty, but has no DLQ; its visibility timeout is only 900s.
- Existing trigger has `FunctionResponseTypes: []`, despite the repository handler
  returning `batchItemFailures`. Enable `ReportBatchItemFailures` when using that
  handler or failures can be acknowledged as success. The generated stack enables it.
- AWS recommends visibility at least 6× the Lambda timeout. The test stack uses
  5,400 seconds and a DLQ after two failed deliveries. Retries therefore take much
  longer than the initial 15-minute attempt; do not interpret an empty DLQ early
  in the run as proof of success.
- Bucket inventory: 12,798 objects; one browser chunk manifest, with 40 chunks,
  6,552,096 input bytes and approximately 201 seconds. No one-hour chunk recording
  was present. Existing MP4s alone are not sufficient inputs for this test.
- Source ID: `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a`.
- No S3 bucket notifications were configured; bucket uses SSE-S3 encryption.
- The backend database is not on the transcoder execution path and was not queried.

Local prepared files (ignored by Git):

| Path | Contents |
|---|---|
| `results/plan/deployment-snapshot.json` | Read-only AWS deployment snapshot |
| `results/plan/stack.json` | Isolated CloudFormation infrastructure |
| `results/fixture/fixture.json` | Fixture metadata and chunk sizes |
| `results/fixture/one-hour.webm` | Continuous 3,600.02 second video, 117,422,480 bytes |
| `results/fixture/chunks/` | 720 byte-contiguous chunks |

Preparation checks passed: full one-hour FFmpeg audio/video decode, exact SHA-256
reconstruction from all 720 parts, production manifest validation, eight harness
tests, three existing repository tests, and local `cfn-lint` template validation.
Fixture SHA-256: `9beccd6c94b20f582912cca1cdde5fead450bb5dea68c0112e3f2f284fea7bd0`.
AWS-side template validation was denied by IAM; actual stack deployment, S3 staging
and Lambda performance runs remain unexecuted.

The fixture loops actual VP8/Opus media without re-encoding: 640×360 video,
48 kHz stereo audio, approximately 261 kbit/s overall. All 720 chunks together
reproduce the continuous WebM. Splits are equal-byte parts with nominal five-second
metadata, not actual browser MediaRecorder boundaries. This is suitable for the
transcoder, which byte-concatenates parts before decoding. It does not test the
browser uploader. The fixture contains real interview media; keep it in the test
bucket/local ignored directory.

A pass proves capacity for **this resolution, bitrate, motion and single-session
input**. Repeat with representative 720p/1080p media and camera-restart/multiple-session
recordings before claiming capacity for those workloads.

## Run

Prerequisites: AWS CLI, Python, `uv`, FFmpeg/ffprobe, and AWS credentials with S3,
Lambda/SQS/CloudWatch read access, test-prefix S3 writes, test queue sends, and
permission to deploy the CloudFormation stack and its IAM role. The current user
was denied `cloudformation:ValidateTemplate`; use a deployment identity with the
required permissions. No infrastructure has been deployed by this preparation.

Run all commands from `conversational-recording-transcoder/`.

1. Regenerate the plan if the deployed image or resource settings have changed:

   ```bash
   uv run --with boto3 python performance-tests/transcoder_perf.py plan
   ```

   To regenerate the fixture on another machine, use a fresh output directory:

   ```bash
   uv run --with boto3 python performance-tests/transcoder_perf.py fixture \
     --source-id interview_50ea8878-e4be-11f1-8c09-0242ac1b000a
   ```

2. Deploy the isolated infrastructure (creates billable AWS resources):

   ```bash
   aws cloudformation deploy \
     --template-file performance-tests/results/plan/stack.json \
     --stack-name transcoder-perf-20 \
     --capabilities CAPABILITY_IAM \
     --region ap-southeast-1
   ```

3. Run a single one-hour smoke test first. Staging writes only synthetic test
   prefixes and creates a dummy transcript that satisfies the transcoder's
   existence check. The dummy transcript is intentionally sent only to the sink.

   ```bash
   uv run --with boto3 python performance-tests/transcoder_perf.py stage \
     --count 1 --state performance-tests/results/smoke.json
   uv run --with boto3 python performance-tests/transcoder_perf.py run \
     --state performance-tests/results/smoke.json
   ```

   After processing completes, inspect its evidence:

   ```bash
   uv run --with boto3 python performance-tests/transcoder_perf.py report \
     --state performance-tests/results/smoke.json --verify \
     --output performance-tests/results/smoke-report.json
   ```

   Logs/metrics can arrive late; repeat the report command if necessary. Do not
   proceed if the one-hour smoke test fails or approaches the 900s timeout.

4. Stage twenty **new** interview IDs, then submit all twenty in parallel:

   ```bash
   uv run --with boto3 python performance-tests/transcoder_perf.py stage \
     --count 20 --state performance-tests/results/run20.json
   uv run --with boto3 python performance-tests/transcoder_perf.py run \
     --state performance-tests/results/run20.json
   ```

   Stage uploads the fixture once, then makes S3-side copies for twenty inputs:
   approximately 14,400 interview chunks plus the 720-chunk fixture, around 2.47 GB
   of input objects. It does not enqueue anything until `run`. Each message has a
   unique FIFO group ID and deduplication ID. Existing output files and markers
   are rejected before submission so the test cannot pass through idempotent skips.

5. Collect and verify every output after the initial attempt finishes:

   ```bash
   uv run --with boto3 python performance-tests/transcoder_perf.py report \
     --state performance-tests/results/run20.json --verify \
     --output performance-tests/results/report20.json
   ```

   The report includes per-interview completion time, MP4 size/duration/codecs,
   Lambda duration p95/max and memory usage from REPORT lines, invocation intervals,
   observed concurrency, queue/DLQ state, and CloudWatch Errors/Throttles/Duration.
   Verification uses ffprobe against signed S3 URLs, which are not stored in reports.
   It checks duration and stream presence, not perceptual lip sync or full output decoding.

## Acceptance

`PASS` requires all outputs and done markers, `--verify` confirming audio/video
and duration within two seconds of 3,600s, the requested number of overlapping
Lambda executions, no additional invocation attempts, and an empty DLQ. A report
without enough evidence says `NOT_PROVEN`; twenty eventual completions alone
cannot establish twenty-way concurrency. An early report may change as logs arrive.
Lambda Errors can remain zero for exceptions caught by the SQS handler, so inspect
output completeness and invocation evidence as well.

The repository FFmpeg timeout defaults to 780s per command. A single one-hour
session needs roughly 4.62× encoding speed to fit that command budget, plus the
download/upload work must fit the Lambda's total 900s. The generated plan carries
over explicit tuning environment variables from the source function, if set.
Each invocation has its own memory and scratch space; this is twenty Lambda
execution environments, not twenty encoders sharing 4,060 MB.

If peak concurrency is below twenty, report capacity as unproven and inspect FIFO
scaling and regional throttling before changing the workload. If jobs time out,
increase CPU allocation by testing a higher Lambda memory setting, adjust the
FFmpeg workload, or consider a longer-running compute service. Re-run with fresh
IDs after each resource change; never reuse done markers.

## Cleanup

After recording results and confirming no test invocation is active, delete the
test stack with the same deployment identity:

```bash
aws cloudformation delete-stack --stack-name transcoder-perf-20 --region ap-southeast-1
aws cloudformation wait stack-delete-complete --stack-name transcoder-perf-20 --region ap-southeast-1
```

Stack deletion removes its queues, function, role and log group. Test objects in
the existing bucket remain. Each state file records `run_id`; only remove keys
starting with the exact `perf_tc_<run_id>_` prefix for that run. Do not delete the
original source interview or purge shared queues. Keep reports before deleting
logs. Interrupted staging can leave partial test prefixes; preserve its state
and use a new state filename/run ID for a new attempt.

## Local checks

```bash
python3 -m unittest discover -s performance-tests -v
uv run --with cfn-lint cfn-lint performance-tests/results/plan/stack.json
```

References: [SQS/Lambda queue configuration](https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-configure.html),
[partial batch failure handling](https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-errorhandling.html),
[FIFO concurrency](https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-scaling.html).
