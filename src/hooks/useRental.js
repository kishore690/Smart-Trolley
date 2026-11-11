import { useNow } from './useNow.js';
import { resolveRental, billingBlocks, secondsUntilNextBlock } from '../utils/billing.js';

/**
 * Elapsed time and rental charge for a session, derived from the backend's real
 * started_at - never from when a component mounted - so reloads and network
 * drops cannot reset or skew it.
 * Completed sessions are frozen at ended_at.
 */
export function useRental(session, clockOffsetMs = 0) {
  const live = session?.state === 'active' && session.startedAtMs != null;
  const now = useNow(live);
  if (!session || session.startedAtMs == null) {
    return { elapsedSeconds: null, charge: null, blocks: null, nextIncreaseIn: null };
  }
  const endMs = session.endedAtMs ?? (now + clockOffsetMs);
  const elapsedSeconds = Math.max(0, Math.floor((endMs - session.startedAtMs) / 1000));
  return {
    elapsedSeconds,
    charge: resolveRental(elapsedSeconds, session.usageFee),
    blocks: billingBlocks(elapsedSeconds),
    nextIncreaseIn: live ? secondsUntilNextBlock(elapsedSeconds) : null,
  };
}
