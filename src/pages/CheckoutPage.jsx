import { ArrowLeft } from 'lucide-react';
import Banner from '../components/Banner.jsx';
import CartItem from '../components/CartItem.jsx';
import CartSummary from '../components/CartSummary.jsx';
import { formatClock, formatDateTime, formatDurationWords } from '../utils/dateTime.js';
import { maskCardId } from '../utils/format.js';

export default function CheckoutPage({ session, rental, cart, connection, busy, error, onBack, onConfirm }) {
  const card = maskCardId(session.cardId);
  const disabled = busy || connection !== 'connected' || !session.canCheckout;

  return (
    <>
      <button type="button" className="back" onClick={onBack} disabled={busy}>
        <ArrowLeft size={16} aria-hidden="true" /> Back to cart
      </button>
      <h1 className="page-title" tabIndex={-1} data-focus-target>Review and check out</h1>

      {error && (
        <Banner tone="danger">
          <b>Checkout didn't complete.</b> {error} Your cart is unchanged, so you can try again.
        </Banner>
      )}
      {connection !== 'connected' && !error && (
        <Banner tone="warn">Reconnecting to the trolley… checkout is available once it's back.</Banner>
      )}

      <section className="panel">
        <dl className="facts">
          {session.customerName && <div><dt>Customer</dt><dd>{session.customerName}</dd></div>}
          {card && <div><dt>RFID card</dt><dd className="num">{card}</dd></div>}
          <div><dt>Started</dt><dd>{formatDateTime(session.startedAtMs)}</dd></div>
          {rental.elapsedSeconds != null && (
            <div>
              <dt>Time so far</dt>
              <dd className="num">{formatClock(rental.elapsedSeconds)} <span className="muted">({formatDurationWords(rental.elapsedSeconds)})</span></dd>
            </div>
          )}
        </dl>
      </section>

      <section className="cart" aria-labelledby="co-items">
        <div className="cart-head"><h2 id="co-items" className="section-title">Products</h2></div>
        {cart.items.length === 0 ? (
          <div className="empty"><p>No products were scanned in this session.</p></div>
        ) : (
          <ul className="rows">{cart.items.map((i) => <CartItem key={i.key} item={i} changed={false} />)}</ul>
        )}
      </section>

      <section className="panel">
        <CartSummary productTotal={cart.productTotal} itemCount={cart.itemCount} rentalAmount={rental.charge?.amount ?? null} />
        <p className="fine-print">These amounts are current figures. The trolley calculates the final bill when you confirm.</p>
      </section>

      <div className="action-bar action-bar-stack">
        <button type="button" className="btn btn-primary btn-block" onClick={onConfirm} disabled={disabled} aria-busy={busy}>
          {busy ? (<><span className="spinner spinner-sm" aria-hidden="true" /> Checking out…</>) : 'Confirm checkout'}
        </button>
      </div>
    </>
  );
}
