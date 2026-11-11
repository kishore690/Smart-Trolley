import { API_BASE_URL, REQUEST_TIMEOUT_MS } from '../config.js';

/**
 * kind: 'network' | 'timeout' | 'http' | 'parse' | 'aborted'
 */
export class ApiError extends Error {
  constructor(message, { kind, status = null, body = null, detail = null } = {}) {
    super(message);
    this.name = 'ApiError';
    this.kind = kind;
    this.status = status;
    this.body = body;
    this.detail = detail;
  }
  get isAborted() { return this.kind === 'aborted'; }
  get isConnectivity() { return this.kind === 'network' || this.kind === 'timeout'; }
}

export const hostLabel = () => (API_BASE_URL ? API_BASE_URL.replace(/^https?:\/\//, '') : 'this origin');

function describeDetail(body) {
  if (!body || typeof body !== 'object') return null;
  const d = body.detail ?? body.message ?? body.error;
  if (typeof d === 'string') return d;
  if (Array.isArray(d)) return d.map((x) => x?.msg ?? JSON.stringify(x)).join('; ');
  return null;
}

/**
 * Single entry point for every backend call.
 * Resolves { data, status, serverDate } where data is parsed JSON (or null for an empty body).
 */
export async function request(path, { method = 'GET', body, signal, timeoutMs = REQUEST_TIMEOUT_MS } = {}) {
  const controller = new AbortController();
  let timedOut = false;
  let callerAborted = false;

  const onCallerAbort = () => { callerAborted = true; controller.abort(); };
  if (signal) {
    if (signal.aborted) onCallerAbort();
    else signal.addEventListener('abort', onCallerAbort, { once: true });
  }
  const timer = setTimeout(() => { timedOut = true; controller.abort(); }, timeoutMs);

  try {
    let res;
    try {
      res = await fetch(`${API_BASE_URL}${path}`, {
        method,
        signal: controller.signal,
        cache: 'no-store',
        headers: {
          Accept: 'application/json',
          ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
        },
        body: body !== undefined ? JSON.stringify(body) : undefined,
      });
    } catch (err) {
      if (callerAborted) throw new ApiError('Request cancelled', { kind: 'aborted' });
      if (timedOut) {
        throw new ApiError(`The trolley did not respond within ${Math.round(timeoutMs / 1000)}s`, { kind: 'timeout' });
      }
      throw new ApiError(`Can't reach the trolley at ${hostLabel()}`, { kind: 'network', detail: err?.message });
    }

    const text = await res.text().catch(() => '');
    let data = null;
    let parsed = true;
    if (text.trim()) {
      try { data = JSON.parse(text); } catch { parsed = false; }
    }

    if (!res.ok) {
      const detail = describeDetail(data);
      throw new ApiError(detail || `Trolley returned HTTP ${res.status}`, {
        kind: 'http', status: res.status, body: data, detail,
      });
    }
    if (!parsed) {
      throw new ApiError('The trolley sent a response the app could not read', { kind: 'parse', status: res.status });
    }
    return { data, status: res.status, serverDate: res.headers.get('date') };
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener('abort', onCallerAbort);
  }
}
