import { useCallback, useState } from 'react';
import { POLL_MS } from '../config.js';
import { getActiveSession } from '../api/sessionApi.js';
import { usePoller } from './usePoller.js';

const INITIAL = {
  status: 'loading', // 'loading' | 'ready' | 'error'
  session: null,
  error: null,
  stale: false,      // last poll failed but earlier data is still shown
  failures: 0,
  clockOffsetMs: 0,
  lastSuccessAt: null,
};

/**
 * The single authoritative session state.
 * "No active session" (status 'ready', session null) is a real backend answer;
 * a failed request is 'error' (or stale data) and is never confused with it.
 */
export function useActiveSession() {
  const [state, setState] = useState(INITIAL);

  const task = useCallback(async (signal, isCurrent) => {
    try {
      const { session, serverTimeMs } = await getActiveSession(signal);
      if (!isCurrent()) return;

      // Correct for a phone/Pi clock difference, but ignore sub-3s jitter.
      let offset = serverTimeMs != null ? serverTimeMs - Date.now() : 0;
      if (Math.abs(offset) < 3000) offset = 0;

      const json = JSON.stringify(session);
      setState((prev) => {
        const sameSession = JSON.stringify(prev.session) === json;
        const nextOffset = serverTimeMs != null ? offset : prev.clockOffsetMs;
        if (prev.status === 'ready' && !prev.stale && sameSession && prev.clockOffsetMs === nextOffset) return prev;
        return {
          status: 'ready',
          session: sameSession ? prev.session : session,
          error: null,
          stale: false,
          failures: 0,
          clockOffsetMs: nextOffset,
          lastSuccessAt: Date.now(),
        };
      });
    } catch (err) {
      if (err.isAborted || !isCurrent()) return;
      setState((prev) => ({
        ...prev,
        status: prev.status === 'ready' ? 'ready' : 'error',
        stale: prev.status === 'ready',
        error: err.message,
        failures: prev.failures + 1,
      }));
    }
  }, []);

  const { refresh } = usePoller(task, {
    interval: state.failures >= 3 ? POLL_MS.sessionBackoff : POLL_MS.session,
  });

  return { ...state, refresh };
}
