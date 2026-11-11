const LABELS = { connected: 'Connected', connecting: 'Connecting', disconnected: 'Disconnected' };

export default function ConnectionStatus({ status }) {
  const label = LABELS[status];
  return (
    <span className={`conn conn-${status}`} role="status">
      <span className="conn-dot" aria-hidden="true" />
      <span>Trolley API {label.toLowerCase()}</span>
    </span>
  );
}
