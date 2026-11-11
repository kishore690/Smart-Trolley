import { useCallback, useEffect, useRef, useState } from 'react';
import { POLL_MS } from '../config.js';
import { getCart, getLatestScan } from '../api/cartApi.js';
import { usePoller } from './usePoller.js';

const EMPTY = { items: [], itemCount: 0, productTotal: null };
const INITIAL = { status: 'loading', cart: EMPTY, error: null, stale: false, source: 'cart' };

/**
 * Read-only mirror of the backend cart, polled while a session is active.
 * The app never adds products: it only reflects what the trolley's scanner recorded.
 * `fallback` (the cart embedded in the session response) is used only if /api/cart does not exist.
 */
export function useCart({ sessionId, enabled, fallback }) {
  const [state, setState] = useState(INITIAL);
  const [changed, setChanged] = useState(() => new Set());
  const [scanProblem, setScanProblem] = useState(null);
  const [latestScan, setLatestScan] = useState(null);

  const prevQty = useRef(null);
  const scanBaseline = useRef(undefined); // undefined = first read not done yet
  const timers = useRef([]);
  const fallbackRef = useRef(fallback);
  fallbackRef.current = fallback;

  // New session (or none): drop everything tied to the previous one.
  useEffect(() => {
    setState(INITIAL);
    setChanged(new Set());
    setScanProblem(null);
    setLatestScan(null);
    prevQty.current = null;
    scanBaseline.current = undefined;
  }, [sessionId, enabled]);

  useEffect(() => () => timers.current.forEach(clearTimeout), []);

  const flash = useCallback((keys) => {
    if (keys.size === 0) return;
    setChanged(keys);
    const t = setTimeout(() => setChanged(new Set()), 1800);
    timers.current.push(t);
  }, []);

  const task = useCallback(async (signal, isCurrent) => {
    const [cartRes, scanRes] = await Promise.allSettled([getCart(signal), getLatestScan(signal)]);
    if (!isCurrent()) return;

    // Scan problems (e.g. unknown barcode) - only changes after the first read are surfaced.
    if (scanRes.status === 'fulfilled') {
      const { key, problem, scan } = scanRes.value;
      setLatestScan(scan);
      if (scanBaseline.current === undefined) scanBaseline.current = key;
      else if (key !== scanBaseline.current) {
        scanBaseline.current = key;
        if (problem) {
          setScanProblem(problem);
          const t = setTimeout(() => setScanProblem((p) => (p === problem ? null : p)), 9000);
          timers.current.push(t);
        }
      }
    }

    if (cartRes.status === 'fulfilled') {
      const cart = cartRes.value;
      const qty = new Map(cart.items.map((i) => [i.key, `${i.quantity}`]));
      if (prevQty.current) {
        const diff = new Set();
        for (const [k, q] of qty) if (prevQty.current.get(k) !== q) diff.add(k);
        flash(diff);
      }
      prevQty.current = qty;
      setState({ status: 'ready', cart, error: null, stale: false, source: 'cart' });
      return;
    }

    const err = cartRes.reason;
    if (err?.isAborted) return;
    if (err?.kind === 'http' && [404, 405, 501].includes(err.status) && fallbackRef.current) {
      setState({ status: 'ready', cart: fallbackRef.current, error: null, stale: false, source: 'session' });
      return;
    }
    setState((prev) => ({
      ...prev,
      status: prev.status === 'ready' ? 'ready' : 'error',
      stale: prev.status === 'ready',
      error: err?.message ?? 'Cart unavailable',
    }));
  }, [flash]);

  const { refresh } = usePoller(task, { interval: POLL_MS.cart, enabled });

  return { ...state, changed, scanProblem, latestScan, dismissScanProblem: () => setScanProblem(null), refresh };
}
