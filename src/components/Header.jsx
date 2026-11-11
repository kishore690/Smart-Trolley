import { ShoppingCart } from 'lucide-react';
import ConnectionStatus from './ConnectionStatus.jsx';

export default function Header({ status }) {
  return (
    <header className="topbar">
      <div className="topbar-inner">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true"><ShoppingCart size={18} strokeWidth={2.3} /></span>
          <span className="brand-name">cartly</span>
        </div>
        <ConnectionStatus status={status} />
      </div>
    </header>
  );
}
