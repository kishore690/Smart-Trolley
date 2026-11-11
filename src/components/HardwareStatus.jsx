import { Cpu, Camera, ScanBarcode } from 'lucide-react';

const ROWS = [
  { key: 'controller', label: 'Trolley controller', Icon: Cpu, ok: 'Connected', off: 'Not connected' },
  { key: 'camera', label: 'Person following', Icon: Camera, ok: 'Active', off: 'Not active' },
  { key: 'scanner', label: 'Barcode scanner', Icon: ScanBarcode, ok: 'Connected', off: 'Not connected' },
];

/** Shows only what GET /api/trolley/status reports; everything else is "Not reported". */
export default function HardwareStatus({ status }) {
  return (
    <>
      <ul className="hw" aria-label="Trolley hardware">
        {ROWS.map(({ key, label, Icon, ok, off }) => {
          const s = status[key] ?? { state: 'unknown' };
          const text = s.state === 'ok' ? ok : s.state === 'off' ? off : 'Not reported';
          return (
            <li key={key} className={`hw-row hw-${s.state}`}>
              <Icon size={18} aria-hidden="true" />
              <span className="hw-label">{label}</span>
              <span className="hw-value"><span className="hw-dot" aria-hidden="true" />{text}</span>
            </li>
          );
        })}
      </ul>
      {status.hardwareNote && <p className="fine-print">{status.hardwareNote}</p>}
    </>
  );
}
