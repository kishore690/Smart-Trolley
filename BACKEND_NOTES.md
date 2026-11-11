# Backend integration notes

The FastAPI source was not part of the upload. The live Raspberry Pi health endpoint, route
OpenAPI document, and safe GET endpoints were inspected on 2026-10-13. Route implementation
source and checkout response behavior are not available from this frontend archive.

## Endpoints the app uses

| Endpoint | Used for | Assumed contract |
|---|---|---|
| `GET /health` | Connected / Disconnected indicator | any 2xx; if the JSON has a `status`, it must be `ok`/`healthy`/`up`/`running`/`alive` |
| `GET /api/session/active` | Session polling | a session object, or `{session: …}` / `{active_session: …}`; "no session" may be `null`, `{}`, `{session:null}`, `{status:"no_active_session"}`, 204, or a 404 with a custom `detail` |
| `GET /api/cart` | Cart polling | an array, or `{items|products|cart: […], product_total?, item_count?}` |
| `GET /api/scans/latest` | Unknown-barcode message only | 404 when empty; a failed scan has `found:false`, `success:false`, `error`, or `status` of `unknown`/`not_found`/`error`/`invalid` |
| `GET /api/trolley/status` | Hardware rows | see below |
| `POST /api/checkout` | Checkout | live OpenAPI declares no request body; response schema is unspecified |

Not used on purpose: `POST /api/scans`, `POST /api/cart/items`, `DELETE /api/cart/items/{id}`,
`GET /api/products`, `GET /api/customers`.

## Fields read

- **Session:** `session_id`, `card_id`, `customer` (string or `{name}`), `started_at`, `ended_at`,
  `status`, `usage_fee`, `billing_periods`, `product_total`, `total_due`. Optional:
  `server_time`, `can_checkout`, `cart`, `receipt_url`.
- **Cart item:** `product_id`/`id`, `barcode`, `name`, `quantity`/`qty`, `unit_price`/`price`,
  `line_total`/`subtotal`. A line total is computed (price × quantity) only if the backend omitted it
  and both inputs exist; a missing price is shown as "—".
- **Bill (checkout response):** `usage_fee`/`rental_fee`, `product_total`, `total_due`,
  `billing_periods`, `started_at`, `ended_at`, `items`, `receipt_url`/`pdf_url`. Anything
  missing is shown as "—" or labelled as not confirmed.

## Things the backend should confirm or implement

1. **`/api/trolley/status` hardware keys (assumed).** The app looks for
   `controller|controller_connected|trolley_controller…`, `camera|person_following|following…`,
   `scanner|barcode_scanner…`, as booleans or strings such as `connected`/`offline`. If the
   endpoint doesn't report them, the UI shows "Not reported" — it never infers health.
2. **Timestamp time zone.** Python's `datetime.utcnow().isoformat()` has no `Z`. The app treats
   zone-less timestamps as **UTC** (`VITE_NAIVE_TIMESTAMPS=local` if the Pi uses
   `datetime.now()`). Best fix: emit `…Z` or `+05:30`.
3. **Pi clock.** A Raspberry Pi has no battery clock; without NTP its time can be wrong. The app
   compares `server_time` (or the `Date` header, which requires `expose_headers=["Date"]` in CORS)
   with the phone's clock and corrects for differences over 3 s. Adding `server_time` to the
   session response is the most reliable option.
4. **Checkout response.** OpenAPI declares no request body and no response schema. The app sends
   an empty POST only after the customer confirms. Checkout should be idempotent per session
   (repeat calls for an ended session ideally return 409 or the same bill; the app treats a 409
   or a message containing "already" as already checked out).
   Returning the final bill and, if available, a `receipt_url` is required for the "Final
   amount due" and receipt button to appear. Without a bill the app shows the last values it
   saw and says they are not a confirmed total.
5. **Sessions that end without the app.** If the trolley ends a session (e.g. staff or RFID
   re-tap), the app shows a "Session ended" screen with last-known values, clearly marked as not
   final. For a proper bill, `/api/session/active` should return the session with
   `status:"completed"`, `ended_at` and `total_due` (or expose a bill endpoint).
6. **Unknown barcodes.** The cart can't show a failed scan; the app relies on
   `/api/scans/latest` to say so. Without a stable `id` or timestamp on scans, scanning the same
   unknown barcode twice in a row won't show a second message.
7. **Billing boundary.** The brief's formula `max(1, ceil(s/1800)) × 20` and its table disagree for
   exactly 1800.0 s (formula → ₹20; table → ₹40). The app implements the **formula**, so the change
   happens one second later (at 30:01) than a literal reading of the table. Make the backend and
   `src/utils/billing.js` use the same convention. Rental is also resolved by the backend at
   checkout, which stays authoritative.
8. **CORS.** See README. Don't use `allow_origins=["*"]` with credentials.

## Live API observations (2026-10-13)

- `GET /health` returned `{"status":"ok","service":"cartly-api"}`.
- `GET /api/trolley/status` returned `connected:true`, `status:"ok"`,
  `session_active:false`, `scanner_ready:false`, and a `hardware_note` saying scanner and live
  hardware status are not integrated. `connected` is described as API reachability, so the UI
  labels the header as trolley API connectivity and does not claim hardware is connected.
- `GET /api/session/active` returned `{"session":null}`; no active session was reported during
  inspection. The live active-session object schema is not described in OpenAPI.
- `/api/products` returned eight products, `/api/scans/latest` returned `{"scan":null}`,
  `/api/cart` returned an empty cart with no active session, and `/api/customers` returned two
  customer records.
- OpenAPI specifies `ScanEvent {barcode}` and `AddCartItem {product_id?, barcode?, quantity}`.
  Checkout has no request body in OpenAPI, so the frontend sends an empty POST and does not
  invent a session-id payload. Its response schema is unspecified and could not be verified
  without ending a real session.

No test has touched real RFID, camera, barcode hardware, or checkout on a live session. The
backend source was not included, so the connection between RFID events, session storage, scanner
events, and API routes cannot be inspected here. The backend must ensure RFID starts the same
session returned by `/api/session/active`, scanner changes update `/api/cart`, and the
session-active response includes a stable session ID and timezone-aware `started_at`.
