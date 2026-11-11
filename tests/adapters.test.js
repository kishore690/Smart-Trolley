import test from 'node:test';
import assert from 'node:assert/strict';
import { normalizeSession, normalizeCart, normalizeBill, normalizeTrolleyStatus, normalizeScanProblem } from '../src/api/adapters.js';
import { buildFinalBill } from '../src/utils/finalBill.js';

const S = { session_id: 'S1', card_id: 'AB12CD34', customer: { name: 'Asha' }, started_at: '2026-10-13T10:00:00Z', status: 'active' };

test('session: bare object, wrapper, and every "no session" shape', () => {
  assert.equal(normalizeSession(S).customerName, 'Asha');
  assert.equal(normalizeSession({ session: S }).id, 'S1');
  assert.equal(normalizeSession({ active_session: S }).state, 'active');
  for (const none of [null, {}, { session: null }, { active: false }, { status: 'no_active_session' }, [], 'x']) {
    assert.equal(normalizeSession(none), null, JSON.stringify(none));
  }
});
test('session: completed detection and string customer', () => {
  assert.equal(normalizeSession({ ...S, status: 'completed' }).state, 'completed');
  assert.equal(normalizeSession({ ...S, ended_at: '2026-10-13T11:00:00Z' }).state, 'completed');
  assert.equal(normalizeSession({ ...S, customer: 'Ravi' }).customerName, 'Ravi');
  assert.equal(normalizeSession({ session_id: 'S2', started_at: S.started_at }).customerName, null);
});
test('session: billing fields stay null when absent', () => {
  const s = normalizeSession(S);
  assert.equal(s.usageFee, null); assert.equal(s.totalDue, null); assert.equal(s.cart, null);
  const f = normalizeSession({ ...S, usage_fee: 40, product_total: 150, billing_periods: 2, total_due: 190 });
  assert.deepEqual([f.usageFee, f.productTotal, f.billingPeriods, f.totalDue], [40, 150, 2, 190]);
});

test('cart: array, wrapper, line totals derived only from real prices', () => {
  const a = normalizeCart([{ product_id: 'P001', barcode: '890100000001', name: 'Classic Biscuits', price: 30, quantity: 2 }]);
  assert.equal(a.items[0].lineTotal, 60); assert.equal(a.productTotal, 60); assert.equal(a.itemCount, 2);
  const b = normalizeCart({ items: [{ id: 'P002', name: 'Chips', unit_price: 20, qty: 1, subtotal: 20 }], product_total: 20, item_count: 1 });
  assert.equal(b.productTotal, 20);
  const c = normalizeCart({ items: [{ name: 'Mystery', quantity: 1 }] });
  assert.equal(c.items[0].unitPrice, null); assert.equal(c.items[0].lineTotal, null); assert.equal(c.productTotal, null);
  assert.deepEqual(normalizeCart([]), { items: [], itemCount: 0, productTotal: 0 });
  assert.deepEqual(normalizeCart(null).items, []);
});

test('trolley status: only reported values count', () => {
  const t = normalizeTrolleyStatus({ controller_connected: true, camera: 'following', barcode_scanner: { connected: false } });
  assert.equal(t.controller.state, 'ok'); assert.equal(t.camera.state, 'ok'); assert.equal(t.scanner.state, 'off');
  const none = normalizeTrolleyStatus({ status: 'ok' });
  assert.deepEqual([none.controller.state, none.camera.state, none.scanner.state], ['unknown', 'unknown', 'unknown']);
  const reported = normalizeTrolleyStatus({ scanner_ready: false, hardware_note: 'Scanner not integrated' });
  assert.equal(reported.scanner.state, 'unknown');
  assert.equal(reported.hardwareNote, 'Scanner not integrated');
  assert.equal(normalizeTrolleyStatus(null).camera.state, 'unknown');
});

test('scan problems', () => {
  assert.equal(normalizeScanProblem({ barcode: '1', found: true }), null);
  assert.equal(normalizeScanProblem(null), null);
  const p = normalizeScanProblem({ id: 7, barcode: '999', status: 'unknown' });
  assert.match(p.message, /999/);
  assert.equal(normalizeScanProblem({ barcode: '5', error: 'Product not in catalog' }).message, 'Product not in catalog');
});

test('bill: reads nested responses and never invents a receipt', () => {
  const b = normalizeBill({ bill: { session_id: 'S1', usage_fee: 40, product_total: 150, total_due: 190, items: [{ name: 'X', price: 150, quantity: 1 }] } });
  assert.equal(b.totalDue, 190); assert.equal(b.receiptUrl, null); assert.equal(b.cart.items.length, 1);
  assert.equal(normalizeBill({ receipt_url: '/receipts/S1.pdf' }).receiptUrl, '/receipts/S1.pdf');
  assert.equal(normalizeBill(null), null);
});

test('final bill labels what the backend did not confirm', () => {
  const session = normalizeSession({ ...S, ended_at: '2026-10-13T10:45:00Z' });
  const unconfirmed = buildFinalBill({ bill: null, session, cart: normalizeCart([{ name: 'A', price: 50, quantity: 1 }]) });
  assert.equal(unconfirmed.isFinal, false); assert.equal(unconfirmed.rentalFee, 40); assert.equal(unconfirmed.rentalConfirmed, false); assert.equal(unconfirmed.totalDue, 90);
  const confirmed = buildFinalBill({ bill: normalizeBill({ usage_fee: 40, product_total: 50, total_due: 90 }), session, cart: null });
  assert.equal(confirmed.isFinal, true); assert.equal(confirmed.rentalConfirmed, true);
});
