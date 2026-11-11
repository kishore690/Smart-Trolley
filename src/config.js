// Central runtime configuration. Everything that can change between
// environments (Wi-Fi network, Pi address, polling cadence) lives here.

// Set the Raspberry Pi address in .env; it is injected into the app at build time.
const rawBase = (import.meta.env?.VITE_API_BASE_URL ?? '').trim();

/** Base URL of the Raspberry Pi FastAPI server, without a trailing slash. */
export const API_BASE_URL = rawBase.replace(/\/+$/, '');

/**
 * How to read backend timestamps that carry no time-zone suffix
 * (e.g. Python's datetime.utcnow().isoformat()).
 *   'utc'   - treat as UTC (default; matches utcnow())
 *   'local' - treat as the phone's local time (matches datetime.now())
 */
export const NAIVE_TIMESTAMPS =
  (import.meta.env?.VITE_NAIVE_TIMESTAMPS ?? 'utc').toLowerCase() === 'local' ? 'local' : 'utc';

export const REQUEST_TIMEOUT_MS = 6000;

export const POLL_MS = {
  health: 7000,
  healthWhileDown: 4000,
  session: 1500,
  sessionBackoff: 4000,
  cart: 1500,
  trolley: 5000,
};

/** Rental pricing. The backend remains authoritative at checkout. */
export const BILLING = {
  blockSeconds: 30 * 60,
  blockFee: 20,
};
