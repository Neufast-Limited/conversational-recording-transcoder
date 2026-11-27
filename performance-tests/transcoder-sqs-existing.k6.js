import http from 'k6/http';
import exec from 'k6/execution';
import { sleep } from 'k6';
import { Counter, Rate, Trend } from 'k6/metrics';
import { signedHeaders, encodePath } from './aws-signature.k6.js';

const state = JSON.parse(open(__ENV.STATE_FILE));
const count = state.ids.length;
const dry = __ENV.DRY_RUN === 'true';
const maxWait = Number(__ENV.MAX_WAIT_SECONDS || 2400);
const sla = Number(__ENV.SLA_SECONDS || 600);
const expectedLimit = state.expected_peak || 20;
const expectedResponses = state.expected_response_types || [];
if (state.mode !== 'sqs-existing' || !state.staged || state.submitted_at || count !== 100 ||
    new Set(state.ids).size !== count || !state.ids.every(id => id.startsWith(`interview_perftc_${state.run_id}_`))) {
  throw new Error('Require 100 fresh sqs-existing staged interviews.');
}
const sent = new Counter('transcoder_submitted');
const completed = new Counter('transcoder_completed');
const failed = new Counter('transcoder_failed');
const success = new Rate('transcoder_success');
const withinSla = new Rate('transcoder_within_sla');
const duration = new Trend('transcoder_completion_seconds');
const enqueue = new Trend('transcoder_enqueue_ms', true);
export const options = {
  scenarios: { queue: { executor: 'per-vu-iterations', vus: count, iterations: 1,
    maxDuration: `${maxWait + 60}s`, gracefulStop: '5s' } },
  setupTimeout: '300s', batch: 24, batchPerHost: 12,
  summaryTrendStats: ['min', 'med', 'avg', 'p(95)', 'max'],
  thresholds: dry ? {} : { transcoder_submitted: ['count==100'], transcoder_completed: ['count==100'],
    transcoder_failed: ['count==0'], transcoder_success: ['rate==1'], transcoder_within_sla: ['rate==1'],
    transcoder_completion_seconds: [`p(95)<${sla}`] },
  tags: { testid: state.run_id, workload: `sqs-100-at-${expectedLimit}-limit` },
};

function aws(service, method, path, body = '', action = '') {
  const host = service === 's3' ? `${state.bucket}.s3.${state.region}.amazonaws.com` : `${service}.${state.region}.amazonaws.com`;
  return { method, url: `https://${host}${path}`, body: body || null, params: {
    headers: signedHeaders(method, host, path, body, service, state.region,
      { key: __ENV.AWS_ACCESS_KEY_ID, secret: __ENV.AWS_SECRET_ACCESS_KEY, token: __ENV.AWS_SESSION_TOKEN, action }),
    timeout: '20s', redirects: 0, tags: { name: `${service}_${action || method}` },
    responseCallback: service === 's3' ? http.expectedStatuses(200, 404) : http.expectedStatuses(200),
  } };
}
function call(request) { return http.request(request.method, request.url, request.body, request.params); }
function head(key) { return call(aws('s3', 'HEAD', encodePath(`/${key}`))); }
function sqs(action, data) { return call(aws('sqs', 'POST', '/', JSON.stringify(data), action)); }
function header(response, name) {
  const key = Object.keys(response.headers).find(key => key.toLowerCase() === name.toLowerCase());
  return key ? response.headers[key] : '';
}
export function setup() {
  if (dry) { console.log('DRY RUN: 100 SQS submissions, no AWS requests.'); return { dry_run: true }; }
  if (!__ENV.AWS_ACCESS_KEY_ID || !__ENV.AWS_SECRET_ACCESS_KEY) throw new Error('AWS credentials required');
  const queue = sqs('GetQueueAttributes', { QueueUrl: state.outputs.QueueUrl, AttributeNames: ['All'] });
  if (queue.status !== 200) throw new Error(`Queue preflight HTTP ${queue.status}`);
  const attributes = queue.json().Attributes;
  if (['ApproximateNumberOfMessages', 'ApproximateNumberOfMessagesNotVisible', 'ApproximateNumberOfMessagesDelayed']
      .some(key => Number(attributes[key] || 0))) throw new Error('Queue must be empty before test');
  const mapping = call(aws('lambda', 'GET', `/2015-03-31/event-source-mappings/${state.outputs.TriggerUUID}`));
  if (mapping.status !== 200) throw new Error(`Trigger preflight HTTP ${mapping.status}`);
  const trigger = mapping.json();
  if (trigger.State !== 'Enabled' || trigger.BatchSize !== 1 || trigger.EventSourceArn !== attributes.QueueArn ||
      trigger.ScalingConfig.MaximumConcurrency !== expectedLimit ||
      JSON.stringify(trigger.FunctionResponseTypes || []) !== JSON.stringify(expectedResponses) ||
      (expectedResponses.includes('ReportBatchItemFailures') && !state.test_completion_markers)) {
    throw new Error('Trigger differs from the staged concurrency/failure settings, or test retry acknowledgement is not configured');
  }
  const keys = state.ids.flatMap(id => [`${id}/${id}.mp4`, `${id}/transcript.json`, `${id}/transcode_done.json`]);
  const checks = http.batch(keys.map(key => aws('s3', 'HEAD', encodePath(`/${key}`))));
  checks.forEach((response, index) => { if (response.status !== 404) throw new Error(`${keys[index]} must be absent`); });
  sent.add(0); completed.add(0); failed.add(0);
  return { ...state, submitted_at: new Date().toISOString(), submitted_by: 'grafana-k6-sqs-existing' };
}
export default function () {
  if (dry) return;
  const id = state.ids[exec.vu.idInTest - 1];
  const started = Date.now();
  const response = sqs('SendMessage', { QueueUrl: state.outputs.QueueUrl,
    MessageBody: JSON.stringify({ interview_id: id }), MessageGroupId: id, MessageDeduplicationId: id });
  enqueue.add(response.timings.duration);
  if (response.status !== 200) { failed.add(1); success.add(false); withinSla.add(false); console.error(`${id}: enqueue HTTP ${response.status}`); return; }
  const messageId = response.json().MessageId;
  sent.add(1);
  console.log(JSON.stringify({ event: 'submitted', interview_id: id, message_id: messageId, enqueued_at: new Date(started).toISOString() }));
  while ((Date.now() - started) / 1000 < maxWait) {
    const output = head(`${id}/${id}.mp4`);
    if (output.status === 200 && Number(header(output, 'content-length')) > 0) {
      const elapsed = (Date.now() - started) / 1000;
      completed.add(1); success.add(true); withinSla.add(elapsed <= sla); duration.add(elapsed);
      console.log(JSON.stringify({ event: 'completed', interview_id: id, message_id: messageId,
        seconds: elapsed, bytes: Number(header(output, 'content-length')),
        enqueued_at: new Date(started).toISOString(), observed_completed_at: new Date().toISOString(), encoding_only: true }));
      return;
    }
    // Retry read-only observation failures; never resend an accepted SQS message.
    if (output.status !== 404 && output.status !== 0 && output.status < 500) {
      failed.add(1); success.add(false); withinSla.add(false); console.error(`${id}: output HTTP ${output.status}`); return;
    }
    sleep(10);
  }
  failed.add(1); success.add(false); withinSla.add(false); console.error(`${id}: timed out waiting for output`);
}
export function handleSummary(data) {
  const outputs = { [__ENV.SUMMARY_FILE]: JSON.stringify({ ...data, mode: 'sqs-existing', dry_run: dry }, null, 2) };
  if (!dry && data.setup_data && data.setup_data.submitted_at) outputs[__ENV.RUN_STATE_FILE] = JSON.stringify(data.setup_data, null, 2);
  const failures = Object.entries(data.metrics || {}).flatMap(([name, metric]) =>
    Object.values(metric.thresholds || {}).some(threshold => !threshold.ok) ? [name] : []);
  outputs.stdout = dry ? 'DRY RUN complete; no messages sent.\n' :
    `SQS test finished. Threshold failures: ${failures.join(', ') || 'none'}. Queue wait is included in completion time.\n`;
  return outputs;
}
