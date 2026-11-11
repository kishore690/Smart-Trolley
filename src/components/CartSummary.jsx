import { formatINR, plural } from '../utils/format.js';

/** Product subtotal + rental = estimated total. The trolley calculates the final bill at checkout. */
export default function CartSummary({ productTotal, itemCount, rentalAmount, label = 'Estimated total' }) {
  const total = productTotal != null && rentalAmount != null ? productTotal + rentalAmount : null;
  return (
    <dl className="summary">
      <div>
        <dt>Products <span className="muted">({plural(itemCount, 'item')})</span></dt>
        <dd className="num">{formatINR(productTotal)}</dd>
      </div>
      <div>
        <dt>Trolley rental</dt>
        <dd className="num">{formatINR(rentalAmount)}</dd>
      </div>
      <div className="summary-total">
        <dt>{label}</dt>
        <dd className="num">{formatINR(total)}</dd>
      </div>
    </dl>
  );
}
