import crypto from 'k6/crypto';

// AWS SigV4, using only k6 built-ins. No credentials are included in metrics.
export function signedHeaders(method, host, path, body, service, region, credentials, now = new Date(), extraHeaders = {}) {
  const timestamp = now.toISOString().replace(/[:-]|\.\d{3}/g, '');
  const date = timestamp.slice(0, 8);
  const payloadHash = crypto.sha256(body, 'hex');
  const headers = {
    host,
    'x-amz-date': timestamp,
    'x-amz-content-sha256': payloadHash,
  };
  if (credentials.token) headers['x-amz-security-token'] = credentials.token;
  for (const [name, value] of Object.entries(extraHeaders)) headers[name.toLowerCase()] = value;
  if (service === 'sqs') {
    headers['content-type'] = 'application/x-amz-json-1.0';
    headers['x-amz-target'] = `AmazonSQS.${credentials.action}`;
  }
  const names = Object.keys(headers).sort();
  const canonicalHeaders = names.map((name) => `${name}:${headers[name].trim()}\n`).join('');
  const signedNames = names.join(';');
  const canonicalRequest = [method, path, '', canonicalHeaders, signedNames, payloadHash].join('\n');
  const scope = `${date}/${region}/${service}/aws4_request`;
  const toSign = ['AWS4-HMAC-SHA256', timestamp, scope, crypto.sha256(canonicalRequest, 'hex')].join('\n');
  const hmac = (key, value) => crypto.hmac('sha256', key, value, 'binary');
  const key = hmac(hmac(hmac(hmac(`AWS4${credentials.secret}`, date), region), service), 'aws4_request');
  const signature = crypto.hmac('sha256', key, toSign, 'hex');
  headers.authorization = `AWS4-HMAC-SHA256 Credential=${credentials.key}/${scope}, SignedHeaders=${signedNames}, Signature=${signature}`;
  return headers;
}

export function encodePath(path) {
  return path.split('/').map((part) => encodeURIComponent(part).replace(/[!'()*]/g,
    (char) => `%${char.charCodeAt(0).toString(16).toUpperCase()}`)).join('/');
}
