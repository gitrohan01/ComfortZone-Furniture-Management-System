const AUTH_STORAGE_KEYS = ['access', 'refresh', 'user'];

export function clearStoredAuth(storage = globalThis.localStorage) {
  AUTH_STORAGE_KEYS.forEach((key) => storage.removeItem(key));
}
