import { Check, ExternalLink } from 'lucide-react';
import Banner from '../components/Banner.jsx';
import CartItem from '../components/CartItem.jsx';
import { API_BASE_URL } from '../config.js';
import { buildFinalBill } from '../utils/finalBill.js';
import { formatDateTime, formatDurationWords } from '../utils/dateTime.js';
import { formatINR, maskCardId } from '../utils/format.js';

function receiptHref(url) {
  try { return new URL(url, API_BASE_URL || window.location.origin).href; } catch { return null; }
}

const NOTICES = {
  checkout: 'Checkout was accepted, but the trolley did not return a final bill. The amounts below are the last ones the app saw.',
  ended: 'This session ended at the trolley and its final bill was not available to the app. The amounts below are the last ones the app saw, not a confirmed total.',
  already: 'This session had already been checked out. The amounts below are the last ones the app saw.',
};

export default function SessionCompletePage({ completion, onDone }) {
  const bill = buildFinalBill(completion);
  const card = maskCardId(bill.cardId);
  const href = bill.receiptUrl ? receiptHref(bill.receiptUrl) : null;

  return (
    <>
      <section className="done-head">
        <div className="done-icon" aria-hidden="true"><Check size={26} strokeWidth={2.4} /></div>
        <h1 className="page-title" tabIndex={-1} data-focus-target>
          {completion.kind === 'checkout' && bill.isFinal ? 'Checkout complete' : 'Session ended'}
        </h1>
        <p className="muted">{bill.isFinal ? 'Final amount due' : 'Last known amount'}</p>
        <p className="done-amount num">{formatINR(bill.totalDue)}</p>
      </section>

      {!bill.isFinal && <Banner tone="warn">{NOTICES[completion.kind] ?? NOTICES.ended}</Banner>}
      {completion.kind === 'already' && bill.isFinal && <Banner tone="info">This session had already been checked out.</Banner>}

      <section className="panel">
        <dl className="facts">
          {bill.reference && <div><dt>Session</dt><dd className="num">{bill.reference}</dd></div>}
          {bill.customerName && <div><dt>Customer</dt><dd>{bill.customerName}</dd></div>}
          {card && <div><dt>RFID card</dt><dd className="num">{card}</dd></div>}
          <div><dt>Started</dt><dd>{formatDateTime(bill.startedAtMs)}</dd></div>
          <div><dt>Ended</dt><dd>{formatDateTime(bill.endedAtMs)}</dd></div>
          <div><dt>Time on trolley</dt><dd>{bill.durationSeconds != null ? formatDurationWords(bill.durationSeconds) : '—'}</dd></div>
        </dl>
      </section>

      <section className="cart" aria-labelledby="bill-items">
        <div className="cart-head"><h2 id="bill-items" className="section-title">Products</h2></div>
        {bill.items.length === 0 ? (
          <div className="empty"><p>No products on this bill.</p></div>
        ) : (
          <ul className="rows">{bill.items.map((i) => <CartItem key={i.key} item={i} changed={false} />)}</ul>
        )}
      </section>

      <section className="panel">
        <dl className="summary">
          <div><dt>Product subtotal</dt><dd className="num">{formatINR(bill.productTotal)}</dd></div>
          <div>
            <dt>Trolley rental{bill.billingPeriods != null && <span className="muted"> ({bill.billingPeriods} × 30 min)</span>}</dt>
            <dd className="num">{formatINR(bill.rentalFee)}</dd>
          </div>
          <div className="summary-total"><dt>{bill.isFinal ? 'Amount due' : 'Last known total'}</dt><dd className="num">{formatINR(bill.totalDue)}</dd></div>
        </dl>
        {bill.rentalFee != null && !bill.rentalConfirmed && (
          <p className="fine-print">Rental charge calculated by the app from the session times; not confirmed by the trolley.</p>
        )}
      </section>

      <div className="action-bar action-bar-stack">
        {href && (
          <a className="btn btn-secondary btn-block" href={href} target="_blank" rel="noopener noreferrer">
            <ExternalLink size={16} aria-hidden="true" /> Open receipt
          </a>
        )}
        <button type="button" className="btn btn-primary btn-block" onClick={onDone}>Done</button>
      </div>
    </>
  );
}
