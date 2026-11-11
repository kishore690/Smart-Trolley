import { useEffect, useRef, useCallback } from 'react';

/**
 * Sequential polling loop.
 *  - The next request is scheduled only after the previous one finished (no overlap).
 *  - `task(signal, isCurrent)` should ignore its result when `isCurrent()` is false,
 *    so an old response can never overwrite newer state.
 *  - Pauses while the page is hidden and refreshes immediately when it returns.
 *  - Everything (timer, in-flight request, listeners) is released on unmount or when disabled.
 * Returns { refresh } to force an immediate poll.
 */
export function usePoller(task, { interval, enabled = true }) {
  const taskRef = useRef(task);
  taskRef.current = task;
  const refreshRef = useRef(() => {});

  useEffect(() => {
    if (!enabled) { refreshRef.current = () => {}; return undefined; }

    let alive = true;
    let generation = 0;
    let timer = null;
    let controller = null;

    const tick = async () => {
      clearTimeout(timer);
      if (!alive || document.hidden) return; // resumed by the visibility handler
      const mine = ++generation;
      controller?.abort();
      controller = new AbortController();
      const isCurrent = () => alive && mine === generation;
      try {
        await taskRef.current(controller.signal, isCurrent);
      } catch { /* tasks report their own errors */ }
      if (isCurrent()) timer = setTimeout(tick, interval);
    };

    const onVisibility = () => { if (!document.hidden) tick(); };
    document.addEventListener('visibilitychange', onVisibility);
    refreshRef.current = tick;
    tick();

    return () => {
      alive = false;
      clearTimeout(timer);
      controller?.abort();
      document.removeEventListener('visibilitychange', onVisibility);
      refreshRef.current = () => {};
    };
  }, [enabled, interval]);

  const refresh = useCallback(() => refreshRef.current(), []);
  return { refresh };
}
