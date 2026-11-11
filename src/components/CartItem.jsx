import { memo } from 'react';
import { formatINR } from '../utils/format.js';

function CartItem({ item, changed }) {
  const code = [item.productId, item.barcode].filter(Boolean).join(' · ');
  return (
    <li className={`row${changed ? ' row-changed' : ''}`}>
      <div className="row-main">
        <p className="row-name">{item.name}</p>
        {code && <p className="row-code num">{code}</p>}
        <p className="row-calc num">
          {item.quantity} × {formatINR(item.unitPrice)}
        </p>
      </div>
      <p className="row-total num">{formatINR(item.lineTotal)}</p>
    </li>
  );
}

export default memo(CartItem);
