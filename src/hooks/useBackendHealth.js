import { useCallback, useEffect, useRef, useState } from 'react';
import { POLL_MS } from '../config.js';
import { getHealth } from '../api/sessionApi.js';
import { usePoller } from './usePoller.js';

/**
 * status: 'connecting' (no answer yet) | 'connected' | 'disconnected' - taken from GET /health.
 * `corroborated` is true while session polling is failing too; then a single failed health
 * check is enough to report Disconnected (otherwise one dropped check is tolerated).
 */
export function useBackendHealth(corroborated = false) {
  const [state, setState] = useState({ status: 'connecting', error: null, checkedAt: null });
  const failures = useRef(0);
  const corroboratedRef = useRef(corroborated);
  corroboratedRef.current = corroborated;

  const task = useCallback(async (signal, isCurrent) => {
    try {
      await getHealth(signal);
      if (!isCurrent()) return;
      failures.current = 0;
      setState({ status: 'connected', error: null, checkedAt: Date.now() });
    } catch (err) {
      if (err.isAborted || !isCurrent()) return;
      failures.current += 1;
      setState((prev) => {
        // Tolerate one dropped check after a good one; report the first-ever failure immediately.
        if (prev.status === 'connected' && failures.current < 2 && !corroboratedRef.current) return prev;
        return { status: 'disconnected', error: err.message, checkedAt: Date.now() };
      });
    }
  }, []);

  const { refresh } = usePoller(task, {
    interval: state.status === 'disconnected' ? POLL_MS.healthWhileDown : POLL_MS.health,
  });

  useEffect(() => { if (corroborated) refresh(); }, [corroborated, refresh]);

  const retry = useCallback(() => {
    setState((prev) => (prev.status === 'disconnected' ? { ...prev, status: 'connecting' } : prev));
    refresh();
  }, [refresh]);

  return { ...state, retry };
}
