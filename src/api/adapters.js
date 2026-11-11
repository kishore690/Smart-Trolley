// Backend responses are normalised here so the rest of the app sees one shape.
// Nothing in this file invents data: a field the backend did not send stays null.

import { parseTimestamp } from '../utils/dateTime.js';

const isObj = (v) => v !== null && typeof v === 'object' && !Array.isArray(v);

/** First defined, non-null value among `keys` across the given objects. */
function pick(layers, keys) {
  for (const layer of layers) {
    if (!isObj(layer)) continue;
    for (const k of keys) if (layer[k] != null) return layer[k];
  }
  return null;
}

function num(v) {
  if (v == null || v === '') return null;
  const n = typeof v === 'number' ? v : Number(String(v).replace(/[₹,\s]/g, ''));
  return Number.isFinite(n) ? n : null;
}

const str = (v) => (v == null || v === '' ? null : String(v));

/* ------------------------------------------------------------------ cart */

export function normalizeCartItem(raw, index) {
  const it = isObj(raw) ? raw : {};
  const product = isObj(it.product) ? it.product : {};
  const productId = str(pick([it, product], ['product_id', 'sku', 'id']));
  const barcode = str(pick([it, product], ['barcode', 'code', 'ean']));
  const quantity = num(pick([it], ['quantity', 'qty', 'count'])) ?? 1;
  const unitPrice = num(pick([it, product], ['unit_price', 'price', 'mrp']));
  let lineTotal = num(pick([it], ['line_total', 'subtotal', 'total', 'amount']));
  if (lineTotal == null && unitPrice != null) lineTotal = unitPrice * quantity;
  return {
    key: str(pick([it], ['item_id'])) ?? productId ?? barcode ?? `row-${index}`,
    productId,
    barcode,
    name: str(pick([it, product], ['name', 'product_name', 'title'])) ?? 'Unnamed product',
    quantity,
    unitPrice,
    lineTotal,
  };
}

export function normalizeCart(raw) {
  let list = [];
  let wrapper = {};
  if (Array.isArray(raw)) {
    list = raw;
  } else if (isObj(raw)) {
    wrapper = isObj(raw.cart) ? raw.cart : raw;
    const candidate = Array.isArray(raw.cart) ? raw.cart : wrapper.items ?? wrapper.products ?? raw.items ?? [];
    list = Array.isArray(candidate) ? candidate : [];
  }
  const items = list.map(normalizeCartItem);
  const itemCount = num(pick([wrapper], ['item_count', 'total_items', 'items_count'])) ?? items.reduce((s, i) => s + i.quantity, 0);
  let productTotal = num(pick([wrapper], ['product_total', 'subtotal', 'items_total']));
  if (productTotal == null && items.every((i) => i.lineTotal != null)) {
    productTotal = items.reduce((s, i) => s + i.lineTotal, 0);
  }
  return { items, itemCount, productTotal };
}

/* --------------------------------------------------------------- session */

const ENDED_STATES = ['completed', 'complete', 'ended', 'closed', 'checked_out', 'finished'];

/** Returns a normalised session, or null when the backend reports no session. */
export function normalizeSession(raw) {
  let s = raw;
  if (isObj(raw)) {
    for (const key of ['session', 'active_session', 'data']) {
      if (key in raw) { s = raw[key]; break; }
    }
  }
  if (!isObj(s) || Object.keys(s).length === 0) return null;
  if (s.active === false || s.has_active_session === false) return null;

  const id = str(pick([s], ['session_id', 'id']));
  const startedAtMs = parseTimestamp(pick([s], ['started_at', 'start_time', 'startedAt']));
  if (id == null && startedAtMs == null) return null; // e.g. {status: "no_active_session"}

  const endedAtMs = parseTimestamp(pick([s], ['ended_at', 'end_time', 'endedAt']));
  const statusRaw = str(pick([s], ['status', 'state']));
  const ended = endedAtMs != null || (statusRaw != null && ENDED_STATES.includes(statusRaw.toLowerCase()));

  const c = s.customer;
  const customerName = typeof c === 'string' ? c : str(pick([c, s], ['name', 'full_name', 'customer_name']));

  return {
    id,
    cardId: str(pick([s], ['card_id', 'rfid', 'rfid_uid', 'uid'])),
    customerName,
    startedAtMs,
    endedAtMs,
    statusRaw,
    state: ended ? 'completed' : 'active',
    productTotal: num(pick([s], ['product_total'])),
    billingPeriods: num(pick([s], ['billing_periods'])),
    usageFee: num(pick([s], ['usage_fee', 'rental_fee', 'rental_charge'])),
    totalDue: num(pick([s], ['total_due'])),
    serverTimeMs: parseTimestamp(pick([s, raw], ['server_time', 'now'])),
    canCheckout: s.can_checkout === false ? false : true,
    cart: Array.isArray(s.cart) || isObj(s.cart) ? normalizeCart(s.cart) : null,
    receiptUrl: str(pick([s], ['receipt_url', 'pdf_url'])),
  };
}

/* ------------------------------------------------------- trolley hardware */

const OK_WORDS = ['connected', 'online', 'ok', 'ready', 'active', 'following', 'running', 'on', 'up', 'true', 'healthy'];
const OFF_WORDS = ['disconnected', 'offline', 'error', 'down', 'off', 'stopped', 'fault', 'failed', 'disabled', 'false', 'unavailable'];

function hardwareState(value) {
  if (value == null) return { state: 'unknown', detail: null };
  if (typeof value === 'boolean') return { state: value ? 'ok' : 'off', detail: null };
  if (typeof value === 'string') {
    const w = value.trim().toLowerCase();
    if (OK_WORDS.includes(w)) return { state: 'ok', detail: value };
    if (OFF_WORDS.includes(w)) return { state: 'off', detail: value };
    return { state: 'unknown', detail: value };
  }
  if (isObj(value)) {
    for (const k of ['connected', 'status', 'state', 'ok', 'active']) {
      if (k in value) return hardwareState(value[k]);
    }
  }
  return { state: 'unknown', detail: null };
}

const HW_KEYS = {
  controller: ['controller', 'controller_connected', 'trolley_controller', 'motor_controller', 'esp32', 'arduino'],
  camera: ['camera', 'camera_status', 'person_following', 'following', 'follow_status', 'camera_following'],
  scanner: ['scanner', 'barcode_scanner', 'scanner_status', 'barcode'],
};

/** Each hardware item is 'ok' | 'off' | 'unknown'; 'unknown' means the backend did not report it. */
export function normalizeTrolleyStatus(raw) {
  const root = isObj(raw) ? raw : {};
  const layers = [root, root.hardware, root.devices, root.status].filter(isObj);
  const out = {};
  for (const [name, keys] of Object.entries(HW_KEYS)) {
    out[name] = hardwareState(pick(layers, keys));
  }
  return {
    ...out,
    hardwareNote: str(root.hardware_note ?? root.message),
  };
}

/* ----------------------------------------------------------------- scans */

const BAD_SCAN_STATES = ['unknown', 'not_found', 'notfound', 'error', 'invalid', 'failed', 'unrecognized'];

/** Returns { key, barcode, message } only when the latest scan is a failure; otherwise null. */
export function normalizeScanProblem(raw) {
  let s = raw;
  if (isObj(raw)) for (const k of ['scan', 'latest', 'data']) if (k in raw) { s = raw[k]; break; }
  if (!isObj(s) || Object.keys(s).length === 0) return null;
  const status = str(pick([s], ['status', 'result']))?.toLowerCase();
  const failed = s.found === false || s.success === false || s.error != null || (status && BAD_SCAN_STATES.includes(status));
  if (!failed) return null;
  const barcode = str(pick([s], ['barcode', 'code']));
  const at = pick([s], ['scanned_at', 'created_at', 'timestamp', 'time']);
  const explicit = typeof s.error === 'string' ? s.error : str(pick([s], ['message', 'detail']));
  return {
    key: `${str(pick([s], ['id', 'scan_id'])) ?? ''}|${barcode ?? ''}|${at ?? ''}`,
    barcode,
    message: explicit ?? (barcode ? `Barcode ${barcode} was not recognised.` : 'The last barcode was not recognised.'),
  };
}

/** Stable identity of the latest scan (success or failure) so the first read can be a baseline. */
export function scanKey(raw) {
  let s = raw;
  if (isObj(raw)) for (const k of ['scan', 'latest', 'data']) if (k in raw) { s = raw[k]; break; }
  if (!isObj(s) || Object.keys(s).length === 0) return null;
  return `${str(pick([s], ['id', 'scan_id'])) ?? ''}|${str(pick([s], ['barcode', 'code'])) ?? ''}|${pick([s], ['scanned_at', 'created_at', 'timestamp', 'time']) ?? ''}`;
}

/* ------------------------------------------------------------------ bill */

/** Normalises the checkout response. Missing fields stay null so the UI can say so. */
export function normalizeBill(raw) {
  const layers = [raw, isObj(raw) ? raw.bill : null, isObj(raw) ? raw.checkout : null, isObj(raw) ? raw.session : null, isObj(raw) ? raw.data : null].filter(isObj);
  if (layers.length === 0) return null;

  const itemsRaw = pick(layers, ['items', 'cart', 'products']);
  const cart = Array.isArray(itemsRaw) || isObj(itemsRaw) ? normalizeCart(itemsRaw) : null;
  const rec = pick(layers, ['receipt_url', 'pdf_url', 'receipt_pdf', 'invoice_url']);
  const receiptUrl = typeof rec === 'string' ? rec : isObj(rec) ? str(rec.url) : null;

  return {
    sessionId: str(pick(layers, ['session_id', 'id'])),
    startedAtMs: parseTimestamp(pick(layers, ['started_at', 'start_time'])),
    endedAtMs: parseTimestamp(pick(layers, ['ended_at', 'end_time', 'checked_out_at'])),
    durationSeconds: num(pick(layers, ['duration_seconds', 'elapsed_seconds'])),
    billingPeriods: num(pick(layers, ['billing_periods'])),
    rentalFee: num(pick(layers, ['usage_fee', 'rental_fee', 'rental_charge'])),
    productTotal: num(pick(layers, ['product_total', 'subtotal', 'items_total'])),
    totalDue: num(pick(layers, ['total_due', 'amount_due', 'final_amount', 'total'])),
    customerName: (() => {
      const c = pick(layers, ['customer']);
      return typeof c === 'string' ? c : str(pick([c], ['name', 'full_name']));
    })(),
    cardId: str(pick(layers, ['card_id', 'rfid'])),
    cart,
    receiptUrl,
  };
}
