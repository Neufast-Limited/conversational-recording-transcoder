import http from 'k6/http';
import { sleep } from 'k6';
import exec from 'k6/execution';
import { Counter, Rate, Trend } from 'k6/metrics';
import { signedHeaders, encodePath } from './aws-signature.k6.js';

// Paths passed to open() are relative to this script, not the shell directory.
const state = JSON.parse(open(__ENV.STATE_FILE || './results/run20.json'));
const dryRun = __ENV.DRY_RUN === 'true';
const count = state.ids.length;
const region = state.region;
const pollSeconds = Number(__ENV.POLL_SECONDS || 10);
const maxWait = Number(__ENV.MAX_WAIT_SECONDS || 1000);
const slaSeconds = Number(__ENV.SLA_SECONDS || 600);
if (!state.staged || state.submitted_at || count < 1 || count > 20 || new Set(state.ids).size !== count) {
  throw new Error('Use a fully staged, fresh state containing 1–20 distinct interview IDs.');
}
if (!state.ids.every((id) => id.startsWith(`perf_tc_${state.run_id}_`) && /^[A-Za-z0-9_-]+$/.test(id))) {
  throw new Error('Every interview ID must belong to this run’s perf_tc_ test prefix.');
}
if (!(pollSeconds > 0 && maxWait > 0 && slaSeconds > 0 && slaSeconds <= maxWait)) {
  throw new Error('Require positive POLL_SECONDS, MAX_WAIT_SECONDS and SLA_SECONDS <= MAX_WAIT_SECONDS.');
}

const submitted = new Counter('transcoder_submitted');
const completed = new Counter('transcoder_completed');
const failed = new Counter('transcoder_failed');
const success = new Rate('transcoder_success');
const withinSla = new Rate('transcoder_within_sla');
const completionTime = new Trend('transcoder_completion_seconds');
const enqueueLatency = new Trend('transcoder_enqueue_ms', true);

export const options = {
  scenarios: {
    interviews: {
      executor: 'per-vu-iterations', vus: count, iterations: 1,
      maxDuration: `${Math.ceil(maxWait + 60)}s`, gracefulStop: '5s',
    },
  },
  setupTimeout: '120s',
  summaryTrendStats: ['min', 'med', 'avg', 'p(95)', 'max'],
  thresholds: dryRun ? {} : {
    transcoder_submitted: [`count==${count}`],
    transcoder_completed: [`count==${count}`],
    transcoder_failed: ['count==0'],
    transcoder_success: ['rate==1'],
    transcoder_within_sla: ['rate==1'],
    transcoder_completion_seconds: [`p(95)<${slaSeconds}`],
  },
  tags: { testid: state.run_id, workload: 'one-hour-transcoder' },
};

function request(service, method, path, body = '', action = '', operation = '') {
  const host = service === 's3' ? `${state.bucket}.s3.${region}.amazonaws.com` : `${service}.${region}.amazonaws.com`;
  const credentials = { key: __ENV.AWS_ACCESS_KEY_ID, secret: __ENV.AWS_SECRET_ACCESS_KEY,
    token: __ENV.AWS_SESSION_TOKEN, action };
  const headers = signedHeaders(method, host, path, body, service, region, credentials);
  return http.request(method, `https://${host}${path}`, body || null, {
    headers, timeout: '15s', redirects: 0,
    tags: { name: operation || `${service}_${action || method}` },
    // A missing S3 marker is normal while work is running, not a failed request.
    responseCallback: service === 's3' ? http.expectedStatuses(200, 404) : http.expectedStatuses(200),
  });
}

function sqs(action, payload) {
  return request('sqs', 'POST', '/', JSON.stringify(payload), action);
}

function s3(method, key, operation) {
  return request('s3', method, encodePath(`/${key}`), '', '', operation);
}

function requireStatus(response, expected, description) {
  if (response.status !== expected) {
    // Do not print AWS response bodies or signed request headers.
    throw new Error(`${description}: HTTP ${response.status}; expected ${expected}`);
  }
}

export function setup() {
  if (dryRun) {
    console.log(`DRY RUN: ${count} VUs, one interview each; no AWS requests or performance assertions.`);
    return { dry_run: true };
  }
  if (!__ENV.AWS_ACCESS_KEY_ID || !__ENV.AWS_SECRET_ACCESS_KEY) {
    throw new Error('Export AWS credentials before running k6; AWS CLI profiles are not read by k6.');
  }
  const outputs = state.outputs;
  if (outputs.FunctionName !== state.stack || !outputs.FunctionName.startsWith('transcoder-perf-')) {
    throw new Error('This script requires an isolated transcoder-perf-* stack.');
  }
  const cfgResponse = request('lambda', 'GET',
    `/2015-03-31/functions/${encodeURIComponent(outputs.FunctionName)}/configuration`, '', '', 'lambda_preflight');
  requireStatus(cfgResponse, 200, 'Read test Lambda configuration');
  const cfg = cfgResponse.json();
  const env = cfg.Environment.Variables;
  if (env.SCORING_QUEUE_URL !== outputs.ScoringSinkUrl || env.SCORING_QUEUE_URL === outputs.QueueUrl ||
      env.AWS_BUCKET_NAME !== state.bucket || env.CVI_RECORDING_BUCKET_NAME !== state.bucket) {
    throw new Error('Test Lambda buckets/scoring sink do not match the staged run.');
  }
  const queueResponse = sqs('GetQueueAttributes', { QueueUrl: outputs.QueueUrl, AttributeNames: ['All'] });
  requireStatus(queueResponse, 200, 'Read test queue');
  const attributes = queueResponse.json().Attributes;
  if (!outputs.TriggerUUID) throw new Error('Regenerate the stack plan to include its TriggerUUID output.');
  const triggerResponse = request('lambda', 'GET',
    `/2015-03-31/event-source-mappings/${outputs.TriggerUUID}`, '', '', 'lambda_trigger_preflight');
  requireStatus(triggerResponse, 200, 'Read test trigger');
  const trigger = triggerResponse.json();
  if (trigger.EventSourceArn !== attributes.QueueArn || trigger.State !== 'Enabled' || trigger.BatchSize !== 1 ||
      !trigger.FunctionArn.endsWith(`:function:${outputs.FunctionName}`) ||
      !(trigger.FunctionResponseTypes || []).includes('ReportBatchItemFailures') ||
      !trigger.ScalingConfig || trigger.ScalingConfig.MaximumConcurrency < count) {
    throw new Error('Require an enabled batch-size-1 trigger with partial failure reporting and enough concurrency.');
  }
  if (['ApproximateNumberOfMessages', 'ApproximateNumberOfMessagesNotVisible', 'ApproximateNumberOfMessagesDelayed']
    .some((key) => Number(attributes[key] || 0) !== 0)) {
    throw new Error('The isolated test queue must be empty before starting.');
  }
  for (const id of state.ids) {
    requireStatus(s3('HEAD', `${id}/${id}.mp4`, 'preflight_mp4'), 404, `${id}: output must not exist`);
    requireStatus(s3('HEAD', `${id}/transcode_done.json`, 'preflight_marker'), 404, `${id}: marker must not exist`);
    requireStatus(s3('HEAD', `${id}/transcript.json`, 'preflight_transcript'), 200, `${id}: transcript required`);
  }
  submitted.add(0); completed.add(0); failed.add(0);
  // handleSummary exports this as a state file for the Python evidence report.
  return { ...state, submitted_at: new Date().toISOString(), submitted_by: 'grafana-k6' };
}

function markFailed(id, reason) {
  failed.add(1); success.add(false); withinSla.add(false);
  console.error(`${id}: ${reason}`);
}

export default function () {
  const id = state.ids[exec.vu.idInTest - 1];
  if (dryRun) return;
  const started = Date.now();
  const response = sqs('SendMessage', {
    QueueUrl: state.outputs.QueueUrl,
    MessageBody: JSON.stringify({ interview_id: id }),
    MessageGroupId: id,
    MessageDeduplicationId: id,
  });
  enqueueLatency.add(response.timings.duration);
  if (response.status !== 200) {
    markFailed(id, `enqueue failed: HTTP ${response.status}`);
    return;
  }
  submitted.add(1);
  while ((Date.now() - started) / 1000 < maxWait) {
    const marker = s3('GET', `${id}/transcode_done.json`, 'poll_completion');
    if (marker.status === 200) {
      let info;
      try { info = marker.json(); } catch (_) { markFailed(id, 'invalid completion marker JSON'); return; }
      if (info.interview_id !== id || info.mp4_key !== `${id}/${id}.mp4`) {
        markFailed(id, 'completion marker does not match interview/output'); return;
      }
      const mp4 = s3('HEAD', info.mp4_key, 'verify_mp4_exists');
      const bytes = Number(mp4.headers['Content-Length'] || mp4.headers['content-length']);
      if (mp4.status !== 200 || !(bytes > 0) || bytes !== Number(info.mp4_size)) {
        markFailed(id, 'MP4 missing, empty or different from marker size'); return;
      }
      const elapsed = (Date.now() - started) / 1000;
      completed.add(1); success.add(true); withinSla.add(elapsed <= slaSeconds);
      completionTime.add(elapsed);
      console.log(`${id}: completed in ${elapsed.toFixed(1)}s, ${bytes} bytes`);
      return;
    }
    if (marker.status !== 404) {
      markFailed(id, `completion check failed: HTTP ${marker.status}`); return;
    }
    sleep(Math.min(pollSeconds, Math.max(0, maxWait - (Date.now() - started) / 1000)));
  }
  markFailed(id, `no completion marker after ${maxWait}s`);
}

export function handleSummary(data) {
  const outputs = {};
  const summaryPath = __ENV.SUMMARY_FILE || 'performance-tests/results/k6-summary.json';
  outputs[summaryPath] = JSON.stringify({ ...data, dry_run: dryRun,
    note: 'k6 verifies submission, markers and MP4 sizes. Python report verifies actual Lambda overlap and media duration.' }, null, 2);
  if (!dryRun && data.setup_data && data.setup_data.submitted_at) {
    outputs[__ENV.RUN_STATE_FILE || 'performance-tests/results/k6-run-state.json'] = JSON.stringify(data.setup_data, null, 2);
  }
  const failures = Object.entries(data.metrics || {}).flatMap(([name, metric]) =>
    Object.entries(metric.thresholds || {}).filter(([, threshold]) => !threshold.ok).map(([condition]) => `${name}: ${condition}`));
  outputs.stdout = dryRun ? 'DRY RUN finished. No AWS jobs were submitted.\n' : !data.setup_data || !data.setup_data.submitted_at ?
    'Test did not start. Review the setup error; no performance result is available.\n' :
    `k6 ${failures.length ? 'threshold failures: ' + failures.join(', ') : 'completion/SLA checks passed'}.\n` +
    'Run the Python report with k6-run-state.json --verify to confirm Lambda concurrency and MP4 duration.\n';
  return outputs;
}
