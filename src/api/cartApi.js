import { request, ApiError } from './client.js';
import { normalizeCart, normalizeScanProblem, scanKey } from './adapters.js';

/** Read-only: the cart is filled by the trolley's barcode scanner, never by this app. */
export async function getCart(signal) {
  const { data } = await request('/api/cart', { signal });
  return normalizeCart(data);
}

/** Latest scan as the backend reports it. A 404 just means nothing was scanned yet. */
export async function getLatestScan(signal) {
  try {
    const { data } = await request('/api/scans/latest', { signal });
    const scan = data && typeof data === 'object'
      ? ('scan' in data ? data.scan : 'latest' in data ? data.latest : 'data' in data ? data.data : data)
      : null;
    return { key: scanKey(data), problem: normalizeScanProblem(data), scan };
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) return { key: null, problem: null, scan: null };
    throw err;
  }
}
