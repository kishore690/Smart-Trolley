const inr0 = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', minimumFractionDigits: 0, maximumFractionDigits: 0 });
const inr2 = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', minimumFractionDigits: 2, maximumFractionDigits: 2 });

/** ₹20, ₹32.50. Returns an em dash for unknown values instead of inventing a number. */
export function formatINR(value) {
  if (value == null || !Number.isFinite(Number(value))) return '—';
  const n = Number(value);
  return Number.isInteger(n) ? inr0.format(n) : inr2.format(n);
}

/** Show only the last four characters of a card identifier. */
export function maskCardId(id) {
  if (id == null || id === '') return null;
  const s = String(id).replace(/\s+/g, '');
  return s.length <= 4 ? '••••' : `•••• ${s.slice(-4).toUpperCase()}`;
}

export function initials(name) {
  if (!name) return '';
  return name.trim().split(/\s+/).slice(0, 2).map((p) => p[0]?.toUpperCase() ?? '').join('');
}

export const plural = (n, one, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;
