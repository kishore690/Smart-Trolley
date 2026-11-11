import { formatDateTime } from '../utils/dateTime.js';
import { maskCardId } from '../utils/format.js';

export default function SessionStatus({ session }) {
  const card = maskCardId(session.cardId);
  return (
    <dl className="facts">
      {session.customerName && (<div><dt>Customer</dt><dd>{session.customerName}</dd></div>)}
      {card && (<div><dt>RFID card</dt><dd className="num">{card}</dd></div>)}
      <div><dt>Started</dt><dd>{formatDateTime(session.startedAtMs)}</dd></div>
    </dl>
  );
}
