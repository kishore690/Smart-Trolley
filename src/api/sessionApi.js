import { request, ApiError } from './client.js';
import { normalizeSession, normalizeTrolleyStatus, normalizeBill } from './adapters.js';
import { parseTimestamp } from '../utils/dateTime.js';

export async function getHealth(signal) {
  const { data } = await request('/health', { signal, timeoutMs: 4000 });
  const status = data && typeof data === 'object' ? data.status : null;
  if (typeof status === 'string' && !/^(ok|healthy|up|running|alive)$/i.test(status)) {
    throw new ApiError(`Backend reported status “${status}”`, { kind: 'http', status: 200 });
  }
  return true;
}

export async function getTrolleyStatus(signal) {
  const { data } = await request('/api/trolley/status', { signal });
  return normalizeTrolleyStatus(data);
}

/** Start a new trolley session from the customer app. */
export async function startSession(signal) {
  const { data } = await request('/api/session/start', {
    method: 'POST',
    signal,
    timeoutMs: 8000,
  });
  return data;
}

/**
 * Resolves { session, serverTimeMs }. `session === null` means the backend answered
 * and there is no active session. Network/HTTP failures throw - they are never "no session".
 */
export async function getActiveSession(signal) {
  try {
    const { data, serverDate } = await request('/api/session/active', { signal });
    const session = normalizeSession(data);
    // serverTimeMs changes on every response, so it is kept out of the session object
    // (otherwise every poll would look like a session change).
    return {
      session: session ? { ...session, serverTimeMs: null } : null,
      serverTimeMs: session?.serverTimeMs ?? parseTimestamp(serverDate),
    };
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) {
      // FastAPI's own "route does not exist" body is exactly {"detail":"Not Found"}.
      // Anything else on a 404 is the backend saying there is no active session.
      if (err.detail === 'Not Found') {
        throw new ApiError('The trolley backend has no /api/session/active endpoint', { kind: 'http', status: 404 });
      }
      return { session: null, serverTimeMs: null };
    }
    throw err;
  }
}

/** Real checkout. Never called automatically. */
export async function checkout(signal) {
  const { data } = await request('/api/checkout', {
    method: 'POST',
    signal,
    timeoutMs: 12000,
  });
  return { bill: normalizeBill(data), raw: data };
}
