import { Play, WifiOff, RefreshCw } from 'lucide-react';
import StateMessage from '../components/StateMessage.jsx';
import HardwareStatus from '../components/HardwareStatus.jsx';
import Banner from '../components/Banner.jsx';
import { BILLING } from '../config.js';
import { hostLabel } from '../api/client.js';
import { formatINR } from '../utils/format.js';
import LatestScan from '../components/LatestScan.jsx';

/** Shown whenever there is no active session: loading, unreachable, or ready to start. */
export default function HomePage({ health, sessionState, trolley, cartState, onRetry, onStart, startBusy, startPending, startError }) {
  const unreachable = health.status === 'disconnected' || sessionState.status === 'error';
  const loading = !unreachable && (health.status === 'connecting' || sessionState.status === 'loading');

  if (loading) {
    return (
      <StateMessage icon={<span className="spinner" />} title="Connecting to your trolley">
        <p>Looking for the trolley at <span className="num">{hostLabel()}</span>…</p>
      </StateMessage>
    );
  }

  if (unreachable) {
    const error = sessionState.error ?? health.error;
    return (
      <StateMessage
        icon={<WifiOff size={28} />}
        tone="danger"
        title="Can't reach the trolley"
        action={<button type="button" className="btn btn-secondary" onClick={onRetry}><RefreshCw size={16} aria-hidden="true" /> Try again</button>}
      >
        <p>Make sure the trolley is switched on and your phone is on the same Wi-Fi network. The app will reconnect on its own.</p>
        {error && <p className="state-detail">Last error: {error}</p>}
        <p className="state-detail num">Trying {hostLabel()}</p>
      </StateMessage>
    );
  }

  return (
    <>
      <StateMessage
        icon={startPending ? <span className="spinner" /> : <Play size={30} />}
        title={startPending ? 'Starting your trolley' : 'Ready to start'}
        pulse={!startPending}
        action={(
          <button type="button" className="btn btn-primary" onClick={onStart} disabled={startBusy || startPending} aria-busy={startBusy || startPending}>
            {startBusy || startPending ? <span className="spinner spinner-sm" aria-hidden="true" /> : <Play size={16} aria-hidden="true" />}
            {startBusy || startPending ? 'Starting trolley…' : 'Start Trolley'}
          </button>
        )}
      >
        <p>Start a shopping session from this app. The trolley will look for you with its camera.</p>
        {startError && <Banner tone="danger">Could not start the trolley. {startError}</Banner>}
      </StateMessage>

      <section className="panel" aria-labelledby="trolley-h">
        <h2 id="trolley-h" className="section-label">Trolley</h2>
        <HardwareStatus status={trolley} />
      </section>

      <LatestScan scan={cartState?.latestScan} />

      <p className="fine-print">
        Rental is {formatINR(BILLING.blockFee)} for the first 30 minutes, then {formatINR(BILLING.blockFee)} for each additional 30 minutes.
      </p>
    </>
  );
}
