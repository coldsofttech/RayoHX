// The only place the page talks to Python: the rayohx_api routes under /api/v1.
const BASE = '/api/v1';

export class ApiError extends Error {}

async function call(path, { method = 'GET', body } = {}) {
  const response = await fetch(`${BASE}${path}`, {
    method,
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (response.status === 204) return null;
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = data.detail ?? data.title ?? `Request failed (${response.status})`;
    throw new ApiError(typeof detail === 'string' ? detail : 'The request was not valid.');
  }
  return data;
}

export const inspect = (url, headers = {}) =>
  call('/inspect', { method: 'POST', body: { url, network: { headers } } });
export const listDownloads = () => call('/downloads');
export const startDownload = (request) => call('/downloads', { method: 'POST', body: request });
export const controlDownload = (id, action) =>
  call(`/downloads/${id}/${action}`, { method: 'POST' });
export const removeDownload = (id) => call(`/downloads/${id}`, { method: 'DELETE' });
export const getSettings = () => call('/settings');
export const saveSettings = (changes) => call('/settings', { method: 'PATCH', body: changes });
export const clean = (request) => call('/clean', { method: 'POST', body: request });
