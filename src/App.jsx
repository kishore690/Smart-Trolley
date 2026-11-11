import { useCallback, useEffect, useRef, useState } from 'react';
import Header from './components/Header.jsx';
import HomePage from './pages/HomePage.jsx';
import ActiveSessionPage from './pages/ActiveSessionPage.jsx';
import CheckoutPage from './pages/CheckoutPage.jsx';
import SessionCompletePage from './pages/SessionCompletePage.jsx';
import { useBackendHealth } from './hooks/useBackendHealth.js';
import { useActiveSession } from './hooks/useActiveSession.js';
import { useCart } from './hooks/useCart.js';
import { useRental } from './hooks/useRental.js';
import { useTrolleyStatus } from './hooks/useTrolleyStatus.js';
import { checkout } from './api/sessionApi.js';

const keyOf = (s) => (s ? s.id ?? `t${s.startedAtMs}` : null);

export default function App() {
  const sess = useActiveSession();
  const health = useBackendHealth(sess.stale || sess.status === 'error');
  const trolley = useTrolleyStatus(health.status === 'connected');

  const session = sess.session;
  const isActive = session?.state === 'active';
  const sessionKey = isActive ? keyOf(session) : null;

  const rental = useRental(isActive ? session : null, sess.clockOffsetMs);
  // Poll the backend scan feed even before RFID starts a session, so the home screen
  // can show the trolley's latest physical barcode scan.
  const cartState = useCart({ sessionId: sessionKey, enabled: health.status === 'connected', fallback: session?.cart ?? null });

  const [checkoutOpen, setCheckoutOpen] = useState(false);
  const [checkoutUi, setCheckoutUi] = useState({ busy: false, error: null });
  const [completion, setCompletion] = useState(null);   // { kind, bill, session, cart }
  const [dismissedKey, setDismissedKey] = useState(null);
  const checkoutLock = useRef(false);                   // blocks duplicate submissions
  const snapshot = useRef(null);                        // last live { session, cart } the app saw

  // Detect a session that ended without this app checking it out. Never triggers a checkout.
  useEffect(() => {
    if (sess.status !== 'ready' || sess.stale || completion || checkoutUi.busy) return;
    const snap = snapshot.current;

    if (session?.state === 'completed') {
      const k = keyOf(session);
      if (k === dismissedKey) return;
      const cart = snap && keyOf(snap.session) === k ? snap.cart : null;
      snapshot.current = null;
      setCompletion({ kind: 'ended', bill: null, session, cart });
    } else if (!isActive && snap) {
      snapshot.current = null;
      setCompletion({ kind: 'ended', bill: null, session: snap.session, cart: snap.cart });
    } else if (isActive && snap && keyOf(snap.session) !== sessionKey) {
      snapshot.current = null; // a different card took over the trolley
      setCompletion({ kind: 'ended', bill: null, session: snap.session, cart: snap.cart });
    }
  }, [session, isActive, sessionKey, sess.status, sess.stale, completion, checkoutUi.busy, dismissedKey]);

  // Remember the last live session + cart, so an ended session can still be summarised honestly.
  // (Declared after the detection effect so that effect sees the previous session first.)
  useEffect(() => {
    if (!isActive) return;
    const prev = snapshot.current;
    const sameSession = prev && keyOf(prev.session) === sessionKey;
    snapshot.current = {
      session,
      cart: cartState.status === 'ready' ? cartState.cart : sameSession ? prev.cart : null,
    };
  }, [isActive, session, sessionKey, cartState.status, cartState.cart]);

  useEffect(() => { if (!isActive) setCheckoutOpen(false); }, [isActive]);

  const handleConfirmCheckout = useCallback(async () => {
    if (checkoutLock.current || !isActive) return;
    checkoutLock.current = true;
    setCheckoutUi({ busy: true, error: null });
    const liveSession = session;
    const liveCart = cartState.cart;
    try {
      const { bill } = await checkout();
      snapshot.current = null;
      setCompletion({ kind: 'checkout', bill, session: liveSession, cart: liveCart });
      setCheckoutOpen(false);
      setCheckoutUi({ busy: false, error: null });
      sess.refresh();
    } catch (err) {
      if (err.kind === 'http' && (err.status === 409 || /already/i.test(err.message))) {
        snapshot.current = null;
        setCompletion({ kind: 'already', bill: null, session: liveSession, cart: liveCart });
        setCheckoutOpen(false);
        setCheckoutUi({ busy: false, error: null });
        sess.refresh();
      } else {
        const unsure = err.isConnectivity ? ' The request may not have reached the trolley.' : '';
        setCheckoutUi({ busy: false, error: `${err.message}.${unsure}` });
        sess.refresh();
      }
    } finally {
      checkoutLock.current = false;
    }
  }, [isActive, session, cartState.cart, sess]);

  const handleDone = useCallback(() => {
    if (completion?.session) setDismissedKey(keyOf(completion.session));
    snapshot.current = null;
    setCompletion(null);
    setCheckoutUi({ busy: false, error: null });
  }, [completion]);

  const view = completion ? 'complete' : isActive ? (checkoutOpen ? 'checkout' : 'session') : 'home';

  // Move focus to the new screen's heading when the screen changes (not on first paint).
  const mainRef = useRef(null);
  const firstView = useRef(true);
  useEffect(() => {
    if (firstView.current) { firstView.current = false; return; }
    const target = mainRef.current?.querySelector('[data-focus-target]') ?? mainRef.current;
    target?.focus({ preventScroll: true });
    window.scrollTo({ top: 0 });
  }, [view]);

  return (
    <div className="app">
      <Header status={health.status} />
      <main className="main" key={view} ref={mainRef} tabIndex={-1} data-view={view}>
        {view === 'home' && (
          <HomePage
            health={health}
            sessionState={sess}
            trolley={trolley}
            cartState={cartState}
            onRetry={() => { health.retry(); sess.refresh(); }}
          />
        )}
        {view === 'session' && (
          <ActiveSessionPage
            session={session}
            rental={rental}
            cartState={cartState}
            connection={health.status}
            sessionStale={sess.stale}
            trolley={trolley}
            onCheckout={() => setCheckoutOpen(true)}
          />
        )}
        {view === 'checkout' && (
          <CheckoutPage
            session={session}
            rental={rental}
            cart={cartState.cart}
            connection={health.status}
            busy={checkoutUi.busy}
            error={checkoutUi.error}
            onBack={() => { setCheckoutOpen(false); setCheckoutUi({ busy: false, error: null }); }}
            onConfirm={handleConfirmCheckout}
          />
        )}
        {view === 'complete' && <SessionCompletePage completion={completion} onDone={handleDone} />}
      </main>
    </div>
  );
}
