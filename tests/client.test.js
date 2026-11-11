import test, { before, after } from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { request, ApiError } from '../src/api/client.js';
import { getActiveSession, getHealth, checkout } from '../src/api/sessionApi.js';
import { getCart } from '../src/api/cartApi.js';

// config.js has an empty base URL under Node, so route relative paths to the mock server.
const realFetch = globalThis.fetch;
let server; let port; let lastPost = null; let slow = false;
const routes = {};

before(async () => {
  server = http.createServer((req, res) => {
    let body = '';
    req.on('data', (c) => (body += c));
    req.on('end', () => {
      const handler = routes[`${req.method} ${req.url}`];
      if (req.method === 'POST') lastPost = { url: req.url, body, type: req.headers['content-type'] };
      const send = () => {
        if (!handler) { res.writeHead(404, { 'content-type': 'application/json' }); return res.end('{"detail":"Not Found"}'); }
        const [status, payload, headers] = handler();
        res.writeHead(status, { 'content-type': 'application/json', ...(headers || {}) });
        res.end(payload === undefined ? '' : typeof payload === 'string' ? payload : JSON.stringify(payload));
      };
      slow ? setTimeout(send, 400) : send();
    });
  });
  await new Promise((r) => server.listen(0, '127.0.0.1', r));
  port = server.address().port;
  globalThis.fetch = (url, init) => {
    const parsed = new URL(url, `http://127.0.0.1:${port}`);
    return realFetch(`http://127.0.0.1:${port}${parsed.pathname}${parsed.search}`, init);
  };
});
after(() => { globalThis.fetch = realFetch; server.close(); });

test('health ok / unhealthy status body', async () => {
  routes['GET /health'] = () => [200, { status: 'ok' }];
  assert.equal(await getHealth(), true);
  routes['GET /health'] = () => [200, { status: 'degraded' }];
  await assert.rejects(getHealth(), /degraded/);
});

test('active session: real session, wrapper, 204/null/{} and 404 "no session" are all "no session"', async () => {
  routes['GET /api/session/active'] = () => [200, { session_id: 'S1', started_at: '2026-10-13T10:00:00Z', status: 'active' }, { date: 'Tue, 13 Oct 2026 10:05:00 GMT' }];
  const live = await getActiveSession();
  assert.equal(live.session.id, 'S1');
  assert.equal(live.session.serverTimeMs, null); // kept out of session identity
  assert.equal(live.serverTimeMs, Date.UTC(2026, 9, 13, 10, 5, 0));
  for (const reply of [[200, 'null'], [200, '{}'], [204, undefined], [200, { session: null }], [404, { detail: 'No active session' }]]) {
    routes['GET /api/session/active'] = () => reply;
    assert.equal((await getActiveSession()).session, null, JSON.stringify(reply));
  }
});

test('failures are NOT "no active session"', async () => {
  routes['GET /api/session/active'] = () => [500, { detail: 'boom' }];
  await assert.rejects(getActiveSession(), (e) => e instanceof ApiError && e.kind === 'http' && e.status === 500 && e.message === 'boom');
  routes['GET /api/session/active'] = () => [404, { detail: 'Not Found' }]; // route missing
  await assert.rejects(getActiveSession(), /no \/api\/session\/active endpoint/);
  routes['GET /api/session/active'] = () => [200, '<html>nope</html>'];
  await assert.rejects(getActiveSession(), (e) => e.kind === 'parse');
});

test('network failure and timeout are distinct kinds', async () => {
  const saved = globalThis.fetch;
  globalThis.fetch = () => Promise.reject(new TypeError('fetch failed'));
  await assert.rejects(request('/health'), (e) => e.kind === 'network' && e.isConnectivity);
  globalThis.fetch = saved;
  slow = true; routes['GET /health'] = () => [200, { status: 'ok' }];
  await assert.rejects(request('/health', { timeoutMs: 50 }), (e) => e.kind === 'timeout');
  slow = false;
});

test('caller abort is reported as aborted, not as an outage', async () => {
  slow = true; routes['GET /health'] = () => [200, { status: 'ok' }];
  const ac = new AbortController();
  const p = request('/health', { signal: ac.signal });
  setTimeout(() => ac.abort(), 20);
  await assert.rejects(p, (e) => e.isAborted);
  slow = false;
});

test('cart is read-only: getCart issues GET only', async () => {
  routes['GET /api/cart'] = () => [200, { items: [{ product_id: 'P003', name: 'Fresh Milk', price: 32, quantity: 1 }] }];
  lastPost = null;
  const cart = await getCart();
  assert.equal(cart.productTotal, 32);
  assert.equal(lastPost, null);
});

test('checkout POSTs without an undocumented body and parses the bill', async () => {
  routes['POST /api/checkout'] = () => [200, { bill: { session_id: 'S1', usage_fee: 20, product_total: 32, total_due: 52 }, pdf_url: '/r/S1.pdf' }];
  const { bill } = await checkout();
  assert.equal(lastPost.body, '');
  assert.equal(lastPost.type, undefined);
  assert.equal(bill.totalDue, 52); assert.equal(bill.receiptUrl, '/r/S1.pdf');
});
