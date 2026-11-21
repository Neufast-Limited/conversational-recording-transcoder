# Transcoder test: 100 concurrent one-hour encodes

**Result: PASS (encoding only).** The existing Lambda `conversational-media-transcoder` was tested with 100 simultaneous one-hour recordings. All 100 succeeded and all 100 MP4s are valid and one hour long.

| | |
|---|---|
| Test window | 2026-11-21, 09:45:21.553 to 09:49:20.237 UTC |
| Run ID | `20261121T094145b39b5c` |
| Method | 100 direct synchronous Lambda invocations (k6, 1 per VU), no SQS, no deployment |
| Evidence | `performance-tests/results/k6-100-final/` |

## Summary

| Check | Result |
|---|---|
| Invocations succeeded | **100 / 100** (0 k6 validation failures) |
| Peak concurrent invocations (Lambda logs) | **100** |
| Time for all 100 to finish | **238.7 s** (first Lambda START to last END) |
| Longest invocation vs 900 s timeout | 238.4 s; headroom 661.6 s |
| Peak memory vs 4,060 MB | 447 MB; headroom 3613 MB |
| Valid output MP4s | **100 / 100**; measured lengths in the table below |
| Cold starts | 100 observed in 100 REPORT records |
| Lambda Errors / Throttles | 0 / 0 (function-level CloudWatch metrics) |
| Completed within ten minutes | **100 / 100**; target PASS |
| Source video duration per task | **3,600.02 s (1 hour and 0.02 seconds)** |

## Processing time (seconds, n = 100)

| Metric | Min | p50 | Avg | p95 | p99 | Max |
|---|---|---|---|---|---|---|
| End-to-end (k6) | 196.9 | 220.4 | 218.2 | 226.2 | 233.8 | 239.5 |
| Lambda duration (REPORT) | 196.1 | 219.5 | 217.2 | 225.2 | 232.8 | 238.4 |
| Cold start (init) | 0.4 | 0.5 | 0.5 | 0.6 | 0.6 | 0.9 |

p50 is the median. Percentiles use linear interpolation. Video duration is recording length; processing times above measure encoding execution. Lambda duration excludes separately reported initialization.

## Memory

| Metric | Min | p50 | Max | Limit |
|---|---|---|---|---|
| Max memory used (MB) | 442 | 445 | 447 | 4,060 |

## Overlap

- The observed peak was **100 test invocations**, attributed to this run's interview IDs; unrelated traffic was excluded.
- Test invocations started across a 0.532 s window.
- All 100 overlapped for approximately 195.6 s.
- 100 attributed invocations; 100/100 interviews have exactly one observed attempt.
- Attribution uses the run-specific message ID in each handler error and its active START RequestId in the same stream. Function-level CloudWatch independently reported 100 concurrent executions.

## Output videos

`interview_id` is the real UAT source interview used to build the fixture. Each test S3 key identifies a separate synthetic interview, with no UAT DB record. The input duration is **3,600.02 s per task**, or **100 hours and 2 seconds of source media** across the run.

| interview_id (UAT source) | Test S3 key | Video length | MP4 size | Processing time |
|---|---|---|---|---|
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_001` | 3600.02 s | 82.6 MB | 224.5 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_002` | 3600.02 s | 82.6 MB | 222.7 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_003` | 3600.02 s | 82.6 MB | 221.1 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_004` | 3600.02 s | 82.6 MB | 199.4 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_005` | 3600.02 s | 82.6 MB | 223.6 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_006` | 3600.02 s | 82.6 MB | 220.2 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_007` | 3600.02 s | 82.6 MB | 216.3 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_008` | 3600.02 s | 82.6 MB | 218.6 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_009` | 3600.02 s | 82.6 MB | 222.1 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_010` | 3600.02 s | 82.6 MB | 218.3 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_011` | 3600.02 s | 82.6 MB | 198.8 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_012` | 3600.02 s | 82.6 MB | 220.1 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_013` | 3600.02 s | 82.6 MB | 239.5 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_014` | 3600.02 s | 82.6 MB | 217.9 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_015` | 3600.02 s | 82.6 MB | 221.5 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_016` | 3600.02 s | 82.6 MB | 224.9 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_017` | 3600.02 s | 82.6 MB | 198.0 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_018` | 3600.02 s | 82.6 MB | 218.8 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_019` | 3600.02 s | 82.6 MB | 220.3 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_020` | 3600.02 s | 82.6 MB | 198.7 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_021` | 3600.02 s | 82.6 MB | 219.4 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_022` | 3600.02 s | 82.6 MB | 221.0 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_023` | 3600.02 s | 82.6 MB | 225.9 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_024` | 3600.02 s | 82.6 MB | 225.8 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_025` | 3600.02 s | 82.6 MB | 220.3 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_026` | 3600.02 s | 82.6 MB | 224.9 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_027` | 3600.02 s | 82.6 MB | 197.7 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_028` | 3600.02 s | 82.6 MB | 223.4 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_029` | 3600.02 s | 82.6 MB | 219.6 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_030` | 3600.02 s | 82.6 MB | 223.0 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_031` | 3600.02 s | 82.6 MB | 221.9 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_032` | 3600.02 s | 82.6 MB | 200.4 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_033` | 3600.02 s | 82.6 MB | 199.3 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_034` | 3600.02 s | 82.6 MB | 221.8 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_035` | 3600.02 s | 82.6 MB | 233.8 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_036` | 3600.02 s | 82.6 MB | 220.1 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_037` | 3600.02 s | 82.6 MB | 223.3 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_038` | 3600.02 s | 82.6 MB | 217.3 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_039` | 3600.02 s | 82.6 MB | 220.5 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_040` | 3600.02 s | 82.6 MB | 217.7 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_041` | 3600.02 s | 82.6 MB | 199.6 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_042` | 3600.02 s | 82.6 MB | 220.3 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_043` | 3600.02 s | 82.6 MB | 221.5 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_044` | 3600.02 s | 82.6 MB | 221.5 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_045` | 3600.02 s | 82.6 MB | 199.4 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_046` | 3600.02 s | 82.6 MB | 223.6 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_047` | 3600.02 s | 82.6 MB | 201.2 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_048` | 3600.02 s | 82.6 MB | 224.6 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_049` | 3600.02 s | 82.6 MB | 217.9 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_050` | 3600.02 s | 82.6 MB | 222.6 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_051` | 3600.02 s | 82.6 MB | 218.8 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_052` | 3600.02 s | 82.6 MB | 222.0 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_053` | 3600.02 s | 82.6 MB | 221.6 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_054` | 3600.02 s | 82.6 MB | 221.1 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_055` | 3600.02 s | 82.6 MB | 219.2 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_056` | 3600.02 s | 82.6 MB | 225.4 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_057` | 3600.02 s | 82.6 MB | 220.0 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_058` | 3600.02 s | 82.6 MB | 199.1 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_059` | 3600.02 s | 82.6 MB | 198.8 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_060` | 3600.02 s | 82.6 MB | 218.9 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_061` | 3600.02 s | 82.6 MB | 221.3 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_062` | 3600.02 s | 82.6 MB | 198.8 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_063` | 3600.02 s | 82.6 MB | 223.6 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_064` | 3600.02 s | 82.6 MB | 219.5 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_065` | 3600.02 s | 82.6 MB | 215.0 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_066` | 3600.02 s | 82.6 MB | 219.7 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_067` | 3600.02 s | 82.6 MB | 199.7 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_068` | 3600.02 s | 82.6 MB | 223.2 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_069` | 3600.02 s | 82.6 MB | 226.0 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_070` | 3600.02 s | 82.6 MB | 220.3 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_071` | 3600.02 s | 82.6 MB | 198.9 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_072` | 3600.02 s | 82.6 MB | 225.2 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_073` | 3600.02 s | 82.6 MB | 219.9 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_074` | 3600.02 s | 82.6 MB | 218.8 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_075` | 3600.02 s | 82.6 MB | 223.1 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_076` | 3600.02 s | 82.6 MB | 219.3 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_077` | 3600.02 s | 82.6 MB | 196.9 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_078` | 3600.02 s | 82.6 MB | 218.3 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_079` | 3600.02 s | 82.6 MB | 222.8 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_080` | 3600.02 s | 82.6 MB | 220.9 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_081` | 3600.02 s | 82.6 MB | 226.2 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_082` | 3600.02 s | 82.6 MB | 224.3 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_083` | 3600.02 s | 82.6 MB | 221.1 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_084` | 3600.02 s | 82.6 MB | 220.8 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_085` | 3600.02 s | 82.6 MB | 220.9 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_086` | 3600.02 s | 82.6 MB | 226.4 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_087` | 3600.02 s | 82.6 MB | 222.3 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_088` | 3600.02 s | 82.6 MB | 222.6 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_089` | 3600.02 s | 82.6 MB | 220.0 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_090` | 3600.02 s | 82.6 MB | 218.3 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_091` | 3600.02 s | 82.6 MB | 219.0 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_092` | 3600.02 s | 82.6 MB | 218.7 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_093` | 3600.02 s | 82.6 MB | 217.2 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_094` | 3600.02 s | 82.6 MB | 230.9 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_095` | 3600.02 s | 82.6 MB | 220.3 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_096` | 3600.02 s | 82.6 MB | 221.4 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_097` | 3600.02 s | 82.6 MB | 227.8 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_098` | 3600.02 s | 82.6 MB | 222.0 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_099` | 3600.02 s | 82.6 MB | 223.0 s |
| `interview_50ea8878-e4be-11f1-8c09-0242ac1b000a` | `interview_perftc_20261121T094145b39b5c_100` | 3600.02 s | 82.6 MB | 223.3 s |

Expected length is 3,600 ± 2 s. All 100 outputs have H.264 640×360 video and AAC audio.
74 outputs passed remote ffprobe. Remote probes timed out for 26; those were verified using signed S3 range reads of the first 8 MiB, a complete faststart `moov` metadata box, and local ffprobe. These are metadata/stream checks, not full-file decoding or perceptual synchronization checks. MP4 sizes use decimal MB.

## Configuration (unchanged)

| Item | Value |
|---|---|
| Function / region | `conversational-media-transcoder` / ap-southeast-1 |
| Image | x86_64 container, `sha256:364f075574b61e1e12043cc32c63f12c8d63591388d5b31e2871648aa9400d88` |
| Memory / scratch / timeout | 4,060 MB / 10,000 MB / 900 s |
| FFmpeg timeout | 780 s per command (repository default; no deployment override) |
| Reserved concurrency | none; account limit 1,000 |
| Input per interview | 3,600.02 s, 117.4 MB, VP8 640×360 + Opus, 720 chunks |

## Scope and limits

- **Encoding only.** Transcripts were deliberately absent. After uploading each successful MP4 the handler reported `TranscriptNotReady`, preventing scoring and done-marker creation. This is not a full processing-pipeline test.
- Direct invocations bypass SQS. The existing trigger remains capped at 20; this test does not establish 100-way queue processing or change that limit.
- The workload is a looped low-bitrate 360p recording and one run. It does not establish capacity for 720p/1080p, higher bitrates or multi-session recordings.
- Validation covers streams/duration, not full decode or visual quality. Ephemeral storage consumption and other account traffic were not measured.

## Notes

- Raw evidence files are generated locally and excluded from Git. Artifact paths refer to the test workspace.

- k6 exit code: `0`. Source configuration, image, queues, IAM and database were unchanged.
- The previous 20-way run observed a 232.0 s maximum Lambda duration and 232.95 s maximum k6 duration; this run's corresponding maxima are 238.4 s and 239.5 s.
- Test inputs/outputs remain under `interview_perftc_20261121T094145b39b5c_*` in `voicebot-testing`. Remove only this run's prefixes when results are no longer required.
- The first automatic log pass could not identify interviews because CloudWatch split the tracebacks and omitted the interview-ID line. Attribution was corrected using the explicit run-specific message IDs. No encoding jobs were repeated.
- Raw artifacts: [k6 summary](k6-100-final/summary.json), [run state](k6-100-final/state.json), [validation and concurrency evidence](k6-100-final/evidence.json), [Lambda system events](k6-100-final/lambda-system-events.json), [message attribution](k6-100-final/lambda-attribution-events.json), [CloudWatch metrics](k6-100-cloudwatch.json), [console output](k6-100-final.log), [configuration before](k6-100-config.json) / [after](k6-100-config-after.json), [run timing/exit code](k6-100-run-meta.json).
