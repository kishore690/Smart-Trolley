import { useCallback, useState } from 'react';
import { POLL_MS } from '../config.js';
import { getTrolleyStatus } from '../api/sessionApi.js';
import { usePoller } from './usePoller.js';

const UNKNOWN = { controller: { state: 'unknown' }, camera: { state: 'unknown' }, scanner: { state: 'unknown' } };

/** Hardware states exactly as GET /api/trolley/status reports them; anything else stays 'unknown'. */
export function useTrolleyStatus(enabled) {
  const [status, setStatus] = useState(UNKNOWN);

  const task = useCallback(async (signal, isCurrent) => {
    try {
      const next = await getTrolleyStatus(signal);
      if (isCurrent()) setStatus(next);
    } catch (err) {
      if (!err.isAborted && isCurrent()) setStatus(UNKNOWN); // never keep claiming hardware works
    }
  }, []);

  usePoller(task, { interval: POLL_MS.trolley, enabled });
  return enabled ? status : UNKNOWN;
}
