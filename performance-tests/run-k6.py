#!/usr/bin/env python3
"""Run k6 with the default boto3 credential chain, without printing credentials."""
import argparse
import json
from datetime import datetime, timezone
import os
from pathlib import Path
import shlex
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--dashboard", action="store_true")
    parser.add_argument("--sla-seconds", type=int, default=600)
    parser.add_argument("--max-wait-seconds", type=int, default=1000)
    parser.add_argument("k6_args", nargs=argparse.REMAINDER, help="Extra k6 flags after --")
    args = parser.parse_args()
    if not args.state.is_file():
        stage_command = ("uv run --with boto3 python performance-tests/transcoder_perf.py stage "
                         "--existing-function conversational-media-transcoder "
                         f"--count 20 --state {shlex.quote(str(args.state))}")
        parser.error(
            f"State file does not exist: {args.state}\n"
            "Stage the inputs against the existing Lambda (no deployment required):\n"
            f"  {stage_command}\n"
            "Staging creates the state file and uploads test inputs; it does not start transcodes.\n"
            "For an offline dry run, use --state performance-tests/test-data/dry-run-state.json --dry-run."
        )
    output = args.output_dir or Path("performance-tests/results") / datetime.now(timezone.utc).strftime("k6-%Y%m%dT%H%M%S%f")
    output = output.resolve()
    if output.exists() and any(output.iterdir()):
        parser.error("Output directory must be empty to preserve previous test evidence")
    output.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env.update({"STATE_FILE": str(args.state.resolve()), "DRY_RUN": str(args.dry_run).lower(),
                "SLA_SECONDS": str(args.sla_seconds), "MAX_WAIT_SECONDS": str(args.max_wait_seconds),
                "SUMMARY_FILE": str(output / "summary.json"), "RUN_STATE_FILE": str(output / "state.json")})
    if args.dashboard:
        env["K6_WEB_DASHBOARD"] = "true"
        env["K6_WEB_DASHBOARD_EXPORT"] = str(output / "dashboard.html")
    if not args.dry_run:
        import boto3
        credentials = boto3.Session().get_credentials()
        if credentials is None:
            parser.error("No AWS credentials found in the default credential chain")
        frozen = credentials.get_frozen_credentials()
        env.update({"AWS_ACCESS_KEY_ID": frozen.access_key, "AWS_SECRET_ACCESS_KEY": frozen.secret_key})
        env.pop("AWS_SESSION_TOKEN", None)
        if frozen.token:
            env["AWS_SESSION_TOKEN"] = frozen.token
    extra = args.k6_args[1:] if args.k6_args[:1] == ["--"] else args.k6_args
    state = json.loads(args.state.read_text())
    script = Path(__file__).with_name("transcoder-direct.k6.js" if state.get("mode") == "direct-existing" else "transcoder.k6.js")
    print(f"k6 results: {output}", flush=True)
    result = subprocess.run(["k6", "run", *extra, str(script)], env=env, check=False)
    if not args.dry_run:
        print(f"Evidence state for Python report: {output / 'state.json'}", flush=True)
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
