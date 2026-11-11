import test from 'node:test';
import assert from 'node:assert/strict';
import { rentalCharge, billingBlocks, secondsUntilNextBlock, resolveRental } from '../src/utils/billing.js';

const reference = (s) => Math.max(1, Math.ceil(s / 1800)) * 20; // the formula from the spec

test('rental charge matches max(1, ceil(s/1800)) * 20 for every second up to 3 hours', () => {
  for (let s = 0; s <= 3 * 3600; s++) assert.equal(rentalCharge(s), reference(s), `s=${s}`);
});

test('billing table rows', () => {
  assert.equal(rentalCharge(0), 20);
  assert.equal(rentalCharge(29 * 60 + 59), 20);
  assert.equal(rentalCharge(30 * 60 + 1), 40);
  assert.equal(rentalCharge(59 * 60 + 59), 40);
  assert.equal(rentalCharge(60 * 60 + 1), 60);
  assert.equal(rentalCharge(89 * 60 + 59), 60);
  assert.equal(rentalCharge(90 * 60 + 1), 80);
  assert.equal(rentalCharge(119 * 60 + 59), 80);
});

test('exact 30:00.0 follows the formula (ceil) - documented difference from the table wording', () => {
  assert.equal(rentalCharge(1800), 20);
  assert.equal(rentalCharge(1801), 40);
});

test('bad input never produces NaN', () => {
  assert.equal(rentalCharge(NaN), 20);
  assert.equal(rentalCharge(-5), 20);
  assert.equal(billingBlocks(undefined), 1);
});

test('time to next increase', () => {
  assert.equal(secondsUntilNextBlock(0), 1800);
  assert.equal(secondsUntilNextBlock(1790), 10);
  assert.equal(secondsUntilNextBlock(1801), 1799);
});

test('resolveRental labels server vs estimate', () => {
  assert.deepEqual(resolveRental(100, 20), { amount: 20, source: 'server', serverAmount: 20 });
  assert.equal(resolveRental(1900, 20).source, 'estimate'); // server value stale after a boundary
  assert.equal(resolveRental(1900, 20).amount, 40);
  assert.equal(resolveRental(100, null).source, 'estimate');
});
