import { NAIVE_TIMESTAMPS } from '../config.js';

/** Parse a backend timestamp (ISO string, epoch seconds or ms) into epoch ms, or null. */
export function parseTimestamp(value, naive = NAIVE_TIMESTAMPS) {
  if (value == null || value === '') return null;
  if (value instanceof Date) return Number.isNaN(value.getTime()) ? null : value.getTime();

  if (typeof value === 'number' || (typeof value === 'string' && /^\d+(\.\d+)?$/.test(value.trim()))) {
    const n = Number(value);
    if (!Number.isFinite(n)) return null;
    return n > 1e11 ? Math.round(n) : Math.round(n * 1000); // ms vs seconds
  }
  if (typeof value !== 'string') return null;

  let s = value.trim();
  if (/^\d{4}-\d{2}-\d{2} \d/.test(s)) s = s.replace(' ', 'T');
  s = s.replace(/(\.\d{3})\d+/, '$1'); // microseconds -> milliseconds
  s = s.replace(/([+-]\d{2})(\d{2})$/, '$1:$2'); // +0530 -> +05:30
  const hasZone = /(Z|[+-]\d{2}:\d{2})$/i.test(s);
  if (!hasZone && naive === 'utc' && /T\d/.test(s)) s += 'Z';
  const ms = Date.parse(s);
  return Number.isNaN(ms) ? null : ms;
}

const pad = (n) => String(n).padStart(2, '0');

/** 3725 -> "01:02:05" */
export function formatClock(totalSeconds) {
  const s = Math.max(0, Math.floor(Number.isFinite(totalSeconds) ? totalSeconds : 0));
  return `${pad(Math.floor(s / 3600))}:${pad(Math.floor((s % 3600) / 60))}:${pad(s % 60)}`;
}

/** 3725 -> "1 hr 2 min" (used on the bill) */
export function formatDurationWords(totalSeconds) {
  const s = Math.max(0, Math.floor(Number.isFinite(totalSeconds) ? totalSeconds : 0));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (h > 0) return `${h} hr ${m} min`;
  if (m > 0) return `${m} min ${s % 60 ? `${s % 60} sec` : ''}`.trim();
  return `${s} sec`;
}

const timeFmt = new Intl.DateTimeFormat('en-IN', { hour: 'numeric', minute: '2-digit', hour12: true });
const dateTimeFmt = new Intl.DateTimeFormat('en-IN', {
  day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit', hour12: true,
});

export const formatTime = (ms) => (Number.isFinite(ms) ? timeFmt.format(ms) : '—');
export const formatDateTime = (ms) => (Number.isFinite(ms) ? dateTimeFmt.format(ms) : '—');
