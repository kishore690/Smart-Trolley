import { BILLING } from '../config.js';
import { formatClock } from '../utils/dateTime.js';
import { formatINR } from '../utils/format.js';

export default function RentalTimer({ rental, offline = false }) {
  const { elapsedSeconds, charge, nextIncreaseIn } = rental;
  if (elapsedSeconds == null) return null;
  const estimated = offline || charge.source === 'estimate';

  return (
    <section className="timer" aria-label="Trolley rental">
      <div className="timer-head">
        <h2 className="section-label">Time on trolley</h2>
        <span className="badge badge-active"><span className="badge-dot" aria-hidden="true" />Active</span>
      </div>
      <p className="timer-value num" role="timer" aria-label={`Elapsed ${formatClock(elapsedSeconds)}`}>
        {formatClock(elapsedSeconds)}
      </p>
      <div className="timer-meta">
        <div>
          <p className="meta-label">Rental charge</p>
          <p className="meta-value num">{formatINR(charge.amount)}</p>
          <p className="meta-note">
            {estimated ? 'Estimated from start time' : 'Confirmed by trolley'}
            {estimated && !offline && charge.serverAmount != null && ` · trolley reports ${formatINR(charge.serverAmount)}`}
            {offline && ' · trolley offline'}
          </p>
        </div>
        <div>
          <p className="meta-label">Next increase</p>
          <p className="meta-value num">{formatINR(charge.amount + BILLING.blockFee)}</p>
          <p className="meta-note num">in {formatClock(nextIncreaseIn).replace(/^00:/, '')}</p>
        </div>
      </div>
    </section>
  );
}
