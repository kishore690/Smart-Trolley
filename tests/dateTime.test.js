import test from 'node:test';
import assert from 'node:assert/strict';
import { parseTimestamp, formatClock, formatDurationWords } from '../src/utils/dateTime.js';

const T = Date.UTC(2026, 9, 13, 10, 0, 0);

test('timestamps with a zone are exact', () => {
  assert.equal(parseTimestamp('2026-10-13T10:00:00Z'), T);
  assert.equal(parseTimestamp('2026-10-13T15:30:00+05:30'), T);
  assert.equal(parseTimestamp('2026-10-13T15:30:00+0530'), T);
});
test('naive timestamps are UTC by default and local on request', () => {
  assert.equal(parseTimestamp('2026-10-13T10:00:00', 'utc'), T);
  assert.equal(parseTimestamp('2026-10-13 10:00:00', 'utc'), T);
  assert.equal(parseTimestamp('2026-10-13T10:00:00', 'local'), new Date(2026, 9, 13, 10, 0, 0).getTime());
});
test('python microseconds and epoch values', () => {
  assert.equal(parseTimestamp('2026-10-13T10:00:00.123456', 'utc'), T + 123);
  assert.equal(parseTimestamp(T / 1000), T);
  assert.equal(parseTimestamp(T), T);
  assert.equal(parseTimestamp(String(T / 1000)), T);
});
test('garbage is null, not NaN', () => {
  for (const v of [null, undefined, '', 'yesterday', {}, [], 'not a date']) assert.equal(parseTimestamp(v), null);
});
test('clock and words', () => {
  assert.equal(formatClock(0), '00:00:00');
  assert.equal(formatClock(754), '00:12:34');
  assert.equal(formatClock(3725), '01:02:05');
  assert.equal(formatClock(null), '00:00:00');
  assert.equal(formatDurationWords(3725), '1 hr 2 min');
  assert.equal(formatDurationWords(45), '45 sec');
});
