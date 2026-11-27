import http from 'k6/http';
import exec from 'k6/execution';
import encoding from 'k6/encoding';
import { Counter, Rate, Trend } from 'k6/metrics';
import { signedHeaders, encodePath } from './aws-signature.k6.js';

const state = JSON.parse(open(__ENV.STATE_FILE || './results/run20.json'));
const dryRun = __ENV.DRY_RUN === 'true';
const count = state.ids.length;
const sla = Number(__ENV.SLA_SECONDS || 600);
const wait = Number(__ENV.MAX_WAIT_SECONDS || 1000);
if (state.mode !== 'direct-existing' || !state.staged || state.submitted_at || count < 1 || count > 100 ||
    new Set(state.ids).size !== count || !state.ids.every((id) =>
      id.startsWith(`interview_perftc_${state.run_id}_`) && /^[A-Za-z0-9_-]+$/.test(id))) {
  throw new Error('Require a fresh direct-existing staged state with 1–100 unique test interview IDs.');
}
if (!(sla > 0 && wait >= sla)) throw new Error('Require MAX_WAIT_SECONDS >= SLA_SECONDS > 0.');
const complete = new Counter('transcoder_completed');
const failed = new Counter('transcoder_failed');
const success = new Rate('transcoder_success');
const withinSla = new Rate('transcoder_within_sla');
const duration = new Trend('transcoder_completion_seconds');
const lambdaDuration = new Trend('transcoder_lambda_duration_seconds');
const memory = new Trend('transcoder_lambda_memory_mb');

export const options = {
  scenarios: { transcodes: { executor: 'per-vu-iterations', vus: count, iterations: 1,
    maxDuration: `${wait + 60}s`, gracefulStop: '5s' } },
  setupTimeout: '300s', batch: 24, batchPerHost: 12,
  summaryTrendStats: ['min', 'med', 'avg', 'p(95)', 'max'],
  thresholds: dryRun ? {} : {
    transcoder_completed: [`count==${count}`], transcoder_failed: ['count==0'],
    transcoder_success: ['rate==1'], transcoder_within_sla: ['rate==1'],
    transcoder_completion_seconds: [`p(95)<${sla}`],
  },
  tags: { testid: state.run_id, workload: 'one-hour-transcoder-direct' },
};

function request(service, method, path, body = '', extra = {}, timeout = '15s', operation = '') {
  const host = service === 's3' ? `${state.bucket}.s3.${state.region}.amazonaws.com` : `${service}.${state.region}.amazonaws.com`;
  const headers = signedHeaders(method, host, path, body, service, state.region,
    { key: __ENV.AWS_ACCESS_KEY_ID, secret: __ENV.AWS_SECRET_ACCESS_KEY, token: __ENV.AWS_SESSION_TOKEN }, new Date(), extra);
  return http.request(method, `https://${host}${path}`, body || null, {
    headers, timeout, redirects: 0, tags: { name: operation },
    responseCallback: service === 's3' ? http.expectedStatuses(200, 404) : http.expectedStatuses(200),
  });
}
function head(key) { return request('s3', 'HEAD', encodePath(`/${key}`), '', {}, '15s', 's3_preflight_or_output'); }
function header(response, name) {
  const key = Object.keys(response.headers).find((key) => key.toLowerCase() === name.toLowerCase());
  return key ? response.headers[key] : '';
}

export function setup() {
  if (dryRun) { console.log(`DRY RUN: ${count} parallel direct invocations; no AWS calls.`); return { dry_run: true }; }
  if (!__ENV.AWS_ACCESS_KEY_ID || !__ENV.AWS_SECRET_ACCESS_KEY) throw new Error('AWS credentials are required.');
  const cfgResponse = request('lambda', 'GET',
    `/2015-03-31/functions/${encodeURIComponent(state.outputs.FunctionName)}/configuration`, '', {}, '15s', 'lambda_preflight');
  if (cfgResponse.status !== 200) throw new Error(`Cannot inspect Lambda: HTTP ${cfgResponse.status}`);
  const cfg = cfgResponse.json();
  if (cfg.Environment.Variables.AWS_BUCKET_NAME !== state.bucket || cfg.Environment.Variables.CVI_RECORDING_BUCKET_NAME !== state.bucket) {
    throw new Error('Staged bucket differs from the existing Lambda buckets.');
  }
  if (wait < cfg.Timeout + 30) throw new Error(`MAX_WAIT_SECONDS must be >= ${cfg.Timeout + 30}.`);
  const host = `${state.bucket}.s3.${state.region}.amazonaws.com`;
  const keys = state.ids.flatMap((id) => [`${id}/${id}.mp4`, `${id}/transcode_done.json`, `${id}/transcript.json`]);
  const responses = http.batch(keys.map((key) => {
    const path = encodePath(`/${key}`);
    return { method: 'HEAD', url: `https://${host}${path}`, params: {
      headers: signedHeaders('HEAD', host, path, '', 's3', state.region,
        { key: __ENV.AWS_ACCESS_KEY_ID, secret: __ENV.AWS_SECRET_ACCESS_KEY, token: __ENV.AWS_SESSION_TOKEN }),
      timeout: '15s', redirects: 0, tags: { name: 's3_preflight' },
      responseCallback: http.expectedStatuses(404),
    } };
  }));
  for (let i = 0; i < responses.length; i++) {
    if (responses[i].status !== 404) throw new Error(`${keys[i]} must be absent before this encoding-only test.`);
  }
  complete.add(0); failed.add(0);
  return { ...state, submitted_at: new Date().toISOString(), submitted_by: 'grafana-k6-direct' };
}

export default function () {
  if (dryRun) return;
  const id = state.ids[exec.vu.idInTest - 1];
  const messageId = `${state.run_id}-${exec.vu.idInTest}`;
  const started = Date.now();
  // No SQS delivery: these synchronous invocations do not retry missing transcripts.
  const response = request('lambda', 'POST',
    `/2015-03-31/functions/${encodeURIComponent(state.outputs.FunctionName)}/invocations`,
    JSON.stringify({ Records: [{ messageId, body: JSON.stringify({ interview_id: id }) }] }),
    { 'content-type': 'application/json', 'x-amz-invocation-type': 'RequestResponse', 'x-amz-log-type': 'Tail' },
    `${wait}s`, 'lambda_transcode');
  const elapsed = (Date.now() - started) / 1000;
  let reason = '';
  if (response.status !== 200 || header(response, 'x-amz-function-error')) reason = `Lambda invocation failed: HTTP ${response.status}`;
  let result;
  try { result = response.json(); } catch (_) { reason = reason || 'Invalid Lambda response'; }
  // Missing transcript is intentional: the production pipeline encodes first, then
  // returns a batch failure without forwarding this synthetic interview to scoring.
  if (!reason && (!result.batchItemFailures || result.batchItemFailures.length !== 1 ||
      result.batchItemFailures[0].itemIdentifier !== messageId)) reason = 'Unexpected encoding-only handler response';
  const mp4 = head(`${id}/${id}.mp4`);
  const bytes = Number(header(mp4, 'content-length'));
  if (!reason && (mp4.status !== 200 || !(bytes > 0))) reason = 'No nonempty MP4 output';
  const transcript = head(`${id}/transcript.json`);
  if (!reason && transcript.status !== 404) reason = 'Transcript absence could not be confirmed';
  let logs = '';
  try { logs = encoding.b64decode(header(response, 'x-amz-log-result'), 'std', 's'); } catch (_) { /* no tail */ }
  const report = logs.match(/REPORT RequestId: ([\w-]+)[\s\S]*?\bDuration: ([\d.]+) ms[\s\S]*?Max Memory Used: (\d+) MB/);
  if (report) { lambdaDuration.add(Number(report[2]) / 1000); memory.add(Number(report[3])); }
  // Current pipeline must fail only after output was uploaded, for the absent transcript.
  if (!reason && !logs.includes('TranscriptNotReady')) reason = 'Expected TranscriptNotReady was not present in the Lambda log tail';
  if (reason) {
    failed.add(1); success.add(false); withinSla.add(false);
    console.error(`${id}: ${reason}`); return;
  }
  complete.add(1); success.add(true); withinSla.add(elapsed <= sla); duration.add(elapsed);
  console.log(JSON.stringify({ interview_id: id, seconds: elapsed, bytes,
    request_id: report ? report[1] : null, started_at: new Date(started).toISOString(),
    completed_at: new Date().toISOString(), encoding_only: true }));
}

export function handleSummary(data) {
  const outputs = {};
  outputs[__ENV.SUMMARY_FILE || 'performance-tests/results/direct-summary.json'] = JSON.stringify({ ...data,
    dry_run: dryRun, mode: 'encoding-only',
    note: 'Direct calls to existing Lambda. No deployment, SQS messages, transcripts, scoring or done markers. MP4 stream/duration validation remains separate.' }, null, 2);
  if (!dryRun && data.setup_data && data.setup_data.submitted_at) {
    outputs[__ENV.RUN_STATE_FILE || 'performance-tests/results/direct-state.json'] = JSON.stringify(data.setup_data, null, 2);
  }
  const failures = Object.entries(data.metrics || {}).flatMap(([name, metric]) =>
    Object.values(metric.thresholds || {}).some((threshold) => !threshold.ok) ? [name] : []);
  outputs.stdout = dryRun ? 'DRY RUN complete; no AWS calls.\n' : !data.setup_data || !data.setup_data.submitted_at ?
    'Test did not start; review the setup error.\n' :
    `Encoding-only test ${failures.length ? 'failed thresholds: ' + failures.join(', ') : 'passed completion/SLA thresholds'}.\n`;
  return outputs;
}
