import { Barcode } from 'lucide-react';
import { formatINR } from '../utils/format.js';
import { parseTimestamp } from '../utils/dateTime.js';

function scanLabel(scan) {
  const status = String(scan.status ?? '').toLowerCase();
  if (scan.cart_added === true) return 'Added to cart';
  if (scan.cart_added === false) return 'Matched, but not added';
  if (['unknown_product', 'unknown', 'not_found', 'invalid', 'error'].includes(status)) return 'Barcode not recognised';
  if (scan.product) return 'Product matched';
  return 'Scan received';
}

export default function LatestScan({ scan }) {
  const product = scan?.product;
  const timestamp = parseTimestamp(scan?.timestamp ?? scan?.scanned_at ?? scan?.created_at);

  return (
    <section className="panel latest-scan" aria-labelledby="latest-scan-h" aria-live="polite">
      <div className="latest-scan-head">
        <Barcode size={20} aria-hidden="true" />
        <h2 id="latest-scan-h" className="section-label">Latest barcode scan</h2>
      </div>
      {!scan ? (
        <p className="muted">Waiting for a barcode scan from the trolley.</p>
      ) : (
        <>
          <span className={`scan-badge ${product ? 'scan-badge-match' : 'scan-badge-unknown'}`}>{scanLabel(scan)}</span>
          <div className="latest-scan-product">
            <strong>{product?.name ?? 'Unrecognised product'}</strong>
            {product?.price != null && <span className="num">{formatINR(product.price)}</span>}
          </div>
          <p className="scan-barcode num">Barcode: {scan.barcode ?? 'Not reported'}</p>
          {scan.cart_added == null && product && (
            <p className="fine-print">The backend has not reported whether this scan was added to the cart.</p>
          )}
          {timestamp != null && <time className="fine-print" dateTime={new Date(timestamp).toISOString()}>{new Date(timestamp).toLocaleString()}</time>}
        </>
      )}
    </section>
  );
}
