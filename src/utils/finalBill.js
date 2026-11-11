import { rentalCharge } from './billing.js';

/**
 * Combine the checkout response with what the app last saw into one bill view-model.
 * Every value says whether the backend supplied it; nothing is filled in silently.
 */
export function buildFinalBill({ bill, session, cart }) {
  const startedAtMs = bill?.startedAtMs ?? session?.startedAtMs ?? null;
  const endedAtMs = bill?.endedAtMs ?? session?.endedAtMs ?? null;
  const durationSeconds = bill?.durationSeconds
    ?? (startedAtMs != null && endedAtMs != null ? Math.max(0, Math.floor((endedAtMs - startedAtMs) / 1000)) : null);

  const cartSource = bill?.cart ?? session?.cart ?? cart ?? null;

  let rentalFee = bill?.rentalFee ?? session?.usageFee ?? null;
  let rentalConfirmed = rentalFee != null;
  if (rentalFee == null && durationSeconds != null) {
    rentalFee = rentalCharge(durationSeconds);
    rentalConfirmed = false;
  }

  const productTotal = bill?.productTotal ?? session?.productTotal ?? cartSource?.productTotal ?? null;

  let totalDue = bill?.totalDue ?? session?.totalDue ?? null;
  const isFinal = totalDue != null;
  if (totalDue == null && productTotal != null && rentalFee != null) totalDue = productTotal + rentalFee;

  return {
    reference: bill?.sessionId ?? session?.id ?? null,
    customerName: bill?.customerName ?? session?.customerName ?? null,
    cardId: bill?.cardId ?? session?.cardId ?? null,
    startedAtMs,
    endedAtMs,
    durationSeconds,
    billingPeriods: bill?.billingPeriods ?? session?.billingPeriods ?? null,
    rentalFee,
    rentalConfirmed,
    productTotal,
    totalDue,
    isFinal,
    items: cartSource?.items ?? [],
    receiptUrl: bill?.receiptUrl ?? session?.receiptUrl ?? null,
  };
}
