import { useEffect, useRef, useState } from 'react';
import { X } from 'lucide-react';
import Banner from '../components/Banner.jsx';
import RentalTimer from '../components/RentalTimer.jsx';
import SessionStatus from '../components/SessionStatus.jsx';
import HardwareStatus from '../components/HardwareStatus.jsx';
import CartItem from '../components/CartItem.jsx';
import CartSummary from '../components/CartSummary.jsx';
import LatestScan from '../components/LatestScan.jsx';
import { formatINR, plural } from '../utils/format.js';

export default function ActiveSessionPage({ session, rental, cartState, connection, sessionStale, trolley, onCheckout }) {
  const { cart, status: cartStatus, stale: cartStale, changed, scanProblem, dismissScanProblem, latestScan } = cartState;
  const interrupted = connection !== 'connected' || sessionStale || cartStale;
  const total = cart.productTotal != null && rental.charge ? cart.productTotal + rental.charge.amount : null;

  // Announce cart changes (item count only, not the ticking timer).
  const [announce, setAnnounce] = useState('');
  const lastCount = useRef(null);
  useEffect(() => {
    if (cartStatus !== 'ready') return;
    if (lastCount.current !== null && lastCount.current !== cart.itemCount) {
      setAnnounce(`Cart updated: ${plural(cart.itemCount, 'item')}, products ${formatINR(cart.productTotal)}.`);
    }
    lastCount.current = cart.itemCount;
  }, [cart.itemCount, cart.productTotal, cartStatus]);

  const canCheckout = session.canCheckout && connection === 'connected' && !sessionStale;

  return (
    <>
      {interrupted && (
        <Banner tone="warn">
          <b>Connection to the trolley was interrupted.</b> Showing the last information received; reconnecting automatically.
        </Banner>
      )}

      <div className="session-grid">
        <div className="area-timer">
          <RentalTimer rental={rental} offline={interrupted} />
        </div>

        <div className="area-cart">
          <LatestScan scan={latestScan} />
          <section className="cart" aria-labelledby="cart-h">
            <div className="cart-head">
              <h2 id="cart-h" className="section-title">Your cart</h2>
              {cartStatus === 'ready' && <span className="count num">{plural(cart.itemCount, 'item')}</span>}
            </div>

            {scanProblem && (
              <Banner tone="warn" action={<button type="button" className="icon-btn" onClick={dismissScanProblem} aria-label="Dismiss"><X size={16} /></button>}>
                {scanProblem.message}
              </Banner>
            )}

            {cartStatus === 'loading' && <p className="muted pad">Loading your cart…</p>}
            {cartStatus === 'error' && (
              <Banner tone="danger">Couldn't load the cart. {cartState.error}</Banner>
            )}
            {cartStatus === 'ready' && cart.items.length === 0 && (
              <div className="empty">
                <p className="empty-title">Your cart is empty</p>
                <p>Scan a product's barcode at the trolley to add it.</p>
              </div>
            )}
            {cartStatus === 'ready' && cart.items.length > 0 && (
              <ul className="rows">
                {cart.items.map((item) => (
                  <CartItem key={item.key} item={item} changed={changed.has(item.key)} />
                ))}
              </ul>
            )}
            {cartStale && cartStatus === 'ready' && <p className="fine-print">Cart may be out of date until the connection returns.</p>}
          </section>

          {cartStatus !== 'loading' && (
            <section className="panel" aria-label="Totals">
              <CartSummary productTotal={cart.productTotal} itemCount={cart.itemCount} rentalAmount={rental.charge?.amount ?? null} />
            </section>
          )}
        </div>

        <div className="area-details">
          <section className="panel" aria-label="Session details">
            <SessionStatus session={session} />
          </section>
          <section className="panel" aria-labelledby="hw-h">
            <h2 id="hw-h" className="section-label">Trolley</h2>
            <HardwareStatus status={trolley} />
          </section>
        </div>
      </div>

      <p className="sr-only" aria-live="polite">{announce}</p>

      <div className="action-bar">
        <div className="action-total">
          <span className="meta-label">{interrupted ? 'Last known total' : 'Estimated total'}</span>
          <span className="action-amount num">{formatINR(total)}</span>
        </div>
        <button type="button" className="btn btn-primary" onClick={onCheckout} disabled={!canCheckout}>
          Checkout
        </button>
      </div>
    </>
  );
}
