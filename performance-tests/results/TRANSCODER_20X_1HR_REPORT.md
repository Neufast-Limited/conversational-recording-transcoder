# Transcoder test: 20 concurrent one-hour encodes

**Result: PASS (encoding only).** The existing Lambda `conversational-media-transcoder` encoded 20 one-hour recordings at the same time. All 20 succeeded and all 20 MP4s are valid and one hour long.

| | |
|---|---|
| Test window | 2026-11-21, 07:17:44 to 07:21:38 UTC |
| Run ID | `20261121T071417782958` |
| Method | 20 direct synchronous Lambda invocations (k6, 1 per VU), no SQS, no deployment |
| Evidence | `performance-tests/results/k6-20-final2/` |

## Summary

| Check | Result |
|---|---|
| Invocations succeeded | **20 / 20** (0 failed) |
| Peak concurrent invocations (Lambda logs) | **20** |
| Time for all 20 to finish | **232 s** |
| Longest invocation vs 900 s timeout | 232 s, headroom 668 s (74%) |
| Peak memory vs 4,060 MB | 443 MB, headroom 3,617 MB (89%) |
| Valid output MP4s | **20 / 20**, each 3,600.02 s |
| Cold starts | 20 (one per invocation) |

## Processing time (seconds, n = 20)

| Metric | Min | p50 | Avg | p95 | p99 | Max |
|---|---|---|---|---|---|---|
| End-to-end (k6) | 197.5 | 222.7 | 220.4 | 230.9 | 232.5 | 233.0 |
| Lambda duration (REPORT) | 196.2 | 221.6 | 219.4 | 229.6 | 231.5 | 232.0 |
| Cold start (init) | 0.4 | 0.5 | 0.5 | 0.6 | 0.7 | 0.7 |

p50 is the median. With 20 samples, p95 and p99 are interpolated and sit close to the max.

## Memory

| Metric | Min | p50 | Max | Limit |
|---|---|---|---|---|
| Max memory used (MB) | 440 | 442 | 443 | 4,060 |

## Overlap

- All 20 invocations started within 0.41 s of each other.
- The first one finished 196.6 s after the first start. The last one started 0.4 s after the first, so all 20 ran simultaneously for about 196 s.
- Lambda logs, attributed by interview ID, show one attempt per interview and no retries.

## Output videos

`interview_id` is the real UAT source interview the test media was built from (the same for all 20). The test S3 key is the synthetic ID that identifies each output. Synthetic keys have no UAT DB records.

| interview_id (UAT source) | Test S3 key | Video length | MP4 size | Processing time |
|---|---|---|---|---|
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T071417782958_001` | 3600.02 s | 82.6 MB | 221.1 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T071417782958_002` | 3600.02 s | 82.6 MB | 215.4 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T071417782958_003` | 3600.02 s | 82.6 MB | 219.1 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T071417782958_004` | 3600.02 s | 82.6 MB | 224.5 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T071417782958_005` | 3600.02 s | 82.6 MB | 223.1 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T071417782958_006` | 3600.02 s | 82.6 MB | 228.1 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T071417782958_007` | 3600.02 s | 82.6 MB | 224.7 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T071417782958_008` | 3600.02 s | 82.6 MB | 222.2 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T071417782958_009` | 3600.02 s | 82.6 MB | 216.3 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T071417782958_010` | 3600.02 s | 82.6 MB | 233.0 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T071417782958_011` | 3600.02 s | 82.6 MB | 223.2 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T071417782958_012` | 3600.02 s | 82.6 MB | 230.8 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T071417782958_013` | 3600.02 s | 82.6 MB | 197.5 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T071417782958_014` | 3600.02 s | 82.6 MB | 206.1 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T071417782958_015` | 3600.02 s | 82.6 MB | 228.4 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T071417782958_016` | 3600.02 s | 82.6 MB | 217.0 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T071417782958_017` | 3600.02 s | 82.6 MB | 221.1 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T071417782958_018` | 3600.02 s | 82.6 MB | 230.4 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T071417782958_019` | 3600.02 s | 82.6 MB | 198.2 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T071417782958_020` | 3600.02 s | 82.6 MB | 227.9 s |

Expected length is 3,600 ± 2 s. All 20 have H.264 640×360 video and AAC audio. Four (`_003`, `_006`, `_007`, `_009`) were verified by a local ffprobe after the remote probe timed out. The other 16 passed the harness's remote ffprobe (stream presence and duration).

## Configuration (unchanged)

| Item | Value |
|---|---|
| Function / region | `conversational-media-transcoder` / ap-southeast-1 |
| Image | x86_64 container, `sha256:364f0755…aa9400d88` |
| Memory / scratch / timeout | 4,060 MB / 10,000 MB / 900 s |
| FFmpeg timeout (repo default) | 780 s per command |
| Reserved concurrency | none; account limit 1,000 |
| Input per interview | 3,600.02 s, 117.4 MB, VP8 640×360 + Opus, 720 chunks |

## Scope and limits

- **Encoding only.** There were no transcripts, so after encoding each handler reported `TranscriptNotReady`, as designed. No scoring message and no done marker were produced. This is not a full pipeline test.
- Direct invocations bypass SQS, so this does not test queue scheduling or the 20-concurrency trigger limit.
- The workload is low-bitrate 360p, one run. It does not prove capacity for 720p/1080p or higher bitrates.
- Validation covers streams and duration, not a full decode or visual quality. Ephemeral storage use and other account traffic were not measured.

## Notes

- Raw evidence files are generated locally and excluded from Git. Artifact paths refer to the test workspace.

- A first attempt failed: the Lambda role can only read `interview_*/*`, so all 20 calls returned `AccessDenied` in about 0.5 s and nothing was encoded. That run is invalid (`k6-20-final/`). IAM was not changed. Inputs were restaged as `interview_perftc_*`.
- Repo edits: `transcoder_perf.py`, `transcoder-direct.k6.js` and `K6.md` now use the `interview_perftc_` prefix.
- Test objects remain in `voicebot-testing`: `interview_perftc_20261121T071417782958_*` (inputs, MP4s, fixture) and the unused `perf_tc_20261121T061619bbd771_*`. Delete only those prefixes when done.
