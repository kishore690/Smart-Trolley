import { BILLING } from '../config.js';

const clean = (s) => (Number.isFinite(s) ? Math.max(0, s) : 0);

/** Number of 30-minute billing blocks started: max(1, ceil(elapsed / 1800)). */
export function billingBlocks(elapsedSeconds) {
  return Math.max(1, Math.ceil(clean(elapsedSeconds) / BILLING.blockSeconds));
}

/** rental_charge = max(1, ceil(elapsed_seconds / 1800)) * 20 */
export function rentalCharge(elapsedSeconds) {
  return billingBlocks(elapsedSeconds) * BILLING.blockFee;
}

/** Seconds until the charge next increases. */
export function secondsUntilNextBlock(elapsedSeconds) {
  const s = clean(elapsedSeconds);
  return Math.max(0, billingBlocks(s) * BILLING.blockSeconds - s);
}

/**
 * Decide what rental charge to show while a session is live.
 *  - server value agrees with the rule      -> shown as confirmed by the trolley
 *  - no server value / server value differs -> locally calculated, labelled estimate
 */
export function resolveRental(elapsedSeconds, serverFee) {
  const estimate = rentalCharge(elapsedSeconds);
  const hasServer = Number.isFinite(serverFee);
  if (hasServer && serverFee === estimate) {
    return { amount: estimate, source: 'server', serverAmount: serverFee };
  }
  return { amount: estimate, source: 'estimate', serverAmount: hasServer ? serverFee : null };
}
