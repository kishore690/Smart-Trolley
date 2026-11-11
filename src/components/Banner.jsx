import { TriangleAlert, Info } from 'lucide-react';

export default function Banner({ tone = 'warn', children, action }) {
  const Icon = tone === 'info' ? Info : TriangleAlert;
  return (
    <div className={`banner banner-${tone}`} role={tone === 'danger' ? 'alert' : 'status'}>
      <Icon size={18} aria-hidden="true" />
      <div className="banner-text">{children}</div>
      {action}
    </div>
  );
}
