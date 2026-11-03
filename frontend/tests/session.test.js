import test from 'node:test';
import assert from 'node:assert/strict';
import { clearStoredAuth } from '../src/auth/session.js';

test('logout clears access token, refresh token, and authenticated user', () => {
  const values = new Map([
    ['access', 'access-token'],
    ['refresh', 'refresh-token'],
    ['user', '{"username":"demo"}'],
    ['cart', '[{"id":1}]'],
  ]);
  const storage = {
    removeItem(key) {
      values.delete(key);
    },
  };

  clearStoredAuth(storage);

  assert.deepEqual([...values], [['cart', '[{"id":1}]']]);
});
