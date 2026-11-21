#!/usr/bin/env python3
"""Prepare and measure an isolated SQS -> Lambda transcoder capacity test.

AWS writes happen only in stage/run. plan and fixture do not change AWS.
Deploy the generated CloudFormation template separately before stage/run.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, default=str) + "\n")


def read(path):
    return json.loads(Path(path).read_text())


def client(service, region):
    import boto3
    from botocore.config import Config
    return boto3.client(service, region_name=region,
                        config=Config(max_pool_connections=128, retries={"mode": "standard", "max_attempts": 5}))


def probe(path, timeout=120):
    result = subprocess.run(["ffprobe", "-v", "error", "-show_format", "-show_streams",
                             "-of", "json", str(path)], capture_output=True, text=True, check=True, timeout=timeout)
    return json.loads(result.stdout)


def validate_probe(info, expected, tolerance=2):
    duration = float(info["format"]["duration"])
    streams = {s["codec_type"] for s in info["streams"]}
    if not {"video", "audio"} <= streams or abs(duration - expected) > tolerance:
        raise ValueError(f"Expected audio/video and {expected}s ±{tolerance}s; got {duration}s, {streams}")
    return duration


def plan(args):
    lam = client("lambda", args.region)
    source = lam.get_function(FunctionName=args.source_function)
    cfg = source["Configuration"]
    if cfg.get("VpcConfig", {}).get("SubnetIds"):
        raise ValueError("Source uses a VPC; review networking before generating a comparable test")
    mappings = lam.list_event_source_mappings(FunctionName=args.source_function)["EventSourceMappings"]
    env = cfg.get("Environment", {}).get("Variables", {})
    image = source["Code"]["ResolvedImageUri"]
    snapshot = {"function": args.source_function, "region": args.region, "image": image,
                "memory_mb": cfg["MemorySize"], "timeout": cfg["Timeout"],
                "scratch_mb": cfg["EphemeralStorage"]["Size"], "architectures": cfg["Architectures"],
                "recording_bucket": env.get("CVI_RECORDING_BUCKET_NAME"),
                "output_bucket": env.get("AWS_BUCKET_NAME"), "mappings": mappings,
                "account": lam.get_account_settings()["AccountLimit"], "queues": []}
    for mapping in mappings:
        arn = mapping["EventSourceArn"].split(":")
        if arn[2] == "sqs":
            sqs = client("sqs", args.region)
            url = sqs.get_queue_url(QueueName=arn[-1], QueueOwnerAWSAccountId=arn[4])["QueueUrl"]
            snapshot["queues"].append(sqs.get_queue_attributes(QueueUrl=url, AttributeNames=["All"])["Attributes"])
    save(args.output / "deployment-snapshot.json", snapshot)
    ref = lambda name: {"Ref": name}
    att = lambda name, field: {"Fn::GetAtt": [name, field]}
    sub = lambda value: {"Fn::Sub": value}
    fifo = {"FifoQueue": True, "MessageRetentionPeriod": 345600, "SqsManagedSseEnabled": True}
    resources = {
        "DeadLetters": {"Type": "AWS::SQS::Queue", "Properties": {
            **fifo, "QueueName": sub("${AWS::StackName}-dlq.fifo")}},
        "ScoringSink": {"Type": "AWS::SQS::Queue", "Properties": {
            **fifo, "QueueName": sub("${AWS::StackName}-scoring-sink.fifo")}},
        "InputQueue": {"Type": "AWS::SQS::Queue", "Properties": {
            **fifo, "QueueName": sub("${AWS::StackName}-input.fifo"), "VisibilityTimeout": cfg["Timeout"] * 6,
            "RedrivePolicy": {"deadLetterTargetArn": att("DeadLetters", "Arn"), "maxReceiveCount": 2}}},
        "ExecutionRole": {"Type": "AWS::IAM::Role", "Properties": {
            "AssumeRolePolicyDocument": {"Version": "2012-10-17", "Statement": [{
                "Effect": "Allow", "Principal": {"Service": "lambda.amazonaws.com"}, "Action": "sts:AssumeRole"}]},
            "Policies": [{"PolicyName": "transcoder-performance-only", "PolicyDocument": {
                "Version": "2012-10-17", "Statement": [
                    {"Effect": "Allow", "Action": ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"],
                     "Resource": att("InputQueue", "Arn")},
                    {"Effect": "Allow", "Action": "sqs:SendMessage", "Resource": att("ScoringSink", "Arn")},
                    # HEAD of missing outputs needs ListBucket to return 404 instead of 403.
                    {"Effect": "Allow", "Action": "s3:ListBucket", "Resource": f"arn:aws:s3:::{args.bucket}"},
                    {"Effect": "Allow", "Action": ["s3:GetObject", "s3:PutObject"],
                     "Resource": f"arn:aws:s3:::{args.bucket}/perf_tc_*"},
                    {"Effect": "Allow", "Action": ["logs:CreateLogStream", "logs:PutLogEvents"],
                     "Resource": sub("arn:${AWS::Partition}:logs:${AWS::Region}:${AWS::AccountId}:log-group:/aws/lambda/${AWS::StackName}:*")}
                ]}}]}},
        "Logs": {"Type": "AWS::Logs::LogGroup", "Properties": {
            "LogGroupName": sub("/aws/lambda/${AWS::StackName}"), "RetentionInDays": 14}},
        "Function": {"Type": "AWS::Lambda::Function", "DependsOn": "Logs", "Properties": {
            "FunctionName": ref("AWS::StackName"), "PackageType": "Image", "Code": {"ImageUri": image},
            "Architectures": cfg["Architectures"], "Role": att("ExecutionRole", "Arn"),
            "MemorySize": cfg["MemorySize"], "Timeout": cfg["Timeout"],
            "EphemeralStorage": cfg["EphemeralStorage"], "ReservedConcurrentExecutions": 20,
            "Environment": {"Variables": {**{k: v for k, v in env.items() if k in (
                "FFMPEG_TIMEOUT_SECONDS", "DOWNLOAD_CONCURRENCY", "SCRATCH_DIR")},
                "AWS_BUCKET_NAME": args.bucket, "CVI_RECORDING_BUCKET_NAME": args.bucket,
                "SCORING_QUEUE_URL": ref("ScoringSink")}}}},
        "Trigger": {"Type": "AWS::Lambda::EventSourceMapping", "Properties": {
            "FunctionName": ref("Function"), "EventSourceArn": att("InputQueue", "Arn"),
            "BatchSize": 1, "Enabled": True, "FunctionResponseTypes": ["ReportBatchItemFailures"],
            "ScalingConfig": {"MaximumConcurrency": 20}}},
    }
    image_config = cfg.get("ImageConfigResponse", {}).get("ImageConfig")
    if image_config:
        resources["Function"]["Properties"]["ImageConfig"] = image_config
    template = {"AWSTemplateFormatVersion": "2010-09-09", "Description": "Isolated 20-way transcoder performance test",
                "Resources": resources, "Outputs": {
                    "FunctionName": {"Value": ref("Function")}, "QueueUrl": {"Value": ref("InputQueue")},
                    "TriggerUUID": {"Value": ref("Trigger")},
                    "ScoringSinkUrl": {"Value": ref("ScoringSink")}, "DeadLetterUrl": {"Value": ref("DeadLetters")}}}
    save(args.output / "stack.json", template)
    print(json.dumps({"snapshot": str(args.output / "deployment-snapshot.json"),
                      "template": str(args.output / "stack.json"), "image": image}, indent=2))


def fixture(args):
    from app.repositories.s3_repository import S3Repository
    from app.services.manifest import find_sessions
    from app.services.transcoder import merge_chunks
    args.output.mkdir(parents=True, exist_ok=True)
    metadata_path = args.output / "fixture.json"
    if metadata_path.exists():
        raise ValueError("Fixture already exists; choose a new output directory")
    storage = S3Repository(client("s3", args.region))
    sessions = find_sessions(storage, args.bucket, args.source_id)
    if len(sessions) != 1:
        raise ValueError("Fixture generation currently requires a single-session source")
    merged = merge_chunks(storage, args.bucket, sessions[0], args.output, 0, 8)
    normalized = args.output / "source.mkv"
    subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-n", "-fflags", "+genpts", "-i", str(merged),
                    "-map", "0:v:0", "-map", "0:a:0", "-c", "copy", str(normalized)], check=True, timeout=300)
    target = args.output / "one-hour.webm"
    subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-n", "-stream_loop", "-1", "-i", str(normalized),
                    "-t", str(args.seconds), "-map", "0:v:0", "-map", "0:a:0", "-c", "copy",
                    "-avoid_negative_ts", "make_zero", str(target)], check=True, timeout=300)
    info = probe(target)
    validate_probe(info, args.seconds)
    count = math.ceil(args.seconds / 5)
    chunk_dir = args.output / "chunks"
    chunk_dir.mkdir(exist_ok=True)
    size = target.stat().st_size
    chunks = []
    with target.open("rb") as source:
        for seq in range(count):
            # Byte splits intentionally need not be independently playable: production merges them.
            length = (seq + 1) * size // count - seq * size // count
            path = chunk_dir / f"chunk_{seq:08d}.webm"
            path.write_bytes(source.read(length))
            chunks.append({"seq": seq, "size": length, "file": path.name,
                           "startMs": seq * 5000, "endMs": min((seq + 1) * 5000, args.seconds * 1000)})
    save(metadata_path, {"source_id": args.source_id, "duration_seconds": args.seconds,
                         "bytes": size, "probe": info, "chunks": chunks,
                         "method": "looped real VP8/Opus media; equal-byte splits, not browser-timed chunks"})
    print(json.dumps({"fixture": str(metadata_path), "bytes": size, "chunks": count,
                      "duration": info["format"]["duration"]}, indent=2))


def stack_outputs(args):
    stack = client("cloudformation", args.region).describe_stacks(StackName=args.stack)["Stacks"][0]
    if stack["StackStatus"] not in ("CREATE_COMPLETE", "UPDATE_COMPLETE"):
        raise ValueError(f"Stack not ready: {stack['StackStatus']}")
    return {x["OutputKey"]: x["OutputValue"] for x in stack["Outputs"]}


def stage(args):
    if args.state.exists():
        raise ValueError("State file exists; choose a new --state path to preserve the earlier run")
    direct = bool(args.existing_function)
    if not direct and args.count > 20:
        raise ValueError("The isolated stack is capped at 20; use --existing-function for the 100-way direct test")
    outputs = {"FunctionName": args.existing_function} if direct else stack_outputs(args)
    cfg = client("lambda", args.region).get_function_configuration(FunctionName=outputs["FunctionName"])
    for key in ("AWS_BUCKET_NAME", "CVI_RECORDING_BUCKET_NAME"):
        if cfg["Environment"]["Variables"][key] != args.bucket:
            raise ValueError("Staging bucket differs from the test function's configured buckets")
    s3 = client("s3", args.region)
    fixture_meta = read(args.fixture / "fixture.json")
    run_id = args.run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + uuid.uuid4().hex[:6]
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,60}", run_id):
        raise ValueError("Invalid run ID")
    root = f"interview_perftc_{run_id}_" if direct else f"perf_tc_{run_id}_"
    if s3.list_objects_v2(Bucket=args.bucket, Prefix=root, MaxKeys=1).get("KeyCount"):
        raise ValueError("Run prefix already exists; use a new run ID")
    ids = [f"{root}{i:03d}" for i in range(1, args.count + 1)]
    state = {"region": args.region, "bucket": args.bucket, "stack": args.stack, "outputs": outputs,
             "mode": "direct-existing" if direct else "isolated-sqs",
             "run_id": run_id, "ids": ids, "fixture": fixture_meta, "staged": False}
    save(args.state, state)
    fixture_prefix = f"{root}fixture/"
    def upload(chunk):
        s3.upload_file(str(args.fixture / "chunks" / chunk["file"]), args.bucket,
                       fixture_prefix + chunk["file"], ExtraArgs={"ContentType": "video/webm"})
    with ThreadPoolExecutor(max_workers=16) as pool:
        list(pool.map(upload, fixture_meta["chunks"]))
    now = datetime.now(timezone.utc)
    def stage_interview(interview_id):
        session_id = str(uuid.uuid4())
        prefix = f"{interview_id}/recording_chunks/{session_id}/"
        def copy(chunk):
            s3.copy_object(Bucket=args.bucket, Key=prefix + chunk["file"],
                           CopySource={"Bucket": args.bucket, "Key": fixture_prefix + chunk["file"]})
        with ThreadPoolExecutor(max_workers=16) as pool:
            list(pool.map(copy, fixture_meta["chunks"]))
        chunks = [{k: v for k, v in chunk.items() if k != "file"} | {"key": prefix + chunk["file"]}
                  for chunk in fixture_meta["chunks"]]
        manifest = {"version": 1, "interviewId": interview_id, "recordingSessionId": session_id,
                    "status": "complete", "mimeType": "video/webm;codecs=vp8,opus",
                    "startedAt": now.isoformat(),
                    "endedAt": (now + timedelta(seconds=fixture_meta["duration_seconds"])).isoformat(),
                    "chunkCount": len(chunks), "totalBytes": fixture_meta["bytes"],
                    "chunks": chunks, "missingSequences": [], "updatedAt": now.isoformat()}
        s3.put_object(Bucket=args.bucket, Key=prefix + "manifest.json", Body=json.dumps(manifest), ContentType="application/json")
        if not direct:
            s3.put_object(Bucket=args.bucket, Key=f"{interview_id}/transcript.json",
                          Body=json.dumps({"performance_test": True, "segments": []}), ContentType="application/json")
        print(f"Staged {interview_id}", flush=True)
    with ThreadPoolExecutor(max_workers=args.stage_concurrency) as pool:
        list(pool.map(stage_interview, ids))
    state["staged"] = True
    save(args.state, state)


def exists(s3, bucket, key):
    from botocore.exceptions import ClientError
    try:
        return s3.head_object(Bucket=bucket, Key=key)
    except ClientError as error:
        if error.response["Error"]["Code"] in ("404", "NoSuchKey", "NotFound"):
            return None
        raise


def run(args):
    state = read(args.state)
    if not state.get("staged") or state.get("submitted_at"):
        raise ValueError("Use a fully staged, fresh run; never resubmit an existing test")
    s3 = client("s3", state["region"])
    sqs = client("sqs", state["region"])
    lam = client("lambda", state["region"])
    cfg = lam.get_function_configuration(FunctionName=state["outputs"]["FunctionName"])
    if cfg["Environment"]["Variables"]["SCORING_QUEUE_URL"] != state["outputs"]["ScoringSinkUrl"]:
        raise ValueError("Function is not configured with the isolated scoring sink")
    mappings = lam.list_event_source_mappings(FunctionName=state["outputs"]["FunctionName"])["EventSourceMappings"]
    attrs = sqs.get_queue_attributes(QueueUrl=state["outputs"]["QueueUrl"], AttributeNames=["All"])["Attributes"]
    matching = [m for m in mappings if m["EventSourceArn"] == attrs["QueueArn"] and m["State"] == "Enabled"]
    if len(matching) != 1 or matching[0]["BatchSize"] != 1 or "ReportBatchItemFailures" not in matching[0].get("FunctionResponseTypes", []):
        raise ValueError("Expected one enabled batch-size-1 trigger with partial failure reporting")
    if matching[0].get("ScalingConfig", {}).get("MaximumConcurrency", 0) < len(state["ids"]):
        raise ValueError("Trigger concurrency is below the requested interview count")
    if int(attrs["VisibilityTimeout"]) < cfg["Timeout"] * 6 or "RedrivePolicy" not in attrs:
        raise ValueError("Test queue requires visibility >=6x function timeout and a dead-letter queue")
    if any(int(attrs.get(k, 0)) for k in ("ApproximateNumberOfMessages", "ApproximateNumberOfMessagesNotVisible", "ApproximateNumberOfMessagesDelayed")):
        raise ValueError("Test queue is not empty")
    for interview_id in state["ids"]:
        if any(exists(s3, state["bucket"], f"{interview_id}/{key}") for key in (f"{interview_id}.mp4", "transcode_done.json")):
            raise ValueError(f"{interview_id} already has output; this would skip encoding")
    state["submitted_at"] = datetime.now(timezone.utc).isoformat()
    save(args.state, state)
    def send(interview_id):
        result = sqs.send_message(QueueUrl=state["outputs"]["QueueUrl"],
                                 MessageBody=json.dumps({"interview_id": interview_id}),
                                 MessageGroupId=interview_id, MessageDeduplicationId=interview_id)
        return {"interview_id": interview_id, "message_id": result["MessageId"]}
    with ThreadPoolExecutor(max_workers=len(state["ids"])) as pool:
        state["messages"] = list(pool.map(send, state["ids"]))
    state["submission_finished_at"] = datetime.now(timezone.utc).isoformat()
    save(args.state, state)
    print(f"Submitted {len(state['ids'])} interviews; use report to poll and verify.")


def invocation_intervals(events):
    starts, ends, reports = {}, {}, {}
    for event in events:
        message = event["message"]
        match = re.search(r"\b(START|END|REPORT) RequestId: ([\w-]+)", message)
        if not match:
            continue
        kind, request_id = match.groups()
        if kind == "START":
            starts[request_id] = event["timestamp"]
        elif kind == "END":
            ends[request_id] = event["timestamp"]
        else:
            reports[request_id] = message.strip()
    intervals = [{"request_id": rid, "start_ms": start, "end_ms": ends.get(rid), "report": reports.get(rid)}
                 for rid, start in starts.items()]
    points = [(i["start_ms"], 1) for i in intervals]
    points += [(i["end_ms"], -1) for i in intervals if i["end_ms"] is not None]
    active = peak = 0
    for _, delta in sorted(points):
        active += delta
        peak = max(peak, active)
    return intervals, peak


def report(args):
    state = read(args.state)
    if not state.get("submitted_at"):
        raise ValueError("Run has not been submitted")
    if state.get("mode") == "direct-existing":
        return report_direct(args, state)
    region, bucket = state["region"], state["bucket"]
    s3, sqs = client("s3", region), client("sqs", region)
    start = datetime.fromisoformat(state["submitted_at"])
    checks = []
    for interview_id in state["ids"]:
        marker = exists(s3, bucket, f"{interview_id}/transcode_done.json")
        mp4 = exists(s3, bucket, f"{interview_id}/{interview_id}.mp4")
        item = {"interview_id": interview_id, "done": bool(marker), "mp4_bytes": mp4["ContentLength"] if mp4 else None}
        if marker:
            done = json.loads(s3.get_object(Bucket=bucket, Key=f"{interview_id}/transcode_done.json")["Body"].read())
            item["completion_seconds"] = (datetime.fromisoformat(done["completed_at"]) - start).total_seconds()
        if mp4 and args.verify:
            url = s3.generate_presigned_url("get_object", Params={"Bucket": bucket, "Key": f"{interview_id}/{interview_id}.mp4"}, ExpiresIn=900)
            # Keep signed URLs out of exception messages and reports.
            try:
                info = probe(url)
                item["duration_seconds"] = validate_probe(info, state["fixture"]["duration_seconds"])
                item["streams"] = [{k: s.get(k) for k in ("codec_type", "codec_name", "width", "height")} for s in info["streams"]]
                item["media_valid"] = True
            except Exception as error:
                item["media_valid"] = False
                item["validation_error"] = type(error).__name__
        checks.append(item)
    events = []
    logs = client("logs", region)
    for page in logs.get_paginator("filter_log_events").paginate(
            logGroupName=f"/aws/lambda/{state['outputs']['FunctionName']}", startTime=int(start.timestamp() * 1000)):
        events.extend(page.get("events", []))
    intervals, peak = invocation_intervals(events)
    queues = {k: sqs.get_queue_attributes(QueueUrl=state["outputs"][k], AttributeNames=["All"])["Attributes"]
              for k in ("QueueUrl", "ScoringSinkUrl", "DeadLetterUrl")}
    metrics = {}
    cloudwatch = client("cloudwatch", region)
    for name, statistic in (("ConcurrentExecutions", "Maximum"), ("Errors", "Sum"), ("Throttles", "Sum"), ("Invocations", "Sum"), ("Duration", "Maximum")):
        metrics[name] = cloudwatch.get_metric_statistics(Namespace="AWS/Lambda", MetricName=name,
            Dimensions=[{"Name": "FunctionName", "Value": state["outputs"]["FunctionName"]}],
            StartTime=start, EndTime=datetime.now(timezone.utc), Period=60, Statistics=[statistic])["Datapoints"]
    complete = all(x["done"] and x.get("media_valid") for x in checks)
    retry_free = len(intervals) == len(state["ids"]) and all(i["end_ms"] is not None for i in intervals)
    dlq_empty = int(queues["DeadLetterUrl"].get("ApproximateNumberOfMessages", 0)) == 0
    durations, memory = [], []
    for invocation in intervals:
        report_line = invocation.get("report") or ""
        duration = re.search(r"\bDuration: ([\d.]+) ms", report_line)
        used = re.search(r"Max Memory Used: (\d+) MB", report_line)
        if duration:
            durations.append(float(duration.group(1)) / 1000)
        if used:
            memory.append(int(used.group(1)))
    result = {"run_id": state["run_id"], "target": len(state["ids"]), "observed_peak": peak,
              "status": "PASS" if complete and peak >= len(state["ids"]) and retry_free and dlq_empty else "NOT_PROVEN",
              "checked_at": datetime.now(timezone.utc).isoformat(), "interviews": checks,
              "invocations": intervals, "queues": queues, "cloudwatch": metrics,
              "lambda_duration_seconds": {"min": min(durations), "max": max(durations),
                  "p95": sorted(durations)[math.ceil(len(durations) * .95) - 1]} if durations else None,
              "max_memory_used_mb": max(memory) if memory else None,
              "note": "PASS requires --verify, all outputs, observed overlap, no extra attempts and an empty DLQ. Logs/metrics can arrive late. Lambda Errors alone misses handled per-item failures."}
    save(args.output, result)
    print(json.dumps({k: result[k] for k in ("status", "target", "observed_peak")}, indent=2))
    print(f"Completed: {sum(x['done'] for x in checks)}/{len(checks)}; report: {args.output}")


def attribute_test_invocations(events, interview_ids, run_id):
    """Match IDs or the explicitly assigned SQS message IDs, including split tracebacks."""
    active_by_stream, own_requests = {}, set()
    per_interview = {interview_id: set() for interview_id in interview_ids}
    message_pattern = re.compile(r"Failed to process message " + re.escape(run_id) + r"-(\d+)\b")
    for event in sorted(events, key=lambda event: event["timestamp"]):
        stream, message = event["logStreamName"], event["message"]
        beginning = re.search(r"\bSTART RequestId: ([\w-]+)", message)
        if beginning:
            active_by_stream[stream] = beginning.group(1)
        request_id = active_by_stream.get(stream)
        if request_id:
            matched = [interview_id for interview_id in interview_ids if interview_id in message]
            explicit_message = message_pattern.search(message)
            if explicit_message and 1 <= int(explicit_message.group(1)) <= len(interview_ids):
                matched.append(interview_ids[int(explicit_message.group(1)) - 1])
            for interview_id in matched:
                own_requests.add(request_id)
                per_interview[interview_id].add(request_id)
    selected = []
    for event in events:
        match = re.search(r"\b(?:START|END|REPORT) RequestId: ([\w-]+)", event["message"])
        if match and match.group(1) in own_requests:
            selected.append(event)
    intervals, peak = invocation_intervals(selected)
    return intervals, peak, per_interview, selected


def report_direct(args, state):
    """Attribute shared-function logs to test IDs before measuring their overlap."""
    region, bucket = state["region"], state["bucket"]
    start = datetime.fromisoformat(state["submitted_at"])
    s3 = client("s3", region)
    def inspect_interview(interview_id):
        key = f"{interview_id}/{interview_id}.mp4"
        mp4 = exists(s3, bucket, key)
        item = {"interview_id": interview_id, "encoded": bool(mp4),
                "mp4_bytes": mp4["ContentLength"] if mp4 else None}
        if mp4:
            item["completion_seconds"] = (mp4["LastModified"] - start).total_seconds()
        if mp4 and args.verify:
            url = s3.generate_presigned_url("get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=900)
            try:
                info = probe(url, timeout=30)
                item["duration_seconds"] = validate_probe(info, state["fixture"]["duration_seconds"])
                item["streams"] = [{key: stream.get(key) for key in ("codec_type", "codec_name", "width", "height")}
                                   for stream in info["streams"]]
                item["media_valid"] = True
            except Exception as error:
                item["media_valid"] = False
                item["validation_error"] = type(error).__name__
        return item
    with ThreadPoolExecutor(max_workers=args.verify_workers) as pool:
        checks = list(pool.map(inspect_interview, state["ids"]))
    events = []
    for page in client("logs", region).get_paginator("filter_log_events").paginate(
            logGroupName=f"/aws/lambda/{state['outputs']['FunctionName']}", startTime=int(start.timestamp() * 1000)):
        events.extend(page.get("events", []))
    # Existing function may also serve real interviews: never count unrelated invocations.
    intervals, peak, per_interview, selected = attribute_test_invocations(events, state["ids"], state["run_id"])
    save(Path(args.output).with_name("lambda-system-events.json"), selected)
    valid = all(item.get("media_valid") for item in checks)
    one_attempt = all(len(ids) == 1 for ids in per_interview.values()) and len(intervals) == len(state["ids"])
    complete = all(interval["end_ms"] is not None for interval in intervals)
    result = {"run_id": state["run_id"], "mode": "direct-existing", "target": len(state["ids"]),
              "status": "PASS" if valid and one_attempt and complete and peak >= len(state["ids"]) else "NOT_PROVEN",
              "observed_peak": peak, "checked_at": datetime.now(timezone.utc).isoformat(),
              "interviews": checks, "invocations": intervals,
              "requests_by_interview": {key: sorted(value) for key, value in per_interview.items()},
              "note": "Encoding-only direct invocations: missing transcript failures are intentional. No SQS scheduling, scoring or done markers are tested. PASS needs --verify and test-attributed Lambda overlap; logs can arrive late."}
    save(args.output, result)
    print(json.dumps({key: result[key] for key in ("status", "target", "observed_peak")}, indent=2))
    print(f"Encoded: {sum(item['encoded'] for item in checks)}/{len(checks)}; report: {args.output}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--region", default="ap-southeast-1")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("plan", help="Read deployment and generate an isolated CloudFormation template")
    p.add_argument("--source-function", default="conversational-media-transcoder")
    p.add_argument("--bucket", default="voicebot-testing")
    p.add_argument("--output", type=Path, default=Path("performance-tests/results/plan"))
    p.set_defaults(action=plan)
    p = sub.add_parser("fixture", help="Download a real recording and generate a local continuous one-hour fixture")
    p.add_argument("--source-id", required=True)
    p.add_argument("--bucket", default="voicebot-testing")
    p.add_argument("--seconds", type=int, default=3600)
    p.add_argument("--output", type=Path, default=Path("performance-tests/results/fixture"))
    p.set_defaults(action=fixture)
    p = sub.add_parser("stage", help="WRITE S3: upload fixture and create unique test interview inputs")
    p.add_argument("--existing-function", help="Use an existing Lambda directly, without deployment, queues or transcripts")
    p.add_argument("--stack", default="transcoder-perf-20")
    p.add_argument("--fixture", type=Path, default=Path("performance-tests/results/fixture"))
    p.add_argument("--bucket", default="voicebot-testing")
    p.add_argument("--count", type=int, choices=range(1, 101), default=20)
    p.add_argument("--stage-concurrency", type=int, choices=range(1, 9), default=4,
                   help="Interviews staged concurrently, with 16 bounded S3 chunk copies per interview")
    p.add_argument("--run-id")
    p.add_argument("--state", type=Path, default=Path("performance-tests/results/run.json"))
    p.set_defaults(action=stage)
    p = sub.add_parser("run", help="WRITE SQS: start actual transcodes on the isolated stack")
    p.add_argument("--state", type=Path, default=Path("performance-tests/results/run.json"))
    p.set_defaults(action=run)
    p = sub.add_parser("report", help="Read results, logs and metrics; --verify checks each MP4 with ffprobe")
    p.add_argument("--state", type=Path, default=Path("performance-tests/results/run.json"))
    p.add_argument("--verify", action="store_true")
    p.add_argument("--verify-workers", type=int, choices=range(1, 17), default=8)
    p.add_argument("--output", type=Path, default=Path("performance-tests/results/report.json"))
    p.set_defaults(action=report)
    args = parser.parse_args()
    args.action(args)


if __name__ == "__main__":
    main()
