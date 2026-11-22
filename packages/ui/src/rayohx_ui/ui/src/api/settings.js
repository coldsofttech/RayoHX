import { call } from './client.js';

export const settings = {
  get: () => call('/settings'),
  /** @param {Record<string, unknown>} changes */
  save: (changes) => call('/settings', { method: 'PATCH', body: changes }),
};
